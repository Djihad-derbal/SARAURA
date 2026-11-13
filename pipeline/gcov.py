"""GCOV path: backscatter layers, ratios, change layers, temporal statistics, Lens Baselines.

Reads the chosen Stack through the shared chunk reader (saraura.change.read_stack), on the
radar's own UTM grid, so no resampling happens between Passes (grids align within a Stack).
"""
from __future__ import annotations

import numpy as np

from saraura import change, cmr
from saraura.config import MATURITY_TO_COLLECTION

from . import coverage, export
from .layers import entry

PIPELINE_MAX_PIXELS = 40_000_000  # Showcase Sites are precomputed offline; the API keeps its own smaller cap


# dB range mapped to 1..255 for each composite channel (team choice; matches the single-layer legends).
RGB_STRETCH = {"hh": (-20.0, 0.0), "hv": (-28.0, -8.0), "hhhv": (4.0, 16.0)}


def select_passes(site: dict) -> list[dict]:
    """One GCOV Granule per date on the site's Stack (its preferred one, else the Stack with most Passes)."""
    start, end = site["dates"]
    allowed = set(site["collections"])
    found = [g for g in cmr.search(tuple(site["bbox"]), start, end, "GCOV") if MATURITY_TO_COLLECTION[g["maturity"]] in allowed]
    if not found:
        raise RuntimeError(f"No calibrated GCOV Granules over {site['id']}")
    pref = site.get("stack")
    if pref:
        found = [g for g in found if g["track"] == pref["track"] and g["direction"] == pref["direction"] and (not pref.get("frame") or g["frame"] == pref["frame"])]
        if not found:
            raise RuntimeError(f"Preferred Stack {pref} has no Granules over {site['id']}")
    by_stack: dict[str, dict[str, dict]] = {}
    for g in found:
        by_stack.setdefault(g["stack"], {}).setdefault(g["date"], g)
    cov = coverage.stack_coverage(found, site["bbox"])
    stack = max(by_stack, key=lambda k: (cov[k] >= coverage.MIN_COVERAGE, round(cov[k], 1), len(by_stack[k])))
    if cov[stack] < coverage.MIN_COVERAGE:
        raise RuntimeError(f"Best GCOV Stack {stack} covers only {cov[stack]:.0%} of {site['id']}")
    best = by_stack[stack]
    return [best[d] for d in sorted(best)]


def _median(a: np.ndarray, axis: int = 0) -> np.ndarray:
    with np.errstate(all="ignore"), np.testing.suppress_warnings() as sup:
        sup.filter(RuntimeWarning)
        return np.nanmedian(a, axis=axis)


def wildfire_baseline(hv: np.ndarray, dates: list[str], event: str, window: int = 3, event_end: str | None = None):
    """HV drop across the fire: median of up to `window` Passes after it stopped growing (event_end,
    default event) minus up to `window` Passes before it started.

    Baseline rule (stated in the README as a team choice): burned where the drop exceeds 1.5 dB
    on land that was vegetated before (pre-fire HV above -20 dB).
    """
    before = [i for i, d in enumerate(dates) if d < event][-window:]
    after = [i for i, d in enumerate(dates) if d >= (event_end or event)][:window]
    if not before or not after:
        return None
    pre, post = _median(hv[before]), _median(hv[after])
    d = (post - pre).astype(np.float32)
    burned = np.where(np.isfinite(d), ((d < -1.5) & (pre > -20.0)).astype(np.uint8), 255)
    return d, burned, dates[after[0]]


def process(site: dict, log=print) -> dict:
    """Write all GCOV layers and series for a site. Returns the manifest fragments (passes, layers, series, stats)."""
    sid = site["id"]
    passes = select_passes(site)
    dates = [p["date"] for p in passes]
    log(f"  Stack {passes[0]['stack']}: {len(passes)} Passes {dates[0]} .. {dates[-1]}")
    db, grid = change.read_stack(
        passes, site["bbox"], site["resolution_m"],
        progress=lambda a, b: log(f"  reading Pass {a}/{b}"),
        max_pixels=PIPELINE_MAX_PIXELS,
    )
    hh, hv = db[:, 0], db[:, 1]
    log(f"  grid {grid['shape'][0]} x {grid['shape'][1]} at {grid['res']:.0f} m, EPSG:{grid['epsg']}")

    layers, stats = [], {}
    for name, cube in (("hh_db", hh), ("hv_db", hv), ("hvhh_db", hv - hh)):
        for t, d in enumerate(dates):
            export.write_cog(sid, f"{name}_{d}", cube[t], grid)
        layers.append(entry(name, dates))
    log("  wrote HH, HV, HV/HH per Pass")

    # False-colour composite in the style of the UAVSAR Postcards: R = HH, G = HV, B = HH/HV.
    for t, d in enumerate(dates):
        export.write_rgb(sid, f"rgb_{d}", [(hh[t], *RGB_STRETCH["hh"]), (hv[t], *RGB_STRETCH["hv"]), (hh[t] - hv[t], *RGB_STRETCH["hhhv"])], grid)
    layers.append(entry("rgb", dates))

    for name, cube in (("dhv", hv), ("dhh", hh)):
        diff = cube[1:] - cube[:-1]
        for t, d in enumerate(dates[1:]):
            export.write_cog(sid, f"{name}_{d}", diff[t], grid)
        layers.append(entry(name, dates[1:]))
    log("  wrote change since previous Pass")

    if site["lens"] in ("farming", "wetland", "volcano"):
        lin = 10 ** (hv / 10)
        with np.errstate(all="ignore"):
            mean_lin = np.nanmean(lin, axis=0)
            cv = (np.nanstd(lin, axis=0) / mean_lin).astype(np.float32)
            hv_std = np.nanstd(hv, axis=0).astype(np.float32)
        last = dates[-1]
        export.write_cog(sid, f"hv_mean_{last}", (10 * np.log10(mean_lin)).astype(np.float32), grid)
        export.write_cog(sid, f"hv_std_{last}", hv_std, grid)
        export.write_cog(sid, f"hv_cv_{last}", cv, grid)
        layers += [entry("hv_mean", [last]), entry("hv_std", [last]), entry("hv_cv", [last])]
        log("  wrote temporal mean, std, coefficient of variation")

    if site["lens"] == "wildfire" and site.get("event_date"):
        res = wildfire_baseline(hv, dates, site["event_date"], event_end=site.get("event_end_date"))
        if res:
            d, burned, first_after = res
            export.write_cog(sid, f"dhv_event_{first_after}", d, grid)
            export.write_cog(sid, f"baseline_wildfire_{first_after}", burned, grid, categorical=True)
            layers += [entry("dhv_event", [first_after]), entry("baseline_wildfire", [first_after], kind="baseline", status="prototype")]
            cell_ha = grid["res"] ** 2 / 1e4
            stats["burned_baseline_ha"] = round(float((burned == 1).sum() * cell_ha), 1)
            stats["dhv_event_median_burned"] = round(float(np.nanmedian(d[burned == 1])), 2) if (burned == 1).any() else None
            log(f"  Baseline: {stats['burned_baseline_ha']:,} ha burned (HV drop > 1.5 dB)")

    series = [export.write_series(sid, name, cube, dates, grid, grid_m=100) for name, cube in (("hv_db", hv), ("hh_db", hh))]
    log("  wrote 100 m time series")

    valid = np.isfinite(db).all(axis=1)  # (T, H, W)
    stats.update(
        area_ha=round(float(np.isfinite(db).any((0, 1)).sum() * grid["res"] ** 2 / 1e4), 1),
        masked_share=round(float(1 - valid.mean()), 3),
    )
    # Share of the area whose HV fell by > 3 dB at each Pass, on 100 m blocks, ignoring cells near the
    # radar noise floor (pre HV < -20 dB) and requiring the drop to persist into the next Pass.
    # Without these guards, noise-floor flicker on 15 July outranked the 1 September fire.
    c = export.coarse(hv, max(1, int(round(100 / grid["res"]))))
    shares = {}
    for t, d in enumerate(dates[1:-1]):  # the last Pass has no later Pass to confirm a change
        pre, post, nxt = c[t], c[t + 1], c[t + 2]
        with np.errstate(invalid="ignore"):
            shares[d] = round(float(np.nanmean((pre > -20) & (post - pre < -3) & (nxt - pre < -3))), 4)
    stats["hv_change_share_3db"] = shares
    manifest_passes = [
        {"date": p["date"], "collection": MATURITY_TO_COLLECTION[p["maturity"]], "stack": p["stack"], "granules": [p["id"]]}
        for p in passes
    ]
    return {"passes": manifest_passes, "layers": layers, "series": series, "stats": stats, "grid": grid}
