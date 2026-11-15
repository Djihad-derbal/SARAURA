"""Exposure context for Questions: what lies on the ground (OpenStreetMap, ODbL).

    lines   railway=subway|light_rail|tram, waterway=canal|drain   (Mexico City: Metro, light rail, Gran Canal)
    places  place=city|town|village|hamlet|suburb|neighbourhood|quarter (points)
    roads   highway=trunk..unclassified
    fields  landuse=farmland|orchard|meadow|vineyard|greenhouse_horticulture (polygons; Jijel: burned farms, A5)
    water   water=reservoir (polygons, multipolygon relations stitched) and waterway=river (lines; A7)
    camps   tourism=camp_site|lodge|hotel|guest_house|chalet and aeroway=aerodrome|airstrip (points at their centre;
            Okavango: safari camps and the airstrips that serve them)
    tracks  highway=track plus the roads above (lines; Okavango: game-drive and village tracks that flood)

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
    "fields": 'way["landuse"~"^(farmland|orchard|meadow|vineyard|greenhouse_horticulture)$"]({b});',
    "water": 'way["water"="reservoir"]({b});relation["water"="reservoir"]({b});way["waterway"="river"]({b});',
    "camps": 'nwr["tourism"~"^(camp_site|lodge|hotel|guest_house|chalet)$"]({b});nwr["aeroway"~"^(aerodrome|airstrip)$"]({b});',
    "tracks": 'way["highway"~"^(track|trunk|primary|secondary|tertiary|unclassified|trunk_link|primary_link)$"]({b});',
}
AREA_KINDS = {"fields", "water"}  # closed ways become polygons
CENTRE_KINDS = {"camps"}  # every element becomes one point at its centre


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


def stitch_rings(parts: list[list]) -> list[list]:
    """Join open ways that share end points into closed rings (outer members of a multipolygon relation)."""
    parts = [list(p) for p in parts if len(p) >= 2]
    rings = []
    while parts:
        ring = parts.pop(0)
        grown = True
        while ring[0] != ring[-1] and grown:
            grown = False
            for i, p in enumerate(parts):
                if p[0] == ring[-1]:
                    ring += p[1:]
                elif p[-1] == ring[-1]:
                    ring += p[::-1][1:]
                elif p[-1] == ring[0]:
                    ring = p[:-1] + ring
                elif p[0] == ring[0]:
                    ring = p[::-1][:-1] + ring
                else:
                    continue
                parts.pop(i)
                grown = True
                break
        if len(ring) >= 4:
            if ring[0] != ring[-1]:
                ring.append(ring[0])  # cut by the query box: close it
            rings.append(ring)
    return rings


def _to_geojson(kind: str, data: dict) -> dict:
    feats = []
    for el in data.get("elements", []):
        tags = el.get("tags", {})
        props = {
            "osm_id": f"{el['type']}/{el['id']}",
            "name": tags.get("name:en") or tags.get("name:fr") or tags.get("name") or tags.get("ref") or "",
            "name_local": tags.get("name", ""),
            "ref": tags.get("ref", ""),
            "class": tags.get("railway") or tags.get("waterway") or tags.get("place") or tags.get("highway") or tags.get("landuse") or tags.get("water")
                     or tags.get("tourism") or tags.get("aeroway") or "",
        }
        if kind in CENTRE_KINDS:
            c = el.get("center") or ({"lon": el["lon"], "lat": el["lat"]} if "lon" in el else None)
            if c:
                feats.append({"type": "Feature", "properties": props, "geometry": {"type": "Point", "coordinates": [c["lon"], c["lat"]]}})
        elif el["type"] == "node":
            feats.append({"type": "Feature", "properties": props, "geometry": {"type": "Point", "coordinates": [el["lon"], el["lat"]]}})
        elif el["type"] == "relation":
            outers = [[[p["lon"], p["lat"]] for p in mb["geometry"]] for mb in el.get("members", [])
                      if mb.get("role") == "outer" and mb.get("geometry")]
            rings = stitch_rings(outers)
            if rings:
                feats.append({"type": "Feature", "properties": props, "geometry": {"type": "MultiPolygon", "coordinates": [[r] for r in rings]}})
        elif el.get("geometry"):
            coords = [[p["lon"], p["lat"]] for p in el["geometry"]]
            if kind in AREA_KINDS and len(coords) >= 4 and coords[0] == coords[-1]:
                feats.append({"type": "Feature", "properties": props, "geometry": {"type": "Polygon", "coordinates": [coords]}})
            elif len(coords) >= 2:
                feats.append({"type": "Feature", "properties": props, "geometry": {"type": "LineString", "coordinates": coords}})
    return {"type": "FeatureCollection", "features": feats, "attribution": "© OpenStreetMap contributors, ODbL"}


def load(site_id: str, bbox, kind: str, refresh: bool = False, log=print) -> dict:
    """GeoJSON FeatureCollection of one context kind over the bbox, fetched once and kept on disk."""
    key = _key(site_id, kind)
    if config.data.exists(key) and not refresh:
        return json.loads(config.data.read_text(key))
    w, s, e, n = bbox
    b = f"{s},{w},{n},{e}"
    out = "out center tags;" if kind in CENTRE_KINDS else "out geom;"
    body = f"[out:json][timeout:150];({QUERIES[kind].format(b=b)});{out}"
    t0 = time.time()
    fc = _to_geojson(kind, _overpass(body))
    config.data.write_text(key, json.dumps(fc))
    log(f"  OpenStreetMap {kind}: {len(fc['features'])} features ({time.time() - t0:.0f} s)")
    return fc
