"""Granule search against NASA's Common Metadata Repository (no login needed)."""
import json
import time

import requests

from . import config

CMR = "https://cmr.earthdata.nasa.gov/search/granules.umm_json"
_recent: dict[tuple, tuple[float, list]] = {}  # search results kept for 10 minutes


def _granule(item: dict, maturity: str, product: str = "GCOV") -> dict:
    u = item["umm"]
    aa = {a["Name"]: a["Values"] for a in u.get("AdditionalAttributes", [])}
    urls = [r["URL"] for r in u.get("RelatedUrls", []) if r["URL"].startswith("https")]
    ur = u["GranuleUR"]
    pts = u["SpatialExtent"]["HorizontalSpatialDomain"]["Geometry"]["GPolygons"][0]["Boundary"]["Points"]
    # Preview PNGs are public; their KML georeferencing sits under a different, login-protected path.
    previews, kmls = {}, {}
    for x in urls:
        for freq in ("A", "B"):
            for term in ("HHHH", "HVHV", "VVVV", "VHVH"):
                if x.endswith(f"_NATIVE_{freq}_{term}.png"):
                    previews[f"{freq}_{term}"] = x
                elif x.endswith(f"_NATIVE_{freq}_{term}.kml"):
                    kmls[f"{freq}_{term}"] = x
    return {
        "id": ur,
        "maturity": maturity,
        "product": product,
        "start": u["TemporalExtent"]["RangeDateTime"]["BeginningDateTime"],
        "date": u["TemporalExtent"]["RangeDateTime"]["BeginningDateTime"][:10],
        "stack": aa.get("STACK_ID", [""])[0],
        "track": int(aa.get("TRACK_NUMBER", ["0"])[0]),
        "frame": int(aa.get("FRAME_NUMBER", ["0"])[0]),
        "direction": aa.get("ASCENDING_DESCENDING", [""])[0].lower(),
        "polarizations": aa.get("FREQUENCY_A_POLARIZATION", []),
        "bandwidth_mhz": aa.get("RANGE_BANDWIDTH_CONCAT", [""])[0],
        "footprint": [[p["Longitude"], p["Latitude"]] for p in pts],
        # GUNW: one interferogram between a reference and a secondary Pass.
        "secondary_date": (aa.get("SECONDARY_ZERO_DOPPLER_START_TIME", [""])[0] or "")[:10] or None,
        "h5_url": next((x for x in urls if x.endswith(ur + ".h5")), None),
        "kml_urls": kmls,
        "preview_urls": previews,
    }


def _key(granule_id: str) -> str:
    return f"granules/{granule_id}.json"


def _remember(granule: dict) -> None:
    config.cache.write_text(_key(granule["id"]), json.dumps(granule))


def search(bbox: tuple[float, float, float, float], start: str, end: str, product: str = "GCOV") -> list[dict]:
    """All calibrated Granules of one product touching bbox (west, south, east, north) between two dates."""
    key = (tuple(round(v, 3) for v in bbox), start, end, product)
    hit = _recent.get(key)
    if hit and time.time() - hit[0] < 600:
        return hit[1]
    out = []
    for maturity, cid in config.PRODUCT_COLLECTIONS[product].items():
        params = {
            "collection_concept_id": cid,
            "bounding_box": ",".join(str(v) for v in bbox),
            "temporal": f"{start}T00:00:00Z,{end}T23:59:59Z",
            "page_size": 500,
            "sort_key": "start_date",
        }
        items = []
        while True:  # page through results; CMR returns a search-after token
            r = requests.get(CMR, params=params, headers=headers if items else {}, timeout=60)
            r.raise_for_status()
            page = r.json()["items"]
            items += page
            token = r.headers.get("CMR-Search-After")
            if len(page) < params["page_size"] or not token:
                break
            headers = {"CMR-Search-After": token}
        for item in items:
            s = _granule(item, maturity, product)
            if s["h5_url"]:
                _remember(s)
                out.append(s)
    out.sort(key=lambda s: s["start"])
    _recent[key] = (time.time(), out)
    return out


def get(granule_id: str) -> dict:
    """One Granule by its name, from the cache if seen before."""
    if config.cache.exists(_key(granule_id)):
        return json.loads(config.cache.read_text(_key(granule_id)))
    product = granule_id.split("_")[3] if granule_id.count("_") > 3 else "GCOV"
    for maturity, cid in config.PRODUCT_COLLECTIONS.get(product, config.COLLECTIONS).items():
        r = requests.get(CMR, params={"collection_concept_id": cid, "granule_ur": granule_id}, timeout=60)
        r.raise_for_status()
        items = r.json()["items"]
        if items:
            s = _granule(items[0], maturity, product)
            _remember(s)
            return s
    raise KeyError(granule_id)


def public(granule: dict) -> dict:
    """Granule record without the raw archive links."""
    return {k: v for k, v in granule.items() if k not in ("h5_url", "kml_urls", "preview_urls")} | {
        "previews": sorted(granule["preview_urls"])
    }
