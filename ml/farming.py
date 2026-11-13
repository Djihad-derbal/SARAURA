"""Farming Model: tell maize, soybean and other land apart from the NISAR season time series.

  python ml/farming.py --site midwest_farming

Labels (proxy): the USDA Cropland Data Layer for 2026 is not published yet (the NASS service accepts
1997 to 2025). Iowa farms mostly rotate maize and soybean, so last year's map is wrong for most
fields. The 2026 label comes from a rotation rule on 2024 and 2025: a field that switched crops
switches back; a field with the same crop both years keeps it; land that was neither crop in both
years is "Other"; anything else is left out. The rule's own accuracy is measured by applying it to
2023 + 2024 and comparing with the real 2025 map. Files: ml/data/cdl/<year>/CDL_<year>_19.tif from
https://nassgeodata.gmu.edu/nass_data_cache/byfips/CDL_<year>_19.zip (Iowa).

Model: LightGBM on each pixel's HH, HV and HV/HH for every Pass, plus season mean, spread and CV.
Baseline: the coefficient-of-variation rule (HV varies most over cropland); it cannot tell crops
apart, so every crop pixel is called the more common crop.
Evaluation: spatial 5-fold cross-validation over 2 km blocks; also with Passes up to 31 August only
("before harvest").

Writes data/<site>/layers/pred_farming_<last Pass>.tif (0 other, 1 maize, 2 soybean).
"""
import argparse
import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin
from rasterio.warp import Resampling, reproject

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "ml"))

from pipeline import export, predictions  # noqa: E402
from predict import load_stack  # noqa: E402
from saraura import config  # noqa: E402

CDL = ROOT / "ml" / "data" / "cdl"
CORN, SOY = 1, 5
NAMES = ["Other", "Maize", "Soybean"]
BLOCK_M = 2000
PARAMS = dict(n_estimators=300, learning_rate=0.05, num_leaves=31, min_child_samples=50, subsample=0.8, subsample_freq=1,
              colsample_bytree=0.8, verbose=-1, random_state=0)
HARVEST_CUTOFF = "2026-08-31"


def cdl_on_grid(year: int, grid: dict) -> np.ndarray:
    out = np.zeros(grid["shape"], np.uint8)
    with rasterio.open(CDL / str(year) / f"CDL_{year}_19.tif") as ds:
        reproject(rasterio.band(ds, 1), out, dst_transform=from_origin(grid["x0"], grid["y0"], grid["res"], grid["res"]),
                  dst_crs=f"EPSG:{grid['epsg']}", resampling=Resampling.mode)
    return out


def crop(c: np.ndarray) -> np.ndarray:
    """CDL code -> 0 other, 1 maize, 2 soybean."""
    return np.where(c == CORN, 1, np.where(c == SOY, 2, 0)).astype(np.int8)


def rotation_rule(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Next year's class from the two previous years; -1 where the rule makes no call."""
    out = np.full(a.shape, -1, np.int8)
    both_crops = (a > 0) & (b > 0)
    out[both_crops & (a != b)] = a[both_crops & (a != b)]  # alternating: back to the crop of two years ago
    out[both_crops & (a == b)] = a[both_crops & (a == b)]  # same crop twice: keep it
    out[(a == 0) & (b == 0)] = 0
    return out


def pixel_features(db: np.ndarray, use: list[int]) -> tuple[np.ndarray, list[str]]:
    """db (T, 2, H, W) -> (H*W, F)."""
    x = db[use]
    hh, hv = x[:, 0], x[:, 1]
    lin = 10 ** (hv / 10)
    with np.errstate(all="ignore"):
        F = [hh, hv, hv - hh, np.nanmean(hv, 0)[None], np.nanstd(hv, 0)[None], (np.nanstd(lin, 0) / np.nanmean(lin, 0))[None],
             np.nanmax(hv, 0)[None] - np.nanmin(hv, 0)[None], np.nanargmax(hv, 0)[None].astype(np.float32)]
    names = [f"hh_{i}" for i in use] + [f"hv_{i}" for i in use] + [f"hvhh_{i}" for i in use] + ["hv_mean", "hv_std", "hv_cv", "hv_range", "hv_peak_pass"]
    return np.concatenate(F, 0).reshape(len(names), -1).T.astype(np.float32), names


def macro_f1(pred, y, k=3) -> dict:
    f1 = []
    for c in range(k):
        tp, fp, fn = ((pred == c) & (y == c)).sum(), ((pred == c) & (y != c)).sum(), ((pred != c) & (y == c)).sum()
        f1.append(2 * tp / max(2 * tp + fp + fn, 1))
    return {"macro_f1": round(float(np.mean(f1)), 4), "accuracy": round(float((pred == y).mean()), 4),
            "f1_per_class": {NAMES[c]: round(float(f1[c]), 4) for c in range(k)}}


def main():
    import lightgbm as lgb

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--site", default="midwest_farming")
    ap.add_argument("--sample", type=int, default=300_000)
    ap.add_argument("--folds", type=int, default=5)
    args = ap.parse_args()
    manifest = json.loads(config.data.read_text(f"{args.site}/manifest.json"))
    db, dates, grid = load_stack(args.site, manifest)
    H, W = grid["shape"]
    print(f"{len(dates)} Passes {dates[0]} .. {dates[-1]}, grid {H} x {W} at {grid['res']:.0f} m")

    c23, c24, c25 = (crop(cdl_on_grid(y, grid)) for y in (2023, 2024, 2025))
    check = rotation_rule(c23, c24)
    m = check >= 0
    rule_acc = float((check[m] == c25[m]).mean())
    rule_cov = float(m.mean())
    print(f"rotation rule checked on 2025 (from 2023 + 2024): {100 * rule_acc:.1f}% right where it makes a call ({100 * rule_cov:.0f}% of pixels)")
    y_all = rotation_rule(c24, c25).reshape(-1)

    valid = np.isfinite(db).all((0, 1)).reshape(-1)
    lab = np.nonzero(valid & (y_all >= 0))[0]
    rng = np.random.default_rng(0)
    pick = np.sort(rng.choice(lab, min(len(lab), args.sample), replace=False))
    y = y_all[pick].astype(int)
    rows, cols = pick // W, pick % W
    bpx = int(BLOCK_M / grid["res"])
    block = (rows // bpx) * 100003 + (cols // bpx)
    fold = (block * 2654435761 % 2**32) % args.folds
    counts = {NAMES[c]: int((y == c).sum()) for c in range(3)}
    print(f"{len(y):,} labelled pixels sampled: {counts}")

    res = {"rotation_rule_accuracy_2025": round(rule_acc, 4), "rotation_rule_coverage": round(rule_cov, 4), "pixels": counts}
    before = [i for i, d in enumerate(dates) if d <= HARVEST_CUTOFF]
    for tag, use in (("full_season", list(range(len(dates)))), ("before_harvest", before)):
        F, names = pixel_features(db, use)
        X = F[pick]
        oof = np.zeros(len(y), int)
        for k in range(args.folds):
            tr, te = fold != k, fold == k
            oof[te] = lgb.LGBMClassifier(**PARAMS).fit(X[tr], y[tr]).predict(X[te])
        res[tag] = {"model": macro_f1(oof, y), "passes": [dates[i] for i in use]}
        if tag == "full_season":
            cv = X[:, names.index("hv_cv")]
            base = np.zeros(len(y), int)
            for k in range(args.folds):
                tr, te = fold != k, fold == k
                crop_tr = y[tr] > 0
                ts = np.quantile(cv[tr], np.linspace(0.05, 0.95, 91))
                t = ts[np.argmax([((cv[tr] > t) == crop_tr).mean() for t in ts])]
                major = 1 if (y[tr] == 1).sum() >= (y[tr] == 2).sum() else 2
                base[te] = np.where(cv[te] > t, major, 0)
            res["baseline"] = macro_f1(base, y)
            full_F, full_names = F, names
        print(f"{tag:15s} Model macro F1 {res[tag]['model']['macro_f1']}  accuracy {res[tag]['model']['accuracy']}  {res[tag]['model']['f1_per_class']}")
    print(f"{'baseline':15s} macro F1 {res['baseline']['macro_f1']}  accuracy {res['baseline']['accuracy']}  {res['baseline']['f1_per_class']}")

    final = lgb.LGBMClassifier(**PARAMS).fit(full_F[pick], y)
    res["feature_importance"] = sorted(zip(full_names, final.feature_importances_.tolist()), key=lambda t: -t[1])[:15]
    out = np.full(H * W, 255, np.uint8)
    idx = np.nonzero(valid)[0]
    for s in range(0, len(idx), 500_000):
        out[idx[s:s + 500_000]] = final.predict(full_F[idx[s:s + 500_000]])
    for key in list(config.data.list(f"{args.site}/layers")):
        if key.split("/")[-1].startswith("pred_farming_"):
            config.data.delete(key)
    export.write_cog(args.site, f"pred_farming_{dates[-1]}", out.reshape(H, W), grid, categorical=True)
    share = {NAMES[c]: round(float((out[idx] == c).mean()), 3) for c in range(3)}
    print(f"wrote pred_farming_{dates[-1]}: {share}")

    run = ROOT / "ml" / "runs" / "farming"
    run.mkdir(parents=True, exist_ok=True)
    (run / "scores.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    write_card(args.site, res)
    raise SystemExit(predictions.refresh(args.site))


def write_card(site_id: str, res: dict):
    fs, bh = res["full_season"]["model"], res["before_harvest"]["model"]
    card = {
        "lens": "farming",
        "name": "farming",
        "job": "Map maize, soybean and other land from the NISAR season, before the official crop map is out",
        "user": "Crop analysts and agricultural agencies who need the crop map months before USDA publishes it",
        "sites": [site_id],
        "inputs": ["hh_db, hv_db, HV/HH for every Pass", "hv_mean", "hv_std", "hv_cv", "hv_range", "hv_peak_pass"],
        "outputs": [{"value": 0, "label": "Other", "reliable": True}, {"value": 1, "label": "Maize", "reliable": True}, {"value": 2, "label": "Soybean", "reliable": True}],
        "labels": {"kind": "proxy", "source": "USDA Cropland Data Layer 2024 + 2025 (Iowa) with a maize/soybean rotation rule, because CDL 2026 is not published yet",
                   "notes": f"The rule was {100 * res['rotation_rule_accuracy_2025']:.0f}% right when tested on 2025 from 2023 + 2024, so about 1 label in {max(2, round(1 / max(1e-6, 1 - res['rotation_rule_accuracy_2025'])))} is wrong; scores are capped by that"},
        "baseline": {"name": "HV coefficient-of-variation rule (crop vs other; crops called the more common crop)", "metric": "macro F1", "score": res["baseline"]["macro_f1"]},
        "model": {"name": "LightGBM on the per-pixel Pass series", "metric": "macro F1", "score": fs["macro_f1"], "framework": "LightGBM"},
        "extra_scores": [
            {"name": f"Model, Passes up to {HARVEST_CUTOFF} only (before harvest)", "metric": "macro F1", "score": bh["macro_f1"]},
            {"name": "Model accuracy", "metric": "accuracy", "score": fs["accuracy"]},
            {"name": "Baseline accuracy", "metric": "accuracy", "score": res["baseline"]["accuracy"]},
        ] + [{"name": f"Model F1, {k}", "metric": "F1", "score": v} for k, v in fs["f1_per_class"].items()],
        "split": "Spatial 5-fold cross-validation over 2 km blocks; scores are out-of-fold",
        "limits": [
            "Labels are a rotation-rule guess, not the 2026 crop map; rerun when USDA publishes CDL 2026 (usually early in the following year)",
            "Fields that broke the rotation in 2026 are labelled wrongly",
            "One county-sized area of central Iowa; other regions grow different crop mixes",
            "Per-pixel at 20 m, so field edges are noisy",
        ],
        "status": "prototype",
        "updated": dt.date.today().isoformat(),
    }
    (config.MODEL_CARDS_DIR / "farming.json").write_text(json.dumps(card, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
