"""Questions -> answers: one evidence pass per site, many questions, several solutions each (ADR-0008).

    python -m pipeline.answers mexico_city_subsidence
    python -m pipeline.answers --all

For a built Showcase Site, this
  1. derives evidence layers (pipeline/evidence.py) and loads OpenStreetMap context (pipeline/context.py),
  2. runs each Question for the site's Lens (questions/*.yaml) through its named recipe below,
  3. writes one map per Question (layers/ans_<question>_<date>.tif, kind "answer"), a ranked list where the
     Question has one, and data/<site_id>/answers/answers.json with the classes, areas, headline, solutions,
     sources and limits; the manifest lists the new layers.

Recipes are rules with thresholds read from the Question file, so every class on the map can be explained at
any spot (`at_point`). No Model runs here: Model outputs are only read as evidence on Showcase Sites (ADR-0001).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import sys
from functools import lru_cache

import numpy as np
import rasterio
import yaml

from saraura import config

from . import context, evidence, export

QUESTIONS_DIR = config.ROOT / "questions"
SOLUTIONS_FILE = config.ROOT / "solutions" / "catalogue.yaml"
TOP_ROWS = 25
COMPASS = ["north", "north-east", "east", "south-east", "south", "south-west", "west", "north-west"]


# ---------------------------------------------------------------- question files


@lru_cache(maxsize=1)
def _all_questions() -> tuple:
    out = []
    for p in sorted(QUESTIONS_DIR.glob("*.yaml")):
        if p.stem != "roles":
            out.append(yaml.safe_load(p.read_text(encoding="utf-8")))
    return tuple(out)


def questions(lens: str | None) -> list[dict]:
    return sorted([q for q in _all_questions() if q["lens"] == lens], key=lambda q: q["order"])


@lru_cache(maxsize=1)
def solutions() -> dict:
    return yaml.safe_load(SOLUTIONS_FILE.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def roles() -> dict:
    return yaml.safe_load((QUESTIONS_DIR / "roles.yaml").read_text(encoding="utf-8"))


# ---------------------------------------------------------------- geometry helpers


class Geo:
    """Lon/lat <-> pixel on one analysis grid."""

    def __init__(self, grid: dict):
        from pyproj import Transformer

        self.g = grid
        self.fwd = Transformer.from_crs(4326, grid["epsg"], always_xy=True)
        self.inv = Transformer.from_crs(grid["epsg"], 4326, always_xy=True)

    def rc(self, x, y):
        g = self.g
        c = np.floor((np.asarray(x, float) - g["x0"]) / g["res"]).astype(int)
        r = np.floor((g["y0"] - np.asarray(y, float)) / g["res"]).astype(int)
        return r, c

    def rc_lonlat(self, lon, lat):
        return self.rc(*self.fwd.transform(lon, lat))

    def lonlat(self, r, c):
        g = self.g
        x = g["x0"] + (np.asarray(c, float) + 0.5) * g["res"]
        y = g["y0"] - (np.asarray(r, float) + 0.5) * g["res"]
        return self.inv.transform(x, y)

    def inside(self, r, c):
        H, W = self.g["shape"]
        return (r >= 0) & (r < H) & (c >= 0) & (c < W)

    def sample(self, a: np.ndarray, r, c):
        r, c = np.asarray(r), np.asarray(c)
        ok = self.inside(r, c)
        out = np.full(r.shape, np.nan, np.float32)
        out[ok] = a[r[ok], c[ok]]
        return out


def densify(xy: np.ndarray, step: float):
    """Points every `step` metres along a projected polyline, with distance along it."""
    pts, dist, total = [], [], 0.0
    for (x0, y0), (x1, y1) in zip(xy[:-1], xy[1:]):
        L = math.hypot(x1 - x0, y1 - y0)
        n = max(1, int(L // step))
        for k in range(n):
            t = k / n
            pts.append((x0 + t * (x1 - x0), y0 + t * (y1 - y0)))
            dist.append(total + t * L)
        total += L
    pts.append(tuple(xy[-1]))
    dist.append(total)
    return np.asarray(pts), np.asarray(dist)


def line_coords(geo: Geo, pts: np.ndarray, step: int = 2) -> list:
    """Projected points of a segment back to rounded lon/lat, thinned, for drawing on the map."""
    idx = sorted(set(list(range(0, len(pts), step)) + [len(pts) - 1]))
    lon, lat = geo.inv.transform(pts[idx, 0], pts[idx, 1])
    return [[round(float(a), 5), round(float(b), 5)] for a, b in zip(np.atleast_1d(lon), np.atleast_1d(lat))]


def project_lines(geo: Geo, fc: dict):
    for f in fc["features"]:
        if f["geometry"]["type"] != "LineString":
            continue
        lon, lat = np.asarray(f["geometry"]["coordinates"]).T
        x, y = geo.fwd.transform(lon, lat)
        yield f["properties"], np.stack([x, y], axis=1)


def points_of(geo: Geo, fc: dict, classes: tuple[str, ...]):
    for f in fc["features"]:
        if f["geometry"]["type"] == "Point" and f["properties"]["class"] in classes:
            lon, lat = f["geometry"]["coordinates"]
            yield f["properties"], lon, lat


def dilate(a: np.ndarray) -> np.ndarray:
    from scipy.ndimage import grey_dilation

    return np.maximum(a, grey_dilation(a, size=3))


def disc(radius_px: int) -> np.ndarray:
    yy, xx = np.mgrid[-radius_px:radius_px + 1, -radius_px:radius_px + 1]
    return (xx**2 + yy**2) <= radius_px**2


def compass(dx: float, dy: float) -> str:
    return COMPASS[int(((math.degrees(math.atan2(dx, dy)) + 360 + 22.5) % 360) // 45)]


def _f(v, nd=0) -> str:
    return "n/a" if v is None or not np.isfinite(v) else f"{v:,.{nd}f}"


def _pct(n, d) -> float:
    return round(100.0 * n / d, 1) if d else 0.0


# ---------------------------------------------------------------- subsidence recipes


def _sub_masks(E: dict, T: dict):
    v, se, coh, years = E["vert_vel_cm_yr"], E["fit_se_cm_yr"], E["mean_coherence"], E["tilt_years_500"]
    measured = np.isfinite(v)
    unknown = measured & ((coh < T["min_coherence"]) | ~(se <= T["max_fit_se_cm_yr"]) | ~np.isfinite(years))
    return measured, unknown


def safe_to_build(ctx: dict, q: dict) -> dict:
    E, T = ctx["E"], q["thresholds"]
    v, years, acc = E["vert_vel_cm_yr"], E["tilt_years_500"], E["accel_cm_yr2"]
    measured, unknown = _sub_masks(E, T)
    speed = np.abs(v)
    with np.errstate(invalid="ignore"):
        red = (years < T["red_years"]) | (speed > T["red_speed_cm_yr"])
        amber = (years < T["amber_years"]) | (speed > T["amber_speed_cm_yr"]) | (acc < -T["accel_cm_yr2"])
    cls = np.zeros(v.shape, np.uint8)
    cls[measured] = 1
    cls[measured & amber] = 2
    cls[measured & red] = 3
    cls[unknown] = 4
    ctx["m1_class"] = cls
    # ranked: neighbourhoods with the most red ground within 500 m
    geo, rows = ctx["geo"], []
    rad = max(1, int(round(500 / geo.g["res"])))
    k = disc(rad)
    for props, lon, lat in points_of(geo, ctx["places"], ("suburb", "neighbourhood", "quarter", "town", "city")):
        if not props["name"]:
            continue
        r, c = geo.rc_lonlat(lon, lat)
        if not geo.inside(r, c):
            continue
        r0, r1, c0, c1 = max(0, r - rad), r + rad + 1, max(0, c - rad), c + rad + 1
        win = cls[r0:r1, c0:c1]
        kk = k[(r0 - (r - rad)):(r0 - (r - rad)) + win.shape[0], (c0 - (c - rad)):(c0 - (c - rad)) + win.shape[1]]
        vals = win[kk & (win >= 1) & (win <= 3)]
        if vals.size < 10:
            continue
        vv = v[r0:r1, c0:c1][kk]
        rows.append({"name": props["name"], "lon": round(lon, 5), "lat": round(lat, 5), "red_share": round(float(np.mean(vals == 3)) * 100, 0),
                     "sinking_cm_yr": round(float(-np.nanmedian(vv)), 1), "years_500": round(float(np.nanmedian(years[r0:r1, c0:c1][kk])), 0)})
    rows = [r for r in rows if r["red_share"] > 0]
    seen, uniq = set(), []
    for row in sorted(rows, key=lambda r: (-r["red_share"], -r["sinking_cm_yr"])):
        if row["name"] not in seen:
            seen.add(row["name"])
            uniq.append(row)
    n = (cls >= 1).sum()
    shares = {i: _pct((cls == i).sum(), n) for i in (1, 2, 3, 4)}
    return {
        "array": cls,
        "headline": f"{shares[3]:.0f}% of the measured ground is red (avoid, or special design), {shares[2]:.0f}% amber (build with conditions) "
                    f"and {shares[1]:.0f}% blue (build normally); {shares[4]:.0f}% could not be measured reliably.",
        "ranked": {"title": "Neighbourhoods with the most red ground (within 500 m)",
                   "columns": [{"key": "name", "label": "Neighbourhood"}, {"key": "red_share", "label": "Red", "unit": "%"},
                               {"key": "sinking_cm_yr", "label": "Sinking", "unit": "cm/yr"}, {"key": "years_500", "label": "Years to 1/500", "unit": "yr"}],
                   "rows": uniq},
    }


def what_to_build(ctx: dict, q: dict) -> dict:
    E, T = ctx["E"], q["thresholds"]
    v, years = E["vert_vel_cm_yr"], E["tilt_years_500"]
    measured, unknown = _sub_masks(E, T)
    cls = np.zeros(v.shape, np.uint8)
    with np.errstate(invalid="ignore"):
        cls[measured] = 1
        cls[measured & (np.abs(v) >= T["amber_speed_cm_yr"])] = 2
        cls[measured & (years < T["amber_years"])] = 3
        cls[measured & (years < T["red_years"])] = 4
    cls[unknown] = 5
    n = (cls >= 1).sum()
    s = {i: _pct((cls == i).sum(), n) for i in range(1, 6)}
    return {"array": cls,
            "headline": f"Any standard building fits {s[1]:.0f}% of the measured ground and most buildings with flexible connections another {s[2]:.0f}%; "
                        f"{s[3]:.0f}% suits light buildings on a raft or floating foundation and {s[4]:.0f}% only light, flexible structures."}


def better_plots(ctx: dict, q: dict) -> dict:
    return {"array": None, "headline": "Click a spot on the map: the steadiest ground within 2 km is ranked for it."}


def lines_at_risk(ctx: dict, q: dict) -> dict:
    E, T, geo = ctx["E"], q["thresholds"], ctx["geo"]
    vs = evidence.smooth(E["vert_vel_cm_yr"]).astype(np.float32)
    cls = np.zeros(vs.shape, np.uint8)
    names = {"subway": "Metro", "light_rail": "Light rail", "tram": "Tram", "canal": "Canal", "drain": "Drain"}
    items, best = [], {}
    step = geo.g["res"] / 2
    for props, xy in project_lines(geo, ctx["lines"]):
        pts, dist = densify(xy, step)
        r, c = geo.rc(pts[:, 0], pts[:, 1])
        val = geo.sample(vs, r, c)
        seg = (dist // T["segment_m"]).astype(int)
        for s in np.unique(seg):
            mk = seg == s
            ok = mk & np.isfinite(val)
            if ok.sum() < 4 or (dist[mk].max() - dist[mk].min()) < T["segment_m"] * 0.4:
                continue
            slope = np.polyfit(dist[ok], val[ok], 1)[0]  # cm/year per metre along the line
            rate = abs(slope) / 100.0
            years = min(200.0, T["limit"] / rate) if rate > 0 else 200.0
            k = 3 if years < T["red_years"] else 2 if years < T["amber_years"] else 1
            mid = int(np.flatnonzero(mk)[mk.sum() // 2])
            lon, lat = geo.inv.transform(pts[mid, 0], pts[mid, 1])
            key = (props["name"], props["class"], round(pts[mid, 0] / 120), round(pts[mid, 1] / 120))  # parallel tracks share a key
            item = {"name": props["name"] or f"Unnamed {names.get(props['class'], props['class']).lower()}", "kind": names.get(props["class"], props["class"]),
                    "lon": round(lon, 5), "lat": round(lat, 5), "length_m": round(float(dist[mk].max() - dist[mk].min())),
                    "sinking_cm_yr": round(float(-np.nanmean(val[ok])), 1), "years_500": round(years, 0), "class": k,
                    "coords": line_coords(geo, pts[mk])}
            if key not in best or best[key]["years_500"] > item["years_500"]:
                best[key] = item
            rr, cc = r[mk], c[mk]
            inb = geo.inside(rr, cc)
            np.maximum.at(cls, (rr[inb], cc[inb]), k)
    items = sorted(best.values(), key=lambda i: i["years_500"])
    km = {k: round(sum(i["length_m"] for i in items if i["class"] == k) / 1000, 1) for k in (1, 2, 3)}
    worst = items[0] if items else None
    head = (f"{km[3]:.1f} km of Metro, rail and canal cross ground where uneven sinking reaches the 1/500 limit within 15 years, "
            f"and {km[2]:.1f} km within 50 years.")
    if worst:
        head += f" The worst segment ({worst['kind']}, {worst['name']}) reaches it in about {worst['years_500']:.0f} years."
    return {
        "array": dilate(cls),
        "items": items,
        "headline": head,
        "ranked": {"title": "Segments to inspect first (250 m each)",
                   "columns": [{"key": "name", "label": "Line"}, {"key": "kind", "label": "Type"}, {"key": "sinking_cm_yr", "label": "Sinking", "unit": "cm/yr"},
                               {"key": "years_500", "label": "Years to 1/500", "unit": "yr"}],
                   "rows": items},
    }


# ---------------------------------------------------------------- wildfire recipes


def _paths(ctx: dict, T: dict):
    """Mud-path class per cell: 0 none, 1 path, 2 main path. A path is a channel (>= channel_ha draining through)
    in a small basin (<= max_basin_ha) whose burned steep share and area pass the thresholds."""
    A = ctx["A"]
    d = np.nan_to_num(A["drainage_ha"])
    up = np.nan_to_num(A["mud_upstream_ha"])
    with np.errstate(invalid="ignore", divide="ignore"):
        share = np.where(d > 0, up / d, 0.0)
    small = (d >= T["channel_ha"]) & (d <= T["max_basin_ha"])
    k = np.zeros(d.shape, np.uint8)
    k[small & (share >= T["path_share"]) & (up >= T["path_ha"])] = 1
    k[small & (share >= T["high_share"]) & (up >= T["high_path_ha"])] = 2
    return k, up, share


def _towns(ctx: dict):
    return list(points_of(ctx["geo"], ctx["places"], ("city", "town", "village", "hamlet", "suburb")))


def burned_slopes(ctx: dict, q: dict) -> dict:
    A, T, geo = ctx["A"], q["thresholds"], ctx["geo"]
    path, up, share = _paths(ctx, T)
    cls = np.zeros(up.shape, np.uint8)
    cls[np.nan_to_num(A["steep_burned_share"]) >= 0.25] = 1
    cls[path == 1] = 2
    cls[path == 2] = 3
    rad = max(1, int(round(T["village_radius_m"] / geo.g["res"])))
    k = disc(rad)
    items = []
    for props, lon, lat in _towns(ctx):
        r, c = geo.rc_lonlat(lon, lat)
        if not geo.inside(r, c):
            continue
        r0, c0 = max(0, r - rad), max(0, c - rad)
        pw = path[r0:r + rad + 1, c0:c + rad + 1]
        kk = k[(r0 - (r - rad)):(r0 - (r - rad)) + pw.shape[0], (c0 - (c - rad)):(c0 - (c - rad)) + pw.shape[1]]
        pw = np.where(kk, pw, 0)
        if pw.max() == 0:
            continue
        score = np.where(pw == pw.max(), up[r0:r + rad + 1, c0:c + rad + 1], -1.0)
        i, j = np.unravel_index(int(np.argmax(score)), score.shape)
        plon, plat = geo.lonlat(r0 + i, c0 + j)
        items.append({"name": props["name"] or "Unnamed place", "kind": props["class"], "lon": round(lon, 5), "lat": round(lat, 5),
                      "upstream_ha": round(float(score[i, j]), 1), "basin_share": round(float(share[r0 + i, c0 + j]) * 100),
                      "class": 3 if pw.max() == 2 else 2, "path_lon": round(float(plon), 5), "path_lat": round(float(plat), 5)})
    items.sort(key=lambda i: (-i["class"], -i["basin_share"], -i["upstream_ha"]))
    n3 = sum(i["class"] == 3 for i in items)
    n2 = len(items) - n3
    cell_ha = geo.g["res"] ** 2 / 1e4
    return {
        "array": cls,
        "items": items,
        "headline": (f"{n3} villages or hamlets lie within {T['village_radius_m']:.0f} m of a main mud path (a small basin over {T['high_share'] * 100:.0f}% burned and steep) "
                     f"and {n2} more near a smaller one." if items else
                     f"No mapped village or hamlet lies within {T['village_radius_m']:.0f} m of a mud path; roads and slopes are the exposure here.")
                    + f" {np.sum(cls == 1) * cell_ha:,.0f} ha of burned steep slopes are mud sources.",
        "ranked": {"title": "Villages below the burned slopes",
                   "columns": [{"key": "name", "label": "Place"}, {"key": "kind", "label": "Type"}, {"key": "basin_share", "label": "Basin burned and steep", "unit": "%"},
                               {"key": "upstream_ha", "label": "Burned steep upstream", "unit": "ha"}],
                   "rows": items},
    }


def _paint_roads(ctx: dict, step: float):
    geo = ctx["geo"]
    for props, xy in project_lines(geo, ctx["roads"]):
        pts, dist = densify(xy, step)
        r, c = geo.rc(pts[:, 0], pts[:, 1])
        yield props, pts, dist, r, c


def roads_to_watch(ctx: dict, q: dict) -> dict:
    T, geo = q["thresholds"], ctx["geo"]
    path, up, share = _paths(ctx, T)
    cls = np.zeros(up.shape, np.uint8)
    items = []
    towns = [(p["name"], *geo.fwd.transform(lon, lat)) for p, lon, lat in _towns(ctx) if p["name"]]
    tx = np.array([t[1] for t in towns]) if towns else np.zeros(0)
    ty = np.array([t[2] for t in towns]) if towns else np.zeros(0)
    for props, pts, dist, r, c in _paint_roads(ctx, geo.g["res"] / 2):
        pk = np.nan_to_num(geo.sample(path.astype(np.float32), r, c)).astype(int)
        u = np.nan_to_num(geo.sample(up, r, c))
        seg = (dist // T["segment_m"]).astype(int)
        for s in np.unique(seg):
            mk = seg == s
            pp = pk[mk]
            if pp.max() == 0:
                continue
            k = int(pp.max())
            uu = np.where(pp == k, u[mk], -1)
            j = int(np.flatnonzero(mk)[int(np.argmax(uu))])
            lon, lat = geo.inv.transform(pts[j, 0], pts[j, 1])
            crossings = int(np.sum(np.diff((pp > 0).astype(int)) == 1) + (pp[0] > 0))
            name = props["ref"] or props["name"]
            if not name and towns:
                dd = np.hypot(tx - pts[j, 0], ty - pts[j, 1])
                name = f"Road near {towns[int(np.argmin(dd))][0]}"
            name = name or "Unnamed road"
            if props["ref"] and props["name"] and props["name"] != props["ref"]:
                name = f"{props['ref']} ({props['name']})"
            items.append({"name": name, "kind": props["class"].replace("_", " "), "lon": round(lon, 5), "lat": round(lat, 5),
                          "upstream_ha": round(float(uu.max()), 1), "crossings": crossings, "class": k, "coords": line_coords(geo, pts[mk])})
            prev = items[-2] if len(items) > 1 else None
            if prev and prev["name"] == name and prev["class"] == k and abs(prev["lat"] - lat) + abs(prev["lon"] - lon) < 0.004:
                last = items.pop()  # merge neighbouring sections of one road
                prev["crossings"] += last["crossings"]
                prev["coords"] += last["coords"]
            rr, cc = r[mk], c[mk]
            inb = geo.inside(rr, cc)
            np.maximum.at(cls, (rr[inb], cc[inb]), k)
    items.sort(key=lambda i: (-i["class"], -i["crossings"], -i["upstream_ha"]))
    n2 = sum(i["class"] == 2 for i in items)
    return {
        "array": dilate(cls),
        "items": items,
        "headline": f"{n2} road sections (500 m) cross a main mud path and should close in heavy rain; {len(items) - n2} more cross a smaller one and need watching."
                    + (f" The most exposed is {items[0]['name']}, crossing {items[0]['crossings']} mud path(s)." if items else ""),
        "ranked": {"title": "Road sections to close or watch (500 m each)",
                   "columns": [{"key": "name", "label": "Road"}, {"key": "kind", "label": "Type"}, {"key": "upstream_ha", "label": "Burned steep ground upstream", "unit": "ha"},
                               {"key": "crossings", "label": "Mud paths crossed"}],
                   "rows": items},
    }


def replant_first(ctx: dict, q: dict) -> dict:
    from scipy.ndimage import binary_dilation, label

    A, T, geo = ctx["A"], q["thresholds"], ctx["geo"]
    burned = np.nan_to_num(A["burned_share"]) >= 0.5
    steep = np.nan_to_num(A["steep_burned_share"]) >= 0.5 * np.nan_to_num(A["burned_share"]) + 1e-6
    assets = np.zeros(burned.shape, bool)
    for props, lon, lat in _towns(ctx):
        r, c = geo.rc_lonlat(lon, lat)
        if geo.inside(r, c):
            assets[r, c] = True
    assets = binary_dilation(assets, structure=disc(max(1, int(round(T["village_radius_m"] / geo.g["res"])))))
    for props, pts, dist, r, c in _paint_roads(ctx, geo.g["res"] / 2):
        inb = geo.inside(r, c)
        assets[r[inb], c[inb]] = True
    rcv, order = ctx["flow"]
    people = evidence.reaches(assets, rcv, order)
    rec = A["hv_recovery"]
    cls = np.zeros(burned.shape, np.uint8)
    cls[burned] = 3
    cls[burned & (steep | people)] = 2
    cls[burned & steep & people] = 1
    with np.errstate(invalid="ignore"):
        cls[burned & (rec >= T["recovering"])] = 4
    lab, n = label(cls == 1, structure=np.ones((3, 3)))
    cell_ha = geo.g["res"] ** 2 / 1e4
    towns = [(p["name"], *geo.fwd.transform(lon, lat)) for p, lon, lat in _towns(ctx) if p["name"]]
    tx = np.array([t[1] for t in towns]) if towns else np.zeros(0)
    ty = np.array([t[2] for t in towns]) if towns else np.zeros(0)
    items = []
    if n:
        sizes = np.bincount(lab.ravel())[1:]
        for idx in np.argsort(-sizes)[:40]:
            rr, cc = np.nonzero(lab == idx + 1)
            lon, lat = geo.lonlat(rr.mean(), cc.mean())
            x, y = geo.fwd.transform(lon, lat)
            near = ""
            if towns:
                d = np.hypot(tx - x, ty - y)
                j = int(np.argmin(d))
                near = f"{towns[j][0]} ({d[j] / 1000:.1f} km {compass(x - tx[j], y - ty[j])})"
            items.append({"name": near or "Burned patch", "lon": round(float(lon), 5), "lat": round(float(lat), 5), "area_ha": round(float(sizes[idx] * cell_ha), 1), "class": 1})
    ha = {k: round(float((cls == k).sum() * cell_ha)) for k in (1, 2, 3, 4)}
    return {
        "array": cls,
        "items": items,
        "headline": f"{ha[1]:,} ha of steep burned ground drains towards villages or roads: protect its soil now and replant it first. "
                    f"{ha[4]:,} ha already shows vegetation coming back and needs protecting rather than planting.",
        "ranked": {"title": "Patches to protect and replant first",
                   "columns": [{"key": "name", "label": "Near"}, {"key": "area_ha", "label": "Area", "unit": "ha"}],
                   "rows": items},
    }


def forest_recovery(ctx: dict, q: dict) -> dict:
    A, T, geo = ctx["A"], q["thresholds"], ctx["geo"]
    rec = A["hv_recovery"]
    cls = np.zeros(rec.shape, np.uint8)
    f = np.isfinite(rec)
    cls[f] = 3
    cls[f & (rec >= T["slow"])] = 2
    cls[f & (rec >= T["recovering"])] = 1
    n = f.sum()
    s = {k: _pct((cls == k).sum(), n) for k in (1, 2, 3)}
    return {"array": cls,
            "headline": f"{s[1]:.0f}% of the burned forest is coming back (30% or more of the lost radar signal), {s[2]:.0f}% slowly, "
                        f"and {s[3]:.0f}% shows no return yet, two months after the fire."}


RECIPES = {f.__name__: f for f in (safe_to_build, what_to_build, better_plots, lines_at_risk, burned_slopes, roads_to_watch, replant_first, forest_recovery)}


# ---------------------------------------------------------------- build


def _load_manifest(site_id: str) -> dict:
    return json.loads(config.data.read_text(f"{site_id}/manifest.json"))


def build(site_id: str, log=print) -> int:
    from . import sites

    m = _load_manifest(site_id)
    qs = questions(m["lens"])
    if not qs:
        log(f"  {site_id}: no Questions for the {m['lens']} Lens")
        return 0
    site = sites.load(site_id)
    log(f"\n{site_id}: answering {len(qs)} Questions")
    ctx: dict = {"site_id": site_id, "m": m}
    if m["lens"] == "subsidence":
        ev = evidence.subsidence(site_id, m, log)
        d = ev["date"]
        ctx["E"] = {n: evidence.read(site_id, n, d, "layers" if n in ("vert_vel_cm_yr", "tilt_years_500", "accel_cm_yr2") else "evidence")
                    for n in ("vert_vel_cm_yr", "tilt_years_500", "accel_cm_yr2", "fit_se_cm_yr", "mean_coherence")}
    elif m["lens"] == "wildfire":
        ev = evidence.wildfire(site_id, m, site, log)
        ctx["A"] = ev["arrays"]
        ctx["flow"] = ev["flow"]
    else:
        raise RuntimeError(f"No evidence step for the {m['lens']} Lens yet")
    ctx["geo"] = Geo(ev["grid"])
    date = ev["date"]
    for kind in sorted({k for q in qs for k in q.get("context", [])} | {"places"}):
        ctx[kind] = context.load(site_id, m["bbox"], kind, log=log)

    cell_ha = ev["grid"]["res"] ** 2 / 1e4
    ans_layers, out_qs = [], []
    for q in qs:
        res = RECIPES[q["recipe"]](ctx, q)
        entry = {k: q[k] for k in ("id", "title", "short", "order", "status", "sources", "limits")}
        entry["point_only"] = bool(q.get("point_only"))
        entry["headline"] = res["headline"]
        entry["layer"] = None
        entry["classes"] = []
        if res.get("array") is not None:
            arr = res["array"]
            lid = f"ans_{q['id']}"
            export.write_cog(site_id, f"{lid}_{date}", arr, ev["grid"], categorical=True)
            entry["layer"] = lid
            total = int((arr > 0).sum())
            for c in q["classes"]:
                n = int((arr == c["value"]).sum())
                entry["classes"].append({**c, "area_ha": round(n * cell_ha, 1), "share": round(n / total, 4) if total else 0.0})
            ans_layers.append({
                "id": lid, "label": q["title"], "kind": "answer", "unit": "class", "colormap": "categorical",
                "range": [0, max(c["value"] for c in q["classes"])], "dates": [date], "status": q["status"],
                "classes": [{"value": c["value"], "label": c["label"], "color": c["color"]} for c in q["classes"]],
                "what_this_shows": q["short"],
            })
        entry["solutions"] = q.get("solutions", [])
        if res.get("ranked"):
            rows = [{k: v for k, v in r.items() if k != "coords"} for r in res["ranked"]["rows"][:TOP_ROWS]]
            entry["ranked"] = {**res["ranked"], "total": len(res["ranked"]["rows"]), "rows": rows}
        entry["features"] = q.get("features")
        if res.get("items") is not None:
            config.data.write_text(f"{site_id}/answers/{q['id']}_items.json", json.dumps(res["items"]))
        out_qs.append(entry)
        log(f"  {q['id']}: {res['headline']}")

    used = sorted({s for q in out_qs for c in q["classes"] for s in c["solutions"]} | {s for q in out_qs for s in q["solutions"]})
    doc = {
        "site": site_id, "lens": m["lens"], "name": m["name"], "bbox": m["bbox"], "date": date, "grid_m": ev["grid"]["res"],
        "generated_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "roles": roles().get(m["lens"], []),
        "questions": out_qs,
        "solutions": {s: solutions()[s] for s in used},
        "evidence": ev["stats"],
        "attribution": "Maps and places: © OpenStreetMap contributors (ODbL); elevation: Copernicus GLO-30; radar: NASA/ISRO NISAR.",
    }
    config.data.write_text(f"{site_id}/answers/answers.json", json.dumps(doc, indent=1))
    drop = {l["id"] for l in ev["layers"] + ans_layers}
    m["layers"] = [l for l in m["layers"] if l["kind"] != "answer" and l["id"] not in drop] + ev["layers"] + ans_layers
    export.write_manifest(site_id, m)
    sys.path.insert(0, str(config.CONTRACTS_DIR))
    from validate import check_manifest

    errs = check_manifest(config.data.local_path(f"{site_id}/manifest.json"))
    log(f"  manifest {'valid' if not errs else 'INVALID'}; answers in data/{site_id}/answers/answers.json")
    for e in errs:
        log(f"    {e}")
    return 1 if errs else 0


# ---------------------------------------------------------------- answers at one spot


def _value_at(site_id: str, key: str, lon: float, lat: float) -> float:
    path = config.data.local_path(key)
    if not path.exists():
        return float("nan")
    from pyproj import Transformer

    with rasterio.open(path) as r:
        x, y = Transformer.from_crs(4326, r.crs, always_xy=True).transform(lon, lat)
        row, col = r.index(x, y)
        if not (0 <= row < r.height and 0 <= col < r.width):
            return float("nan")
        v = float(r.read(1, window=((row, row + 1), (col, col + 1)))[0, 0])
        if r.nodata is not None and not np.isnan(r.nodata) and v == r.nodata:
            return float("nan")
        return v


def _window(site_id: str, key: str, lon: float, lat: float, radius_m: float):
    """Array around a spot plus (geo, row0, col0) to map window pixels back to lon/lat."""
    with rasterio.open(config.data.local_path(key)) as r:
        g = {"epsg": r.crs.to_epsg(), "x0": r.transform.c, "y0": r.transform.f, "res": r.transform.a, "shape": [r.height, r.width]}
        geo = Geo(g)
        rr, cc = geo.rc_lonlat(lon, lat)
        rad = int(math.ceil(radius_m / g["res"]))
        r0, c0 = max(0, int(rr) - rad), max(0, int(cc) - rad)
        r1, c1 = min(r.height, int(rr) + rad + 1), min(r.width, int(cc) + rad + 1)
        if r1 <= r0 or c1 <= c0:
            return None, geo, r0, c0, int(rr), int(cc)
        a = r.read(1, window=((r0, r1), (c0, c1))).astype(np.float32)
        if r.nodata is not None and not np.isnan(r.nodata):
            a[a == r.nodata] = np.nan
        return a, geo, r0, c0, int(rr), int(cc)


def _nearest_item(site_id: str, qid: str, lon: float, lat: float, max_m: float):
    key = f"{site_id}/answers/{qid}_items.json"
    if not config.data.exists(key):
        return None, None
    items = json.loads(config.data.read_text(key))
    if not items:
        return None, None
    lons = np.array([i["lon"] for i in items])
    lats = np.array([i["lat"] for i in items])
    d = np.hypot((lons - lon) * 111320 * math.cos(math.radians(lat)), (lats - lat) * 110540)
    j = int(np.argmin(d))
    return (items[j], float(d[j])) if d[j] <= max_m else (None, float(d[j]))


def _explain_subsidence(v: dict, q: dict) -> list[str]:
    T, out = q["thresholds"], []
    if not np.isfinite(v["vel"]):
        return ["No radar measurement here (outside the swath or masked)."]
    word = "sinks" if v["vel"] < 0 else "rises"
    out.append(f"The ground {word} {abs(v['vel']):.1f} cm per year (± {2 * v['se']:.1f}, 95%), vertical, from 28 Passes.")
    if np.isfinite(v["coh"]) and v["coh"] < T["min_coherence"]:
        out.append(f"The radar signal is noisy here (coherence {v['coh']:.2f}, below {T['min_coherence']}).")
    if np.isfinite(v["years"]):
        if v["years"] >= 200:
            out.append("Neighbouring ground sinks at the same speed: no measurable tilt.")
        else:
            out.append(f"Uneven sinking between neighbouring spots reaches the 1/500 crack limit in about {v['years']:.0f} years.")
    elif np.isfinite(v.get("slope", np.nan)) and v["slope"] >= evidence.MAX_TILT_SLOPE_DEG:
        out.append(f"Slope of {v['slope']:.0f} degrees: the radar tilt is not reliable on hillsides, so a slope-stability check is needed instead.")
    if "accel_cm_yr2" in T and np.isfinite(v["acc"]) and v["acc"] < -T["accel_cm_yr2"]:
        out.append(f"First sign of sinking speeding up ({v['acc']:.0f} cm/year each year); confirm with next year's data.")
    return out


def at_point(site_id: str, lon: float, lat: float) -> dict:
    """Every Question's answer at one spot: class, reasons with the numbers behind them, and solutions."""
    key = f"{site_id}/answers/answers.json"
    if not config.data.exists(key):
        raise FileNotFoundError(site_id)
    doc = json.loads(config.data.read_text(key))
    d = doc["date"]
    qfiles = {q["id"]: q for q in questions(doc["lens"])}
    cards = []
    vals: dict = {}
    if doc["lens"] == "subsidence":
        L, Ev = f"{site_id}/layers/", f"{site_id}/evidence/"
        slope_l = next((l for l in _load_manifest(site_id)["layers"] if l["id"] == "slope"), None)
        vals = {
            "vel": _value_at(site_id, f"{L}vert_vel_cm_yr_{d}.tif", lon, lat), "years": _value_at(site_id, f"{L}tilt_years_500_{d}.tif", lon, lat),
            "acc": _value_at(site_id, f"{L}accel_cm_yr2_{d}.tif", lon, lat), "se": _value_at(site_id, f"{Ev}fit_se_cm_yr_{d}.tif", lon, lat),
            "coh": _value_at(site_id, f"{Ev}mean_coherence_{d}.tif", lon, lat),
            "slope": _value_at(site_id, f"{L}slope_{slope_l['dates'][-1]}.tif", lon, lat) if slope_l else float("nan"),
        }
    elif doc["lens"] == "wildfire":
        L, Ev = f"{site_id}/layers/", f"{site_id}/evidence/"
        vals = {"up": _value_at(site_id, f"{L}mud_upstream_ha_{d}.tif", lon, lat), "rec": _value_at(site_id, f"{L}hv_recovery_{d}.tif", lon, lat),
                "drain": _value_at(site_id, f"{Ev}drainage_ha_{d}.tif", lon, lat), "burned": _value_at(site_id, f"{Ev}burned_share_{d}.tif", lon, lat),
                "steep": _value_at(site_id, f"{Ev}steep_burned_share_{d}.tif", lon, lat)}
    for q in doc["questions"]:
        qf = qfiles[q["id"]]
        card = {"question": q["id"], "title": q["title"], "class": None, "label": None, "verdict": None, "color": None, "reasons": [], "solutions": []}
        cls = None
        if q["layer"]:
            cv = _value_at(site_id, f"{site_id}/layers/{q['layer']}_{d}.tif", lon, lat)
            cls = next((c for c in q["classes"] if np.isfinite(cv) and c["value"] == int(cv)), None)
        if cls:
            card.update({"class": cls["value"], "label": cls["label"], "verdict": cls["verdict"], "color": cls["color"], "solutions": cls["solutions"]})
            card["reasons"].append(cls["meaning"])
        recipe = qf["recipe"]
        if recipe in ("safe_to_build", "what_to_build"):
            card["reasons"] += _explain_subsidence(vals, qf)
        elif recipe == "better_plots":
            card.update(_better_plots_at(site_id, doc, qf, lon, lat))
        elif recipe == "lines_at_risk":
            it, dist = _nearest_item(site_id, q["id"], lon, lat, 200)
            if it:
                card["reasons"].append(f"Nearest segment: {it['kind']} {it['name']}, {dist:.0f} m away. It sinks {it['sinking_cm_yr']:.1f} cm/year and uneven sinking along it "
                                       f"reaches 1/500 in about {it['years_500']:.0f} years.")
                cl = next(c for c in qf["classes"] if c["value"] == it["class"])
                card.update({"class": cl["value"], "label": cl["label"], "verdict": cl["verdict"], "color": cl["color"], "solutions": cl["solutions"]})
            else:
                card["reasons"] = ["No mapped Metro, rail or canal line within 200 m of this spot."]
                card.update({"class": None, "label": "No line here", "verdict": None, "color": None, "solutions": []})
        elif recipe in ("burned_slopes", "replant_first", "forest_recovery", "roads_to_watch"):
            extra = _explain_wildfire(site_id, recipe, vals, qf, lon, lat, card)  # may replace card["reasons"]
            card["reasons"] = card["reasons"] + extra
        if not card["label"]:
            card["label"] = "Nothing to flag here" if recipe not in ("better_plots",) else card.get("label")
        cards.append(card)
    return {"lon": lon, "lat": lat, "date": d, "cards": cards, "values": {k: (None if not np.isfinite(v) else round(v, 3)) for k, v in vals.items()}}


def _better_plots_at(site_id: str, doc: dict, q: dict, lon: float, lat: float) -> dict:
    T = q["thresholds"]
    d = doc["date"]
    cls, geo, r0, c0, rr, cc = _window(site_id, f"{site_id}/layers/ans_m1_safe_to_build_{d}.tif", lon, lat, T["radius_m"])
    if cls is None:
        return {"label": "Outside the measured area", "reasons": ["This spot is outside the measured area."], "alternatives": []}
    years, *_ = _window(site_id, f"{site_id}/layers/tilt_years_500_{d}.tif", lon, lat, T["radius_m"])
    vel, *_ = _window(site_id, f"{site_id}/layers/vert_vel_cm_yr_{d}.tif", lon, lat, T["radius_m"])
    res = geo.g["res"]
    H, W = cls.shape
    yy, xx = np.mgrid[0:H, 0:W]
    dist = np.hypot((yy + r0 - rr) * res, (xx + c0 - cc) * res)
    here = cls[rr - r0, cc - c0] if 0 <= rr - r0 < H and 0 <= cc - c0 < W else np.nan
    # score: steadier is better; prefer blue (1), else amber (2)
    target = 1 if np.any((cls == 1) & (dist <= T["radius_m"])) else 2
    ok = (cls == target) & (dist <= T["radius_m"]) & (dist > res)
    score = np.where(ok, np.minimum(np.nan_to_num(years, nan=0), 100) - 3 * np.abs(np.nan_to_num(vel, nan=99)) - dist / 500, -np.inf)
    picks = []
    sep = T["min_separation_m"] / res
    for _ in range(int(T["max_results"])):
        if not np.isfinite(score).any() or score.max() == -np.inf:
            break
        i, j = np.unravel_index(int(np.argmax(score)), score.shape)
        plon, plat = geo.lonlat(r0 + i, c0 + j)
        dx, dy = (j + c0 - cc) * res, -(i + r0 - rr) * res
        picks.append({"lon": round(float(plon), 5), "lat": round(float(plat), 5), "distance_m": round(float(dist[i, j]), -1), "direction": compass(dx, dy),
                      "sinking_cm_yr": round(float(-vel[i, j]), 1), "years_500": round(float(min(years[i, j], 200)), 0),
                      "label": "Build normally" if target == 1 else "Build with conditions"})
        score[np.hypot(yy - i, xx - j) <= sep] = -np.inf
    reasons = []
    if picks:
        reasons.append(f"{len(picks)} steadier spots within {T['radius_m'] / 1000:.0f} km" + (" (all 'build with conditions'; no 'build normally' ground nearby)." if target == 2 else "."))
        if np.isfinite(here) and int(here) == 1:
            reasons.insert(0, "This spot is already 'build normally'; these are alternatives.")
    else:
        reasons.append(f"No steadier ground within {T['radius_m'] / 1000:.0f} km.")
    return {"label": f"{len(picks)} alternatives" if picks else "None nearby", "reasons": reasons, "alternatives": picks, "solutions": q.get("solutions", [])}


def _explain_wildfire(site_id: str, recipe: str, v: dict, q: dict, lon: float, lat: float, card: dict) -> list[str]:
    T, out = q["thresholds"], []
    if recipe == "burned_slopes":
        if np.isfinite(v["steep"]) and v["steep"] > 0:
            out.append(f"{v['steep'] * 100:.0f}% of this 60 m cell is burned ground on slopes of {T['steep_deg']:.0f} degrees or more.")
        if np.isfinite(v["drain"]) and v["drain"] >= T["channel_ha"]:
            share = v["up"] / v["drain"] * 100 if v["drain"] else 0
            big = " (a large river: it carries sediment floods rather than starting debris flows)" if v["drain"] > T["max_basin_ha"] else ""
            out.append(f"It is a channel: {v['drain']:,.0f} ha drain through it, {share:.0f}% of them burned steep ground{big}.")
        it, dist = _nearest_item(site_id, q["id"], lon, lat, 3000)
        if it and dist <= 80:  # the spot is the village itself: answer for the village, not its exact pixel
            cl = next(c for c in q["classes"] if c["value"] == it["class"])
            if not card["class"] or card["class"] < cl["value"]:
                card.update({"class": cl["value"], "label": cl["label"], "verdict": cl["verdict"], "color": cl["color"], "solutions": cl["solutions"]})
                card["reasons"] = [cl["meaning"]]
            kind = "a main mud path" if it["class"] == 3 else "a mud path"
            out = []  # the cell under the village pin says little; the village's own exposure does
            out.append(f"{it['name']} lies within {T['village_radius_m']:.0f} m of {kind}: {it['basin_share']}% of that channel's basin is burned and steep "
                       f"({it['upstream_ha']:.0f} ha).")
        elif it:
            out.append(f"Nearest village beside a mud path: {it['name']} ({it['kind']}), {dist / 1000:.1f} km away; {it['basin_share']}% of that path's basin is burned and steep.")
    elif recipe == "roads_to_watch":
        it, dist = _nearest_item(site_id, q["id"], lon, lat, 300)
        if it:
            cl = next(c for c in q["classes"] if c["value"] == it["class"])
            card.update({"class": cl["value"], "label": cl["label"], "verdict": cl["verdict"], "color": cl["color"], "solutions": cl["solutions"]})
            out.append(f"Nearest flagged road: {it['name']} ({it['kind']}), {dist:.0f} m away; it crosses {it['crossings']} mud path(s) with up to {it['upstream_ha']:.0f} ha of burned steep ground upstream.")
        else:
            out.append("No flagged road section within 300 m of this spot.")
    elif recipe == "replant_first":
        if not (np.isfinite(v["burned"]) and v["burned"] >= 0.5):
            out.append("This spot did not burn (or burned only partly).")
        else:
            if np.isfinite(v["steep"]):
                out.append(f"{v['steep'] / max(v['burned'], 1e-6) * 100:.0f}% of the burned ground here is on slopes of {T['steep_deg']:.0f} degrees or more.")
            if np.isfinite(v["rec"]):
                out.append(f"{max(v['rec'], 0) * 100:.0f}% of the radar signal lost in the fire has come back.")
    elif recipe == "forest_recovery":
        if np.isfinite(v["rec"]):
            out.append(f"{max(v['rec'], 0) * 100:.0f}% of the vegetation signal (HV) lost in the fire has returned since its post-fire low.")
        else:
            out.append("Not a burned forest block with a clear drop in the fire.")
    return out


# ---------------------------------------------------------------- map features and place search


def features(site_id: str, qid: str) -> dict:
    """A Question's ranked items as GeoJSON for the map: lines (segments, roads) or points (villages, patches),
    each with its class colour and a short label."""
    doc = json.loads(config.data.read_text(f"{site_id}/answers/answers.json"))
    q = next((x for x in doc["questions"] if x["id"] == qid), None)
    key = f"{site_id}/answers/{qid}_items.json"
    if q is None or not config.data.exists(key):
        raise FileNotFoundError(qid)
    colors = {c["value"]: c["color"] for c in q["classes"]}
    labels = {c["value"]: c["label"] for c in q["classes"]}
    feats = []
    for rank, it in enumerate(json.loads(config.data.read_text(key)), start=1):
        props = {k: v for k, v in it.items() if k not in ("coords", "lon", "lat", "path_lon", "path_lat")}
        props.update({"rank": rank, "color": colors.get(it.get("class"), "#d7191c"), "class_label": labels.get(it.get("class"), ""), "lon": it["lon"], "lat": it["lat"],
                      # patches are labelled by priority rank, villages by name
                      "label": f"#{rank}" if "area_ha" in it else it.get("name", "")})
        if it.get("coords") and len(it["coords"]) >= 2:
            geom = {"type": "LineString", "coordinates": it["coords"]}
        else:
            geom = {"type": "Point", "coordinates": [it["lon"], it["lat"]]}
        feats.append({"type": "Feature", "properties": props, "geometry": geom})
    return {"type": "FeatureCollection", "features": feats}


def _fold(s: str) -> str:
    import unicodedata

    return "".join(c for c in unicodedata.normalize("NFKD", s.lower()) if not unicodedata.combining(c))


@lru_cache(maxsize=16)
def _places(site_id: str, mtime: float) -> list:
    fc = json.loads(config.data.read_text(f"{site_id}/context/places.geojson"))
    out = []
    for f in fc["features"]:
        p = f["properties"]
        names = {n for n in (p.get("name"), p.get("name_local")) if n}
        if names and f["geometry"]["type"] == "Point":
            lon, lat = f["geometry"]["coordinates"]
            out.append({"name": p["name"] or p.get("name_local"), "local": p.get("name_local", ""), "kind": p["class"], "lon": lon, "lat": lat,
                        "keys": [_fold(n) for n in names]})
    return out


def search_places(site_id: str, q: str, limit: int = 8) -> list:
    """Places in this site's cached OpenStreetMap names (both scripts), starts-with matches first."""
    key = f"{site_id}/context/places.geojson"
    if not config.data.exists(key) or len(q.strip()) < 2:
        return []
    needle = _fold(q.strip())
    rank = {"city": 0, "town": 1, "suburb": 2, "village": 3, "quarter": 4, "neighbourhood": 5, "hamlet": 6}
    hits = []
    for p in _places(site_id, config.data.local_path(key).stat().st_mtime):
        best = min((0 if k.startswith(needle) else 1 if needle in k else 9) for k in p["keys"])
        if best < 9:
            hits.append((best, rank.get(p["kind"], 9), p["name"]))
            hits[-1] = hits[-1] + ({k: v for k, v in p.items() if k != "keys"},)
    hits.sort(key=lambda h: h[:3])
    return [h[3] for h in hits[:limit]]


def main(argv: list[str] | None = None) -> int:
    from . import sites

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("site", nargs="?")
    ap.add_argument("--all", action="store_true", help="every built site whose Lens has Questions")
    args = ap.parse_args(argv)
    lenses = {q["lens"] for q in _all_questions()}
    if args.all:
        ids = [s for s in sites.all_ids() if config.data.exists(f"{s}/manifest.json") and _load_manifest(s)["lens"] in lenses]
    elif args.site:
        ids = [args.site]
    else:
        ap.error("give a site or --all")
    return 1 if sum(build(s) for s in ids) else 0


if __name__ == "__main__":
    sys.exit(main())
