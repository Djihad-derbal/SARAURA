"""Export a trained run to models/change_utae.onnx so the web app can use it.

  python ml/export_onnx.py --run ml/runs/fires

Also copies the test scores (and baseline scores, if baselines.py was run) to
models/change_utae.metrics.json, which the app shows next to the model.
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ml"))

from sardance.data import CLASSES  # noqa: E402
from sardance.model import ChangeUTAE  # noqa: E402


def export(run: Path, out: Path) -> float:
    model = ChangeUTAE(in_channels=4, n_classes=len(CLASSES))
    model.load_state_dict(torch.load(run / "best.pt", map_location="cpu")["model"])
    model.eval()
    x, days = torch.randn(1, 6, 4, 64, 64), torch.arange(6).float()[None] * 12
    out.parent.mkdir(parents=True, exist_ok=True)
    torch.onnx.export(
        model, (x, days), str(out), input_names=["x", "days"], output_names=["logits"], opset_version=17, dynamo=False,
        dynamic_axes={"x": {0: "batch", 1: "passes", 3: "height", 4: "width"}, "days": {0: "batch", 1: "passes"}, "logits": {0: "batch", 2: "height", 3: "width"}},
    )
    # Check the exported graph against PyTorch on a different number of passes and a different size.
    import onnxruntime as ort

    x2, d2 = torch.randn(1, 9, 4, 96, 128), torch.arange(9).float()[None] * 12
    got = ort.InferenceSession(str(out), providers=["CPUExecutionProvider"]).run(None, {"x": x2.numpy(), "days": d2.numpy()})[0]
    with torch.no_grad():
        want = model(x2, d2).numpy()
    return float(np.abs(got - want).max())


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", required=True)
    ap.add_argument("--out", default=str(ROOT / "models" / "change_utae.onnx"))
    args = ap.parse_args()
    run, out = Path(args.run), Path(args.out)
    diff = export(run, out)
    print(f"wrote {out} ({out.stat().st_size / 1e6:.1f} MB); max difference from PyTorch {diff:.2e}")
    summary = {"run": run.name}
    if (run / "metrics.json").exists():
        m = json.loads((run / "metrics.json").read_text(encoding="utf-8"))
        summary.update(parameters=m["parameters"], data=m["data"], test=m["test"])
    if (run / "clean_scores.json").exists():  # leak-free comparison from evaluate.py; the app shows this one
        clean = json.loads((run / "clean_scores.json").read_text(encoding="utf-8"))["test"]
        summary["clean_test"] = {k: {"burned": clean[k]["per_class"].get("burned"), "vegetation_loss_merged": clean[k]["vegetation_loss_merged"]} for k in ("neural", "trees", "rules")}
        summary["labels"] = "Sentinel-2 burn index (dNBR >= 0.27 on vegetation); agreement with these labels, not field truth"
    if (run / "baselines.json").exists():
        summary["baselines"] = json.loads((run / "baselines.json").read_text(encoding="utf-8"))
    out.with_suffix(".metrics.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
