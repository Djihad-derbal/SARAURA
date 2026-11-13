"""Subsidence forecast Model: predict each pixel's cumulative displacement 1 to 3 Passes ahead.

  python ml/subsidence.py --site mexico_city_subsidence

Self-supervised: the GUNW time series is its own label. The last 3 Passes are held out; the Model
and the Baseline forecast them from the Passes before (origin = the 4th-last Pass).

Baseline: straight-line extrapolation of the pixel's whole history (least squares).
Model: a small, heavily regularised LightGBM that corrects the straight line, from other trend
estimates and how far the last Passes sit off the line. Training uses earlier origins whose targets
all fall before the held-out Passes. A validation origin (the 3 Passes before the test) is scored too.

Result on Mexico City (2026-11-13): the Model does NOT beat the straight line. With under a year of
data and about 1 cm of atmospheric noise per interferogram, a line is the best 12 to 36 day forecast.

The final Model (trained on every origin) forecasts one Pass (12 days) past the last date and
writes data/<site>/layers/pred_subsidence_<date>.tif (cm, same sign as cum_disp_cm).
"""
import argparse
import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np
import rasterio

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import export, predictions  # noqa: E402
from saraura import config  # noqa: E402

HOLDOUT = 3
MIN_HISTORY = 12
PARAMS = dict(n_estimators=100, learning_rate=0.05, num_leaves=7, min_child_samples=2000, verbose=-1, random_state=0)


def load(site: str, manifest: dict, layer_id: str):
    dates = next(l["dates"] for l in manifest["layers"] if l["id"] == layer_id)
    arrs, grid = [], None
    for d in dates:
        with rasterio.open(config.data.local_path(f"{site}/layers/{layer_id}_{d}.tif")) as ds:
            arrs.append(ds.read(1).astype(np.float32))
            if grid is None:
                tr = ds.transform
                grid = {"x0": tr.c, "y0": tr.f, "res": tr.a, "epsg": ds.crs.to_epsg(), "shape": [ds.height, ds.width]}
    return np.stack(arrs), dates, grid


def line(days: np.ndarray, Y: np.ndarray):
    """Least-squares slope and intercept per pixel. days (t,), Y (t, N) -> (N,), (N,)."""
    d = days - days.mean()
    slope = (d[:, None] * (Y - Y.mean(0))).sum(0) / (d**2).sum()
    return slope, Y.mean(0) - slope * days.mean()


def smooth(v: np.ndarray, valid: np.ndarray, shape, k: int) -> np.ndarray:
    a = np.zeros(shape, np.float32)
    a.reshape(-1)[valid] = v
    w = np.zeros(shape, np.float32)
    w.reshape(-1)[valid] = 1
    return (uniform_filter(a, k) / np.maximum(uniform_filter(w, k), 1e-6)).reshape(-1)[valid]


def features(Y: np.ndarray, days: np.ndarray, t0: int, horizon_days: float, coh: np.ndarray):
    """Features for a forecast `horizon_days` past day[t0], from the history Y[:t0+1] (t, N) only.

    Returns (features, straight-line forecast). The Model predicts the departure from that line,
    from other trend estimates (last 6, 9, 12 Passes), how far the last Passes sit off the line,
    the horizon and coherence. All pixels of one origin share that day's atmosphere, so there are
    only ~40 independent training examples: the Model is kept small and heavily regularised.
    """
    tgt = days[t0] + horizon_days
    s, b = line(days[: t0 + 1], Y[: t0 + 1])
    base = s * tgt + b
    F = []
    for w in (6, 9, 12):
        w = min(w, t0 + 1)
        s2, b2 = line(days[t0 + 1 - w: t0 + 1], Y[t0 + 1 - w: t0 + 1])
        F.append(s2 * tgt + b2 - base)
    F.append(Y[t0 - 2: t0 + 1].mean(0) - (s * days[t0 - 2: t0 + 1].mean() + b))
    F.append(Y[t0] - (s * days[t0] + b))
    F.append(np.full(len(s), horizon_days, np.float32))
    F.append(coh)
    return np.stack(F, 1), base


NAMES = ["trend_last6_minus_line", "trend_last9_minus_line", "trend_last12_minus_line", "last3_off_line", "last_off_line", "horizon_days", "coherence_mean"]


def rmse(a, b):
    return float(np.sqrt(np.mean((a - b) ** 2)))


def main():
    import lightgbm as lgb

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--site", default="mexico_city_subsidence")
    ap.add_argument("--max-rows", type=int, default=600_000)
    args = ap.parse_args()
    manifest = json.loads(config.data.read_text(f"{args.site}/manifest.json"))
    cube, dates, grid = load(args.site, manifest, "cum_disp_cm")
    coh_cube, _, _ = load(args.site, manifest, "coherence")
    T = len(dates)
    shape = tuple(grid["shape"])
    valid = np.isfinite(cube).all(0).reshape(-1)
    Y = cube.reshape(T, -1)[:, valid]
    coh = np.nanmean(coh_cube.reshape(len(coh_cube), -1)[:, valid], 0)
    days = np.array([(dt.date.fromisoformat(d) - dt.date.fromisoformat(dates[0])).days for d in dates], np.float32)
    print(f"{T} Passes {dates[0]} .. {dates[-1]}, {valid.sum():,} pixels with a full series")

    rng = np.random.default_rng(0)

    def training_rows(last: int):
        """Rows from every origin whose targets fall at or before index `last`."""
        Xs, ys = [], []
        for t0 in range(MIN_HISTORY - 1, last):
            for h in range(1, HOLDOUT + 1):
                if t0 + h > last:
                    break
                F, base = features(Y, days, t0, days[t0 + h] - days[t0], coh)
                Xs.append(F)
                ys.append(Y[t0 + h] - base)
        X, y = np.concatenate(Xs), np.concatenate(ys)
        pick = rng.choice(len(y), min(len(y), args.max_rows), replace=False)
        return X[pick], y[pick]

    def evaluate(origin: int) -> dict:
        """Train on targets up to `origin`, forecast the next HOLDOUT Passes."""
        X, y = training_rows(origin)
        model = lgb.LGBMRegressor(**PARAMS).fit(X, y)
        s_all, _ = line(days[: origin + 1], Y[: origin + 1])
        fast = s_all * 30.4 <= np.percentile(s_all * 30.4, 10)  # fastest-moving 10% away from the satellite
        out = {"origin": dates[origin], "per_horizon": []}
        em, eb = [], []
        for h in range(1, HOLDOUT + 1):
            F, base = features(Y, days, origin, days[origin + h] - days[origin], coh)
            truth, pm = Y[origin + h], base + model.predict(F)
            out["per_horizon"].append({"date": dates[origin + h], "model_rmse_cm": round(rmse(pm, truth), 3), "baseline_rmse_cm": round(rmse(base, truth), 3),
                                       "model_rmse_fast_cm": round(rmse(pm[fast], truth[fast]), 3), "baseline_rmse_fast_cm": round(rmse(base[fast], truth[fast]), 3),
                                       "persistence_rmse_cm": round(rmse(Y[origin], truth), 3)})
            em.append(pm - truth)
            eb.append(base - truth)
        out["model_rmse_cm"] = round(rmse(np.concatenate(em), 0), 3)
        out["baseline_rmse_cm"] = round(rmse(np.concatenate(eb), 0), 3)
        return out

    val = evaluate(T - 1 - 2 * HOLDOUT)  # validation: the 3 Passes before the test Passes
    res = evaluate(T - 1 - HOLDOUT)
    res.update(pixels=int(valid.sum()), held_out=dates[T - HOLDOUT:], validation=val)
    for name, r in (("validation", val), ("test", res)):
        print(f"{name}: Model RMSE {r['model_rmse_cm']} cm, Baseline {r['baseline_rmse_cm']} cm  (origin {r['origin']})")
    for row in res["per_horizon"]:
        print(f"  {row['date']}: Model {row['model_rmse_cm']}, Baseline {row['baseline_rmse_cm']}, no change {row['persistence_rmse_cm']}"
              f" | fastest 10%: Model {row['model_rmse_fast_cm']}, Baseline {row['baseline_rmse_fast_cm']}")

    # Final: train on every origin, forecast 12 days past the last Pass.
    X, y = training_rows(T - 1)
    final = lgb.LGBMRegressor(**PARAMS).fit(X, y)
    res["feature_importance"] = sorted(zip(NAMES, final.feature_importances_.tolist()), key=lambda t: -t[1])
    F, base = features(Y, days, T - 1, 12.0, coh)
    out = np.full(shape[0] * shape[1], np.nan, np.float32)
    out[valid] = base + final.predict(F)
    target = (dt.date.fromisoformat(dates[-1]) + dt.timedelta(days=12)).isoformat()
    for key in list(config.data.list(f"{args.site}/layers")):
        if key.split("/")[-1].startswith("pred_subsidence_"):
            config.data.delete(key)
    export.write_cog(args.site, f"pred_subsidence_{target}", out.reshape(shape), grid)
    print(f"wrote pred_subsidence_{target} (forecast 12 days past {dates[-1]})")
    res["forecast_date"] = target

    run = ROOT / "ml" / "runs" / "subsidence"
    run.mkdir(parents=True, exist_ok=True)
    (run / "scores.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    cum = next(l for l in manifest["layers"] if l["id"] == "cum_disp_cm")
    write_card(args.site, res, cum)
    raise SystemExit(predictions.refresh(args.site))


def write_card(site_id: str, res: dict, cum: dict):
    card = {
        "lens": "subsidence",
        "name": "subsidence",
        "job": "Forecast how far each spot will have sunk at the next NISAR Pass",
        "user": "City water and infrastructure planners watching where the ground sinks fastest",
        "sites": [site_id],
        "inputs": NAMES,
        "prediction": {"unit": "cm", "colormap": cum["colormap"], "range": cum["range"], "label": f"AI forecast: cumulative displacement on {res['forecast_date']}"},
        "labels": {"kind": "self_supervised", "source": f"The site's own GUNW time series; Passes {', '.join(res['held_out'])} held out",
                   "notes": "Scores measure how well the next Passes are forecast, not ground truth from levelling or GNSS"},
        "baseline": {"name": "Straight-line extrapolation of each pixel's history", "metric": "RMSE, cm (3 held-out Passes)", "score": res["baseline_rmse_cm"]},
        "model": {"name": "LightGBM correction of the straight line", "metric": "RMSE, cm (3 held-out Passes)", "score": res["model_rmse_cm"], "framework": "LightGBM"},
        "extra_scores": [{"name": f"{who}, +{i + 1} Pass, fastest-sinking 10%", "metric": "RMSE, cm", "score": r[f"{key}_rmse_fast_cm"]}
                         for i, r in enumerate(res["per_horizon"]) for who, key in (("Model", "model"), ("Baseline", "baseline"))]
                        + [{"name": "No change (last value)", "metric": "RMSE, cm (+1 Pass)", "score": res["per_horizon"][0]["persistence_rmse_cm"]}],
        "split": f"Time split: trained on forecasts ending by {res['origin']}, tested on the next 3 Passes; validation origin {res['validation']['origin']} (Model {res['validation']['model_rmse_cm']} cm, Baseline {res['validation']['baseline_rmse_cm']} cm)",
        "limits": [
            "Does not beat the straight-line Baseline: use the Baseline forecast; the Model is shown for transparency",
            "Under one year of data, so seasonal swings (groundwater pumping, rain) cannot be learned",
            "Errors include the atmospheric noise of each interferogram, which no forecast can predict",
            "Line-of-sight displacement only; vertical sinking is assumed to dominate in Mexico City",
            "The displacement sign (toward or away from the satellite) is our reading of the product; ASF has not yet confirmed it",
        ],
        "status": "prototype",
        "updated": dt.date.today().isoformat(),
    }
    (config.MODEL_CARDS_DIR / "subsidence.json").write_text(json.dumps(card, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
