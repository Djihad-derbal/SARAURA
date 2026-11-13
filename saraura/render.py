"""Turn GCOV pixels into web-map tiles and point samples."""
import io
import math
from functools import lru_cache

import numpy as np
from PIL import Image
from pyproj import Transformer

from . import config, gcov

TILE = 256
EARTH = 6378137.0
# Default display ranges in dB (gamma0), chosen from the August 2026 Passes.
DB_RANGE = {"HHHH": (-20.0, 0.0), "VVVV": (-20.0, 0.0), "HVHV": (-26.0, -6.0), "VHVH": (-26.0, -6.0)}
TERM = {"HH": "HHHH", "HV": "HVHV", "VV": "VVVV", "VH": "VHVH"}


@lru_cache(maxsize=16)
def _to_grid(epsg: int) -> Transformer:
    return Transformer.from_crs(4326, epsg, always_xy=True)


def _tile_lonlat(z: int, x: int, y: int):
    """Longitude and latitude of every pixel centre in a tile."""
    n = 2.0**z
    px = (x + (np.arange(TILE) + 0.5) / TILE) / n
    py = (y + (np.arange(TILE) + 0.5) / TILE) / n
    lon = px * 360.0 - 180.0
    lat = np.degrees(np.arctan(np.sinh(math.pi * (1 - 2 * py))))
    return np.meshgrid(lon, lat)


def pick_freq(granule_id: str, z: int) -> str:
    freqs = gcov.index(granule_id)["freqs"]
    if z >= config.DETAIL_MIN_ZOOM or "B" not in freqs:
        return "A"
    return "B"


def _block_mean(a: np.ndarray, k: int) -> np.ndarray:
    if k <= 1:
        return a
    h, w = (a.shape[0] // k) * k, (a.shape[1] // k) * k
    if h == 0 or w == 0:
        return a
    b = a[:h, :w].reshape(h // k, k, w // k, k)
    ok = np.isfinite(b)
    n = ok.sum(axis=(1, 3))
    s = np.where(ok, b, 0).sum(axis=(1, 3))
    return np.where(n > 0, s / np.maximum(n, 1), np.nan).astype(np.float32)


def sample_tile(granule_id: str, term: str, z: int, x: int, y: int, smooth_m: float = 0.0):
    """Linear backscatter resampled onto a 256 x 256 web-mercator tile, or None if the tile misses the Granule.

    Data finer than the tile (or than smooth_m metres) is averaged first, which
    is also what tames radar speckle.
    """
    freq = pick_freq(granule_id, z)
    fm = gcov.index(granule_id)["freqs"][freq]
    lon, lat = _tile_lonlat(z, x, y)
    gx, gy = _to_grid(fm["epsg"]).transform(lon, lat)
    col = (gx - fm["x0"]) / fm["dx"]
    row = (gy - fm["y0"]) / fm["dy"]
    rows, cols = fm["shape"]
    r0, r1 = int(math.floor(row.min())), int(math.ceil(row.max())) + 1
    c0, c1 = int(math.floor(col.min())), int(math.ceil(col.max())) + 1
    if r1 <= 0 or c1 <= 0 or r0 >= rows or c0 >= cols:
        return None
    tile_res = 2 * math.pi * EARTH * math.cos(math.radians(float(lat.mean()))) / (TILE * 2.0**z)
    k = max(1, int(max(tile_res, smooth_m) / abs(fm["dx"])))
    # Align the window to multiples of k so neighbouring tiles average the same cells.
    r0, c0 = (r0 // k) * k, (c0 // k) * k
    r1, c1 = -(-r1 // k) * k, -(-c1 // k) * k
    win = _block_mean(gcov.read_window(granule_id, freq, term, r0, r1, c0, c1), k)
    ri = np.clip(((row - r0) / k).astype(np.int64), 0, win.shape[0] - 1)
    ci = np.clip(((col - c0) / k).astype(np.int64), 0, win.shape[1] - 1)
    out = win[ri, ci]
    out[(row < 0) | (row >= rows) | (col < 0) | (col >= cols)] = np.nan
    return out


def to_db(a: np.ndarray) -> np.ndarray:
    with np.errstate(divide="ignore", invalid="ignore"):
        return 10.0 * np.log10(np.where(a > 0, a, np.nan))


def _png(rgba: np.ndarray) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(rgba, "RGBA").save(buf, "PNG", compress_level=3)
    return buf.getvalue()


EMPTY_TILE = _png(np.zeros((TILE, TILE, 4), np.uint8))


def backscatter_tile(granule_id, term, z, x, y, lo=None, hi=None) -> bytes:
    a = sample_tile(granule_id, term, z, x, y)
    if a is None:
        return EMPTY_TILE
    d = to_db(a)
    lo = DB_RANGE[term][0] if lo is None else lo
    hi = DB_RANGE[term][1] if hi is None else hi
    g = np.clip((d - lo) / (hi - lo), 0, 1)
    v = (np.nan_to_num(g) * 255).astype(np.uint8)
    alpha = np.where(np.isfinite(d), 255, 0).astype(np.uint8)
    return _png(np.dstack([v, v, v, alpha]))


def composite_tile(granule_id, z, x, y) -> bytes:
    """False colour from one pass: red = HH, green = HV, blue = HH/HV ratio."""
    hh = sample_tile(granule_id, "HHHH", z, x, y)
    hv = sample_tile(granule_id, "HVHV", z, x, y)
    if hh is None or hv is None:
        return EMPTY_TILE
    dhh, dhv = to_db(hh), to_db(hv)
    r = np.clip((dhh + 20) / 20, 0, 1)
    g = np.clip((dhv + 26) / 20, 0, 1)
    b = np.clip((dhh - dhv - 2) / 12, 0, 1)
    ok = np.isfinite(dhh) & np.isfinite(dhv)
    rgb = (np.nan_to_num(np.dstack([r, g, b])) * 255).astype(np.uint8)
    return _png(np.dstack([rgb, np.where(ok, 255, 0).astype(np.uint8)]))


def change_db(before_id, after_id, term, z, x, y, smooth_m=50.0):
    """After minus before, in dB, on the tile grid. Positive means brighter."""
    a = sample_tile(before_id, term, z, x, y, smooth_m)
    b = sample_tile(after_id, term, z, x, y, smooth_m)
    if a is None or b is None:
        return None
    return to_db(b) - to_db(a)


def change_tile(before_id, after_id, term, z, x, y, scale=6.0, floor=1.5) -> bytes:
    """Red where backscatter fell, blue where it rose; transparent where |change| < floor dB."""
    d = change_db(before_id, after_id, term, z, x, y)
    if d is None:
        return EMPTY_TILE
    mag = np.clip((np.abs(d) - floor) / (scale - floor), 0, 1)
    mag = np.nan_to_num(mag)
    drop = np.nan_to_num(d) < 0
    rgba = np.zeros((TILE, TILE, 4), np.uint8)
    rgba[..., 0] = np.where(drop, 239, 37)
    rgba[..., 1] = np.where(drop, 68, 139)
    rgba[..., 2] = np.where(drop, 68, 235)
    rgba[..., 3] = (np.sqrt(mag) * 230).astype(np.uint8)
    return _png(rgba)


def sample_point(granule_id: str, lon: float, lat: float, radius_m: float = 50.0) -> dict:
    """Mean backscatter in dB in a small square around a point, per polarization."""
    fm = gcov.index(granule_id)["freqs"]["A"]
    gx, gy = _to_grid(fm["epsg"]).transform(lon, lat)
    col = int(round((gx - fm["x0"]) / fm["dx"]))
    row = int(round((gy - fm["y0"]) / fm["dy"]))
    n = max(1, int(round(radius_m / abs(fm["dx"]))))
    out = {}
    for term in fm["terms"]:
        w = gcov.read_window(granule_id, "A", term, row - n, row + n + 1, col - n, col + n + 1)
        ok = np.isfinite(w) & (w > 0)
        out[term[:2]] = round(float(10 * np.log10(w[ok].mean())), 2) if ok.any() else None
    return out
