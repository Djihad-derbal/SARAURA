"""How much of a site each Granule (and Stack) actually covers. Stacks are ranked by coverage first:
a Stack with many Passes that only clips the site is useless (Venezuela: 054_D_083 covered 2%)."""
from __future__ import annotations

from shapely.geometry import Polygon, box

MIN_COVERAGE = 0.5  # below this share of the site, a Stack is not offered for processing


def share(granule: dict, bbox) -> float:
    site = box(*bbox)
    try:
        return round(Polygon(granule["footprint"]).intersection(site).area / site.area, 3)
    except Exception:  # degenerate footprint
        return 0.0


def stack_coverage(granules: list[dict], bbox) -> dict[str, float]:
    """Best coverage per Stack (Granules of one Stack share a frame footprint)."""
    out: dict[str, float] = {}
    for g in granules:
        out[g["stack"]] = max(out.get(g["stack"], 0.0), share(g, bbox))
    return out
