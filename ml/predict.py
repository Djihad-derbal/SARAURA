"""Run a trained Model over a built Showcase Site and write its prediction layer (ADR-0005).

  python ml/predict.py --site algeria_ne_wildfire
  python ml/predict.py --site washington_sinlahekin_wildfire

Wildfire: ChangeUTAE (models/change_utae.onnx) reads the site's HH/HV time series from the
pipeline's own COGs, so it sees exactly what the Study page shows. Only "burned" is kept; the
model's other change classes are unreliable (see the Model card). Writes
data/<site>/layers/pred_wildfire_<last Pass>.tif (0 no clear change, 1 burned, 255 no data),
then refreshes the manifest.

Run the site through the pipeline first (python -m pipeline.run_site sites/<site>.yaml).
"""
import argparse
import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np
import rasterio

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import export, predictions  # noqa: E402
from saraura import change, config  # noqa: E402
sys.path.insert(0, str(ROOT / "ml"))
from sardance.const import CLASSES  # noqa: E402  (plain list, no PyTorch import)

BURNED = CLASSES.index("burned")


def load_stack(site_id: str, manifest: dict) -> tuple[np.ndarray, list[str], dict]:
    """(T, 2, H, W) dB stack of HH and HV from the site's COGs, the dates, and the grid."""
    layer = {l["id"]: l for l in manifest["layers"]}
    dates = sorted(set(layer["hh_db"]["dates"]) & set(layer["hv_db"]["dates"]))
    stack, grid = None, None
    for t, d in enumerate(dates):
        for b, name in enumerate(("hh_db", "hv_db")):
            with rasterio.open(config.data.local_path(f"{site_id}/layers/{name}_{d}.tif")) as ds:
                if stack is None:
                    stack = np.full((len(dates), 2, ds.height, ds.width), np.nan, np.float32)
                    tr = ds.transform
                    grid = {"x0": tr.c, "y0": tr.f, "res": tr.a, "epsg": ds.crs.to_epsg(), "shape": [ds.height, ds.width]}
                stack[t, b] = ds.read(1)
    return stack, dates, grid


def wildfire(site_id: str, manifest: dict) -> str:
    db, dates, grid = load_stack(site_id, manifest)
    t0 = dt.date.fromisoformat(dates[0])
    days = [(dt.date.fromisoformat(d) - t0).days for d in dates]
    print(f"  {len(dates)} Passes {dates[0]} .. {dates[-1]}, grid {grid['shape'][0]} x {grid['shape'][1]} at {grid['res']:.0f} m")
    cls = change.classify_model(db, days)
    out = np.where(np.isfinite(db).all(1).any(0), (cls == BURNED).astype(np.uint8), 255).astype(np.uint8)
    valid = out != 255
    ha = float((out == 1).sum()) * grid["res"] ** 2 / 1e4
    print(f"  burned: {ha:,.0f} ha ({100 * (out == 1).sum() / max(valid.sum(), 1):.1f}% of valid area)")
    return export.write_cog(site_id, f"pred_wildfire_{dates[-1]}", out, grid, categorical=True)


RUNNERS = {"wildfire": wildfire}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--site", required=True)
    args = ap.parse_args()
    manifest = json.loads(config.data.read_text(f"{args.site}/manifest.json"))
    lens = manifest["lens"]
    if lens not in RUNNERS:
        raise SystemExit(f"No Model for the {lens} Lens yet")
    for key in list(config.data.list(f"{args.site}/layers")):  # one current prediction per site
        if key.split("/")[-1].startswith(f"pred_{lens}_"):
            config.data.delete(key)
    print(f"wrote data/{RUNNERS[lens](args.site, manifest)}")
    raise SystemExit(predictions.refresh(args.site))


if __name__ == "__main__":
    main()
