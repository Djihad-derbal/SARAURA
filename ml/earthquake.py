"""Earthquake damage Model: rank 250 m Neighborhoods by the chance that buildings were damaged.

  python ml/earthquake.py --site venezuela_eq

Labels: Copernicus EMS EMSR884 building damage grades (real, not proxy), from the products downloaded
to ml/data/emsr884/x/ (see ml/README.md). A Neighborhood is positive if any building in it is graded
Damaged or Destroyed, negative if it lies inside an analysed area with no graded building, and left
out if it only has "Possibly damaged" buildings.

Features per Neighborhood come from the site's own layers (pipeline output): coherence before, across
and after the event, coherence loss and recovery, HH/HV change across the event, pre-event backscatter
(built-up areas are bright in HH) and slope. Displacement size and gradient are left out: they mark
distance from the fault, so with them the Model learned location instead of damage.

Baseline: mean coherence loss of the Neighborhood (the classic InSAR damage proxy). It is scored at
its best threshold on the test cells, so the comparison favours the Baseline.

Evaluation: spatial cross-validation over 5 km blocks, repeated with the block grid shifted 5 times;
the Model score is the mean average precision, with its range. The final
Model is trained on all labelled Neighborhoods and predicts the whole site.

Writes data/<site>/layers/pred_earthquake_<event pair date>.tif (0 low, 1 elevated, 2 high), the
scores to ml/runs/earthquake/scores.json, and the Model card ml/model_cards/earthquake.json.
"""
import argparse
import datetime as dt
import glob
import json
import sys
from pathlib import Path

import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.features import rasterize
from rasterio.transform import from_origin
from rasterio.warp import Resampling, reproject
from shapely.geometry import box, shape
from shapely.ops import transform as shp_transform, unary_union

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import export, predictions, sites  # noqa: E402
from saraura import config  # noqa: E402

CELL = 250.0  # Neighborhood size, metres (GLOSSARY.md)
BLOCK = 20  # cross-validation block = 20 x 20 Neighborhoods = 5 km
EMSR = ROOT / "ml" / "data" / "emsr884" / "x"
GRADES = {"Possibly damaged": 1, "Damaged": 2, "Destroyed": 3}
LOCATION_FEATURES = ["disp_abs_cm", "phase_gradient", "phase_gradient_max"]
CLASSES = [(0, "Low damage likelihood", True), (1, "Elevated damage likelihood", True), (2, "High damage likelihood", True)]


# ---------------------------------------------------------------- grid and layers

def neighborhood_grid(site_id: str, manifest: dict) -> dict:
    """A 250 m grid over the site in the layers' CRS, aligned to the GUNW grid origin."""
    l = next(l for l in manifest["layers"] if l["id"] == "coherence")
    with rasterio.open(config.data.local_path(f"{site_id}/layers/coherence_{l['dates'][0]}.tif")) as ds:
        b, epsg = ds.bounds, ds.crs.to_epsg()
    w, h = int((b.right - b.left) // CELL), int((b.top - b.bottom) // CELL)
    return {"x0": b.left, "y0": b.top, "res": CELL, "epsg": epsg, "shape": [h, w]}


def to_grid(site_id: str, layer_id: str, date: str, grid: dict, how=Resampling.average) -> np.ndarray:
    out = np.full(grid["shape"], np.nan, np.float32)
    with rasterio.open(config.data.local_path(f"{site_id}/layers/{layer_id}_{date}.tif")) as ds:
        src = ds.read(1).astype(np.float32)
        reproject(src, out, src_transform=ds.transform, src_crs=ds.crs, src_nodata=np.nan,
                  dst_transform=from_origin(grid["x0"], grid["y0"], CELL, CELL), dst_crs=f"EPSG:{grid['epsg']}", dst_nodata=np.nan, resampling=how)
    return out


def features(site_id: str, manifest: dict, grid: dict, event: str) -> tuple[np.ndarray, list[str], str]:
    dates = {l["id"]: l["dates"] for l in manifest["layers"]}
    coh = dates["coherence"]  # pair ids are the secondary date
    co = next(d for d in coh if d > event)  # first pair spanning the event
    pre = [d for d in coh if d <= event][-1]
    post = next(d for d in coh if d > co)
    gcov = dates["hh_db"]
    g_pre = [d for d in gcov if d <= event][-1]
    g_post = next(d for d in gcov if d > event)
    F, names = [], []

    def add(name, a):
        F.append(a)
        names.append(name)

    for tag, d in (("pre", pre), ("co", co), ("post", post)):
        add(f"coherence_{tag}", to_grid(site_id, "coherence", d, grid))
    add("coherence_co_min", to_grid(site_id, "coherence", co, grid, Resampling.min))
    add("coherence_loss", to_grid(site_id, "coherence_loss", co, grid))
    add("coherence_loss_max", to_grid(site_id, "coherence_loss", co, grid, Resampling.max))
    add("coherence_recovery", F[names.index("coherence_post")] - F[names.index("coherence_co")])
    add("disp_abs_cm", np.abs(to_grid(site_id, "disp_cm", co, grid)))
    add("phase_gradient", to_grid(site_id, "phase_gradient", co, grid))
    add("phase_gradient_max", to_grid(site_id, "phase_gradient", co, grid, Resampling.max))
    for v in ("hh_db", "hv_db", "hvhh_db"):
        add(f"{v}_pre", to_grid(site_id, v, g_pre, grid))
    add("hh_db_pre_max", to_grid(site_id, "hh_db", g_pre, grid, Resampling.max))
    for v in ("dhh", "dhv"):
        add(f"{v}_event", to_grid(site_id, v, g_post, grid))
        a = to_grid(site_id, v, g_post, grid, Resampling.min)
        add(f"{v}_event_min", a)
    add("slope", to_grid(site_id, "slope", dates["slope"][0], grid))
    return np.stack(F, -1), names, co


# ---------------------------------------------------------------- labels

def labels(grid: dict, bbox) -> tuple[np.ndarray, np.ndarray, dict]:
    """y: 1 damaged, 0 not, -1 unknown; grade: max EMS grade per Neighborhood; info for the card."""
    to_utm = Transformer.from_crs(4326, grid["epsg"], always_xy=True).transform
    site = box(*bbox)
    analysed, holes, pts = [], [], []
    used = set()
    for d in sorted(glob.glob(str(EMSR / "*GRA*"))):
        aoi = [shape(f["geometry"]) for f in json.loads(next(Path(d).glob("*areaOfInterest*.json")).read_text(encoding="utf-8"))["features"]]
        if not any(a.intersects(site) for a in aoi):
            continue
        used.add(Path(d).name)
        analysed += aoi
        for f in Path(d).glob("*notAnalysed*.json"):
            holes += [shape(x["geometry"]) for x in json.loads(f.read_text(encoding="utf-8"))["features"]]
        for f in Path(d).glob("*builtUp*.json"):
            for x in json.loads(f.read_text(encoding="utf-8"))["features"]:
                g = GRADES.get(x["properties"].get("damage_gra"))
                if g:
                    pts.append((shape(x["geometry"]).representative_point(), g))
    tr = from_origin(grid["x0"], grid["y0"], CELL, CELL)
    shp = tuple(grid["shape"])
    area = rasterize([shp_transform(to_utm, unary_union(analysed))], shp, transform=tr, fill=0, default_value=1).astype(bool)
    if holes:
        area &= ~rasterize([shp_transform(to_utm, unary_union(holes))], shp, transform=tr, fill=0, default_value=1).astype(bool)
    grade = np.zeros(shp, np.uint8)
    inv = ~tr
    for p, g in pts:
        x, y = to_utm(p.x, p.y)
        c, r = (int(v) for v in inv * (x, y))
        if 0 <= r < shp[0] and 0 <= c < shp[1]:
            grade[r, c] = max(grade[r, c], g)
    y = np.full(shp, -1, np.int8)
    y[area & (grade == 0)] = 0
    y[grade >= 2] = 1
    info = {"products": sorted(used), "graded_buildings": len(pts), "analysed_neighborhoods": int(area.sum())}
    return y, grade, info


# ---------------------------------------------------------------- scoring

def average_precision(score: np.ndarray, y: np.ndarray) -> float:
    o = np.argsort(-score, kind="stable")
    y = y[o]
    tp = np.cumsum(y)
    prec = tp / np.arange(1, len(y) + 1)
    return float((prec * y).sum() / max(y.sum(), 1))


def best_f1(score: np.ndarray, y: np.ndarray) -> dict:
    best = {"f1": 0.0}
    for t in np.unique(np.quantile(score, np.linspace(0.5, 0.999, 300))):
        p = score >= t
        tp, fp, fn = int((p & (y == 1)).sum()), int((p & (y == 0)).sum()), int((~p & (y == 1)).sum())
        f1 = 2 * tp / max(2 * tp + fp + fn, 1)
        if f1 > best["f1"]:
            best = {"f1": round(f1, 4), "precision": round(tp / max(tp + fp, 1), 4), "recall": round(tp / max(tp + fn, 1), 4), "threshold": round(float(t), 4)}
    return best


def scores(score, y) -> dict:
    return {"average_precision": round(average_precision(score, y), 4), "best_f1": best_f1(score, y)}


PARAMS = dict(n_estimators=300, learning_rate=0.03, num_leaves=15, min_child_samples=20, subsample=0.8, subsample_freq=1,
              colsample_bytree=0.8, reg_lambda=1.0, verbose=-1, random_state=0)


def main():
    import lightgbm as lgb

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--site", default="venezuela_eq")
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--block", type=int, default=BLOCK, help="cross-validation block size in Neighborhoods")
    ap.add_argument("--drop", nargs="*", default=LOCATION_FEATURES, help="features to leave out")
    ap.add_argument("--repeats", type=int, default=5, help="cross-validation runs, each with the block grid shifted")
    args = ap.parse_args()
    site = sites.load(args.site)
    manifest = json.loads(config.data.read_text(f"{args.site}/manifest.json"))
    grid = neighborhood_grid(args.site, manifest)
    X, names, co = features(args.site, manifest, grid, site["event_date"])
    y, grade, info = labels(grid, site["bbox"])
    ok = (y >= 0) & np.isfinite(X).all(-1)
    rows, cols = np.nonzero(ok)
    Xl, yl = X[ok], y[ok].astype(int)
    print(f"{info['analysed_neighborhoods']} analysed Neighborhoods, {ok.sum()} usable: {yl.sum()} damaged, {(yl == 0).sum()} not; {info['graded_buildings']} graded buildings")

    # Location features (displacement size and gradient) vary smoothly over tens of km, so they let the
    # Model learn where the fault is rather than what damage looks like; with 5 km blocks they lowered
    # the score. They stay out by default.
    keep = [i for i, n in enumerate(names) if n not in args.drop]
    Xl, X, names = Xl[:, keep], X[..., keep], [names[i] for i in keep]

    def cross_validate(offset: int) -> np.ndarray:
        """Out-of-fold scores, blocks of args.block Neighborhoods; `offset` shifts the block grid."""
        off = np.random.default_rng(offset).integers(0, args.block, 2) if offset else (0, 0)
        block = ((rows + off[0]) // args.block) * 100003 + ((cols + off[1]) // args.block)
        fold = (block * 2654435761 % 2**32) % args.folds
        oof = np.zeros(len(yl))
        for k in range(args.folds):
            tr, te = fold != k, fold == k
            if yl[tr].sum() and te.sum():
                oof[te] = lgb.LGBMClassifier(**PARAMS).fit(Xl[tr], yl[tr]).predict_proba(Xl[te])[:, 1]
        return oof

    runs = [cross_validate(s) for s in range(args.repeats)]
    oof = runs[0]
    aps = [average_precision(r, yl) for r in runs]
    base = Xl[:, names.index("coherence_loss")]
    res = {"model": scores(oof, yl), "baseline": scores(base, yl), "positives": int(yl.sum()), "negatives": int((yl == 0).sum()),
           "prevalence": round(float(yl.mean()), 4), **info, "event_pair": co, "dropped_features": args.drop}
    res["model"]["average_precision"] = round(float(np.mean(aps)), 4)
    res["model"]["average_precision_range"] = [round(min(aps), 4), round(max(aps), 4)]
    res["model"]["repeats"] = args.repeats
    for k in ("model", "baseline"):
        print(f"{k:8s} AP {res[k]['average_precision']:.3f} {res[k].get('average_precision_range', '')}  best F1 {res[k]['best_f1']}")
    print(f"chance AP = prevalence = {res['prevalence']:.3f}")

    # Final Model on all labels; predict every Neighborhood in the site.
    final = lgb.LGBMClassifier(**PARAMS).fit(Xl, yl)
    imp = sorted(zip(names, final.feature_importances_.tolist()), key=lambda t: -t[1])
    res["feature_importance"] = imp
    print("top features:", ", ".join(f"{n} {v}" for n, v in imp[:6]))
    valid = np.isfinite(X).all(-1)
    p = np.full(grid["shape"], np.nan, np.float32)
    p[valid] = final.predict_proba(X[valid])[:, 1]
    hi, mid = res["model"]["best_f1"]["threshold"], np.quantile(oof[yl == 1], 0.25)
    mid = min(mid, hi)
    cls = np.where(np.isnan(p), 255, np.where(p >= hi, 2, np.where(p >= mid, 1, 0))).astype(np.uint8)
    res["class_thresholds"] = {"elevated": round(float(mid), 4), "high": hi}
    for key in list(config.data.list(f"{args.site}/layers")):
        if key.split("/")[-1].startswith("pred_earthquake_"):
            config.data.delete(key)
    export.write_cog(args.site, f"pred_earthquake_{co}", cls, grid, categorical=True)
    print(f"wrote pred_earthquake_{co}: high {int((cls == 2).sum())}, elevated {int((cls == 1).sum())} of {int(valid.sum())} Neighborhoods")

    run = ROOT / "ml" / "runs" / "earthquake"
    run.mkdir(parents=True, exist_ok=True)
    (run / "scores.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    res["block_km"] = args.block * CELL / 1000
    write_card(args.site, res, names)
    raise SystemExit(predictions.refresh(args.site))


def write_card(site_id: str, res: dict, names: list[str]):
    card = {
        "lens": "earthquake",
        "name": "earthquake",
        "job": "Rank 250 m Neighborhoods by the chance that buildings were damaged, from NISAR coherence, displacement and backscatter change",
        "user": "Search-and-rescue and damage-assessment teams deciding where to look first",
        "sites": [site_id],
        "inputs": names,
        "outputs": [{"value": v, "label": l, "reliable": r} for v, l, r in CLASSES],
        "labels": {"kind": "real", "source": "Copernicus EMS EMSR884 building damage grades: " + ", ".join(res["products"]),
                   "notes": "Positive = any building graded Damaged or Destroyed. Neighborhoods with only 'Possibly damaged' buildings are left out. Negatives are analysed areas with no graded building, which includes empty land."},
        "baseline": {"name": "Mean coherence loss across the event (best threshold)", "metric": "average precision", "score": res["baseline"]["average_precision"]},
        "model": {"name": "LightGBM on per-Neighborhood radar features", "metric": "average precision (mean of 5 block layouts)", "score": res["model"]["average_precision"], "framework": "LightGBM"},
        "extra_scores": [
            {"name": "Model, worst block layout", "metric": "average precision", "score": res["model"]["average_precision_range"][0]},
            {"name": "Model, best block layout", "metric": "average precision", "score": res["model"]["average_precision_range"][1]},
            {"name": "Model, best F1", "metric": "F1", "score": res["model"]["best_f1"]["f1"]},
            {"name": "Baseline, best F1", "metric": "F1", "score": res["baseline"]["best_f1"]["f1"]},
            {"name": "Chance (share of damaged Neighborhoods)", "metric": "average precision", "score": res["prevalence"]},
        ],
        "split": f"Spatial 5-fold cross-validation over {res['block_km']:g} km blocks ({res['positives']} damaged, {res['negatives']} undamaged Neighborhoods); scores are out-of-fold",
        "limits": [
            "Labels cover only the Caraballeda coast and part of Caracas; elsewhere in the site the map is an extrapolation",
            "Copernicus mapped damage from optical imagery; buildings hidden by roofs or cloud are missed, so some 'undamaged' Neighborhoods are not",
            "NISAR coherence is 80 m, coarser than single buildings: the Model finds damaged areas, not damaged buildings",
            "One earthquake, one track (126 descending)",
            "Only 142 damaged Neighborhoods: scores move by about 0.1 between block layouts, so the gain over the Baseline is modest",
        ],
        "status": "prototype",
        "updated": dt.date.today().isoformat(),
    }
    (config.MODEL_CARDS_DIR / "earthquake.json").write_text(json.dumps(card, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
