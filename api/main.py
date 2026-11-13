"""SARAURA HTTP API.

Study pages (Showcase Sites and Analyses): /sites, /tiles, /terrain, /timeseries/{id}, /stats, /models  (api/study.py)
Explorer tier 1, raw Granules: /coverage, /granules, /browse/{granule_id}/...
Explorer tier 2, Analyses: POST /jobs, GET /jobs/{id}  (api/analyses.py)
Assistant: POST /assistant (Gemini, grounded)    Report: POST /report/{id} (PDF)  (api/report.py)
"""
import re
from concurrent.futures import ThreadPoolExecutor

import requests
from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware

from pydantic import BaseModel, Field

from saraura import cmr, config, gcov, remote, render

# Import the GDAL-based libraries once, at start-up. Imported lazily, the first burst of parallel requests
# (a Report asks for ~20 pictures at once) raced on rasterio's initialisation and failed with ImportError.
import pyarrow.parquet  # noqa: E402,F401
import rasterio  # noqa: E402,F401
import rasterio.features  # noqa: E402,F401
import rasterio.warp  # noqa: E402,F401
import rio_tiler.io  # noqa: E402,F401

from . import analyses, jobs, report, research, study

app = FastAPI(title="SARAURA API", version="0.3.0", description="NISAR radar, explained: Showcase Sites, on-demand Analyses, Models and Reports.")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET", "POST"], allow_headers=["*"])
app.include_router(study.router, tags=["Study pages"])
app.include_router(analyses.router, tags=["Analyses"])
app.include_router(report.router, tags=["Report"])
app.include_router(research.router, tags=["Research plots"])

_series_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="series")
PNG = {"Cache-Control": "public, max-age=86400"}


def _granule(granule_id: str) -> dict:
    # Granule ids become cache keys, so accept only granule-name characters.
    if not re.fullmatch(r"NISAR_[A-Za-z0-9_]{20,120}", granule_id):
        raise HTTPException(400, "Malformed granule id")
    try:
        return cmr.get(granule_id)
    except KeyError:
        raise HTTPException(404, f"Unknown granule {granule_id}")


def _term(pol: str) -> str:
    if pol.upper() not in render.TERM:
        raise HTTPException(400, "pol must be one of HH, HV, VV, VH")
    return render.TERM[pol.upper()]


def _bbox(text: str) -> tuple[float, float, float, float]:
    try:
        w, s, e, n = (float(v) for v in text.split(","))
    except ValueError:
        raise HTTPException(400, "bbox must be west,south,east,north")
    if not (-180 <= w < e <= 180 and -90 <= s < n <= 90):
        raise HTTPException(400, "bbox out of range")
    return w, s, e, n


@app.get("/health")
def health():
    return {"ok": True, "fetched_mb": round(remote.stats["bytes"] / 1e6, 1), "requests": remote.stats["requests"]}


@app.get("/coverage", tags=["Explorer"])
def coverage(bbox: str, product: str = "GCOV", start: str = "2025-10-29", end: str = "2026-12-31"):
    """Footprints of calibrated Granules as GeoJSON, for the Explorer map. Cached per 1-degree tile and day."""
    import datetime as dt
    import json
    import math

    if product not in config.PRODUCT_COLLECTIONS:
        raise HTTPException(400, f"product must be one of {sorted(config.PRODUCT_COLLECTIONS)}")
    w, s_, e, n = _bbox(bbox)
    tiles = [(x, y) for x in range(math.floor(w), math.ceil(e)) for y in range(math.floor(s_), math.ceil(n))]
    if len(tiles) > 64:
        raise HTTPException(400, "Zoom in: coverage is served for up to 64 one-degree tiles at a time")
    today = dt.date.today().isoformat()
    seen: dict[str, dict] = {}
    for x, y in tiles:
        key = f"coverage/{product}/{today}/{x}_{y}_{start}_{end}.json"
        if config.cache.exists(key):
            found = json.loads(config.cache.read_text(key))
        else:
            found = [cmr.public(g) for g in cmr.search((x, y, x + 1, y + 1), start, end, product)]
            config.cache.write_text(key, json.dumps(found))
        for g in found:
            seen.setdefault(g["id"], g)
    feats = [{"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [g["footprint"]]},
              "properties": {k: g.get(k) for k in ("id", "date", "secondary_date", "stack", "track", "direction", "maturity", "product")}}
             for g in sorted(seen.values(), key=lambda g: g["date"]) if g.get("footprint")]
    return {"type": "FeatureCollection", "features": feats}


@app.get("/granules", tags=["Explorer"])
def granules(bbox: str, start: str = "2026-06-17", end: str = "2026-12-31"):
    """NISAR Granules over an area, grouped into Stacks (same track, frame and direction), one Pass per entry."""
    found = cmr.search(_bbox(bbox), start, end)
    stacks: dict[str, dict] = {}
    for s in found:
        key = f"{s['stack']}|{s['bandwidth_mhz']}"
        st = stacks.setdefault(
            key,
            {
                "stack": s["stack"],
                "track": s["track"],
                "direction": s["direction"],
                "bandwidth_mhz": s["bandwidth_mhz"],
                "polarizations": s["polarizations"],
                "footprint": s["footprint"],
                "passes": [],
            },
        )
        st["passes"].append(
            {"id": s["id"], "date": s["date"], "start": s["start"], "maturity": s["maturity"], "ready": gcov.is_indexed(s["id"])}
        )
    return {"count": len(found), "stacks": sorted(stacks.values(), key=lambda v: -len(v["passes"]))}


@app.get("/browse/{granule_id}", tags=["Explorer"])
@app.get("/granules/{granule_id}", tags=["Explorer"])
def granule_detail(granule_id: str):
    """One Granule, with the map corners of its preview image."""
    s = _granule(granule_id)
    out = cmr.public(s)
    key = next((k for k in ("A_HVHV", "A_HHHH") if k in s["kml_urls"]), None)
    if key:
        m = re.search(r"<coordinates>([^<]+)</coordinates>", remote.get_text(s["kml_urls"][key]))
        if m:
            # KML LatLonQuad order is lower-left, lower-right, upper-right, upper-left.
            ll, lr, ur, ul = ([float(v) for v in p.split(",")[:2]] for p in m.group(1).split())
            out["preview_corners"] = [ul, ur, lr, ll]  # MapLibre image-source order
    return out


@app.get("/browse/{granule_id}/preview/{pol}.png", tags=["Explorer"])
@app.get("/granules/{granule_id}/preview/{pol}.png", tags=["Explorer"])
def preview(granule_id: str, pol: str):
    """NASA's low-resolution preview image for a Granule (instant, no data read)."""
    s = _granule(granule_id)
    key = "A_" + _term(pol)
    if key not in s["preview_urls"]:
        raise HTTPException(404, "No preview for that polarization")
    cache_key = f"previews/{granule_id}_{key}.png"
    if not config.cache.exists(cache_key):
        r = requests.get(s["preview_urls"][key], timeout=120)
        r.raise_for_status()
        config.cache.write_bytes(cache_key, r.content)
    return Response(config.cache.read_bytes(cache_key), media_type="image/png", headers=PNG)


@app.post("/browse/{granule_id}/prepare", tags=["Explorer"])
@app.post("/granules/{granule_id}/prepare", tags=["Explorer"])
def prepare(granule_id: str):
    """Read a Granule's layout so its tiles can be served (about 10 seconds the first time)."""
    _granule(granule_id)
    idx = gcov.index(granule_id)
    return {"id": granule_id, "ready": True, "grids": {k: {"shape": v["shape"], "pixel_m": v["dx"]} for k, v in idx["freqs"].items()}}


@app.get("/browse/{granule_id}/tiles/{pol}/{z}/{x}/{y}.png", tags=["Explorer"])
@app.get("/tiles/{granule_id}/{pol}/{z}/{x}/{y}.png", tags=["Explorer"], include_in_schema=False)
def granule_tile(granule_id: str, pol: str, z: int, x: int, y: int, min_db: float | None = None, max_db: float | None = None):
    """Backscatter tile. pol is HH, HV or RGB (false-colour composite of both)."""
    _granule(granule_id)
    if pol.upper() == "RGB":
        return Response(render.composite_tile(granule_id, z, x, y), media_type="image/png", headers=PNG)
    return Response(render.backscatter_tile(granule_id, _term(pol), z, x, y, min_db, max_db), media_type="image/png", headers=PNG)


@app.get("/change/{before_id}/{after_id}/{pol}/{z}/{x}/{y}.png", tags=["Explorer"])
def change(before_id: str, after_id: str, pol: str, z: int, x: int, y: int, scale_db: float = 6.0, floor_db: float = 1.5):
    """Change tile: red where backscatter fell between two passes, blue where it rose."""
    _granule(before_id)
    _granule(after_id)
    data = render.change_tile(before_id, after_id, _term(pol), z, x, y, scale_db, floor_db)
    return Response(data, media_type="image/png", headers=PNG)


@app.get("/browse/timeseries", tags=["Explorer"])
@app.get("/timeseries", tags=["Explorer"], include_in_schema=False)
def timeseries(
    lon: float = Query(ge=-180, le=180),
    lat: float = Query(ge=-90, le=90),
    stack: str | None = None,
    start: str = "2026-06-17",
    end: str = "2026-12-31",
    radius_m: float = Query(50.0, ge=10, le=500),
):
    """Backscatter in dB at a point for every pass of one stack. Slow the first time each pass is touched."""
    d = 0.01
    found = cmr.search((lon - d, lat - d, lon + d, lat + d), start, end)
    if not found:
        raise HTTPException(404, "No NISAR Passes cover that point")
    if stack is None:
        counts: dict[str, int] = {}
        for s in found:
            counts[s["stack"]] = counts.get(s["stack"], 0) + 1
        stack = max(counts, key=counts.get)
    # One pass per date: a stack can hold two bandwidth modes of the same overpass.
    by_date: dict[str, dict] = {}
    for s in found:
        if s["stack"] == stack:
            by_date.setdefault(s["date"], s)
    passes = [by_date[k] for k in sorted(by_date)]
    if not passes:
        raise HTTPException(404, f"Stack {stack} does not cover that point")

    def one(s):
        try:
            return {"date": s["date"], "id": s["id"], **render.sample_point(s["id"], lon, lat, radius_m)}
        except Exception as e:  # one unreadable pass should not sink the series
            return {"date": s["date"], "id": s["id"], "error": str(e)[:200]}

    return {
        "lon": lon,
        "lat": lat,
        "stack": stack,
        "radius_m": radius_m,
        "units": "dB (gamma0)",
        "stacks_available": sorted({s["stack"] for s in found}),
        "series": list(_series_pool.map(one, passes)),
    }


# ---------------------------------------------------------------- quick change view (deprecated)


class AnalysisRequest(BaseModel):
    stack: str = Field(pattern=r"^[0-9]{3}_[AD]_[0-9]{3}$")
    bbox: tuple[float, float, float, float]
    resolution_m: int = 80


def _job(job_id: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{14}", job_id):
        raise HTTPException(400, "Malformed analysis id")
    return job_id


@app.post("/analysis", tags=["Explorer (deprecated)"], deprecated=True)
def analysis_start(req: AnalysisRequest):
    """Rule-based change detection over one track. Superseded by POST /jobs; kept until the frontend moves.
    Physics rules only: Models never run on a user's area (ADR-0001)."""
    if req.resolution_m not in (20, 80):
        raise HTTPException(400, "resolution_m must be 20 or 80")
    _bbox(",".join(str(v) for v in req.bbox))
    try:
        return jobs.start(req.stack, req.bbox, req.resolution_m)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/analysis/{job_id}", tags=["Explorer (deprecated)"], deprecated=True)
def analysis_status(job_id: str):
    try:
        return jobs.status(_job(job_id))
    except KeyError:
        raise HTTPException(404, "Unknown analysis")


@app.get("/analysis/{job_id}/point", tags=["Explorer (deprecated)"], deprecated=True)
def analysis_point(job_id: str, lon: float, lat: float):
    try:
        return jobs.point(_job(job_id), lon, lat) or {"class": None}
    except KeyError:
        raise HTTPException(404, "Unknown analysis")


@app.get("/analysis/{job_id}/{layer}/{z}/{x}/{y}.png", tags=["Explorer (deprecated)"], deprecated=True)
def analysis_tile(job_id: str, layer: str, z: int, x: int, y: int):
    if layer not in ("class", "when"):
        raise HTTPException(400, "layer must be class or when")
    try:
        return Response(jobs.tile(_job(job_id), layer, z, x, y), media_type="image/png", headers=PNG)
    except KeyError:
        raise HTTPException(404, "Unknown analysis")


# ---------------------------------------------------------------- Assistant


class AssistantRequest(BaseModel):
    study_id: str = Field(pattern=r"^[a-z0-9_]{3,64}$")
    question: str = Field(min_length=2, max_length=600)
    layer: str | None = Field(None, pattern=r"^[a-z0-9_]+$")
    date: str | None = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    language: str = "en"


@app.get("/assistant", tags=["Assistant"])
def assistant_status():
    """Whether the Assistant is set up (GEMINI_API_KEY) and which model it uses."""
    from . import assistant

    return assistant.info()


@app.post("/assistant", tags=["Assistant"])
def assistant_ask(req: AssistantRequest):
    """Ask about the study on screen. Grounded in its manifest, insights, the visible layer's statistics
    and (Showcase Sites only) its Model card. Answers are AI-generated and labelled so."""
    import json

    from . import assistant

    m = study.manifest(req.study_id)
    layer_stats = None
    if req.layer and req.date:
        try:
            layer_stats = study.layer_stats(req.study_id, req.layer, req.date)
        except HTTPException:
            layer_stats = None
    card = None
    if m["kind"] == "showcase" and m.get("model_card") and (config.MODEL_CARDS_DIR / f"{m['model_card']}.json").exists():
        card = json.loads((config.MODEL_CARDS_DIR / f"{m['model_card']}.json").read_text(encoding="utf-8"))
    try:
        text = assistant.ask(req.question, m, layer_stats, card, req.language)
    except assistant.Unavailable as e:
        raise HTTPException(503, str(e))
    except Exception as e:  # network, quota, API errors: report without a stack trace
        raise HTTPException(502, f"The Assistant request failed: {str(e)[:200]}")
    grounded = ["manifest", "insights"] + (["layer statistics"] if layer_stats else []) + (["Model card"] if card else [])
    return {"text": text, "generated_by": "AI", "model": config.GEMINI_MODEL, "grounded_on": grounded}


# Fixed paths must be matched before the /browse/{granule_id} pattern that would swallow them.
def _fixed_first(prefix: str = "/browse/") -> None:
    routes = app.router.routes
    fixed = [r for r in routes if getattr(r, "path", "").startswith(prefix) and "{" not in r.path]
    for r in fixed:
        routes.remove(r)
    first = next(i for i, r in enumerate(routes) if getattr(r, "path", "").startswith(prefix))
    routes[first:first] = fixed


_fixed_first()
