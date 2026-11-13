"""Score a site's wildfire Model and Baseline against Sentinel-2 proxy labels made for that site.

  python ml/score_site.py --site washington_sinlahekin_wildfire --pre 2026-06-10 2026-07-25 --post 2026-09-05 2026-10-10

Use it on a site the Model never trained on, to test transfer. Labels come from the same rule as the
training labels (ml/sardance/labels.py: dNBR >= 0.27 on vegetation), on the site's own radar grid.
Every labelled cell counts: the site is unseen, so there is no train/test split to respect.
Writes ml/runs/transfer_<site>.json and adds the result to ml/model_cards/wildfire.json.
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import rasterio

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "ml"))

from saraura import config  # noqa: E402
from sardance import labels  # noqa: E402
from sardance.const import CLASSES, IGNORE  # noqa: E402

BURNED = CLASSES.index("burned")


def layer(site: str, manifest: dict, layer_id: str):
    l = next(l for l in manifest["layers"] if l["id"] == layer_id)
    with rasterio.open(config.data.local_path(f"{site}/layers/{layer_id}_{l['dates'][-1]}.tif")) as ds:
        tr = ds.transform
        grid = {"x0": tr.c, "y0": tr.f, "res": tr.a, "epsg": ds.crs.to_epsg(), "shape": [ds.height, ds.width]}
        return ds.read(1), grid


def score(pred: np.ndarray, y: np.ndarray) -> dict:
    ok = (y != IGNORE) & (pred != 255)
    p, t = (pred == 1) & ok, (y == BURNED) & ok
    tp, fp, fn = int((p & t).sum()), int((p & ~t).sum()), int((~p & t).sum())
    return {"burned_iou": round(tp / max(tp + fp + fn, 1), 4), "precision": round(tp / max(tp + fp, 1), 4), "recall": round(tp / max(tp + fn, 1), 4)}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--site", required=True)
    ap.add_argument("--pre", nargs=2, required=True, metavar=("START", "END"))
    ap.add_argument("--post", nargs=2, required=True, metavar=("START", "END"))
    args = ap.parse_args()
    manifest = json.loads(config.data.read_text(f"{args.site}/manifest.json"))
    pred, grid = layer(args.site, manifest, "pred_wildfire")
    base, grid_b = layer(args.site, manifest, "baseline_wildfire")
    assert grid == grid_b, "Model and Baseline layers must share a grid"

    cache = ROOT / "ml" / "data" / f"labels_{args.site}.npz"
    if cache.exists():
        y = np.load(cache)["y"]
    else:
        y = labels.build(grid, manifest["bbox"], tuple(args.pre), tuple(args.post))
        np.savez_compressed(cache, y=y, pre=args.pre, post=args.post)
    labelled = y != IGNORE
    burned_ha = float((y == BURNED).sum()) * grid["res"] ** 2 / 1e4
    print(f"labels: {100 * labelled.mean():.0f}% of cells judged, {burned_ha:,.0f} ha burned")

    out = {"site": args.site, "labels": {"pre": args.pre, "post": args.post, "judged_share": round(float(labelled.mean()), 3), "burned_ha": round(burned_ha)},
           "model": score(pred, y), "baseline": score(base, y)}
    for k in ("model", "baseline"):
        print(f"{k:8s} burned IoU {out[k]['burned_iou']}  precision {out[k]['precision']}  recall {out[k]['recall']}")
    (ROOT / "ml" / "runs" / f"transfer_{args.site}.json").write_text(json.dumps(out, indent=1), encoding="utf-8")

    card_path = ROOT / "ml" / "model_cards" / "wildfire.json"
    card = json.loads(card_path.read_text(encoding="utf-8"))
    tag = f"on {args.site}, not retrained"
    card["extra_scores"] = [s for s in card.get("extra_scores", []) if tag not in s["name"]] + [
        {"name": f"ChangeUTAE {tag}", "metric": "burned IoU", "score": out["model"]["burned_iou"]},
        {"name": f"Baseline {tag}", "metric": "burned IoU", "score": out["baseline"]["burned_iou"]},
    ]
    card["limits"] = [l for l in card["limits"] if "Untested on the Washington" not in l]
    card_path.write_text(json.dumps(card, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"updated {card_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
