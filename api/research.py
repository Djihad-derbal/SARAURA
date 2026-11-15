"""Research plots for a study (Showcase Site or Analysis), computed from the pipeline's own files.

  /research/{id}/series_by_class   a variable's time series inside each class of a categorical layer
                                   (e.g. HV inside vs outside the burned area; maize vs soybean growth curves)
  /research/{id}/change_by_date    share of the area with a strong backscatter drop or rise at each Pass
  /research/{id}/class_area        hectares of each class of a categorical layer on every date
                                   (e.g. the flood pulse: open water and flooded vegetation through the season)
  /research/{id}/agreement         where the AI Model and its Baseline agree, as areas and a picture

Results are cached per study build (manifest generated_at), so a Report asks for them cheaply.
"""
from __future__ import annotations

import io
import json

import numpy as np
from fastapi import APIRouter, HTTPException, Query, Response

from saraura import config

from .study import DATE, ID, _summarise, class_labels, cog_path, layer_of, manifest

router = APIRouter()
PNG = {"Cache-Control": "public, max-age=86400"}

AGREE = {  # value -> (label, colour); colour-blind safe pairing (red / amber / blue)
    1: ("AI Model and Baseline", "#b91c1c"),
    2: ("AI Model only", "#f59e0b"),
    3: ("Baseline only", "#2563eb"),
}


def _cached(study_id: str, name: str, build):
    m = manifest(study_id)
    key = f"research/{study_id}/{m['generated_at'].replace(':', '')}/{name}.json"
    if config.cache.exists(key):
        return json.loads(config.cache.read_text(key))
    out = build(m)
    config.cache.write_text(key, json.dumps(out))
    return out


@router.get("/research/{study_id}/series_by_class")
def series_by_class(study_id: str, variable: str, layer: str, date: str, min_cells: int = Query(20, ge=1)):
    """A variable through time inside each class of a categorical layer on one date: mean and middle half."""
    import pyarrow.parquet as pq
    import rasterio
    from pyproj import Transformer

    if not (ID.fullmatch(layer) and ID.fullmatch(variable) and DATE.fullmatch(date)):
        raise HTTPException(400, "Malformed variable, layer or date")

    def build(m):
        lay = layer_of(m, layer, date)
        if lay["colormap"] != "categorical":
            raise HTTPException(400, f"{layer} is not a class layer")
        spec = next((s for s in m["series"] if s["variable"] == variable), None)
        if spec is None:
            raise HTTPException(404, f"No series {variable}")
        t = pq.read_table(config.data.local_path(f"{study_id}/{spec['path']}"))
        pid = t["pixel_id"].to_numpy()
        upid, first, inv = np.unique(pid, return_index=True, return_inverse=True)
        lon, lat = t["lon"].to_numpy()[first], t["lat"].to_numpy()[first]
        with rasterio.open(cog_path(study_id, layer, date)) as ds:
            cls = ds.read(1)
            x, y = Transformer.from_crs(4326, ds.crs, always_xy=True).transform(lon, lat)
            col, row = ~ds.transform * (np.asarray(x), np.asarray(y))
            row, col = np.floor(row).astype(int), np.floor(col).astype(int)
            inside = (row >= 0) & (row < ds.height) & (col >= 0) & (col < ds.width)
            pix_cls = np.full(len(upid), 255, np.int32)
            pix_cls[inside] = cls[row[inside], col[inside]]
        row_cls = pix_cls[inv]
        labels = class_labels(m, lay)
        colors = {c["value"]: c["color"] for c in lay.get("classes", [])}
        out = []
        for v in sorted(set(pix_cls.tolist()) - {255}):
            n = int((pix_cls == v).sum())
            if n < min_cells:
                continue
            out.append({"value": v, "label": labels.get(v, str(v)), "color": colors.get(v), "cells": n,
                        "series": _summarise(t.filter(row_cls == v), spec["unit"], "polygon")})
        return {"variable": variable, "unit": spec["unit"], "layer": layer, "date": date, "layer_label": lay["label"], "classes": out}

    return _cached(study_id, f"sbc_{variable}_{layer}_{date}", build)


@router.get("/research/{study_id}/change_by_date")
def change_by_date(study_id: str, layer: str = "dhv", threshold: float = Query(3.0, gt=0, le=20)):
    """For every Pass, the share of the area where the layer fell below -threshold or rose above +threshold
    (with dhv: vegetation scattering dropped or rose by more than threshold dB since the previous Pass)."""
    import rasterio

    if not ID.fullmatch(layer):
        raise HTTPException(400, "Malformed layer")

    def build(m):
        lay = next((l for l in m["layers"] if l["id"] == layer), None)
        if lay is None:
            raise HTTPException(404, f"No layer {layer}")
        rows = []
        for d in lay["dates"]:
            with rasterio.open(cog_path(study_id, layer, d)) as ds:
                k = max(1, int(max(ds.width, ds.height) / 1024))  # an overview is plenty for shares
                a = ds.read(1, out_shape=(max(1, ds.height // k), max(1, ds.width // k)), masked=True).astype(np.float32).filled(np.nan)
            v = a[np.isfinite(a)]
            if not v.size:
                continue
            rows.append({"date": d, "drop_share": round(float((v < -threshold).mean()), 5), "rise_share": round(float((v > threshold).mean()), 5),
                         "median": round(float(np.median(v)), 3)})
        return {"layer": layer, "label": lay["label"], "unit": lay["unit"], "threshold": threshold, "rows": rows}

    return _cached(study_id, f"cbd_{layer}_{threshold:g}", build)


@router.get("/research/{study_id}/class_area")
def class_area(study_id: str, layer: str | None = None):
    """Hectares of each coloured class of a categorical layer on every date it has. Without `layer`: the AI Model's
    class layer, else the Baseline's. With a water Model this is the flood pulse."""
    import rasterio

    if layer is not None and not ID.fullmatch(layer):
        raise HTTPException(400, "Malformed layer")

    def build(m):
        cats = [l for l in m["layers"] if l["colormap"] == "categorical" and l.get("classes")]
        lay = (next((l for l in cats if l["id"] == layer), None) if layer
               else next((l for l in cats if l["kind"] == "prediction"), None) or next((l for l in cats if l["kind"] == "baseline"), None))
        if lay is None:
            raise HTTPException(404, f"No class layer {layer}" if layer else "This study has no class layer")
        values = [c["value"] for c in lay["classes"]]
        rows = []
        for d in lay["dates"]:
            with rasterio.open(cog_path(study_id, lay["id"], d)) as ds:
                a = ds.read(1)
                cell_ha = abs(ds.transform.a * ds.transform.e) / 1e4
            counts = np.bincount(a.ravel(), minlength=256)
            rows.append({"date": d, "analysed_ha": round(float(counts[:255].sum()) * cell_ha, 2),
                         "area_ha": {str(v): round(float(counts[v]) * cell_ha, 2) for v in values}})
        return {"layer": lay["id"], "label": lay["label"], "kind": lay["kind"], "status": lay["status"],
                "classes": lay["classes"], "rows": rows}

    return _cached(study_id, f"area_{layer or 'auto'}", build)


def _agreement_arrays(study_id: str, m: dict):
    import rasterio
    from rasterio.warp import Resampling, reproject

    pred = next((l for l in m["layers"] if l["kind"] == "prediction" and l["colormap"] == "categorical"), None)
    base = next((l for l in m["layers"] if l["kind"] == "baseline" and l["colormap"] == "categorical"), None)
    if not pred or not base:
        raise HTTPException(404, "This study has no categorical AI Model and Baseline to compare")
    pd, bd = pred["dates"][-1], base["dates"][-1]
    with rasterio.open(cog_path(study_id, pred["id"], pd)) as p_ds:
        p = p_ds.read(1)
        b = np.full(p.shape, 255, np.uint8)
        with rasterio.open(cog_path(study_id, base["id"], bd)) as b_ds:
            reproject(rasterio.band(b_ds, 1), b, dst_transform=p_ds.transform, dst_crs=p_ds.crs, dst_nodata=255, resampling=Resampling.nearest)
        cell_ha = abs(p_ds.transform.a * p_ds.transform.e) / 1e4
    valid = (p != 255) & (b != 255)
    P, B = (p == 1) & valid, (b == 1) & valid
    cat = np.zeros(p.shape, np.uint8)
    cat[P & B], cat[P & ~B], cat[~P & B] = 1, 2, 3
    return pred, base, pd, bd, cat, valid, cell_ha


@router.get("/research/{study_id}/agreement")
def agreement(study_id: str):
    """Where the AI Model and its Baseline agree on the positive class (e.g. burned), in hectares."""

    def build(m):
        pred, base, pd, bd, cat, valid, cell_ha = _agreement_arrays(study_id, m)
        both, mo, bo = (int((cat == k).sum()) for k in (1, 2, 3))
        union = both + mo + bo
        return {
            "model_layer": pred["id"], "model_label": pred["label"], "model_date": pd,
            "baseline_layer": base["id"], "baseline_label": base["label"], "baseline_date": bd,
            "classes": [{"value": k, "label": AGREE[k][0], "color": AGREE[k][1], "area_ha": round(n * cell_ha, 1)} for k, n in zip((1, 2, 3), (both, mo, bo))],
            "analysed_ha": round(float(valid.sum()) * cell_ha, 1),
            "overlap_share": round(both / union, 4) if union else None,
        }

    return _cached(study_id, "agreement", build)


@router.get("/research/{study_id}/agreement.png")
def agreement_png(study_id: str, max_size: int = Query(1100, ge=128, le=2048)):
    """The agreement map as a picture on the Model's grid (north up)."""
    from PIL import Image

    m = manifest(study_id)
    key = f"research/{study_id}/{m['generated_at'].replace(':', '')}/agreement_{max_size}.png"
    if config.cache.exists(key):
        return Response(config.cache.read_bytes(key), media_type="image/png", headers=PNG)
    *_, cat, valid, _ = _agreement_arrays(study_id, m)
    rgba = np.zeros((*cat.shape, 4), np.uint8)
    for k, (_, c) in AGREE.items():
        rgba[cat == k] = [int(c[i:i + 2], 16) for i in (1, 3, 5)] + [235]
    img = Image.fromarray(rgba, "RGBA")
    img.thumbnail((max_size, max_size), Image.Resampling.NEAREST)
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    config.cache.write_bytes(key, buf.getvalue())
    return Response(buf.getvalue(), media_type="image/png", headers=PNG)
