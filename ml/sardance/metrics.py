"""IoU, precision, recall and F1 from a confusion matrix."""
import numpy as np

from .const import CLASSES, IGNORE


def confusion(pred: np.ndarray, target: np.ndarray, n: int = len(CLASSES)) -> np.ndarray:
    ok = target != IGNORE
    return np.bincount(target[ok] * n + pred[ok], minlength=n * n).reshape(n, n)


def scores(cm: np.ndarray) -> dict:
    """Per-class IoU / precision / recall / F1 and their means over classes that occur."""
    tp = np.diag(cm).astype(np.float64)
    fp, fn = cm.sum(0) - tp, cm.sum(1) - tp
    out = {"per_class": {}}
    for i, name in enumerate(CLASSES):
        if cm[i].sum() == 0:
            continue
        p = tp[i] / max(tp[i] + fp[i], 1)
        r = tp[i] / max(tp[i] + fn[i], 1)
        out["per_class"][name] = {
            "iou": round(tp[i] / max(tp[i] + fp[i] + fn[i], 1), 4),
            "precision": round(p, 4),
            "recall": round(r, 4),
            "f1": round(2 * p * r / max(p + r, 1e-9), 4),
            "pixels": int(cm[i].sum()),
        }
    # Burned and other vegetation loss merged: a fair comparison for detectors that cannot tell them apart.
    m = [CLASSES.index("burned"), CLASSES.index("veg_loss")]
    tpm = cm[np.ix_(m, m)].sum()
    fpm, fnm = cm[:, m].sum() - tpm, cm[m, :].sum() - tpm
    out["vegetation_loss_merged"] = {"iou": round(tpm / max(tpm + fpm + fnm, 1), 4), "precision": round(tpm / max(tpm + fpm, 1), 4), "recall": round(tpm / max(tpm + fnm, 1), 4)}
    changed = [v for k, v in out["per_class"].items() if k != "stable"]
    total = max(cm.sum(), 1)
    solid = [v["iou"] for k, v in out["per_class"].items() if k != "stable" and v["pixels"] / total >= 0.005]
    out["supported_change_iou"] = round(float(np.mean(solid)), 4) if solid else None  # change classes with at least 0.5% of cells
    out["mean_iou"] = round(float(np.mean([v["iou"] for v in out["per_class"].values()])), 4)
    out["mean_iou_change_classes"] = round(float(np.mean([v["iou"] for v in changed])), 4) if changed else None
    return out
