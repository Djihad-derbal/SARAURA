"""Training labels from Sentinel-2 optical imagery ("optical teaches radar").

Builds a cloud-free composite before and after an event, then labels each cell
from the change in three spectral indices. The labels are weak: they are only
as good as the thresholds and the clear-sky coverage, which is why evaluation
keeps a held-out area and why cells we cannot judge get the IGNORE label.

Checked on a real scene (2026-09-07, tile 32SKF): asset names are right, and
scenes flagged earthsearch:boa_offset_applied already have the +1000 offset
removed (open water reads about 0.007), so no further offset is applied.
"""
import numpy as np

from .const import IGNORE

STAC = "https://earth-search.aws.element84.com/v1"
COLLECTION = "sentinel-2-l2a"
BANDS = ["green", "red", "nir", "nir08", "swir16", "swir22"]
BAD_SCL = [0, 1, 3, 8, 9, 10, 11]  # no data, saturated, shadow, clouds, cirrus, snow


def composite(grid: dict, bbox, start: str, end: str, max_cloud: int = 40, per_tile: int = 3, tiles=None) -> dict:
    """Median reflectance per band on the radar grid, from clear pixels between two dates."""
    import rasterio
    from affine import Affine
    from pystac_client import Client
    from rasterio.enums import Resampling
    from rasterio.vrt import WarpedVRT

    items = list(Client.open(STAC).search(collections=[COLLECTION], bbox=list(bbox), datetime=f"{start}/{end}", query={"eo:cloud_cover": {"lt": max_cloud}}).items())
    # Keep the clearest few scenes of every Sentinel-2 tile, so each part of the area is covered.
    if tiles:  # optional: restrict to named Sentinel-2 tiles, e.g. ["MGRS-32SKF"], to avoid reading overlapping ones
        items = [it for it in items if it.properties.get("grid:code") in tiles]
    items.sort(key=lambda it: it.properties.get("eo:cloud_cover", 100))
    seen: dict[str, int] = {}
    chosen = []
    for it in items:
        tile = it.properties.get("grid:code") or it.properties.get("s2:mgrs_tile") or it.id[:9]
        if seen.get(tile, 0) < per_tile:
            seen[tile] = seen.get(tile, 0) + 1
            chosen.append(it)
    items = chosen
    print(f"  Sentinel-2 {start}..{end}: {len(items)} scenes over tiles {sorted(seen)}")
    if not items:
        raise RuntimeError(f"No Sentinel-2 scenes between {start} and {end}")
    h, w = grid["shape"]
    target = dict(crs=f"EPSG:{grid['epsg']}", transform=Affine(grid["res"], 0, grid["x0"], 0, -grid["res"], grid["y0"]), width=w, height=h)

    def read(href, resampling):
        with rasterio.open(href) as src, WarpedVRT(src, resampling=resampling, **target) as vrt:
            return vrt.read(1)

    stack = {b: [] for b in BANDS}
    with rasterio.Env(AWS_NO_SIGN_REQUEST="YES", GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR"):
        for it in items:
            scl = read(it.assets["scl"].href, Resampling.nearest)
            bad = np.isin(scl, BAD_SCL)
            # Processing baseline 04.00 and later adds 1000 to every value; earth-search flags scenes where it was removed.
            offset = 0.0 if it.properties.get("earthsearch:boa_offset_applied") else -0.1
            for b in BANDS:
                raw = read(it.assets[b].href, Resampling.bilinear).astype(np.float32)
                refl = raw * 1e-4 + offset
                refl[bad | (raw == 0)] = np.nan
                stack[b].append(refl)
    with np.errstate(all="ignore"):
        return {b: np.nanmedian(np.stack(v), 0) for b, v in stack.items()}


def _nd(a, b):
    with np.errstate(all="ignore"):
        return (a - b) / (a + b)


def classify(pre: dict, post: dict) -> np.ndarray:
    """Class per cell: 0 stable, 1 burned, 2 vegetation lost, 3 vegetation grew, 4 water appeared, 5 water receded."""
    nbr0, nbr1 = _nd(pre["nir08"], pre["swir22"]), _nd(post["nir08"], post["swir22"])
    ndvi0, ndvi1 = _nd(pre["nir"], pre["red"]), _nd(post["nir"], post["red"])
    w0, w1 = _nd(pre["green"], pre["swir16"]), _nd(post["green"], post["swir16"])  # MNDWI
    y = np.zeros(nbr0.shape, np.uint8)
    y[(ndvi1 - ndvi0 <= -0.2) & (ndvi0 >= 0.3)] = 2
    y[(ndvi1 - ndvi0 >= 0.2)] = 3
    y[(nbr0 - nbr1 >= 0.27) & (ndvi0 >= 0.3) & (w1 < 0)] = 1  # dNBR at or above moderate-low severity, on vegetation
    y[(w0 < 0) & (w1 > 0.1)] = 4
    y[(w0 > 0.1) & (w1 < 0)] = 5
    y[~(np.isfinite(nbr0) & np.isfinite(nbr1) & np.isfinite(ndvi0) & np.isfinite(ndvi1) & np.isfinite(w0) & np.isfinite(w1))] = IGNORE
    return y


def build(grid: dict, bbox, pre: tuple[str, str], post: tuple[str, str], tiles=None) -> np.ndarray:
    return classify(composite(grid, bbox, *pre, tiles=tiles), composite(grid, bbox, *post, tiles=tiles))
