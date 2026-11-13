"""Quick change view over a drawn area (deprecated; POST /jobs replaces it): run, poll, tiles, point lookups.

Rule-based detection only (saraura.change.classify_rules). Models never run on a user's area (ADR-0001).
"""
import hashlib
import json
import threading

import numpy as np

from saraura import config, render
from saraura.change import CLASSES, change_point, classify_rules, read_stack, stack_passes

_jobs: dict[str, dict] = {}
_results: dict[str, tuple[dict, dict]] = {}
_lock = threading.Lock()


def _key(job_id: str, name: str) -> str:
    return f"analysis/{job_id}/{name}"


# ---------------------------------------------------------------- jobs


def _job_id(stack, bbox, res, passes) -> str:
    key = json.dumps([stack, [round(v, 4) for v in bbox], res, "rules", [p["id"] for p in passes]])
    return hashlib.sha1(key.encode()).hexdigest()[:14]


def _run(job_id, stack, bbox, res, passes):
    job = _jobs[job_id]
    try:
        job.update(status="reading", message="Reading radar passes")
        db, grid = read_stack(passes, bbox, res, lambda a, b: job.update(progress=round(0.85 * a / b, 3)))
        job.update(status="analysing", message="Finding what changed", progress=0.88)
        cp = change_point(db)
        dates = [p["date"] for p in passes]
        cls = classify_rules(cp)
        cell_ha = grid["res"] ** 2 / 1e4
        changed = cls > 0
        stats = {
            "cell_ha": cell_ha,
            "area_ha": round(float(np.isfinite(db).any((0, 1)).sum() * cell_ha), 1),
            "classes": {c["key"]: round(float((cls == c["id"]).sum() * cell_ha), 1) for c in CLASSES[1:]},
            "by_date": {dates[k]: round(float((changed & (cp["when"] == k)).sum() * cell_ha), 1) for k in range(1, len(dates))},
        }
        meta = {"id": job_id, "stack": stack, "bbox": list(bbox), "resolution_m": res, "method": "rules", "dates": dates, "passes": [p["id"] for p in passes], "grid": grid, "stats": stats}
        np.savez_compressed(config.cache.local_path(_key(job_id, "result.npz")), cls=cls, when=cp["when"], d_hv=cp["d"][1].astype(np.float16), d_hh=cp["d"][0].astype(np.float16), t=np.clip(cp["t"], 0, 50).astype(np.float16))
        config.cache.write_text(_key(job_id, "meta.json"), json.dumps(meta))
        job.update(status="done", message="Done", progress=1.0)
    except Exception as e:
        job.update(status="error", message=str(e)[:300])


def start(stack: str, bbox, res: int) -> dict:
    passes = stack_passes(stack, bbox)
    if len(passes) < 4:
        raise ValueError("This track has fewer than four passes over the area; not enough to find a change.")
    job_id = _job_id(stack, bbox, res, passes)
    with _lock:
        if config.cache.exists(_key(job_id, "meta.json")):
            _jobs[job_id] = {"status": "done", "progress": 1.0, "message": "Done"}
        elif _jobs.get(job_id, {}).get("status") not in ("queued", "reading", "analysing"):  # not already running
            _jobs[job_id] = {"status": "queued", "progress": 0.0, "message": "Starting"}
            threading.Thread(target=_run, args=(job_id, stack, bbox, res, passes), daemon=True).start()
    return status(job_id)


def status(job_id: str) -> dict:
    job = _jobs.get(job_id)
    if config.cache.exists(_key(job_id, "meta.json")):
        meta = json.loads(config.cache.read_text(_key(job_id, "meta.json")))
        return {"id": job_id, "status": "done", "progress": 1.0, "message": "Done", "result": meta}
    if job is None:
        raise KeyError(job_id)
    return {"id": job_id, **job}


def load(job_id: str):
    if job_id not in _results:
        if not config.cache.exists(_key(job_id, "meta.json")):
            raise KeyError(job_id)
        meta = json.loads(config.cache.read_text(_key(job_id, "meta.json")))
        _results[job_id] = (meta, dict(np.load(config.cache.local_path(_key(job_id, "result.npz")))))
        while len(_results) > 6:
            _results.pop(next(iter(_results)))
    return _results[job_id]


# ---------------------------------------------------------------- tiles


def _hex(c: str):
    return tuple(int(c[i : i + 2], 16) for i in (1, 3, 5))


def _date_ramp(n: int) -> np.ndarray:
    """Colour per pass index, early = violet, late = yellow (single-direction ramp, colour-blind safe)."""
    stops = np.array([[68, 1, 84], [59, 82, 139], [33, 145, 140], [94, 201, 98], [253, 231, 37]], np.float32)
    pos = np.linspace(0, len(stops) - 1, max(n, 2))
    lo = np.clip(np.floor(pos).astype(int), 0, len(stops) - 2)
    return (stops[lo] + (stops[lo + 1] - stops[lo]) * (pos - lo)[:, None]).astype(np.uint8)


def tile(job_id: str, layer: str, z: int, x: int, y: int) -> bytes:
    """Map tile of an analysis. layer: 'class' (what changed) or 'when' (date of change)."""
    meta, arr = load(job_id)
    g = meta["grid"]
    lon, lat = render._tile_lonlat(z, x, y)
    gx, gy = render._to_grid(g["epsg"]).transform(lon, lat)
    col = np.floor((gx - g["x0"]) / g["res"]).astype(np.int64)
    row = np.floor((g["y0"] - gy) / g["res"]).astype(np.int64)
    H, W = g["shape"]
    inside = (row >= 0) & (row < H) & (col >= 0) & (col < W)
    if not inside.any():
        return render.EMPTY_TILE
    r, c = np.clip(row, 0, H - 1), np.clip(col, 0, W - 1)
    cls = np.where(inside, arr["cls"][r, c], 0)
    rgba = np.zeros((render.TILE, render.TILE, 4), np.uint8)
    if layer == "when":
        ramp = _date_ramp(len(meta["dates"]))
        rgba[..., :3] = ramp[np.clip(arr["when"][r, c], 0, len(ramp) - 1)]
    else:
        for k in CLASSES[1:]:
            rgba[cls == k["id"], :3] = _hex(k["color"])
    rgba[..., 3] = np.where(cls > 0, 215, 0)
    return render._png(rgba)


def point(job_id: str, lon: float, lat: float) -> dict | None:
    """What the analysis found at one location."""
    meta, arr = load(job_id)
    g = meta["grid"]
    gx, gy = render._to_grid(g["epsg"]).transform(lon, lat)
    c, r = int((gx - g["x0"]) // g["res"]), int((g["y0"] - gy) // g["res"])
    if not (0 <= r < g["shape"][0] and 0 <= c < g["shape"][1]):
        return None
    k = int(arr["cls"][r, c])
    return {
        "class": CLASSES[k]["key"],
        "label": CLASSES[k]["label"],
        "changed_on": meta["dates"][int(arr["when"][r, c])] if k else None,
        "hv_change_db": round(float(arr["d_hv"][r, c]), 2),
        "hh_change_db": round(float(arr["d_hh"][r, c]), 2),
        "confidence_t": round(float(arr["t"][r, c]), 1),
    }
