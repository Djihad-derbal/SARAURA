"""DEM step: Copernicus GLO-30 crop, slope, and heightmaps for the 3D study view.

Reads the public Copernicus DEM COGs on AWS (no login), reprojects onto the site's analysis grid,
and writes:
  layers/slope_<date>.tif                  slope in degrees (input feature for Models)
  terrain/dem.f32                           heightmap, row-major float32, at most 512 x 512
  terrain/disp_<YYYY-MM-DD>.f32             cumulative LOS displacement on the same heightmap grid (cm)
  terrain/meta.json                         shape, bbox, CRS, height range, dates
"""
from __future__ import annotations

import json
import math

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.merge import merge
from rasterio.transform import from_origin
from rasterio.warp import reproject

from saraura import config

from . import export
from .layers import LAYERS, entry

COP30 = "https://copernicus-dem-30m.s3.amazonaws.com/{name}/{name}.tif"
MAX_SIDE = 512

LAYERS["slope"] = {
    "label": "Terrain slope",
    "unit": "degrees",
    "colormap": "magma",
    "range": [0, 45],
    "what_this_shows": "Steepness of the ground from the Copernicus 30 m elevation model. Steep slopes distort radar and are more prone to landslides.",
}


def _tile_name(lat: int, lon: int) -> str:
    ns, ew = ("N" if lat >= 0 else "S"), ("E" if lon >= 0 else "W")
    return f"Copernicus_DSM_COG_10_{ns}{abs(lat):02d}_00_{ew}{abs(lon):03d}_00_DEM"


def fetch_dem(bbox, grid: dict) -> np.ndarray:
    """Copernicus GLO-30 heights (m) resampled onto `grid` (epsg, x0, y0, res, shape)."""
    w, s, e, n = bbox
    names = [_tile_name(la, lo) for la in range(math.floor(s), math.floor(n) + 1) for lo in range(math.floor(w), math.floor(e) + 1)]
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", GDAL_HTTP_MAX_RETRY="3"):
        sources = []
        for name in names:
            try:
                sources.append(rasterio.open(COP30.format(name=name)))
            except rasterio.RasterioIOError:
                pass  # ocean tiles do not exist
        if not sources:
            raise RuntimeError(f"No Copernicus DEM tiles for bbox {bbox}")
        pad = 0.01
        mosaic, transform = merge(sources, bounds=(w - pad, s - pad, e + pad, n + pad))
        crs = sources[0].crs
        for src in sources:
            src.close()
    H, W = grid["shape"]
    out = np.full((H, W), np.nan, np.float32)
    reproject(
        mosaic[0].astype(np.float32), out,
        src_transform=transform, src_crs=crs,
        dst_transform=from_origin(grid["x0"], grid["y0"], grid["res"], grid["res"]), dst_crs=f"EPSG:{grid['epsg']}",
        resampling=Resampling.bilinear, src_nodata=-32767.0, dst_nodata=np.nan,
    )
    return out


def slope_deg(dem: np.ndarray, res: float) -> np.ndarray:
    gy, gx = np.gradient(dem, res)
    return np.degrees(np.arctan(np.hypot(gx, gy))).astype(np.float32)


def _shrink(a: np.ndarray, side: int) -> np.ndarray:
    """Block-mean down to at most side x side (keeps the aspect ratio)."""
    k = max(1, math.ceil(max(a.shape) / side))
    if k == 1:
        return a.astype(np.float32)
    return export.coarse(a[None], k)[0]


def process(site: dict, grid: dict, slope_date: str, disp: dict[str, np.ndarray] | None = None, log=print) -> dict:
    """Write slope, and (for 3D sites) heightmaps. `disp` maps date -> cumulative displacement (cm) on `grid`."""
    sid = site["id"]
    dem = fetch_dem(site["bbox"], grid)
    log(f"  DEM {dem.shape[0]} x {dem.shape[1]}, {np.nanmin(dem):.0f} to {np.nanmax(dem):.0f} m")
    export.write_cog(sid, f"slope_{slope_date}", slope_deg(dem, grid["res"]), grid)
    layers = [entry("slope", [slope_date], kind="context")]
    terrain = None
    if site["view"] == "3d":
        h = _shrink(dem, MAX_SIDE)
        config.data.write_bytes(f"{sid}/terrain/dem.f32", np.nan_to_num(h, nan=float(np.nanmin(h))).astype("<f4").tobytes())
        dates = []
        for d, arr in sorted((disp or {}).items()):
            config.data.write_bytes(f"{sid}/terrain/disp_{d}.f32", np.nan_to_num(_shrink(arr, MAX_SIDE), nan=0.0).astype("<f4").tobytes())
            dates.append(d)
        meta = {
            "shape": list(h.shape),
            "crs": f"EPSG:{grid['epsg']}",
            "bounds": [grid["x0"], grid["y0"] - grid["shape"][0] * grid["res"], grid["x0"] + grid["shape"][1] * grid["res"], grid["y0"]],
            "bbox": site["bbox"],
            "cell_m": grid["res"] * max(1, math.ceil(max(dem.shape) / MAX_SIDE)),
            "height_m": [round(float(np.nanmin(h)), 1), round(float(np.nanmax(h)), 1)],
            "dtype": "float32 little-endian, row-major, north row first",
            "displacement_unit": "cm (line of sight, positive toward satellite)",
            "dates": dates,
        }
        config.data.write_text(f"{sid}/terrain/meta.json", json.dumps(meta, indent=1))
        terrain = {"meta": "terrain/meta.json", "dates": dates}
        log(f"  heightmap {h.shape[0]} x {h.shape[1]} with {len(dates)} displacement dates")
    return {"layers": layers, "terrain": terrain}
