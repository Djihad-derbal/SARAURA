"""Check a Model export (e.g. from a notebook) before it replaces a Showcase Site's Model, and install it if it passes.

  python ml/check_export.py <export_dir>                 # report only
  python ml/check_export.py <export_dir> --install       # install if every check passes
  python ml/check_export.py <export_dir> --install --force   # install despite failed checks (not recommended)

An export has the same layout as the repo (ADR-0005: a Model plugs in through files only):

  <export_dir>/ml/model_cards/<name>.json
  <export_dir>/data/<site_id>/layers/pred_<lens>_<YYYY-MM-DD>.tif

Checks (ADR-0010):
  card     valid against contracts/model_card.schema.json; lens matches the site; the site is listed
  score    the Model and its Baseline are scored on the same metric, and the Model beats it (lower is better for
           errors such as RMSE, higher for scores such as IoU or average precision)
           (notes in brackets may differ, with a warning: check both were scored on the same samples)
  layers   file names; the site's projection and area (a coarser grid, e.g. 250 m Neighborhoods, is allowed
           with a note); class values are the card's outputs
  dates    the dates are Passes of the site, or a forecast after the last one; missing Passes are looked up in
           NASA's catalogue at install (metadata only)
  pulse    for a water Model: the wet area does not peak on the very first Pass (warning only)

Install backs up the current card and prediction maps to data/<site_id>/previous_model/<UTC time>/, copies the
export in, and refreshes the manifest (which also derives the season maps for a water Model).
Nothing in the export is executed; only JSON and GeoTIFF files are read.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import shutil
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "contracts"))

from pipeline import predictions, sites  # noqa: E402
from saraura import config  # noqa: E402

NAME = re.compile(r"^pred_([a-z]+)_(\d{4}-\d{2}-\d{2})\.tif$")


class Report:
    def __init__(self):
        self.lines: list[tuple[str, str]] = []

    def ok(self, msg):
        self.lines.append(("PASS", msg))

    def fail(self, msg):
        self.lines.append(("FAIL", msg))

    def warn(self, msg):
        self.lines.append(("WARN", msg))

    @property
    def failed(self) -> bool:
        return any(k == "FAIL" for k, _ in self.lines)

    def print(self):
        for k, msg in self.lines:
            print(f"  {k}  {msg}")


def _site_grid(site_id: str):
    """CRS, transform, shape and name of an existing physics layer of the site, or None when the site is not built."""
    import rasterio

    layers = config.data.local_path(f"{site_id}/layers")
    for p in sorted(Path(layers).glob("*.tif")) if Path(layers).exists() else []:
        if not p.name.startswith("pred_"):
            with rasterio.open(p) as r:
                return r.crs, r.transform, (r.height, r.width), p.name
    return None


def _metric(m: str) -> str:
    """'average precision (out-of-fold, spatial blocks)' -> 'average precision'."""
    return m.split(" (")[0].strip().lower()


LOWER_IS_BETTER = ("rmse", "mae", "mse", "error", "loss", "brier", "crps", "pinball")


def _lower_is_better(metric: str) -> bool:
    """Errors (RMSE, MAE, Brier, ...) are better when lower; scores (IoU, AP, F1, accuracy) when higher."""
    return any(w in _metric(metric) for w in LOWER_IS_BETTER)


def _built_dates(site_id: str) -> list[str] | None:
    key = f"{site_id}/manifest.json"
    if not config.data.exists(key):
        return None
    return [p["date"] for p in json.loads(config.data.read_text(key)).get("passes", [])]


def check(export: Path) -> tuple[Report, dict | None, list[Path]]:
    import rasterio
    from rasterio.transform import array_bounds
    from validate import _schema_errors

    rep = Report()
    cards = sorted((export / "ml" / "model_cards").glob("*.json"))
    if len(cards) != 1:
        rep.fail(f"expected one card in ml/model_cards/, found {len(cards)}")
        return rep, None, []
    card_path = cards[0]
    try:
        c = json.loads(card_path.read_text(encoding="utf-8"))
    except ValueError as e:
        rep.fail(f"card is not valid JSON: {e}")
        return rep, None, []

    # card
    errs = _schema_errors("model_card", c)
    if errs:
        for e in errs:
            rep.fail(f"card: {e}")
        return rep, c, []
    if c["name"] != card_path.stem:
        rep.fail(f"card: name '{c['name']}' must equal the file name '{card_path.stem}'")
    site_ids = [s for s in c["sites"] if sites.path_for(s).exists()]
    for s in set(c["sites"]) - set(site_ids):
        rep.fail(f"card: no sites/{s}.yaml")
    for s in site_ids:
        site = sites.load(s)
        if site.get("lens") != c["lens"]:
            rep.fail(f"card: lens '{c['lens']}' but site {s} is '{site.get('lens')}'")
        if site.get("model_card") != c["name"]:
            rep.fail(f"card: site {s} expects model card '{site.get('model_card')}'")
    if not rep.failed:
        rep.ok(f"card '{c['name']}' is valid for {', '.join(site_ids)}")

    # score: like with like, and in the right direction (an error such as RMSE is better when lower)
    b, m = c["baseline"], c["model"]
    same = _metric(b["metric"]) == _metric(m["metric"])
    lower = _lower_is_better(b["metric"])
    beats = lambda s: s is not None and b["score"] is not None and (s < b["score"] if lower else s > b["score"])
    word = "lower is better" if lower else "higher is better"
    if b["score"] is None or m["score"] is None:
        rep.fail("score: the Model or the Baseline has no score")
    elif not same:
        rep.fail(f"score: Model scored on '{m['metric']}' but Baseline on '{b['metric']}'; score both the same way")
    elif not beats(m["score"]):
        rep.fail(f"score: Model {m['score']} does not beat the Baseline {b['score']} ({_metric(m['metric'])}, {word})")
    else:
        rep.ok(f"score: Model {m['score']} beats the Baseline {b['score']} ({_metric(m['metric'])}, {word})")
    if same and b["metric"] != m["metric"]:
        rep.warn(f"score: Model metric '{m['metric']}' vs Baseline '{b['metric']}': check both were scored on the same samples")
    if b["score"] is not None and (not same or not beats(m["score"])):
        better = [x for x in c.get("extra_scores", []) if _metric(x["metric"]) == _metric(b["metric"]) and beats(x["score"])
                  and "baseline" not in x["name"].lower()]
        for x in better:
            rep.warn(f"score: '{x['name']}' scores {x['score']} on {x['metric']}; consider exporting that Model instead")

    # layers
    outputs = {o["value"] for o in c.get("outputs", [])}
    files: list[Path] = []
    for s in site_ids:
        folder = export / "data" / s / "layers"
        found = sorted(folder.glob("*.tif")) if folder.exists() else []
        bad = [p.name for p in found if not (NAME.match(p.name) and NAME.match(p.name).group(1) == c["lens"])]
        for n in bad:
            rep.fail(f"layers: {s}/{n} is not named pred_{c['lens']}_<YYYY-MM-DD>.tif")
        good = [p for p in found if p.name not in bad]
        if not good:
            rep.fail(f"layers: no pred_{c['lens']}_<date>.tif for {s}")
            continue
        files += good
        grid = _site_grid(s)
        if grid is None:
            rep.warn(f"layers: site {s} is not built yet, so the grid cannot be compared (build it, then re-check)")
        dates = _built_dates(s)
        wet = [o["value"] for o in c.get("outputs", []) if o["label"] in predictions.WET]
        shares, grid_ok, values_ok = [], True, True
        for p in good:
            with rasterio.open(p) as r:
                a = r.read(1)
                if grid is not None:
                    crs, tr, shape, ref = grid
                    sb = array_bounds(shape[0], shape[1], tr)  # (west, south, east, north)
                    pb = r.bounds
                    overlap = max(0.0, min(pb.right, sb[2]) - max(pb.left, sb[0])) * max(0.0, min(pb.top, sb[3]) - max(pb.bottom, sb[1]))
                    share = overlap / max((sb[2] - sb[0]) * (sb[3] - sb[1]), 1e-9)
                    exact = (r.height, r.width) == shape and np.allclose(tuple(r.transform)[:6], tuple(tr)[:6], atol=1e-6)
                    if r.crs != crs:
                        grid_ok = False
                        rep.fail(f"layers: {p.name} is in {r.crs}, the site in {crs} ({ref})")
                    elif share < 0.5:
                        grid_ok = False
                        rep.fail(f"layers: {p.name} covers only {share:.0%} of the site area")
                    elif not exact and p == good[0]:
                        rep.warn(f"layers: {p.name} is on its own {r.res[0]:g} m grid ({r.width}x{r.height}), not the site's "
                                 f"{tr.a:g} m grid; allowed (the map server resamples), covers {share:.0%} of the site")
                if "prediction" not in c:
                    if r.dtypes[0] != "uint8":
                        values_ok = False
                        rep.fail(f"layers: {p.name} is {r.dtypes[0]}; class maps must be uint8 with 255 as no data")
                    vals = set(np.unique(a).tolist()) - {255}
                    if not vals <= outputs:
                        values_ok = False
                        rep.fail(f"layers: {p.name} has values {sorted(vals - outputs)} that are not outputs on the card")
                    valid = a != 255
                    if wet and valid.any():
                        shares.append(float(np.isin(a[valid], wet).mean()))
        if grid_ok and grid is not None:
            rep.ok(f"layers: {len(good)} map(s) for {s} in the site's projection and area")
        if values_ok and "prediction" not in c:
            rep.ok(f"layers: class values are the card's outputs {sorted(outputs)}")
        if dates:
            ds = [NAME.match(p.name).group(2) for p in good]
            ahead = [d for d in ds if d > dates[-1]] if "prediction" in c else []  # a forecast may point past the last Pass
            stray = [d for d in ds if d not in dates and d not in ahead]
            if ahead:
                rep.ok(f"dates: forecast for {', '.join(ahead)}, after the last built Pass {dates[-1]}")
            if stray:
                rep.warn(f"dates: {', '.join(stray)} are not in {s}'s built Pass list; install adds them from NASA's catalogue "
                         "(metadata only) if NISAR acquired them")
            elif not ahead:
                rep.ok(f"dates: all {len(good)} are Passes of {s}")
        if len(shares) > 2:
            peak = int(np.argmax(shares))
            table = ", ".join(f"{NAME.match(p.name).group(2)[5:]}: {x:.0%}" for p, x in zip(good, shares))
            if peak == 0:
                rep.warn(f"pulse: the wet area peaks on the first Pass ({table}); a flood pulse should rise first. "
                         "Check the maps against optical images before trusting them.")
            else:
                rep.ok(f"pulse: wet area by Pass ({table})")
    return rep, c, files


def install(export: Path, c: dict, files: list[Path]) -> None:
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for s in c["sites"]:
        layers = Path(config.data.local_path(f"{s}/layers"))
        layers.mkdir(parents=True, exist_ok=True)
        backup = Path(config.data.local_path(f"{s}/previous_model/{stamp}"))
        backup.mkdir(parents=True, exist_ok=True)
        current_card = config.MODEL_CARDS_DIR / f"{c['name']}.json"
        if current_card.exists():
            shutil.copy2(current_card, backup / current_card.name)
        for old in layers.glob(f"pred_{c['lens']}_*.tif"):
            shutil.move(str(old), backup / old.name)
        for p in files:
            if p.parent.parent.name == s:
                shutil.copy2(p, layers / p.name)
        print(f"  {s}: previous Model kept in {backup}")
    shutil.copy2(export / "ml" / "model_cards" / f"{c['name']}.json", config.MODEL_CARDS_DIR / f"{c['name']}.json")
    for s in c["sites"]:
        if config.data.exists(f"{s}/manifest.json"):
            predictions.refresh(s)
            try:  # dates the Model mapped that the build did not list: look them up (metadata only, no pixels)
                from pipeline import catalogue_passes

                added = catalogue_passes.add_missing(s)
                if added:
                    print(f"  {s}: added Passes {', '.join(added)} from NASA's catalogue")
                    predictions.refresh(s)
            except Exception as e:  # offline: the manifest lists the dates once the catalogue is reachable
                print(f"  {s}: could not reach NASA's catalogue ({str(e)[:80]}); run python -m pipeline.catalogue_passes {s} later")
        else:
            print(f"  {s}: not built yet; build it to list the new maps")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("export", type=Path)
    ap.add_argument("--install", action="store_true", help="install the export if every check passes")
    ap.add_argument("--force", action="store_true", help="with --install: install even if checks fail")
    a = ap.parse_args(argv)
    export = a.export.resolve()
    if not export.is_dir():
        print(f"{export} is not a folder")
        return 2
    rep, c, files = check(export)
    print(f"Model export {export}")
    rep.print()
    verdict = "FAILED" if rep.failed else "passed"
    print(f"Checks {verdict}.")
    if a.install:
        if rep.failed and not a.force:
            print("Not installed. Fix the failures (or pass --force to install anyway).")
            return 1
        if c is None or not files:
            print("Nothing to install.")
            return 1
        install(export, c, files)
        print("Installed.")
    return 1 if rep.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
