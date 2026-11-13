"""Volcano Model: map lava emplaced during the NISAR window at Krasheninnikov, Kamchatka.

  python ml/volcano.py --site kamchatka_volcano

Labels (proxy): Sentinel-2 hot spots. A pixel is "new lava" if it was hot on any clear scene in the
NISAR window, by the Normalized Hotspot Index NHI_SWIR = (B12 - B11) / (B12 + B11) > 0 (Marchese
et al. 2019) with B12 itself bright, within 10 km of the vent, on at least 3 scenes (lava stays hot
for weeks in one place; cloud artefacts do not). (The second index, NHI_SWNIR, was
dropped: on surface reflectance it fired on 71% of the window, on dark rock and October snow.) Hot spots trace active flows and channels, so the labels mark where lava moved,
not every cooled lobe. Lava has flowed since August 2025, so a before/after image comparison
would miss new lava laid on older lava; heat does not.

Window: a 30 km box around the volcano (54.59 N, 160.27 E), inside the site.
Baseline: backscatter change (largest HH change between consecutive Passes); scored at 3 dB and at
its best threshold.
Model: LightGBM on per-pixel radar change statistics (largest and summed HH/HV changes, coherence
minimum and mean, season backscatter, slope).
Evaluation: spatial 5-fold cross-validation over 1.5 km blocks. Lava is rare (about 0.3% of the
window), so the main score is average precision; IoU is reported for both methods at each one's best
threshold, which the final map also uses.

Writes data/<site>/layers/pred_volcano_<last Pass>.tif (0 no new lava, 1 new lava).
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

VENT = (160.27, 54.59)
HALF_M = 15000
BLOCK_M = 1500
NEAR_M = 10000  # hot spots further than this from the vent are not lava
MIN_HOT_SCENES = 3  # real lava stays hot for weeks; cloud artefacts move between scenes
HOT_B12 = 3000  # raw Sentinel-2 L2A digital number (reflectance about 0.2 to 0.3)
CHANGE_DB = 3.0
PARAMS = dict(n_estimators=300, learning_rate=0.05, num_leaves=15, min_child_samples=30, subsample=0.8, subsample_freq=1,
              colsample_bytree=0.8, verbose=-1, random_state=0)


def window(grid: dict):
    from pyproj import Transformer

    x, y = Transformer.from_crs(4326, grid["epsg"], always_xy=True).transform(*VENT)
    c, r = int((x - grid["x0"]) / grid["res"]), int((grid["y0"] - y) / grid["res"])
    n = int(HALF_M / grid["res"])
    H, W = grid["shape"]
    return slice(max(r - n, 0), min(r + n, H)), slice(max(c - n, 0), min(c + n, W))


def hot_labels(grid: dict, bbox, start: str, end: str, max_cloud: int = 70) -> tuple[np.ndarray, dict]:
    """1 hot at least once, 0 clear at least twice and never hot, 255 unknown."""
    from affine import Affine
    from pystac_client import Client
    from rasterio.enums import Resampling as R
    from rasterio.vrt import WarpedVRT
    from sardance.labels import BAD_SCL, COLLECTION, STAC

    items = list(Client.open(STAC).search(collections=[COLLECTION], bbox=list(bbox), datetime=f"{start}/{end}", query={"eo:cloud_cover": {"lt": max_cloud}}).items())
    h, w = grid["shape"]
    target = dict(crs=f"EPSG:{grid['epsg']}", transform=Affine(grid["res"], 0, grid["x0"], 0, -grid["res"], grid["y0"]), width=w, height=h)
    hot = np.zeros((h, w), np.int16)
    rr, cc = np.mgrid[0:h, 0:w]
    near = np.hypot(rr - h / 2, cc - w / 2) * grid["res"] <= NEAR_M
    clear = np.zeros((h, w), np.int16)
    used = []

    def read(href, rs):
        with rasterio.open(href) as src, WarpedVRT(src, resampling=rs, **target) as vrt:
            return vrt.read(1)

    with rasterio.Env(AWS_NO_SIGN_REQUEST="YES", GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR"):
        for it in sorted(items, key=lambda i: i.datetime):
            scl = read(it.assets["scl"].href, R.nearest)
            ok = ~np.isin(scl, BAD_SCL) & (scl > 0)
            if ok.mean() < 0.2:
                continue
            b8a, b11, b12 = (read(it.assets[b].href, R.max).astype(np.float32) for b in ("nir08", "swir16", "swir22"))
            with np.errstate(all="ignore"):
                nhi_swir = (b12 - b11) / (b12 + b11)
                nhi_swnir = (b11 - b8a) / (b11 + b8a)
            # Hot pixels saturate SWIR and can be flagged as "saturated" or cloud by the classifier: trust heat over SCL.
            # On surface reflectance NHI_SWNIR alone also fires on dark rock and snow, so heat must show in
            # SWIR-2 itself: brighter than SWIR-1 and above HOT_B12 (raw L2A digital number).
            is_hot = (nhi_swir > 0) & (b12 > HOT_B12) & near
            del nhi_swnir
            hot += is_hot.astype(np.int16)
            clear += (ok | is_hot).astype(np.int16)
            used.append({"date": it.datetime.date().isoformat(), "hot_pixels": int(is_hot.sum()), "clear_share": round(float(ok.mean()), 2)})
    y = np.full((h, w), 255, np.uint8)
    y[clear >= 2] = 0
    y[hot >= MIN_HOT_SCENES] = 1
    # Pixels hot once or twice are ambiguous (cloud edges, sun glint): leave them out rather than call them lava or not.
    y[(hot > 0) & (hot < MIN_HOT_SCENES)] = 255
    np.save(Path(__file__).resolve().parents[1] / "ml" / "data" / "lava_hot_count.npy", hot)
    print(f"  Sentinel-2 {start}..{end}: {len(used)} usable scenes, {int((hot >= MIN_HOT_SCENES).sum())} pixels hot on {MIN_HOT_SCENES}+ scenes")
    return y, {"scenes": used, "min_hot_scenes": MIN_HOT_SCENES}


def stats(db: np.ndarray, coh: np.ndarray | None) -> tuple[np.ndarray, list[str]]:
    hh, hv = db[:, 0], db[:, 1]
    with np.errstate(all="ignore"):
        dhh, dhv = np.diff(hh, axis=0), np.diff(hv, axis=0)
        F = {"dhh_absmax": np.nanmax(np.abs(dhh), 0), "dhv_absmax": np.nanmax(np.abs(dhv), 0), "dhh_abssum": np.nansum(np.abs(dhh), 0),
             "dhv_abssum": np.nansum(np.abs(dhv), 0), "hh_last_minus_first": hh[-1] - hh[0], "hv_last_minus_first": hv[-1] - hv[0],
             "hh_mean": np.nanmean(hh, 0), "hv_mean": np.nanmean(hv, 0), "hh_std": np.nanstd(hh, 0)}
        if coh is not None:
            F["coherence_min"], F["coherence_mean"] = np.nanmin(coh, 0), np.nanmean(coh, 0)
    return np.stack(list(F.values()), -1), list(F)


def on_grid(src_key: str, grid: dict, how=Resampling.average) -> np.ndarray:
    out = np.full(grid["shape"], np.nan, np.float32)
    with rasterio.open(config.data.local_path(src_key)) as ds:
        reproject(ds.read(1).astype(np.float32), out, src_transform=ds.transform, src_crs=ds.crs, src_nodata=np.nan,
                  dst_transform=from_origin(grid["x0"], grid["y0"], grid["res"], grid["res"]), dst_crs=f"EPSG:{grid['epsg']}", dst_nodata=np.nan, resampling=how)
    return out


def scores(pred, y) -> dict:
    tp, fp, fn = int(((pred == 1) & (y == 1)).sum()), int(((pred == 1) & (y == 0)).sum()), int(((pred == 0) & (y == 1)).sum())
    return {"lava_iou": round(tp / max(tp + fp + fn, 1), 4), "precision": round(tp / max(tp + fp, 1), 4), "recall": round(tp / max(tp + fn, 1), 4)}


def average_precision(score, y) -> float:
    o = np.argsort(-score, kind="stable")
    t = y[o]
    prec = np.cumsum(t) / np.arange(1, len(t) + 1)
    return round(float((prec * t).sum() / max(t.sum(), 1)), 4)


def best_iou(score, y) -> dict:
    """IoU at the best threshold (chosen on the scored cells: favours whichever method it is applied to)."""
    best = {"lava_iou": 0.0}
    for th in np.unique(np.quantile(score, 1 - np.geomspace(0.0005, 0.2, 120))):
        r = scores((score >= th).astype(int), y)
        if r["lava_iou"] > best["lava_iou"]:
            best = {**r, "threshold": round(float(th), 4)}
    return best


def main():
    import lightgbm as lgb

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--site", default="kamchatka_volcano")
    args = ap.parse_args()
    manifest = json.loads(config.data.read_text(f"{args.site}/manifest.json"))
    db, dates, grid = load_stack(args.site, manifest)
    rs, cs = window(grid)
    db = db[:, :, rs, cs]
    wgrid = {**grid, "x0": grid["x0"] + cs.start * grid["res"], "y0": grid["y0"] - rs.start * grid["res"], "shape": [rs.stop - rs.start, cs.stop - cs.start]}
    coh_dates = next(l["dates"] for l in manifest["layers"] if l["id"] == "coherence")
    coh = np.stack([on_grid(f"{args.site}/layers/coherence_{d}.tif", wgrid) for d in coh_dates])
    slope = on_grid(f"{args.site}/layers/slope_{next(l['dates'][0] for l in manifest['layers'] if l['id'] == 'slope')}.tif", wgrid)
    F, names = stats(db, coh)
    F = np.concatenate([F, slope[..., None]], -1)
    names.append("slope")
    H, W = wgrid["shape"]
    print(f"{len(dates)} Passes {dates[0]} .. {dates[-1]}; window {H} x {W} at {grid['res']:.0f} m around the vent")

    cache = ROOT / "ml" / "data" / f"lava_labels_{args.site}.npz"
    if cache.exists():
        z = np.load(cache, allow_pickle=True)
        y_img, info = z["y"], json.loads(str(z["info"]))
    else:
        from pyproj import Transformer

        t = Transformer.from_crs(wgrid["epsg"], 4326, always_xy=True)
        lon0, lat0 = t.transform(wgrid["x0"], wgrid["y0"] - H * grid["res"])
        lon1, lat1 = t.transform(wgrid["x0"] + W * grid["res"], wgrid["y0"])
        y_img, info = hot_labels(wgrid, [lon0, lat0, lon1, lat1], dates[0], dates[-1])
        np.savez_compressed(cache, y=y_img, info=json.dumps(info))

    Xf = F.reshape(-1, F.shape[-1])
    yf = y_img.reshape(-1)
    ok = (yf != 255) & np.isfinite(Xf).all(1)
    idx = np.nonzero(ok)[0]
    X, y = Xf[idx], yf[idx].astype(int)
    rows, cols = np.divmod(idx, W)
    bpx = int(BLOCK_M / grid["res"])
    fold = ((rows // bpx) * 100003 + (cols // bpx)) * 2654435761 % 2**32 % 5
    print(f"{len(y):,} labelled pixels, {int(y.sum())} new lava ({100 * y.mean():.2f}%)")
    oof = np.zeros(len(y))
    for k in range(5):
        tr, te = fold != k, fold == k
        if y[tr].sum():
            oof[te] = lgb.LGBMClassifier(**PARAMS).fit(X[tr], y[tr]).predict_proba(X[te])[:, 1]
    base_score = X[:, names.index("dhh_absmax")]
    m_best, b_best = best_iou(oof, y), best_iou(base_score, y)
    base_fixed = scores((base_score > CHANGE_DB).astype(int), y)
    res = {"model": {"average_precision": average_precision(oof, y), **m_best}, "baseline": {"average_precision": average_precision(base_score, y), **b_best},
           "baseline_at_3db": base_fixed, "pixels": int(len(y)), "lava_pixels": int(y.sum()), "prevalence": round(float(y.mean()), 5), **info}
    print(f"Model    {res['model']}")
    print(f"Baseline {res['baseline']}  (at {CHANGE_DB:g} dB: {base_fixed})")
    print(f"chance AP {res['prevalence']}")

    final = lgb.LGBMClassifier(**PARAMS).fit(X, y)
    res["feature_importance"] = sorted(zip(names, final.feature_importances_.tolist()), key=lambda t: -t[1])
    out = np.full(H * W, 255, np.uint8)
    v = np.isfinite(Xf).all(1)
    out[v] = (final.predict_proba(Xf[v])[:, 1] >= m_best["threshold"]).astype(np.uint8)
    rr, cc = np.divmod(np.arange(H * W), W)
    out[(np.hypot(rr - H / 2, cc - W / 2) * grid["res"] > NEAR_M) & (out != 255)] = 0  # lava only near the vent
    for key in list(config.data.list(f"{args.site}/layers")):
        if key.split("/")[-1].startswith("pred_volcano_"):
            config.data.delete(key)
    export.write_cog(args.site, f"pred_volcano_{dates[-1]}", out.reshape(H, W), wgrid, categorical=True)
    print(f"wrote pred_volcano_{dates[-1]}: {int((out == 1).sum())} pixels of new lava ({(out == 1).sum() * grid['res'] ** 2 / 1e6:.1f} km2)")

    run = ROOT / "ml" / "runs" / "volcano"
    run.mkdir(parents=True, exist_ok=True)
    (run / "scores.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    write_card(args.site, res, names, dates)
    raise SystemExit(predictions.refresh(args.site))


def write_card(site_id: str, res: dict, names: list[str], dates: list[str]):
    card = {
        "lens": "volcano",
        "name": "volcano",
        "job": "Map where new lava went during the NISAR window, through cloud and the long Kamchatka nights",
        "user": "Volcano observatories (KVERT) and aviation and hazard teams",
        "sites": [site_id],
        "inputs": names,
        "outputs": [{"value": 0, "label": "No new lava", "reliable": True}, {"value": 1, "label": "New lava", "reliable": True}],
        "labels": {"kind": "proxy", "source": f"Sentinel-2 hot spots (NHI_SWIR > 0 with bright B12, within 10 km of the vent, hot on 3+ scenes; Marchese et al. 2019) on {len(res['scenes'])} scenes, {dates[0]} to {dates[-1]}",
                   "notes": "Hot spots mark active flows and channels; cooled lobes that were never seen hot through cloud are labelled 'no new lava'"},
        "baseline": {"name": "Largest HH change between Passes", "metric": "average precision", "score": res["baseline"]["average_precision"]},
        "model": {"name": "LightGBM on per-pixel radar change statistics", "metric": "average precision", "score": res["model"]["average_precision"], "framework": "LightGBM"},
        "extra_scores": [
            {"name": "Model, best threshold", "metric": "lava IoU", "score": res["model"]["lava_iou"]},
            {"name": "Baseline, best threshold", "metric": "lava IoU", "score": res["baseline"]["lava_iou"]},
            {"name": f"Baseline at {CHANGE_DB:g} dB", "metric": "lava IoU", "score": res["baseline_at_3db"]["lava_iou"]},
            {"name": "Chance (share of lava pixels)", "metric": "average precision", "score": res["prevalence"]},
            {"name": "Model precision", "metric": "precision", "score": res["model"]["precision"]},
            {"name": "Model recall", "metric": "recall", "score": res["model"]["recall"]},
            {"name": "Baseline precision", "metric": "precision", "score": res["baseline"]["precision"]},
            {"name": "Baseline recall", "metric": "recall", "score": res["baseline"]["recall"]},
        ],
        "split": "Spatial 5-fold cross-validation over 1.5 km blocks in a 30 km window around the vent",
        "limits": [
            "One volcano and one lava field; few independent blocks contain lava, so scores are noisy",
            "Labels mark heat, not the full outline of cooled lava",
            "Snow from October changes backscatter and coherence and can look like change",
            "Ionosphere residuals are larger at this latitude (ASF known issues)",
        ],
        "status": "prototype",
        "updated": dt.date.today().isoformat(),
    }
    (config.MODEL_CARDS_DIR / "volcano.json").write_text(json.dumps(card, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
