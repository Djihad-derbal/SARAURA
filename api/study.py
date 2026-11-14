"""Read side of a Study page, shared by Showcase Sites and Analyses: manifest, layer tiles, terrain,
time series, statistics and Model cards. Everything here reads pipeline/ml output files; nothing
loads or runs a Model (ADR-0005).
"""
from __future__ import annotations

import json
import re
from functools import lru_cache

import numpy as np
import pyarrow.compute as pc
import pyarrow.parquet as pq
from fastapi import APIRouter, Body, HTTPException, Query, Response

from saraura import config

router = APIRouter()
PNG = {"Cache-Control": "public, max-age=86400"}
ID = re.compile(r"^[a-z0-9_]{3,64}$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TERRAIN_FILES = re.compile(r"^(meta\.json|dem\.f32|disp_\d{4}-\d{2}-\d{2}\.f32)$")


# ---------------------------------------------------------------- manifests


def manifest(study_id: str) -> dict:
    if not ID.fullmatch(study_id):
        raise HTTPException(400, "Malformed id")
    key = f"{study_id}/manifest.json"
    if not config.data.exists(key):
        raise HTTPException(404, f"No Showcase Site or finished Analysis called {study_id}")
    return json.loads(config.data.read_text(key))


def layer_of(m: dict, layer_id: str, date: str) -> dict:
    layer = next((l for l in m["layers"] if l["id"] == layer_id), None)
    if layer is None:
        raise HTTPException(404, f"No layer {layer_id}")
    if date not in layer["dates"]:
        raise HTTPException(404, f"Layer {layer_id} has no {date}; it has {layer['dates'][:3]}...")
    return layer


def cog_path(study_id: str, layer_id: str, date: str):
    return config.data.local_path(f"{study_id}/layers/{layer_id}_{date}.tif")


@router.get("/sites")
def sites():
    """The Showcase Sites, one summary each (for the globe markers)."""
    from pipeline import sites as site_configs

    out = []
    for sid in site_configs.all_ids():
        if not config.data.exists(f"{sid}/manifest.json"):
            continue
        m = json.loads(config.data.read_text(f"{sid}/manifest.json"))
        b = m["bbox"]
        # Questions answered here (ADR-0008): what the Places home page leads with
        decide = None
        if config.data.exists(f"{sid}/answers/answers.json"):
            a = json.loads(config.data.read_text(f"{sid}/answers/answers.json"))
            first = next((q for q in a["questions"] if q.get("layer")), None)
            decide = {
                "date": a["date"],
                "questions": [{"id": q["id"], "title": q["title"], "headline": q["headline"], "layer": q.get("layer")} for q in a["questions"]],
                "roles": [{"id": r["id"], "label": r["label"], "first": r["questions"][0]} for r in a["roles"]],
                "cover_layer": first["layer"] if first else None,
            }
        try:
            hook = site_configs.load(sid).get("hook")
        except Exception:
            hook = None
        out.append({
            "hook": hook,
            "decide": decide,
            "id": sid, "name": m["name"], "lens": m["lens"], "view": m["view"], "bbox": b, "center": [(b[0] + b[2]) / 2, (b[1] + b[3]) / 2],
            "event_date": m.get("event_date"), "passes": len(m["passes"]), "first": m["passes"][0]["date"], "last": m["passes"][-1]["date"],
            "headline": (m.get("insights") or [None])[0], "has_model": any(l["kind"] == "prediction" for l in m["layers"]),
        })
    return out


@router.get("/sites/{study_id}")
def site(study_id: str):
    """Full manifest of a Showcase Site or a finished Analysis (contracts/manifest.schema.json)."""
    return manifest(study_id)


# ---------------------------------------------------------------- tiles


def _colormap(layer: dict):
    from rio_tiler.colormap import cmap

    if layer["colormap"] == "categorical":
        cm = {int(c["value"]): tuple(int(c["color"][i:i + 2], 16) for i in (1, 3, 5)) + (220,) for c in layer.get("classes", []) if c.get("color")}
        return {k: cm.get(k, (0, 0, 0, 0)) for k in range(256)}
    return cmap.get(layer["colormap"])


def _paint(img, layer: dict) -> bytes:
    """Colour an image the way the layer's legend says: RGB as is, classes by colour, values by colormap and range."""
    if layer["colormap"] == "rgb":
        return img.render(img_format="PNG")
    if layer["colormap"] == "categorical":
        img.array.mask |= img.array.data == 0  # class 0 ("nothing found") stays transparent
        return img.render(img_format="PNG", colormap=_colormap(layer))
    lo, hi = layer["range"]
    img.rescale(in_range=((lo, hi),))
    return img.render(img_format="PNG", colormap=_colormap(layer))


def _check(layer_id: str, date: str):
    if not DATE.fullmatch(date) or not ID.fullmatch(layer_id):
        raise HTTPException(400, "Malformed layer or date")


@router.get("/tiles/{study_id}/{layer_id}/{date}/{z}/{x}/{y}.png")
def tile(study_id: str, layer_id: str, date: str, z: int, x: int, y: int):
    """Map tile of one layer on one date, coloured with the layer's legend (range and colormap from the manifest)."""
    from rio_tiler.errors import TileOutsideBounds
    from rio_tiler.io import Reader

    _check(layer_id, date)
    m = manifest(study_id)
    layer = layer_of(m, layer_id, date)
    try:
        with Reader(str(cog_path(study_id, layer_id, date))) as src:
            img = src.tile(x, y, z, tilesize=256)
    except TileOutsideBounds:
        return Response(_empty(), media_type="image/png", headers=PNG)
    return Response(_paint(img, layer), media_type="image/png", headers=PNG)


@router.get("/preview/{study_id}/{layer_id}/{date}.png")
def preview(study_id: str, layer_id: str, date: str, max_size: int = Query(1024, ge=128, le=2048)):
    """The whole layer as one picture in Web Mercator (north up), for the Report and thumbnails.
    Its corners are in the X-Bounds header: west,south,east,north."""
    from rio_tiler.io import Reader

    _check(layer_id, date)
    m = manifest(study_id)
    layer = layer_of(m, layer_id, date)
    path = cog_path(study_id, layer_id, date)
    # A layer file changes only when its study is rebuilt, so the picture is cached per file version.
    key = f"previews/{study_id}/{layer_id}_{date}_{max_size}_{path.stat().st_mtime_ns}.png"
    meta_key = key[:-4] + ".bounds"
    if config.cache.exists(key) and config.cache.exists(meta_key):
        png, bounds = config.cache.read_bytes(key), config.cache.read_text(meta_key)
    else:
        with Reader(str(path)) as src:
            b = src.get_geographic_bounds("EPSG:4326")
            img = src.part(b, dst_crs="EPSG:3857", bounds_crs="EPSG:4326", max_size=max_size)
        png, bounds = _paint(img, layer), ",".join(f"{v:.5f}" for v in b)
        config.cache.write_bytes(key, png)
        config.cache.write_text(meta_key, bounds)
    return Response(png, media_type="image/png", headers={**PNG, "X-Bounds": bounds, "Access-Control-Expose-Headers": "X-Bounds"})


@lru_cache(1)
def _empty() -> bytes:
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGBA", (256, 256), (0, 0, 0, 0)).save(buf, "PNG")
    return buf.getvalue()


@router.get("/terrain/{study_id}/{name}")
def terrain(study_id: str, name: str):
    """3D terrain files: meta.json, dem.f32 (heights) and disp_<date>.f32 (displacement), little-endian float32."""
    if not TERRAIN_FILES.fullmatch(name):
        raise HTTPException(400, "name must be meta.json, dem.f32 or disp_<date>.f32")
    manifest(study_id)
    key = f"{study_id}/terrain/{name}"
    if not config.data.exists(key):
        raise HTTPException(404, "No terrain for this study")
    media = "application/json" if name.endswith(".json") else "application/octet-stream"
    return Response(config.data.read_bytes(key), media_type=media, headers=PNG)


# ---------------------------------------------------------------- time series


def _series(m: dict, study_id: str, variable: str):
    s = next((s for s in m["series"] if s["variable"] == variable), None)
    if s is None:
        raise HTTPException(404, f"No series {variable}; available: {[x['variable'] for x in m['series']]}")
    return s, pq.read_table(config.data.local_path(f"{study_id}/{s['path']}"))


def _summarise(t, unit: str, how: str) -> list[dict]:
    """Per-date mean (and, for a polygon, the 25th to 75th percentile). Vectorised: a site series holds millions of rows."""
    days = t.column("date").cast("int32").to_numpy()  # date32 -> days since 1970
    vals = t.column("value").to_numpy(zero_copy_only=False).astype(np.float64)
    ok = np.isfinite(vals)
    days, vals = days[ok], vals[ok]
    uniq, inv = np.unique(days, return_inverse=True)
    counts = np.bincount(inv, minlength=len(uniq))
    means = np.bincount(inv, weights=vals, minlength=len(uniq)) / np.maximum(counts, 1)
    out = []
    order = np.argsort(inv, kind="stable") if how == "polygon" else None
    bounds = np.concatenate([[0], np.cumsum(counts)])
    for i, d in enumerate(uniq):
        if not counts[i]:
            continue
        row = {"date": (np.datetime64(0, "D") + int(d)).astype(str), "value": round(float(means[i]), 3)}
        if how == "polygon":
            v = vals[order[bounds[i]:bounds[i + 1]]]
            q25, q75 = np.percentile(v, [25, 75])
            row.update(p25=round(float(q25), 3), p75=round(float(q75), 3), n=int(v.size))
        out.append(row)
    return out


@router.get("/timeseries/{study_id}")
def timeseries_point(study_id: str, variable: str, lon: float = Query(ge=-180, le=180), lat: float = Query(ge=-90, le=90)):
    """A variable's value on every date at the series cell nearest to a point."""
    m = manifest(study_id)
    s, t = _series(m, study_id, variable)
    d = 0.02
    near = t.filter(pc.and_(pc.and_(pc.greater(t["lon"], lon - d), pc.less(t["lon"], lon + d)), pc.and_(pc.greater(t["lat"], lat - d), pc.less(t["lat"], lat + d))))
    if near.num_rows == 0:
        raise HTTPException(404, "The point is outside this study's series grid")
    dist = (near["lon"].to_numpy() - lon) ** 2 + ((near["lat"].to_numpy() - lat) * 1.0) ** 2
    pid = near["pixel_id"].to_numpy()[int(np.argmin(dist))]
    cell = near.filter(pc.equal(near["pixel_id"], pid))
    return {"variable": variable, "unit": s["unit"], "grid_m": s.get("grid_m"), "lon": lon, "lat": lat, "pixel_id": int(pid), "series": _summarise(cell, s["unit"], "point")}


@router.post("/timeseries/{study_id}")
def timeseries_polygon(study_id: str, variable: str, polygon: dict = Body(..., description="GeoJSON Polygon in lon/lat")):
    """Mean (and 25th to 75th percentile) of a variable over a drawn polygon, per date."""
    import shapely
    from shapely.geometry import box, shape

    m = manifest(study_id)
    try:
        poly = shape(polygon)
    except Exception:
        raise HTTPException(400, "polygon must be a GeoJSON Polygon")
    whole = poly.equals(poly.envelope) and box(*m["bbox"]).within(poly.buffer(1e-6))
    spec = next((x for x in m["series"] if x["variable"] == variable), None)
    cache_key = None
    if whole and spec:  # the default chart: whole study area, cached per series file version
        mtime = config.data.local_path(f"{study_id}/{spec['path']}").stat().st_mtime_ns
        cache_key = f"series_summary/{study_id}/{variable}_{mtime}.json"
        if config.cache.exists(cache_key):
            return json.loads(config.cache.read_text(cache_key))
    s, t = _series(m, study_id, variable)
    lon, lat = t["lon"].to_numpy(), t["lat"].to_numpy()
    w, s_, e, n = poly.bounds
    if poly.equals(poly.envelope) and w <= lon.min() and e >= lon.max() and s_ <= lat.min() and n >= lat.max():
        sel = t
    else:
        sel = t.filter(shapely.contains_xy(poly, lon, lat))
    if sel.num_rows == 0:
        raise HTTPException(404, "No series cells inside the polygon")
    out = {"variable": variable, "unit": s["unit"], "cells": int(len(np.unique(sel["pixel_id"].to_numpy()))), "series": _summarise(sel, s["unit"], "polygon")}
    if cache_key:
        config.cache.write_text(cache_key, json.dumps(out))
    return out


# ---------------------------------------------------------------- statistics


def layer_stats(study_id: str, layer_id: str, date: str, polygon: dict | None = None) -> dict:
    import rasterio
    from rasterio.features import geometry_mask
    from rasterio.warp import transform_geom

    m = manifest(study_id)
    layer = layer_of(m, layer_id, date)
    with rasterio.open(cog_path(study_id, layer_id, date)) as ds:
        a = ds.read(1, masked=True)
        if polygon is not None:
            g = transform_geom("EPSG:4326", ds.crs, polygon)
            a.mask |= geometry_mask([g], out_shape=a.shape, transform=ds.transform)
        cell_ha = abs(ds.transform.a * ds.transform.e) / 1e4
        if ds.count > 1:
            raise HTTPException(400, "Statistics are not defined for a colour composite")
    v = a.compressed()
    if v.dtype.kind == "f":
        v = v[np.isfinite(v)]
    out = {"layer": layer_id, "date": date, "unit": layer["unit"], "cells": int(v.size), "area_ha": round(float(v.size * cell_ha), 1)}
    if layer["colormap"] == "categorical":
        labels = class_labels(m, layer)
        out["classes"] = [{"value": int(k), "label": labels.get(int(k), str(int(k))), "area_ha": round(float(n * cell_ha), 1), "share": round(float(n / max(v.size, 1)), 4)}
                          for k, n in zip(*np.unique(v, return_counts=True))]
    elif v.size:
        p = np.percentile(v, [5, 25, 50, 75, 95])
        out.update(mean=round(float(v.mean()), 3), p5=round(float(p[0]), 3), p25=round(float(p[1]), 3), median=round(float(p[2]), 3), p75=round(float(p[3]), 3), p95=round(float(p[4]), 3))
        # Distribution over the legend's range (values outside it fall in the end bins), for the histogram plot.
        lo, hi = layer["range"]
        counts, edges = np.histogram(np.clip(v, lo, hi), bins=24, range=(lo, hi))
        out["histogram"] = {"edges": [round(float(e), 4) for e in edges], "counts": counts.astype(int).tolist(), "std": round(float(v.std()), 3)}
    return out


def class_labels(m: dict, layer: dict) -> dict[int, str]:
    """Names of every class value of a categorical layer (the Model card names classes that have no colour)."""
    labels = {0: "None of the classes"}
    if layer["kind"] == "prediction" and m.get("model_card"):
        card = config.MODEL_CARDS_DIR / f"{m['model_card']}.json"
        if card.exists():
            labels.update({o["value"]: o["label"] for o in json.loads(card.read_text(encoding="utf-8")).get("outputs", [])})
    labels.update({c["value"]: c["label"] for c in layer.get("classes", [])})
    return labels


@router.get("/stats/{study_id}")
def stats(study_id: str, layer: str, date: str):
    """Summary of one layer on one date over the whole study: percentiles, or area per class."""
    return layer_stats(study_id, layer, date)


@router.post("/stats/{study_id}")
def stats_polygon(study_id: str, layer: str, date: str, polygon: dict = Body(...)):
    """The same summary inside a drawn polygon (GeoJSON, lon/lat)."""
    return layer_stats(study_id, layer, date, polygon)


# ---------------------------------------------------------------- Models


@router.get("/models")
def models():
    """Every Model card: Lens, Status and both scores, for the comparison table."""
    out = []
    for p in sorted(config.MODEL_CARDS_DIR.glob("*.json")):
        c = json.loads(p.read_text(encoding="utf-8"))
        out.append({"lens": c["lens"], "name": c["model"]["name"], "status": c["status"], "metric": c["model"]["metric"],
                    "model_score": c["model"]["score"], "baseline_score": c["baseline"]["score"], "baseline": c["baseline"]["name"], "sites": c["sites"],
                    "labels": c["labels"]["kind"]})
    return out


@router.get("/models/{lens}")
def model_card(lens: str):
    """One Model card (contracts/model_card.schema.json)."""
    if not re.fullmatch(r"[a-z_]+", lens):
        raise HTTPException(400, "Malformed lens")
    p = config.MODEL_CARDS_DIR / f"{lens}.json"
    if not p.exists():
        raise HTTPException(404, f"No Model card for {lens}")
    return json.loads(p.read_text(encoding="utf-8"))
