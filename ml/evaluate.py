"""Leak-free comparison of the neural model, the trees and the rules on held-out patches.

  python ml/evaluate.py --data ml/data/fires

build_dataset.py cuts overlapping patches (stride smaller than patch size), so a
test patch can share an edge strip with a neighbouring training patch. This
script drops every held-out cell that any training patch covers, then scores
all three methods on what is left. Writes ml/runs/<name>/clean_scores.json.
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "ml"))

from saraura.change import change_point, classify_rules  # noqa: E402
from sardance.const import CLASSES, IGNORE  # noqa: E402
from sardance.data import features  # noqa: E402
from sardance.metrics import confusion, scores  # noqa: E402
from sardance.model import ChangeUTAE  # noqa: E402


def cp_features(x):
    cp = change_point(x.astype(np.float32))
    f = np.stack([cp["d"][0], cp["d"][1], cp["pre"][0], cp["pre"][1], cp["post"][0], cp["post"][1], cp["t"], cp["when"].astype(np.float32)], -1)
    return np.nan_to_num(f.reshape(-1, f.shape[-1])), cp


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", required=True)
    ap.add_argument("--name", default=None)
    ap.add_argument("--stride", type=int, default=96)
    args = ap.parse_args()
    from sklearn.ensemble import HistGradientBoostingClassifier

    root = Path(args.data)
    run = ROOT / "ml" / "runs" / (args.name or root.name)
    files = {s: sorted(root.glob(f"{s}_*.npz")) for s in ("train", "val", "test")}
    pos = lambda f: tuple(int(v) for v in f.stem.split("_")[1:])  # noqa: E731
    train_at = {pos(f) for f in files["train"]}
    patch = np.load(files["train"][0])["y"].shape[0]
    lap = patch - args.stride  # width of the strip shared with a neighbour

    def clean(f, y):
        """Held-out labels with every cell also covered by a training patch set to IGNORE."""
        i, j = pos(f)
        y = y.copy()
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                if (di or dj) and (i + di, j + dj) in train_at:
                    rows = slice(0, lap) if di < 0 else slice(patch - lap, patch) if di > 0 else slice(None)
                    cols = slice(0, lap) if dj < 0 else slice(patch - lap, patch) if dj > 0 else slice(None)
                    y[rows, cols] = IGNORE
        return y

    # Trees: trained on training cells only.
    rng = np.random.default_rng(0)
    X, Y = [], []
    for f in files["train"]:
        d = np.load(f)
        feat, _ = cp_features(d["x"])
        ok = d["y"].ravel() != IGNORE
        X.append(feat[ok])
        Y.append(d["y"].ravel()[ok])
    X, Y = np.concatenate(X), np.concatenate(Y)
    pick = rng.choice(len(Y), min(len(Y), 400_000), replace=False)
    trees = HistGradientBoostingClassifier(max_iter=200, learning_rate=0.1, class_weight="balanced", random_state=0).fit(X[pick], Y[pick])

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = ChangeUTAE(in_channels=4, n_classes=len(CLASSES)).to(device)
    model.load_state_dict(torch.load(run / "best.pt", map_location=device)["model"])
    model.eval()

    out = {}
    n = len(CLASSES)
    for split in ("val", "test"):
        cm = {k: np.zeros((n, n), np.int64) for k in ("neural", "trees", "rules")}
        kept = total = 0
        for f in files[split]:
            d = np.load(f)
            y = clean(f, d["y"]).astype(np.int64).ravel()
            total += (d["y"] != IGNORE).sum()
            kept += (y != IGNORE).sum()
            feat, cp = cp_features(d["x"])
            days = torch.tensor(d["days"] - d["days"][0], dtype=torch.float32)[None].to(device)
            with torch.no_grad():
                pred = model(torch.from_numpy(features(d["x"]))[None].to(device), days).argmax(1).cpu().numpy().ravel()
            cm["neural"] += confusion(pred, y)
            cm["trees"] += confusion(trees.predict(feat).astype(np.int64), y)
            cm["rules"] += confusion(classify_rules(cp).ravel().astype(np.int64), y)
        out[split] = {"cells_kept_share": round(float(kept / max(total, 1)), 3), **{k: scores(v) for k, v in cm.items()}}
        print(f"\n{split}: {100 * kept / max(total, 1):.0f}% of held-out cells are untouched by training patches")
        for k in ("neural", "trees", "rules"):
            s = out[split][k]
            b = s["per_class"].get("burned", {})
            print(f"  {k:7s} burned IoU {b.get('iou')}  precision {b.get('precision')}  recall {b.get('recall')}  | vegetation loss merged IoU {s['vegetation_loss_merged']['iou']}")
    (run / "clean_scores.json").write_text(json.dumps(out, indent=1, default=float), encoding="utf-8")


if __name__ == "__main__":
    main()
