"""Train ChangeUTAE on patches from build_dataset.py.

  python ml/train.py --data ml/data/fires --epochs 40

Writes ml/runs/<name>/best.pt and metrics.json (validation curve plus a final
score on the held-out test blocks). Runs in full precision: GTX 16-series
cards are unreliable with half precision.
"""
import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from torch.utils.data import DataLoader

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ml"))

from sardance.data import CLASSES, IGNORE, PatchDataset, class_weights, confusion, scores  # noqa: E402
from sardance.model import ChangeUTAE, count_parameters  # noqa: E402


def drop_passes(x, days, keep_min=4):
    """Train-time augmentation: hide a few random passes so the model copes with gaps."""
    t = x.shape[1]
    if t <= keep_min + 2 or np.random.rand() < 0.7:
        return x, days
    keep = np.sort(np.random.choice(t, np.random.randint(t - 2, t), replace=False))  # hide one or two passes
    return x[:, keep], days[:, keep] - days[:, keep[:1]]


@torch.no_grad()
def evaluate(model, loader, device) -> dict:
    model.eval()
    cm = np.zeros((len(CLASSES), len(CLASSES)), np.int64)
    for x, days, y in loader:
        pred = model(x.to(device), days.to(device)).argmax(1).cpu().numpy()
        cm += confusion(pred.ravel(), y.numpy().ravel())
    return scores(cm)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", required=True)
    ap.add_argument("--name", default=None)
    ap.add_argument("--epochs", type=int, default=40)
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--lr", type=float, default=2e-3)
    ap.add_argument("--workers", type=int, default=0)
    args = ap.parse_args()

    device = "cuda" if torch.cuda.is_available() else "cpu"
    run = ROOT / "ml" / "runs" / (args.name or Path(args.data).name)
    run.mkdir(parents=True, exist_ok=True)
    train = DataLoader(PatchDataset(args.data, "train", augment=True), batch_size=args.batch, shuffle=True, num_workers=args.workers, drop_last=True)
    val = DataLoader(PatchDataset(args.data, "val"), batch_size=args.batch, num_workers=args.workers)
    model = ChangeUTAE(in_channels=4, n_classes=len(CLASSES)).to(device)
    weights = class_weights(args.data).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=args.lr, total_steps=max(1, args.epochs * len(train)))
    print(f"device {device} | {count_parameters(model):,} parameters | {len(train.dataset)} train / {len(val.dataset)} val patches")

    history, best = [], -1.0
    for epoch in range(1, args.epochs + 1):
        model.train()
        t0, total = time.time(), 0.0
        for x, days, y in train:
            x, days = drop_passes(x, days)
            loss = F.cross_entropy(model(x.to(device), days.to(device)), y.to(device), weight=weights, ignore_index=IGNORE)
            opt.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 2.0)
            opt.step()
            sched.step()
            total += loss.item()
        s = evaluate(model, val, device)
        key = s["supported_change_iou"] or s["mean_iou"]  # judged on change classes common enough to measure
        history.append({"epoch": epoch, "loss": round(total / max(len(train), 1), 4), "val_mean_iou": s["mean_iou"], "val_change_iou": s["supported_change_iou"]})
        print(f"epoch {epoch:3d}  loss {history[-1]['loss']:.4f}  val mIoU {s['mean_iou']:.3f}  change mIoU {key:.3f}  {time.time() - t0:.0f}s")
        if key > best:
            best = key
            torch.save({"model": model.state_dict(), "classes": CLASSES, "epoch": epoch}, run / "best.pt")

    model.load_state_dict(torch.load(run / "best.pt", map_location=device)["model"])
    try:
        test = evaluate(model, DataLoader(PatchDataset(args.data, "test"), batch_size=args.batch), device)
    except FileNotFoundError:
        test = None
    metrics = {"model": "ChangeUTAE", "parameters": count_parameters(model), "data": str(args.data), "history": history, "test": test}
    (run / "metrics.json").write_text(json.dumps(metrics, indent=1), encoding="utf-8")
    print("test:", json.dumps(test and {"mean_iou": test["mean_iou"], "supported_change_iou": test["supported_change_iou"], "burned": test["per_class"].get("burned"), "merged": test["vegetation_loss_merged"]}))


if __name__ == "__main__":
    main()
