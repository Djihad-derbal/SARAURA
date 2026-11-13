"""Score the wildfire Baseline (HV drop > 1.5 dB on vegetated land) on the same held-out cells as the Model.

  python ml/score_baseline.py --data ml/data/fires --site algeria_ne_wildfire

Uses the pipeline's own rule (pipeline.gcov.wildfire_baseline) with the site's event dates, and the
same leak-free test cells as ml/evaluate.py (cells shared with a training patch are dropped).
Writes ml/runs/<name>/baseline_hv_drop.json and fills baseline.score in ml/model_cards/wildfire.json.
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import sites  # noqa: E402
from pipeline.gcov import wildfire_baseline  # noqa: E402
sys.path.insert(0, str(ROOT / "ml"))
from sardance.const import CLASSES  # noqa: E402  (plain list, no PyTorch import)

BURNED, IGNORE = CLASSES.index("burned"), 255


def clean_mask(root: Path, stride: int):
    """Same rule as ml/evaluate.py: blank every held-out cell that a training patch also covers."""
    pos = lambda f: tuple(int(v) for v in f.stem.split("_")[1:])  # noqa: E731
    train_at = {pos(f) for f in root.glob("train_*.npz")}

    def clean(f: Path, y: np.ndarray) -> np.ndarray:
        patch = y.shape[0]
        lap = patch - stride
        i, j = pos(f)
        y = y.copy()
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                if (di or dj) and (i + di, j + dj) in train_at:
                    rows = slice(0, lap) if di < 0 else slice(patch - lap, patch) if di > 0 else slice(None)
                    cols = slice(0, lap) if dj < 0 else slice(patch - lap, patch) if dj > 0 else slice(None)
                    y[rows, cols] = IGNORE
        return y

    return clean


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", required=True)
    ap.add_argument("--site", required=True)
    ap.add_argument("--name", default=None)
    ap.add_argument("--stride", type=int, default=96)
    args = ap.parse_args()
    root = Path(args.data)
    site = sites.load(args.site)
    dates = json.loads((root / "dataset.json").read_text(encoding="utf-8"))["dates"]
    clean = clean_mask(root, args.stride)

    out = {}
    for split in ("val", "test"):
        tp = fp = fn = 0
        for f in sorted(root.glob(f"{split}_*.npz")):
            d = np.load(f)
            y = clean(f, d["y"])
            res = wildfire_baseline(d["x"][:, 1].astype(np.float32), dates, site["event_date"], event_end=site.get("event_end_date"))
            if res is None:
                raise SystemExit("No Passes on one side of the event in this dataset")
            pred = res[1] == 1
            ok = y != IGNORE
            truth = y == BURNED
            tp += int((pred & truth & ok).sum())
            fp += int((pred & ~truth & ok).sum())
            fn += int((~pred & truth & ok).sum())
        out[split] = {
            "burned_iou": round(tp / max(tp + fp + fn, 1), 4),
            "precision": round(tp / max(tp + fp, 1), 4),
            "recall": round(tp / max(tp + fn, 1), 4),
        }
        print(f"{split}: Baseline burned IoU {out[split]['burned_iou']}  precision {out[split]['precision']}  recall {out[split]['recall']}")

    run = ROOT / "ml" / "runs" / (args.name or root.name)
    (run / "baseline_hv_drop.json").write_text(json.dumps({"rule": "HV drop > 1.5 dB, pre-fire HV > -20 dB", "event_date": site["event_date"], **out}, indent=1), encoding="utf-8")
    card_path = ROOT / "ml" / "model_cards" / "wildfire.json"
    card = json.loads(card_path.read_text(encoding="utf-8"))
    card["baseline"]["score"] = out["test"]["burned_iou"]
    card["limits"] = [l for l in card["limits"] if "Baseline score is not computed" not in l]
    card_path.write_text(json.dumps(card, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"updated {card_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
