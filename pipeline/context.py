"""Exposure context for Questions: what lies on the ground (OpenStreetMap, ODbL).

    lines   railway=subway|light_rail|tram, waterway=canal|drain   (Mexico City: Metro, light rail, Gran Canal)
    places  place=city|town|village|hamlet|suburb|neighbourhood|quarter (points)
    roads   highway=trunk..unclassified

Fetched once per site from the public Overpass API with a generic client name, and kept as GeoJSON under
data/<site_id>/context/<kind>.geojson so rebuilds and the API never refetch. Only the site's bbox is sent.
"""
from __future__ import annotations

import json
import time

import requests

from saraura import config

OVERPASS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]
HEADERS = {"User-Agent": "SARAURA/1.0 (NASA Space Apps 2026 open-source app)"}

QUERIES = {
    "lines": 'way["railway"~"^(subway|light_rail|tram)$"]({b});way["waterway"~"^(canal|drain)$"]({b});',
    "places": 'node["place"~"^(city|town|village|hamlet|suburb|neighbourhood|quarter)$"]({b});',
    "roads": 'way["highway"~"^(trunk|primary|secondary|tertiary|unclassified|trunk_link|primary_link)$"]({b});',
}


def _key(site_id: str, kind: str) -> str:
    return f"{site_id}/context/{kind}.geojson"


def _overpass(body: str) -> dict:
    last = None
    for url in OVERPASS:
        for attempt in range(2):
            try:
                r = requests.post(url, data={"data": body}, headers=HEADERS, timeout=180)
                if r.status_code == 200:
                    return r.json()
                last = f"{url}: HTTP {r.status_code}"
            except requests.RequestException as e:
                last = f"{url}: {e}"
            time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"Overpass failed ({last})")


def _to_geojson(kind: str, data: dict) -> dict:
    feats = []
    for el in data.get("elements", []):
        tags = el.get("tags", {})
        props = {
            "osm_id": f"{el['type']}/{el['id']}",
            "name": tags.get("name:en") or tags.get("name:fr") or tags.get("name") or tags.get("ref") or "",
            "name_local": tags.get("name", ""),
            "ref": tags.get("ref", ""),
            "class": tags.get("railway") or tags.get("waterway") or tags.get("place") or tags.get("highway") or "",
        }
        if el["type"] == "node":
            feats.append({"type": "Feature", "properties": props, "geometry": {"type": "Point", "coordinates": [el["lon"], el["lat"]]}})
        elif el.get("geometry"):
            coords = [[p["lon"], p["lat"]] for p in el["geometry"]]
            if len(coords) >= 2:
                feats.append({"type": "Feature", "properties": props, "geometry": {"type": "LineString", "coordinates": coords}})
    return {"type": "FeatureCollection", "features": feats, "attribution": "© OpenStreetMap contributors, ODbL"}


def load(site_id: str, bbox, kind: str, refresh: bool = False, log=print) -> dict:
    """GeoJSON FeatureCollection of one context kind over the bbox, fetched once and kept on disk."""
    key = _key(site_id, kind)
    if config.data.exists(key) and not refresh:
        return json.loads(config.data.read_text(key))
    w, s, e, n = bbox
    b = f"{s},{w},{n},{e}"
    body = f"[out:json][timeout:150];({QUERIES[kind].format(b=b)});out geom;"
    t0 = time.time()
    fc = _to_geojson(kind, _overpass(body))
    config.data.write_text(key, json.dumps(fc))
    log(f"  OpenStreetMap {kind}: {len(fc['features'])} features ({time.time() - t0:.0f} s)")
    return fc
