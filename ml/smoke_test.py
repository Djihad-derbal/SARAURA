"""End-to-end wiring check on synthetic data: patches -> train -> baselines -> ONNX export.

  python ml/smoke_test.py

Uses made-up radar values, so the scores mean nothing. It only proves the
pipeline runs. Output goes to ml/data/_smoke and ml/runs/_smoke.
"""
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ml"))
from build_dataset import cut  # noqa: E402


def synthetic(T=8, size=384, seed=0):
    rng = np.random.default_rng(seed)
    db = np.empty((T, 2, size, size), np.float32)
    db[:, 0] = -8 + rng.normal(0, 0.8, (T, size, size))   # HH
    db[:, 1] = -13 + rng.normal(0, 0.8, (T, size, size))  # HV
    y = np.zeros((size, size), np.uint8)
    for k in range(12):  # scattered squares of each change type, starting at a random pass
        r, c, s, t0 = rng.integers(0, size - 48), rng.integers(0, size - 48), rng.integers(20, 48), rng.integers(3, T - 2)
        kind = (1, 3, 4)[k % 3]
        y[r : r + s, c : c + s] = kind
        if kind == 1:
            db[t0:, 1, r : r + s, c : c + s] -= 3.0
        elif kind == 3:
            db[t0:, 1, r : r + s, c : c + s] += 3.0
        else:
            db[t0:, 0, r : r + s, c : c + s] = -19 + rng.normal(0, 0.5, (T - t0, s, s))
            db[t0:, 1, r : r + s, c : c + s] = -26 + rng.normal(0, 0.5, (T - t0, s, s))
    return db, y, [20000 + 12 * i for i in range(T)]


if __name__ == "__main__":
    data, run = ROOT / "ml" / "data" / "_smoke", ROOT / "ml" / "runs" / "_smoke"
    db, y, days = synthetic()
    print("patches:", cut(db, y, days, data, patch=64, stride=48, block_patches=2, keep_stable=1.0)["patches"])
    py = sys.executable
    for cmd in (
        [py, str(ROOT / "ml" / "train.py"), "--data", str(data), "--name", "_smoke", "--epochs", "3", "--batch", "4"],
        [py, str(ROOT / "ml" / "baselines.py"), "--data", str(data), "--name", "_smoke"],
        [py, str(ROOT / "ml" / "export_onnx.py"), "--run", str(run), "--out", str(run / "smoke.onnx")],
    ):
        print("\n$", " ".join(Path(c).name if c.endswith(".py") else c for c in cmd[1:]))
        subprocess.run(cmd, check=True)
    print("\nSmoke test passed.")
