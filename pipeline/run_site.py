"""Turn one Showcase Site's NISAR Granules into COG layers, parquet series and a manifest.

    python -m pipeline.run_site sites/algeria_ne_wildfire.yaml --plan
    python -m pipeline.run_site --all --plan

--plan lists the calibrated Passes per Stack without reading any pixels, so site
choices (enough Passes? a Pass before the event?) can be checked first.
Without --plan it runs the processing and writes data/<site_id>/ (contracts/manifest.schema.json).
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict

from saraura import cmr
from saraura.config import MATURITY_TO_COLLECTION

from . import coverage, dem, export, gcov, gunw, insights, predictions, sites


def granules_for(site: dict, product: str) -> list[dict]:
    """Calibrated Granules of one product over the site, restricted to the site's collections and dates."""
    start, end = site["dates"]
    allowed = set(site["collections"])
    found = cmr.search(tuple(site["bbox"]), start, end, product)
    out = [g for g in found if MATURITY_TO_COLLECTION[g["maturity"]] in allowed]
    if product == "GUNW":  # both Passes of a pair must fall inside the site's dates
        out = [g for g in out if g["secondary_date"] and g["secondary_date"] <= end and g["date"] >= start]
    return out


def gunw_pairs_for(site: dict) -> list[dict]:
    """GUNW pairs per Stack: which consecutive pairs exist, where the chain breaks, which pairs span the event."""
    by_stack: dict[str, dict[tuple, dict]] = defaultdict(dict)
    for g in granules_for(site, "GUNW"):
        by_stack[g["stack"]].setdefault((g["date"], g["secondary_date"]), g)
    cov = coverage.stack_coverage([g for p in by_stack.values() for g in p.values()], site["bbox"])
    out = []
    for stack, pairs in by_stack.items():
        keys = sorted(pairs)
        chain_breaks = [f"{a[1]} -> {b[0]}" for a, b in zip(keys, keys[1:]) if a[1] != b[0]]
        first = pairs[keys[0]]
        out.append({"stack": stack, "direction": first["direction"], "pairs": keys, "breaks": chain_breaks, "coverage": cov[stack]})
    return sorted(out, key=lambda s: (-s["coverage"], -len(s["pairs"])))


def stacks_for(site: dict) -> list[dict]:
    """Calibrated GCOV Passes over the site, grouped by Stack, most Passes first."""
    found = granules_for(site, "GCOV")
    cov = coverage.stack_coverage(found, site["bbox"])
    by_stack: dict[str, dict[str, dict]] = defaultdict(dict)
    for g in found:
        by_stack[g["stack"]].setdefault(g["date"], g)  # one Pass per date (a Stack can hold two bandwidth modes)
    out = []
    for stack, passes in by_stack.items():
        dates = sorted(passes)
        first = passes[dates[0]]
        out.append({
            "stack": stack,
            "track": first["track"],
            "direction": first["direction"],
            "dates": dates,
            "collections": sorted({MATURITY_TO_COLLECTION[passes[d]["maturity"]] for d in dates}),
            "polarizations": first["polarizations"],
            "coverage": cov[stack],
        })
    return sorted(out, key=lambda s: (-s["coverage"], -len(s["dates"])))


def plan(site: dict) -> int:
    print(f"\n{site['id']}  ({site['lens']}, {site['view']}, products {', '.join(site['products'])})")
    event = site.get("event_date")
    if "GUNW" in site["products"]:
        print("  GUNW pairs:")
        gstacks = gunw_pairs_for(site)
        if not gstacks:
            print("    NO calibrated GUNW pairs found")
        for g in gstacks:
            span = [p for p in g["pairs"] if event and p[0] < event <= p[1]]
            extra = f", spanning event: {', '.join(a + '>' + b for a, b in span) or 'NONE'}" if event else ""
            print(f"    {g['stack']:>10}  {g['direction']:<10} covers {g['coverage']:>4.0%}  {len(g['pairs']):>2} pairs  "
                  f"{g['pairs'][0][0]} .. {g['pairs'][-1][1]}  chain breaks: {len(g['breaks'])}{extra}")
    print("  GCOV Passes:")
    stacks = stacks_for(site)
    if not stacks:
        print("  NO calibrated GCOV Passes found: pick another site or widen dates")
        return 1
    preferred = site.get("stack")
    for s in stacks:
        mark = ""
        if preferred and s["track"] == preferred["track"] and s["direction"] == preferred["direction"]:
            mark = "  <- preferred"
        pre = sum(d < event for d in s["dates"]) if event else None
        extra = f", {pre} before event" if event else ""
        print(f"  {s['stack']:>10}  {s['direction']:<10} covers {s['coverage']:>4.0%}  {len(s['dates']):>2} Passes{extra}  "
              f"{s['dates'][0]} .. {s['dates'][-1]}  {'/'.join(s['collections'])}  {','.join(s['polarizations'])}{mark}")
    if event and not any(d < event for s in stacks for d in s["dates"]):
        print(f"  WARNING: no calibrated Pass before the event ({event}); change detection has no 'before'")
    return 0


def run(site: dict, kind: str = "showcase") -> int:
    """Process one Showcase Site (or, with kind="analysis", one on-demand Analysis) end to end and
    validate its manifest. An Analysis never gets Model layers or a Model card (ADR-0001)."""
    import time

    t0 = time.time()
    print(f"\n{site['id']}: processing ({', '.join(site['products'])})")
    parts = {"passes": {}, "layers": [], "series": [], "stats": {}, "notes": []}
    for product, module in (("GCOV", gcov), ("GUNW", gunw)):
        if product not in site["products"]:
            continue
        out = module.process(site)
        for p in out["passes"]:  # merge by date; GCOV and GUNW can come from different Granules
            e = parts["passes"].setdefault(p["date"], {**p, "granules": []})
            e["granules"] += [g for g in p["granules"] if g not in e["granules"]]
            if e["stack"] != p["stack"]:
                parts["notes"].append(f"{p['date']}: GCOV and GUNW come from different Stacks ({e['stack']}, {p['stack']})")
        parts["layers"] += out["layers"]
        parts["series"] += out["series"]
        parts["stats"].update(out["stats"])
        parts["notes"] += out.get("notes", [])
        parts.setdefault("grids", {})[product] = out["grid"]
        if "cum" in out:
            parts["cum"] = out["cum"]
    parts["passes"] = [parts["passes"][d] for d in sorted(parts["passes"])]
    terrain = None
    if parts.get("grids"):
        grid = parts["grids"].get("GUNW") or parts["grids"]["GCOV"]
        try:
            t = dem.process(site, grid, parts["passes"][-1]["date"], parts.get("cum"))
            parts["layers"] += t["layers"]
            terrain = t["terrain"]
        except Exception as e:  # the DEM is context; a failure should not lose the radar layers
            parts["notes"].append(f"DEM step failed: {str(e)[:160]}")
            print(f"  DEM step failed: {e}")
    todo = [p for p in site["products"] if p not in ("GCOV", "GUNW")]
    dates = [p["date"] for p in parts["passes"]]
    manifest = {
        "kind": kind,
        "id": site["id"],
        "lens": site["lens"],
        "name": site["name"],
        "bbox": site["bbox"],
        "event_date": site.get("event_date"),
        "view": site["view"],
        "passes": parts["passes"],
        "layers": parts["layers"],
        "series": parts["series"],
        "insights": insights.from_stats(site, parts["stats"], dates),
        "quality": {
            "passes": len(dates),
            "gaps": ["2026-07-27 to 2026-08-10 instrument gap"] if dates and dates[0] < "2026-07-27" < dates[-1] else [],
            "masked_share": parts["stats"].get("masked_share", 0.0),
            "notes": parts["notes"] + [f"{p} processing not built yet" for p in todo],
        },
        "model_card": site.get("model_card") if kind == "showcase" else None,
    }
    if kind == "showcase":
        manifest["layers"] += predictions.entries(site["id"], site["lens"], site["model_card"])
    if terrain:
        manifest["terrain"] = terrain
    key = export.write_manifest(site["id"], manifest)
    stale = export.prune(site["id"], manifest)
    if stale:
        print(f"  removed {len(stale)} stale files from earlier runs")
    from saraura import config

    sys.path.insert(0, str(config.CONTRACTS_DIR))
    from validate import check_manifest

    errs = check_manifest(config.data.local_path(key))
    print(f"  manifest {'valid' if not errs else 'INVALID'}: data/{key}  ({time.time() - t0:.0f} s)")
    for e in errs:
        print(f"    {e}")
    for line in manifest["insights"]:
        print(f"  - {line}")
    return 1 if errs else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("site", nargs="?", help="site id or path to sites/<id>.yaml")
    ap.add_argument("--all", action="store_true", help="every site in sites/")
    ap.add_argument("--plan", action="store_true", help="list Passes per Stack only (no pixel reads)")
    args = ap.parse_args(argv)
    ids = sites.all_ids() if args.all else [args.site] if args.site else None
    if not ids:
        ap.error("give a site or --all")
    failed = 0
    for sid in ids:
        try:
            failed += plan(sites.load(sid)) if args.plan else run(sites.load(sid))
        except (sites.InvalidSite, FileNotFoundError) as e:
            print(e)
            failed += 1
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
