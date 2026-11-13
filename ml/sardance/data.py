"""Patch dataset, input scaling, augmentation and metrics."""
import json
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import Dataset

from .const import CLASSES, IGNORE  # noqa: F401


def features(db: np.ndarray) -> np.ndarray:
    """dB stack (T, 2, H, W) -> model input (T, 4, H, W).

    Channels 0-1: backscatter level. Channels 2-3: each pass minus that cell's
    median over time, so a step change stands out from terrain and land cover.
    Must match saraura/change.py features().
    """
    db = db.astype(np.float32)
    level = np.clip((np.nan_to_num(db, nan=-30.0) + 15.0) / 10.0, -3, 3)
    with np.errstate(all="ignore"):
        anomaly = db - np.nanmedian(db, axis=0, keepdims=True)
    anomaly = np.clip(np.nan_to_num(anomaly, nan=0.0) / 3.0, -3, 3)
    return np.concatenate([level, anomaly], axis=1).astype(np.float32)


class PatchDataset(Dataset):
    """Patches written by build_dataset.py: x (T, 2, P, P) dB, y (P, P) class ids, days (T,)."""

    def __init__(self, root: str | Path, split: str, augment: bool = False, min_passes: int = 4):
        self.files = sorted(Path(root).glob(f"{split}_*.npz"))
        self.augment, self.min_passes = augment, min_passes
        if not self.files:
            raise FileNotFoundError(f"No {split} patches in {root}")

    def __len__(self):
        return len(self.files)

    def __getitem__(self, i):
        d = np.load(self.files[i])
        db, y, days = d["x"].astype(np.float32), d["y"].astype(np.int64), d["days"].astype(np.float32)
        if self.augment:
            # Per-pass calibration jitter, kept well below the 1 to 2 dB signal we are looking for.
            db = db + np.random.normal(0, 0.15, (db.shape[0], db.shape[1], 1, 1)).astype(np.float32)
        x = features(db)
        if self.augment:
            k = np.random.randint(4)
            x, y = np.rot90(x, k, (2, 3)), np.rot90(y, k, (0, 1))
            if np.random.rand() < 0.5:
                x, y = x[..., ::-1], y[..., ::-1]
        return torch.from_numpy(np.ascontiguousarray(x)), torch.from_numpy(days - days[0]), torch.from_numpy(np.ascontiguousarray(y))


def class_weights(root: str | Path) -> torch.Tensor:
    """Inverse square-root frequency, so rare change classes are not drowned out by 'stable'."""
    counts = np.array(json.loads((Path(root) / "dataset.json").read_text())["train_pixels"], np.float64)
    w = 1.0 / np.sqrt(np.maximum(counts, 1.0))
    w = w / w[counts > 0].min()  # most common class = 1
    w = np.clip(w, 1.0, 3.0)  # cap: a handful of noisy rare cells must not dominate the loss
    w[counts == 0] = 0.0
    return torch.tensor(w, dtype=torch.float32)


from .metrics import confusion, scores  # noqa: E402,F401
