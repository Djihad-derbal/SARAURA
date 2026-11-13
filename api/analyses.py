"""On-demand Analyses (Explorer tier 2): any calibrated area, run through the same pipeline as the
Showcase Sites, with an optional Lens that adds its physics layers and Baseline. Never a Model
(ADR-0001). The result is a manifest like a site's, so the Study page and every read route work on it.

An Analysis id is a hash of (Granules, bbox, product, Lens, event dates): asking again for the same
thing returns the cached result. Jobs run one at a time, in order.
"""
from __future__ import annotations

import contextlib
import datetime as dt
import hashlib
import io
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, model_validator

from saraura import config

router = APIRouter()
_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="analysis")
_lock = threading.Lock()
_queue: list[str] = []

GCOV_LENSES = {"wildfire", "farming", "wetland", "volcano"}
GUNW_LENSES = {"earthquake", "subsidence", "volcano", "wetland"}


class JobRequest(BaseModel):
    bbox: tuple[float, float, float, float] = Field(description="west, south, east, north (degrees)")
    product: Literal["GCOV", "GUNW"]
    start: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    end: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    lens: Literal["wildfire", "earthquake", "volcano", "subsidence", "wetland", "farming"] | None = None
    event_date: str | None = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    event_end_date: str | None = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    name: str | None = Field(None, max_length=80)

    @model_validator(mode="after")
    def check(self):
        w, s, e, n = self.bbox
        if not (-180 <= w < e <= 180 and -90 <= s < n <= 90):
            raise ValueError("bbox must be west < east, south < north, in degrees")
        if self.start >= self.end:
            raise ValueError("start must be before end")
        if self.lens and self.lens not in (GCOV_LENSES if self.product == "GCOV" else GUNW_LENSES):
            raise ValueError(f"The {self.lens} Lens needs {'GUNW' if self.product == 'GCOV' else 'GCOV'} data")
        if self.lens == "wildfire" and not self.event_date:
            raise ValueError("The wildfire Lens needs event_date (when the fire started)")
        return self


def area_km2(bbox) -> float:
    from pyproj import Geod
    from shapely.geometry import box

    a, _ = Geod(ellps="WGS84").geometry_area_perimeter(box(*bbox))
    return abs(a) / 1e6


def resolution_for(product: str, km2: float) -> int:
    """Finer pixels for small areas, so a big area does not take hours."""
    if product == "GUNW":
        return 80
    return 20 if km2 <= 400 else 40 if km2 <= 2000 else 80


def _site(req: JobRequest, analysis_id: str) -> dict:
    km2 = area_km2(req.bbox)
    return {
        "id": analysis_id,
        "lens": req.lens,
        "name": req.name or f"Analysis: {req.product}{' / ' + req.lens if req.lens else ''}, {req.start} to {req.end}",
        "bbox": list(req.bbox),
        "dates": [req.start, req.end],
        "products": [req.product],
        "collections": ["PROVISIONAL_V1", "VALIDATED_V1"],
        "view": "3d" if req.product == "GUNW" else "2d",
        "resolution_m": resolution_for(req.product, km2),
        "event_date": req.event_date,
        "event_end_date": req.event_end_date,
        "model_card": None,
    }


def _key(analysis_id: str) -> str:
    return f"jobs/{analysis_id}.json"


def _save(analysis_id: str, **state) -> dict:
    cur = json.loads(config.cache.read_text(_key(analysis_id))) if config.cache.exists(_key(analysis_id)) else {}
    cur.update(state, updated=dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    config.cache.write_text(_key(analysis_id), json.dumps(cur))
    return cur


class _Log(io.TextIOBase):
    """Pipeline progress lines become the job's message."""

    def __init__(self, analysis_id: str):
        self.id, self.lines = analysis_id, []

    def write(self, s: str) -> int:
        for line in s.splitlines():
            if line.strip():
                self.lines.append(line.strip())
                _save(self.id, message=line.strip()[:200])
        return len(s)


def _run(analysis_id: str, site: dict):
    from pipeline import run_site

    with _lock:
        if analysis_id in _queue:
            _queue.remove(analysis_id)
    _save(analysis_id, status="running", message="Starting")
    log = _Log(analysis_id)
    try:
        with contextlib.redirect_stdout(log):  # one job at a time, so the redirect is not shared
            code = run_site.run(site, kind="analysis")
        if code:
            _save(analysis_id, status="error", message="The result failed the manifest check: " + " | ".join(log.lines[-3:])[:300])
        else:
            _save(analysis_id, status="done", message="Done")
    except Exception as e:
        _save(analysis_id, status="error", message=str(e)[:300])


@router.post("/jobs")
def start(req: JobRequest):
    """Start an Analysis (or return the cached one). Poll GET /jobs/{id}; when done, read it like a site:
    /sites/{id}, /tiles/{id}/..., /stats/{id}, /timeseries/{id}."""
    from pipeline import run_site

    km2 = area_km2(req.bbox)
    limit = config.AREA_LIMIT_KM2[req.product]
    if km2 > limit:
        raise HTTPException(400, f"The area is {km2:,.0f} km²; the limit for {req.product} is {limit:,.0f} km². Draw a smaller area.")
    probe = _site(req, "probe")
    try:
        granules = sorted(g["id"] for g in run_site.granules_for(probe, req.product))
    except Exception as e:
        raise HTTPException(502, f"Searching NASA's catalogue failed: {str(e)[:200]}")
    if len(granules) < 2:
        raise HTTPException(404, f"Only {len(granules)} calibrated {req.product} Granule(s) cover this area and dates; an Analysis needs at least 2.")
    digest = hashlib.sha1(json.dumps([granules, [round(v, 4) for v in req.bbox], req.product, req.lens, req.event_date, req.event_end_date]).encode()).hexdigest()[:12]
    analysis_id = f"an_{digest}"
    if config.data.exists(f"{analysis_id}/manifest.json"):
        return status(analysis_id)
    with _lock:
        state = json.loads(config.cache.read_text(_key(analysis_id))) if config.cache.exists(_key(analysis_id)) else {}
        if state.get("status") in ("queued", "running"):
            return status(analysis_id)
        _queue.append(analysis_id)
        _save(analysis_id, id=analysis_id, status="queued", message="Waiting for the jobs ahead", request=req.model_dump(), area_km2=round(km2, 1), granules=len(granules))
    _pool.submit(_run, analysis_id, _site(req, analysis_id))
    return status(analysis_id)


@router.get("/jobs/{analysis_id}")
def status(analysis_id: str):
    """State of an Analysis: queued (with its place), running (with the pipeline's last step), done, or error."""
    if not analysis_id.startswith("an_") or not analysis_id[3:].isalnum():
        raise HTTPException(400, "Malformed Analysis id")
    done = config.data.exists(f"{analysis_id}/manifest.json")
    if not config.cache.exists(_key(analysis_id)):
        if done:
            return {"id": analysis_id, "status": "done", "message": "Done"}
        raise HTTPException(404, "Unknown Analysis")
    state = json.loads(config.cache.read_text(_key(analysis_id)))
    if state.get("status") == "queued":
        with _lock:
            state["place"] = _queue.index(analysis_id) + 1 if analysis_id in _queue else None
    if done and state.get("status") not in ("running", "queued"):
        state["status"] = "done"
    return {"id": analysis_id, **state}


@router.get("/jobs")
def recent(limit: int = 10):
    """The most recent Analyses, newest first (for the Explorer's recent list)."""
    items = []
    for key in config.cache.list("jobs"):
        try:
            items.append(json.loads(config.cache.read_text(key)))
        except Exception:
            continue
    items.sort(key=lambda s: s.get("updated", ""), reverse=True)
    return items[: max(1, min(limit, 50))]
