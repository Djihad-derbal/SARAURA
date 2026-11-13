"""Score the two baselines the neural model must beat, on the same held-out test patches.

  python ml/baselines.py --data ml/data/fires

* rules: the backend's change-point detector with fixed physical thresholds.
* trees: gradient-boosted trees on the same per-pixel change-point features,
  trained on the training patches.

Writes ml/runs/<name>/baselines.json.
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "ml"))

from saraura.change import change_point, classify_rules  # noqa: E402
from sardance.const import CLASSES, IGNORE  # noqa: E402
from sardance.metrics import confusion, scores  # noqa: E402


def features(x: np.ndarray):
    """Per-pixel features (N, 8) from one patch's dB stack, plus the change-point dict."""
    cp = change_point(x.astype(np.float32))
    f = np.stack([cp["d"][0], cp["d"][1], cp["pre"][0], cp["pre"][1], cp["post"][0], cp["post"][1], cp["t"], cp["when"].astype(np.float32)], -1)
    return f.reshape(-1, f.shape[-1]), cp


def load(root: Path, split: str):
    for f in sorted(root.glob(f"{split}_*.npz")):
        d = np.load(f)
        yield d["x"], d["y"]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", required=True)
    ap.add_argument("--name", default=None)
    ap.add_argument("--max-train-pixels", type=int, default=400_000)
    args = ap.parse_args()
    from sklearn.ensemble import HistGradientBoostingClassifier

    root = Path(args.data)
    rng = np.random.default_rng(0)
    X, Y = [], []
    for x, y in load(root, "train"):
        f, _ = features(x)
        ok = y.ravel() != IGNORE
        X.append(f[ok])
        Y.append(y.ravel()[ok])
    X, Y = np.concatenate(X), np.concatenate(Y)
    if len(Y) > args.max_train_pixels:
        pick = rng.choice(len(Y), args.max_train_pixels, replace=False)
        X, Y = X[pick], Y[pick]
    trees = HistGradientBoostingClassifier(max_iter=200, learning_rate=0.1, class_weight="balanced", random_state=0).fit(np.nan_to_num(X), Y)

    n = len(CLASSES)
    cm_rules, cm_trees = np.zeros((n, n), np.int64), np.zeros((n, n), np.int64)
    for x, y in load(root, "test"):
        f, cp = features(x)
        cm_rules += confusion(classify_rules(cp).ravel().astype(np.int64), y.ravel().astype(np.int64))
        cm_trees += confusion(trees.predict(np.nan_to_num(f)).astype(np.int64), y.ravel().astype(np.int64))
    out = {"rules": scores(cm_rules), "trees": scores(cm_trees), "note": "rules never predicts 'burned'; it reports fire as vegetation loss"}
    run = ROOT / "ml" / "runs" / (args.name or root.name)
    run.mkdir(parents=True, exist_ok=True)
    (run / "baselines.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    for k in ("rules", "trees"):
        print(f"{k:6s} mean IoU {out[k]['mean_iou']:.3f}   change-class IoU {out[k]['mean_iou_change_classes']}")


if __name__ == "__main__":
    main()
