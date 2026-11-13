"""Change detection over a whole Stack: what changed, when, and by how much.

Shared by api/ (on-demand Analyses), pipeline/ and ml/, so training and serving see identical pixels.

Two detectors share one output format:

* "rules": a statistical change-point detector plus physical rules. Needs no
  training and is the baseline the neural model must beat.
* "model": the trained spatio-temporal network (see ml/), run through ONNX
  Runtime when models/change_utae.onnx exists.

Both run on the native radar grid, so results line up exactly with the data.
"""
import json
import math
import threading
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from . import cmr, config, gcov, render

CLASSES = [
    {"id": 0, "key": "stable", "label": "No clear change", "color": None},
    {"id": 1, "key": "burned", "label": "Burned", "color": "#f97316"},
    {"id": 2, "key": "veg_loss", "label": "Vegetation lost", "color": "#d946ef"},
    {"id": 3, "key": "veg_gain", "label": "Vegetation grew", "color": "#22c55e"},
    {"id": 4, "key": "water_gain", "label": "Water appeared", "color": "#3b82f6"},
    {"id": 5, "key": "water_loss", "label": "Water receded", "color": "#eab308"},
]
MODEL_PATH = config.ROOT / "models" / "change_utae.onnx"
MAX_PIXELS = 8_000_000  # the stack itself is about 80 bytes per cell for ten passes
_lock = threading.Lock()
_readers = ThreadPoolExecutor(max_workers=4, thread_name_prefix="stack")
_session = None


# ---------------------------------------------------------------- reading


def stack_passes(stack: str, bbox, start="2026-06-17", end="2026-12-31") -> list[dict]:
    """One pass per date for a stack, oldest first."""
    by_date: dict[str, dict] = {}
    for s in cmr.search(tuple(bbox), start, end):
        if s["stack"] == stack:
            by_date.setdefault(s["date"], s)
    return [by_date[k] for k in sorted(by_date)]


def _box(a: np.ndarray) -> np.ndarray:
    """3 x 3 mean that ignores NaN."""
    ok = np.isfinite(a)
    v = np.pad(np.where(ok, a, 0), 1)
    n = np.pad(ok.astype(np.float32), 1)
    h, w = a.shape
    s = sum(v[i : i + h, j : j + w] for i in range(3) for j in range(3))
    c = sum(n[i : i + h, j : j + w] for i in range(3) for j in range(3))
    return np.where(c > 0, s / np.maximum(c, 1), np.nan).astype(np.float32)


def read_stack(passes: list[dict], bbox, res: int, progress=lambda done, total: None, max_pixels: int = MAX_PIXELS):
    """Backscatter in dB for every pass over bbox, shape (T, 2, H, W) with channels HH, HV, plus the grid."""
    freq = "B" if res >= 80 else "A"
    fm = gcov.index(passes[0]["id"])["freqs"][freq]
    k = max(1, int(round(res / abs(fm["dx"]))))
    step = abs(fm["dx"]) * k
    w, s, e, n = bbox
    edge = np.linspace(0, 1, 9)
    lon = np.concatenate([w + (e - w) * edge, w + (e - w) * edge, np.full(9, w), np.full(9, e)])
    lat = np.concatenate([np.full(9, s), np.full(9, n), s + (n - s) * edge, s + (n - s) * edge])
    gx, gy = render._to_grid(fm["epsg"]).transform(lon, lat)
    X0 = math.floor(gx.min() / step) * step
    Y0 = math.ceil(gy.max() / step) * step
    W = int(math.ceil((gx.max() - X0) / step))
    H = int(math.ceil((Y0 - gy.min()) / step))
    if H * W > max_pixels:
        raise ValueError(f"Area too large at {res} m ({H} x {W} cells). Zoom in, or use the 80 m quick scan.")
    out = np.full((len(passes), 2, H, W), np.nan, np.float32)
    done = [0]

    def one(i):
        f = gcov.index(passes[i]["id"])["freqs"][freq]
        # Cell corner (X0, Y0) -> this pass's row/column; pixel centres are at x0 + j*dx.
        c0 = int(round((X0 - (f["x0"] - f["dx"] / 2)) / f["dx"]))
        r0 = int(round((Y0 - (f["y0"] - f["dy"] / 2)) / f["dy"]))
        for ch, term in enumerate(("HHHH", "HVHV")):
            if term not in f["terms"]:
                continue
            win = render._block_mean(gcov.read_window(passes[i]["id"], freq, term, r0, r0 + H * k, c0, c0 + W * k), k)
            if res < 80:
                win = _box(win)  # extra speckle reduction at fine resolution
            out[i, ch] = render.to_db(win)
        with _lock:
            done[0] += 1
            progress(done[0], len(passes))

    list(_readers.map(one, range(len(passes))))
    grid = {"epsg": fm["epsg"], "x0": X0, "y0": Y0, "res": step, "shape": [H, W]}
    return out, grid


# ---------------------------------------------------------------- detectors


def change_point(db: np.ndarray, min_side: int = 2, strip: int = 512):
    """change_point_strip over the whole array, a band of rows at a time to bound memory."""
    parts = [change_point_strip(db[:, :, r : r + strip], min_side) for r in range(0, db.shape[2], strip)]
    return {k: np.concatenate([p[k] for p in parts], axis=-2) for k in parts[0]}


def change_point_strip(db: np.ndarray, min_side: int = 2):
    """Best single step in each pixel's series.

    Tries every split of the T passes into "before" and "after", keeps the one
    that best explains the series as a single step (least squares), and scores
    the jump against the scatter left over once the step is removed.
    Returns d (2, H, W) dB change, pre and post means, when (index of the first
    "after" pass) and t (jump divided by its standard error, on HV).
    """
    T = db.shape[0]
    ok = np.isfinite(db)
    v = np.where(ok, db, 0).astype(np.float32)
    cs, cn = np.cumsum(v, 0), np.cumsum(ok, 0).astype(np.float32)
    cs2 = np.cumsum(v * v, 0)
    best = np.full(db.shape[2:], -1.0, np.float32)
    when = np.zeros(db.shape[2:], np.uint8)
    pre = np.full(db.shape[1:], np.nan, np.float32)
    post = np.full(db.shape[1:], np.nan, np.float32)
    tval = np.zeros(db.shape[2:], np.float32)
    for k in range(min_side, T - min_side + 1):
        n1, n2 = cn[k - 1], cn[-1] - cn[k - 1]
        valid = (n1 >= min_side) & (n2 >= min_side)
        m1 = cs[k - 1] / np.maximum(n1, 1)
        m2 = (cs[-1] - cs[k - 1]) / np.maximum(n2, 1)
        d = m2 - m1
        # Least-squares criterion: the drop in residual sum of squares from fitting a step here.
        # The n1*n2/(n1+n2) weight keeps a few outlying passes at either end from winning.
        gain = (n1 * n2 / np.maximum(n1 + n2, 1)) * d * d
        score = np.where(valid.all(0), gain[1] + 0.25 * gain[0], -1)
        better = score > best
        if not better.any():
            continue
        # Residual variance of HV around the two-level fit.
        ss = (cs2[k - 1, 1] - n1[1] * m1[1] ** 2) + ((cs2[-1, 1] - cs2[k - 1, 1]) - n2[1] * m2[1] ** 2)
        sd = np.sqrt(np.maximum(ss, 0) / np.maximum(n1[1] + n2[1] - 2, 1)) + 0.15  # floor: calibration noise
        t = np.abs(d[1]) / (sd * np.sqrt(1 / np.maximum(n1[1], 1) + 1 / np.maximum(n2[1], 1)))
        best = np.where(better, score, best)
        when = np.where(better, k, when).astype(np.uint8)
        tval = np.where(better, t, tval)
        pre = np.where(better, m1, pre)
        post = np.where(better, m2, post)
    return {"d": post - pre, "pre": pre, "post": post, "when": when, "t": tval}


def classify_rules(cp: dict) -> np.ndarray:
    """Physical rules on the detected step. Radar alone cannot tell fire from clearing, so class 1 is never used here."""
    d_hh, d_hv = cp["d"]
    pre_hh, pre_hv = cp["pre"]
    post_hh, post_hv = cp["post"]
    sure = cp["t"] >= 3.0
    water_pre = (pre_hv < -22) & (pre_hh < -15)
    water_post = (post_hv < -22) & (post_hh < -15)
    cls = np.zeros(d_hv.shape, np.uint8)
    cls[(d_hv <= -1.5) & sure & (pre_hv > -19)] = 2
    cls[(d_hv >= 1.5) & sure & ~water_pre] = 3
    cls[water_post & ~water_pre & (d_hh <= -3)] = 4
    cls[water_pre & ~water_post & (d_hh >= 3)] = 5
    return _sieve(cls)


def _sieve(cls: np.ndarray, need: int = 5) -> np.ndarray:
    """Drop speckle: keep a changed cell only if most of its 3 x 3 neighbourhood agrees."""
    out = np.zeros_like(cls)
    h, w = cls.shape
    for c in range(1, len(CLASSES)):
        m = np.pad((cls == c).astype(np.uint8), 1)
        count = sum(m[i : i + h, j : j + w] for i in range(3) for j in range(3))
        out[(cls == c) & (count >= need)] = c
    return out


def model_available() -> bool:
    return MODEL_PATH.exists()


def model_info() -> dict:
    info = {"available": model_available(), "path": MODEL_PATH.relative_to(config.ROOT).as_posix(), "metrics": None}
    metrics = MODEL_PATH.with_suffix(".metrics.json")
    if metrics.exists():
        info["metrics"] = json.loads(metrics.read_text(encoding="utf-8"))
    return info


def features(db: np.ndarray) -> np.ndarray:
    """dB stack (T, 2, H, W) -> model input (T, 4, H, W).

    Channels 0-1: backscatter level. Channels 2-3: each pass minus that cell's
    median over time, so a step change stands out from terrain and land cover.
    Must match ml/sardance/data.py features().
    """
    db = db.astype(np.float32)
    level = np.clip((np.nan_to_num(db, nan=-30.0) + 15.0) / 10.0, -3, 3)
    with np.errstate(all="ignore"):
        anomaly = db - np.nanmedian(db, axis=0, keepdims=True)
    anomaly = np.clip(np.nan_to_num(anomaly, nan=0.0) / 3.0, -3, 3)
    return np.concatenate([level, anomaly], axis=1).astype(np.float32)


def classify_model(db: np.ndarray, days: list[int], tile: int = 256, overlap: int = 32) -> np.ndarray:
    """Run the trained network over the stack in overlapping tiles and average the scores."""
    global _session
    if _session is None:
        import onnxruntime as ort  # optional dependency, only needed once a model exists

        _session = ort.InferenceSession(str(MODEL_PATH), providers=["CPUExecutionProvider"])
    x = features(db)
    T, C, H, W = x.shape
    d = (np.asarray(days, np.float32) - days[0])[None]
    score = np.zeros((len(CLASSES), H, W), np.float32)
    hits = np.zeros((H, W), np.float32)
    step = tile - overlap
    for r in range(0, max(H - overlap, 1), step):
        for c in range(0, max(W - overlap, 1), step):
            r0, c0 = min(r, max(H - tile, 0)), min(c, max(W - tile, 0))
            patch = x[:, :, r0 : r0 + tile, c0 : c0 + tile]
            ph, pw = patch.shape[2:]
            pad = np.zeros((T, C, tile, tile), np.float32)
            pad[:, :, :ph, :pw] = patch
            logits = _session.run(None, {"x": pad[None], "days": d})[0][0]
            score[:, r0 : r0 + ph, c0 : c0 + pw] += logits[:, :ph, :pw]
            hits[r0 : r0 + ph, c0 : c0 + pw] += 1
    cls = (score / np.maximum(hits, 1)).argmax(0).astype(np.uint8)
    cls[~np.isfinite(db).any((0, 1))] = 0
    return cls
