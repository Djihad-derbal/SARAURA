"""Wetland Model: map open water on each NISAR Pass over the Okavango Delta.

  python ml/wetland.py --site okavango_wetland

Labels (proxy): Sentinel-2 water index (MNDWI > 0) from clear scenes within 4 days of a Pass, on
three Passes spread through the flood season. Optical images cannot see water under vegetation, so
the labels (and this Model) cover open water only; flooded vegetation stays a physics layer.

Baseline: Otsu threshold on HH per Pass (calm open water is dark).
Model: LightGBM on the Pass's HH, HV, HV/HH, change since the previous Pass, and the pixel's season
mean and minimum.
Evaluation: spatial 5-fold cross-validation over 5 km blocks, all label dates pooled; also scored
per date.

Writes data/<site>/layers/pred_wetland_<date>.tif for every Pass (0 not water, 1 open water).
"""
import argparse
import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "ml"))

from pipeline import export, predictions  # noqa: E402
from predict import load_stack  # noqa: E402
from saraura import config  # noqa: E402

BLOCK_M = 5000
WINDOW_DAYS = 4
PARAMS = dict(n_estimators=300, learning_rate=0.05, num_leaves=31, min_child_samples=50, subsample=0.8, subsample_freq=1,
              colsample_bytree=0.8, verbose=-1, random_state=0)


def water_labels(grid: dict, bbox, date: str) -> np.ndarray:
    """1 water, 0 not, 255 unknown, from the clearest Sentinel-2 scenes within WINDOW_DAYS of `date`."""
    import rasterio
    from affine import Affine
    from pystac_client import Client
    from rasterio.enums import Resampling
    from rasterio.vrt import WarpedVRT
    from sardance.labels import BAD_SCL, COLLECTION, STAC

    d = dt.date.fromisoformat(date)
    span = f"{d - dt.timedelta(days=WINDOW_DAYS)}/{d + dt.timedelta(days=WINDOW_DAYS)}"
    items = list(Client.open(STAC).search(collections=[COLLECTION], bbox=list(bbox), datetime=span, query={"eo:cloud_cover": {"lt": 30}}).items())
    items.sort(key=lambda it: it.properties.get("eo:cloud_cover", 100))
    seen, chosen = set(), []
    for it in items:
        tile = it.properties.get("grid:code") or it.id[:9]
        if tile not in seen:  # clearest scene per tile
            seen.add(tile)
            chosen.append(it)
    h, w = grid["shape"]
    target = dict(crs=f"EPSG:{grid['epsg']}", transform=Affine(grid["res"], 0, grid["x0"], 0, -grid["res"], grid["y0"]), width=w, height=h)
    out = np.full((h, w), 255, np.uint8)

    def read(href, rs):
        with rasterio.open(href) as src, WarpedVRT(src, resampling=rs, **target) as vrt:
            return vrt.read(1)

    with rasterio.Env(AWS_NO_SIGN_REQUEST="YES", GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR"):
        for it in chosen:
            scl = read(it.assets["scl"].href, Resampling.nearest)
            g = read(it.assets["green"].href, Resampling.average).astype(np.float32)
            s = read(it.assets["swir16"].href, Resampling.average).astype(np.float32)
            ok = (g > 0) & (s > 0) & ~np.isin(scl, BAD_SCL) & (out == 255)
            with np.errstate(all="ignore"):
                mndwi = (g - s) / (g + s)  # offset-free ratio is close enough for a sign test
            out[ok] = (mndwi[ok] > 0).astype(np.uint8)
    print(f"  Sentinel-2 {span}: {len(chosen)} scenes, {100 * (out != 255).mean():.0f}% judged, {100 * (out == 1).sum() / max((out != 255).sum(), 1):.1f}% water")
    return out


def otsu(x: np.ndarray) -> float:
    x = x[np.isfinite(x)]
    hist, edges = np.histogram(x, 256)
    mids = (edges[:-1] + edges[1:]) / 2
    w0 = np.cumsum(hist)
    w1 = w0[-1] - w0
    m0 = np.cumsum(hist * mids) / np.maximum(w0, 1)
    m1 = (np.sum(hist * mids) - np.cumsum(hist * mids)) / np.maximum(w1, 1)
    return float(mids[np.argmax(w0 * w1 * (m0 - m1) ** 2)])


def pass_features(db: np.ndarray, t: int) -> np.ndarray:
    hh, hv = db[t, 0], db[t, 1]
    prev = db[max(t - 1, 0)]
    with np.errstate(all="ignore"):
        F = [hh, hv, hv - hh, hh - prev[0], hv - prev[1], np.nanmean(db[:, 0], 0), np.nanmin(db[:, 0], 0), np.nanmean(db[:, 1], 0), np.nanmin(db[:, 1], 0)]
    return np.stack(F, -1).reshape(-1, len(F)).astype(np.float32)


NAMES = ["hh_db", "hv_db", "hvhh_db", "dhh", "dhv", "hh_season_mean", "hh_season_min", "hv_season_mean", "hv_season_min"]


def scores(pred, y) -> dict:
    tp, fp, fn = int(((pred == 1) & (y == 1)).sum()), int(((pred == 1) & (y == 0)).sum()), int(((pred == 0) & (y == 1)).sum())
    return {"water_iou": round(tp / max(tp + fp + fn, 1), 4), "precision": round(tp / max(tp + fp, 1), 4), "recall": round(tp / max(tp + fn, 1), 4)}


def main():
    import lightgbm as lgb

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--site", default="okavango_wetland")
    ap.add_argument("--labels", nargs="*", default=None, help="Pass dates to label (default: 3 spread through the season)")
    ap.add_argument("--sample", type=int, default=100_000, help="pixels per label date")
    args = ap.parse_args()
    manifest = json.loads(config.data.read_text(f"{args.site}/manifest.json"))
    db, dates, grid = load_stack(args.site, manifest)
    H, W = grid["shape"]
    label_dates = args.labels or [dates[1], dates[len(dates) // 2], dates[-1]]
    print(f"{len(dates)} Passes {dates[0]} .. {dates[-1]}, grid {H} x {W} at {grid['res']:.0f} m; labels on {label_dates}")

    cache = ROOT / "ml" / "data" / f"water_labels_{args.site}.npz"
    have = dict(np.load(cache)) if cache.exists() else {}
    for d in label_dates:
        if d not in have:
            have[d] = water_labels(grid, manifest["bbox"], d)
            np.savez_compressed(cache, **have)

    rng = np.random.default_rng(0)
    bpx = int(BLOCK_M / grid["res"])
    rows_all, cols_all = np.divmod(np.arange(H * W), W)
    fold_all = ((rows_all // bpx) * 100003 + (cols_all // bpx)) * 2654435761 % 2**32 % 5
    X, y, fold, tdx, base = [], [], [], [], []
    for d in label_dates:
        t = dates.index(d)
        F = pass_features(db, t)
        lab = have[d].reshape(-1)
        ok = np.nonzero((lab != 255) & np.isfinite(F).all(1))[0]
        # Balance: keep all water pixels up to half the sample, fill the rest with land.
        wat, land = ok[lab[ok] == 1], ok[lab[ok] == 0]
        n_w = min(len(wat), args.sample // 2)
        pick = np.concatenate([rng.choice(wat, n_w, replace=False), rng.choice(land, min(len(land), args.sample - n_w), replace=False)])
        X.append(F[pick])
        y.append(lab[pick].astype(int))
        fold.append(fold_all[pick])
        tdx.append(np.full(len(pick), t))
        base.append((F[pick, 0] < otsu(db[t, 0])).astype(int))
    X, y, fold, tdx, base = (np.concatenate(a) for a in (X, y, fold, tdx, base))
    oof = np.zeros(len(y), int)
    for k in range(5):
        tr, te = fold != k, fold == k
        oof[te] = lgb.LGBMClassifier(**PARAMS).fit(X[tr], y[tr]).predict(X[te])
    res = {"label_dates": label_dates, "model": scores(oof, y), "baseline": scores(base, y), "per_date": {},
           "note": "Samples are balanced (up to half water), so IoU is higher than on the raw delta, where water is rarer"}
    for t in np.unique(tdx):
        m = tdx == t
        res["per_date"][dates[t]] = {"model": scores(oof[m], y[m]), "baseline": scores(base[m], y[m])}
    print(f"Model    water IoU {res['model']}\nBaseline water IoU {res['baseline']}")
    for d, r in res["per_date"].items():
        print(f"  {d}: Model {r['model']['water_iou']}, Baseline {r['baseline']['water_iou']}")

    final = lgb.LGBMClassifier(**PARAMS).fit(X, y)
    for key in list(config.data.list(f"{args.site}/layers")):
        if key.split("/")[-1].startswith("pred_wetland_"):
            config.data.delete(key)
    for t, d in enumerate(dates):
        F = pass_features(db, t)
        ok = np.isfinite(F).all(1)
        out = np.full(H * W, 255, np.uint8)
        out[ok] = final.predict(F[ok])
        export.write_cog(args.site, f"pred_wetland_{d}", out.reshape(H, W), grid, categorical=True)
    print(f"wrote pred_wetland for {len(dates)} Passes")

    run = ROOT / "ml" / "runs" / "wetland"
    run.mkdir(parents=True, exist_ok=True)
    (run / "scores.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    write_card(args.site, res)
    raise SystemExit(predictions.refresh(args.site))


def write_card(site_id: str, res: dict):
    card = {
        "lens": "wetland",
        "name": "wetland",
        "job": "Map open water on every NISAR Pass across the delta, through cloud and day or night",
        "user": "Wetland managers and water authorities tracking the yearly flood pulse",
        "sites": [site_id],
        "inputs": NAMES,
        "outputs": [{"value": 0, "label": "Dry land", "reliable": True}, {"value": 1, "label": "Open water", "reliable": True}],
        "labels": {"kind": "proxy", "source": f"Sentinel-2 water index (MNDWI > 0) within {WINDOW_DAYS} days of the Passes {', '.join(res['label_dates'])}",
                   "notes": "Optical labels miss water under vegetation and count it as dry land"},
        "baseline": {"name": "Otsu threshold on HH, per Pass", "metric": "open-water IoU", "score": res["baseline"]["water_iou"]},
        "model": {"name": "LightGBM on per-Pass backscatter and season statistics", "metric": "open-water IoU", "score": res["model"]["water_iou"], "framework": "LightGBM"},
        "extra_scores": [{"name": f"{who} on {d}", "metric": "open-water IoU", "score": r[key]["water_iou"]} for d, r in res["per_date"].items() for who, key in (("Model", "model"), ("Baseline", "baseline"))],
        "split": "Spatial 5-fold cross-validation over 5 km blocks, label dates pooled; water and land sampled about equally",
        "limits": [
            "Open water only: water under reeds and papyrus (flooded vegetation) is not learned, because optical labels cannot see it",
            "Wind-roughened water is bright and can be missed",
            "Scores use balanced samples; on the whole delta, where water is rarer, IoU is lower",
        ],
        "status": "prototype",
        "updated": dt.date.today().isoformat(),
    }
    (config.MODEL_CARDS_DIR / "wetland.json").write_text(json.dumps(card, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
