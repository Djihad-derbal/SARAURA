"""Write pipeline outputs in the contract formats: COG layers, time-series parquet, manifest.json.

Every write goes through saraura.config.data (the storage interface), keyed
"<site_id>/layers/<variable>_<date>.tif" and so on (contracts/manifest.schema.json).
"""
from __future__ import annotations

import datetime as dt
import json
import tempfile
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import rasterio
from pyproj import Transformer
from rasterio.transform import from_origin
from rio_cogeo.cogeo import cog_translate
from rio_cogeo.profiles import cog_profiles

from saraura import config

TS_SCHEMA = pa.schema(
    [
        ("pixel_id", pa.int64()),
        ("lon", pa.float64()),
        ("lat", pa.float64()),
        ("date", pa.date32()),
        ("variable", pa.string()),
        ("value", pa.float32()),
        ("sigma", pa.float32()),
        ("valid", pa.bool_()),
    ]
)


def _transform(grid: dict):
    return from_origin(grid["x0"], grid["y0"], grid["res"], grid["res"])


def write_cog(site_id: str, name: str, array: np.ndarray, grid: dict, categorical: bool = False, sub: str = "layers") -> str:
    """One 2-D layer as a Cloud-Optimized GeoTIFF with internal overviews. Returns its storage key.
    `sub` is the folder under data/<site_id>/: "layers" (listed in the manifest) or "evidence" (read by Questions only)."""
    key = f"{site_id}/{sub}/{name}.tif"
    h, w = array.shape
    if categorical:
        data, dtype, nodata, resampling = array.astype(np.uint8), "uint8", 255, "nearest"
    else:
        data, dtype, nodata, resampling = array.astype(np.float32), "float32", np.nan, "average"
    profile = {
        "driver": "GTiff",
        "height": h,
        "width": w,
        "count": 1,
        "dtype": dtype,
        "crs": f"EPSG:{grid['epsg']}",
        "transform": _transform(grid),
        "nodata": nodata,
    }
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "src.tif"
        with rasterio.open(src, "w", **profile) as ds:
            ds.write(data, 1)
        out = config.data.local_path(key)
        cog_profile = cog_profiles.get("deflate")
        cog_profile.update(blockxsize=512, blockysize=512, predictor=3 if dtype == "float32" else 2)
        cog_translate(src, out, cog_profile, overview_resampling=resampling, in_memory=False, quiet=True)
    return key


def write_rgb(site_id: str, name: str, channels: list[tuple[np.ndarray, float, float]], grid: dict) -> str:
    """A 3-band uint8 colour composite COG. channels: (array, lo, hi) per band, stretched linearly to 1..255.
    0 is nodata (any band not finite)."""
    key = f"{site_id}/layers/{name}.tif"
    bands = []
    valid = np.ones(channels[0][0].shape, bool)
    for a, lo, hi in channels:
        valid &= np.isfinite(a)
        bands.append(np.clip(1 + (a - lo) / (hi - lo) * 254, 1, 255))
    data = np.stack([np.where(valid, b, 0).astype(np.uint8) for b in bands])
    h, w = data.shape[1:]
    profile = {"driver": "GTiff", "height": h, "width": w, "count": 3, "dtype": "uint8", "crs": f"EPSG:{grid['epsg']}",
               "transform": _transform(grid), "nodata": 0, "photometric": "RGB"}
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "src.tif"
        with rasterio.open(src, "w", **profile) as ds:
            ds.write(data)
        cog_profile = cog_profiles.get("deflate")
        cog_profile.update(blockxsize=512, blockysize=512, predictor=2)
        cog_translate(src, config.data.local_path(key), cog_profile, overview_resampling="average", in_memory=False, quiet=True)
    return key


def coarse(array: np.ndarray, k: int) -> np.ndarray:
    """NaN-aware k x k block mean of the last two axes (for the time-series grid)."""
    *lead, h, w = array.shape
    H, W = h // k, w // k
    a = array[..., : H * k, : W * k].reshape(*lead, H, k, W, k)
    with np.errstate(all="ignore"), np.testing.suppress_warnings() as sup:
        sup.filter(RuntimeWarning)
        return np.nanmean(a, axis=(-3, -1)).astype(np.float32)


def write_series(site_id: str, variable: str, stack_db: np.ndarray, dates: list[str], grid: dict, grid_m: float) -> dict:
    """Per-pixel series on a coarser grid. stack_db: (T, H, W) at grid resolution. Returns the manifest entry."""
    k = max(1, int(round(grid_m / grid["res"])))
    c = coarse(stack_db, k)  # (T, Hc, Wc)
    T, Hc, Wc = c.shape
    step = grid["res"] * k
    cols, rows = np.meshgrid(np.arange(Wc), np.arange(Hc))
    x = grid["x0"] + (cols + 0.5) * step
    y = grid["y0"] - (rows + 0.5) * step
    lon, lat = Transformer.from_crs(grid["epsg"], 4326, always_xy=True).transform(x, y)
    pid = (rows * Wc + cols).ravel()
    tables = []
    for t, d in enumerate(dates):
        v = c[t].ravel()
        ok = np.isfinite(v)
        if not ok.any():
            continue
        n = int(ok.sum())
        tables.append(
            pa.table(
                {
                    "pixel_id": pa.array(pid[ok], pa.int64()),
                    "lon": pa.array(np.asarray(lon).ravel()[ok], pa.float64()),
                    "lat": pa.array(np.asarray(lat).ravel()[ok], pa.float64()),
                    "date": pa.array([dt.date.fromisoformat(d)] * n, pa.date32()),
                    "variable": pa.array([variable] * n, pa.string()),
                    "value": pa.array(v[ok], pa.float32()),
                    "sigma": pa.nulls(n, pa.float32()),
                    "valid": pa.array(np.ones(n, bool), pa.bool_()),
                },
                schema=TS_SCHEMA,
            )
        )
    path = f"series/{variable}.parquet"
    pq.write_table(pa.concat_tables(tables), config.data.local_path(f"{site_id}/{path}"), compression="zstd")
    return {"variable": variable, "path": path, "unit": "dB", "grid_m": float(step)}


def write_manifest(site_id: str, manifest: dict) -> str:
    key = f"{site_id}/manifest.json"
    manifest = {**manifest, "generated_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    config.data.write_text(key, json.dumps(manifest, indent=1))
    return key


def prune(site_id: str, manifest: dict) -> list[str]:
    """Delete layer and series files from earlier runs that this manifest no longer lists."""
    keep = {f"{site_id}/layers/{l['id']}_{d}.tif" for l in manifest["layers"] for d in l["dates"]}
    keep |= {f"{site_id}/{s['path']}" for s in manifest["series"]}
    gone = []
    for sub in ("layers", "series"):
        for key in list(config.data.list(f"{site_id}/{sub}")):
            if key not in keep and not key.split("/")[-1].startswith("pred_"):  # Model outputs belong to ml/
                config.data.delete(key)
                gone.append(key)
    return gone
