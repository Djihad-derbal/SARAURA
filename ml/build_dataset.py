"""Cut training patches: NISAR time stack as input, Sentinel-2 change labels as target.

Example (the August 2026 fires, track 109):
  python ml/build_dataset.py --name fires --stack 109_D_070 --bbox 5.6 36.55 6.5 36.95 \
      --pre 2026-07-20 2026-08-20 --post 2026-09-01 2026-09-30

The area is split into square blocks that go wholly to train, validation or
test, so the model is always scored on ground it has not seen.
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "ml"))

from sardance.const import CLASSES, IGNORE  # noqa: E402


def split_of(block_row: int, block_col: int) -> str:
    """Deterministic 70 / 15 / 15 split by block."""
    h = (block_row * 73856093 ^ block_col * 19349663) % 100
    return "train" if h < 70 else "val" if h < 85 else "test"


def cut(db, labels, days, out: Path, patch=128, stride=96, block_patches=4, keep_stable=0.3, seed=0) -> dict:
    """Write patches to disk and return pixel counts per class and split."""
    rng = np.random.default_rng(seed)
    out.mkdir(parents=True, exist_ok=True)
    counts = {s: np.zeros(len(CLASSES), np.int64) for s in ("train", "val", "test")}
    n = {s: 0 for s in counts}
    _, _, H, W = db.shape
    for i, r in enumerate(range(0, H - patch + 1, stride)):
        for j, c in enumerate(range(0, W - patch + 1, stride)):
            y = labels[r : r + patch, c : c + patch]
            x = db[:, :, r : r + patch, c : c + patch]
            if (y == IGNORE).mean() > 0.5 or np.isnan(x).mean() > 0.4:
                continue
            if not ((y > 0) & (y != IGNORE)).any() and rng.random() > keep_stable:
                continue  # thin out patches where nothing changed
            split = split_of(i // block_patches, j // block_patches)
            np.savez_compressed(out / f"{split}_{i:04d}_{j:04d}.npz", x=x.astype(np.float16), y=y, days=np.asarray(days, np.int32))
            counts[split] += np.bincount(y[y != IGNORE], minlength=len(CLASSES))[: len(CLASSES)]
            n[split] += 1
    meta = {"classes": CLASSES, "patches": n, "train_pixels": counts["train"].tolist(), "val_pixels": counts["val"].tolist(), "test_pixels": counts["test"].tolist()}
    (out / "dataset.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    return meta


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--name", required=True)
    ap.add_argument("--stack", required=True)
    ap.add_argument("--bbox", type=float, nargs=4, required=True, metavar=("WEST", "SOUTH", "EAST", "NORTH"))
    ap.add_argument("--pre", nargs=2, required=True, metavar=("START", "END"), help="clear-sky window before the event")
    ap.add_argument("--post", nargs=2, required=True, metavar=("START", "END"), help="clear-sky window after the event")
    ap.add_argument("--res", type=int, default=20, choices=[20, 80])
    ap.add_argument("--s2-tiles", nargs="*", default=None, help="limit labels to these Sentinel-2 tiles, e.g. MGRS-32SKF")
    args = ap.parse_args()

    from saraura import change as analysis  # the shared reader's own reader, so training and serving see identical pixels
    from sardance import labels

    passes = analysis.stack_passes(args.stack, args.bbox)
    print(f"{len(passes)} passes: {passes[0]['date']} .. {passes[-1]['date']}")
    db, grid = analysis.read_stack(passes, args.bbox, args.res, lambda a, b: print(f"  radar pass {a}/{b}", end="\r"))
    print(f"\nradar stack {db.shape}, grid {grid}")
    y = labels.build(grid, args.bbox, tuple(args.pre), tuple(args.post), tiles=args.s2_tiles)
    np.savez_compressed(ROOT / "ml" / "data" / f"{args.name}_labels.npz", y=y, hv_first=db[0, 1].astype(np.float16), hv_last=db[-1, 1].astype(np.float16))  # for eyeballing
    days = [int(np.datetime64(p["date"]).astype("datetime64[D]").astype(int)) for p in passes]
    out = ROOT / "ml" / "data" / args.name
    print("label cells:", {CLASSES[i]: int((y == i).sum()) for i in range(len(CLASSES))}, "ignored:", int((y == IGNORE).sum()))
    meta = cut(db, y, days, out)
    meta.update(stack=args.stack, bbox=args.bbox, resolution_m=args.res, dates=[p["date"] for p in passes], pre=args.pre, post=args.post)
    (out / "dataset.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    print(json.dumps({k: meta[k] for k in ("patches", "train_pixels", "test_pixels")}, indent=1))


if __name__ == "__main__":
    main()
