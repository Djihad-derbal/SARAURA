# AI models: how to train them and how they reach the app

There are six Models, one per Lens. Each writes prediction layers for its Showcase Sites
(`data/<site>/layers/pred_<lens>_<date>.tif`) and a Model card (`ml/model_cards/<lens>.json`).
The app only reads those files (ADR-0005); it never runs a Model, and never on a user's own
Analysis (ADR-0001). Scores against each Model's Baseline, and the commands, are in the project
README ("Models") and PLAN.md (Phase 2).

This file documents the first and largest Model, the wildfire ChangeUTAE.

## Results of the first trained model (2026-11-10)

Trained on track 109, ten passes from 21 June to 19 October 2026, over a
62 x 38 km area around Jijel. Labels: Sentinel-2 burn index (dNBR >= 0.27 on
vegetation), tile 32SKF. 347 training, 99 validation and 141 test patches.

Scores on held-out test cells that no training patch covers (90% of the
test cells), from `ml/evaluate.py`:

| Method | Burned IoU | Precision | Recall |
|---|---|---|---|
| Neural model | 0.86 | 0.90 | 0.95 |
| Gradient-boosted trees | 0.67 | 0.81 | 0.80 |
| Rules detector | cannot label "burned" | | |

With burned and other vegetation loss merged, so the rules can be compared:
neural 0.85, trees 0.54, rules 0.39 (IoU). On the validation blocks the
neural model scored 0.81 burned IoU and the trees 0.70.

What these numbers do and do not mean:

- They measure agreement with labels made from optical imagery, not with
  field surveys or official fire perimeters.
- Test areas are separate blocks, but from the same fires, dates and track.
  Performance in another region, season or track is unknown.
- Only "burned" is learned. The other change classes had too few clean
  labels and score near zero; ignore the model's "vegetation grew" output.
- A first run scored 0.47 and lost to the trees. The fixes were: smaller
  augmentation noise, capped class weights, picking the checkpoint on
  well-supported classes, and adding a "difference from the cell's median"
  input. The first run is kept as `ml/runs/fires/best_run1.pt`.
- The labels wrongly mark a thin strip of shoreline as "vegetation grew".

## Using it in the app

`python ml/predict.py --site <wildfire site>` runs the exported ONNX model over a built site and
writes `pred_wildfire_<last Pass>.tif`; the site's manifest then lists it and the Study page shows it
next to the HV-drop Baseline. The Assistant is now Gemini (ADR-0006), set up in the project README.

## Training the neural model

Set up once (GPU build of PyTorch for your GTX 1660 Ti):

```bash
python -m venv ml/.venv
ml/.venv/Scripts/python -m pip install torch --index-url https://download.pytorch.org/whl/cu126
ml/.venv/Scripts/python -m pip install -r ml/requirements.txt
```

Check the wiring first. This uses made-up data and takes under a minute:

```bash
ml/.venv/Scripts/python ml/smoke_test.py
```

Then the real run, in four steps. The API does not need to be running,
but `.env` must hold the Earthdata token.

```bash
ml/.venv/Scripts/python ml/build_dataset.py --name fires --stack 109_D_070 --bbox 5.6 36.55 6.5 36.95 --pre 2026-07-20 2026-08-20 --post 2026-09-01 2026-09-30
```

```bash
ml/.venv/Scripts/python ml/train.py --data ml/data/fires --epochs 40
```

```bash
ml/.venv/Scripts/python ml/baselines.py --data ml/data/fires
```

```bash
ml/.venv/Scripts/python ml/evaluate.py --data ml/data/fires
```

```bash
ml/.venv/Scripts/python ml/export_onnx.py --run ml/runs/fires
```

`evaluate.py` gives the leak-free comparison. The last step writes
`models/change_utae.onnx` and its scores. Restart the
API and the "Neural model" option becomes available.

### How it learns

- **Input:** every pass of a track, HH and HV, in 128 x 128 patches at 20 m.
- **Labels:** made from Sentinel-2 optical images before and after the
  event (burn index, greenness, water index). Optical teaches radar; after
  training only radar is needed.
- **Honest scoring:** the area is cut into blocks, and whole blocks are held
  out for testing. `baselines.py` scores the rules detector and
  gradient-boosted trees on the same test blocks. Ship the neural model only
  if it beats both.

### Before you trust the results

- **Look at the labels before training.** `build_dataset.py` saves
  `ml/data/<name>_labels.npz`; compare it with the radar change. Pass
  `--s2-tiles` to avoid reading overlapping Sentinel-2 tiles.
- **Patches overlap.** Neighbouring patches share a 32-cell strip, so use
  `evaluate.py`, which drops held-out cells that training patches cover.
- **Thresholds are standard starting points**, not tuned for Algeria.
- **One event, one region.** A model trained on the August 2026 fires is
  unproven anywhere else. Add more areas with `build_dataset.py` before
  claiming it generalises.
- **Disk:** the example area is about 80 x 45 km; the patches take well
  under 1 GB.

## Files

| File | Purpose |
|---|---|
| `sardance/model.py` | ChangeUTAE network (about 480,000 parameters) |
| `sardance/labels.py` | Sentinel-2 composites and label rules |
| `sardance/data.py` | Patch dataset, input scaling, augmentation, IoU and F1 |
| `build_dataset.py` | Radar stack plus labels, cut into train / val / test patches |
| `train.py` | Training loop, writes `runs/<name>/best.pt` and `metrics.json` |
| `baselines.py` | Rules and gradient-boosted trees on the same test set |
| `evaluate.py` | Leak-free comparison of neural model, trees and rules |
| `export_onnx.py` | Exports to `models/change_utae.onnx` and checks it against PyTorch |
| `smoke_test.py` | Runs all of the above on synthetic data |
| `../saraura/change.py` | Rules detector and model inference (shared) |
| `../api/jobs.py` | On-demand Analysis jobs and tiles |
| `../api/assistant.py` | Claude explainer and tool-using agent |
