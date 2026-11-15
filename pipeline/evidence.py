"""Evidence layers that Questions read (questions/*.yaml), derived from a built Showcase Site's own layers.

Subsidence (from the GUNW series):
  vert_vel_cm_yr     vertical speed: line-of-sight series / cos(incidence), straight-line fit (cm/year, + = up)
  fit_se_cm_yr       standard error of that speed (cm/year)
  accel_cm_yr2       change of speed per year from a quadratic fit (cm/year^2, - = sinking faster)
  tilt_years_500     years until uneven sinking between neighbouring pixels reaches Bjerrum's 1/500 limit
  mean_coherence     mean interferometric coherence over all pairs (0-1)

Wildfire (from GCOV, the burn map and the elevation model), on a 60 m grid:
  mud_upstream_ha    burned ground on slopes >= 23 degrees draining through each cell (ha)
  hv_recovery        share of the HV lost in the fire that has returned since (0-1)
  burned_upstream_ha all burned ground draining through each cell (ha): mud reaching rivers and dams (A7)
  edge_upstream      1 where part of the catchment lies beyond the edge of the map, so upstream shares are partial
  dhv60, dhh60       HV and HH change between the last two Passes on 60 m blocks (dB): what changed (A9)

Earthquake (from the GUNW pairs, the elevation model and, on a Showcase Site, the damage Model's map), on the GUNW grid:
  strain_cm_km       how sharply the ground was bent or torn by the earthquake: gradient of the event pair's motion
                     after a 400 m median smoothing (cm of line-of-sight motion per km)
  post_vel_cm_month  line-of-sight speed since the earthquake, a straight-line fit through the Passes after it
  post_coherence     mean coherence of the pairs after the earthquake (how reliable the speed is)
  damage_class       0 low, 1 elevated, 2 high damage likelihood: the AI Model's map where installed, else the
                     coherence-loss Baseline rule
  slope80            terrain slope (degrees), averaged onto this grid

Everything here is physics or rules on measured layers; no Model runs (ADR-0001, ADR-0005). The earthquake damage
class is the one place a Model's own output is read, as a Showcase Site's evidence (its card states the score).
"""
from __future__ import annotations

import heapq
import json
import math

import numpy as np
import rasterio

from saraura import config

from . import export
from .layers import LAYERS, entry

LAYERS.update({
    "vert_vel_cm_yr": {
        "label": "Vertical ground speed",
        "unit": "cm/year",
        "colormap": "rdbu",
        "range": [-30, 30],
        "what_this_shows": "How fast the ground sinks (red) or rises (blue), from the line-of-sight series divided by the cosine of the radar's incidence angle at each pixel, assuming the motion is vertical.",
    },
    "tilt_years_500": {
        "label": "Years until uneven sinking reaches the 1/500 crack limit",
        "unit": "years",
        "colormap": "magma",
        "range": [0, 50],
        "what_this_shows": "Neighbouring ground sinking at different speeds tilts buildings. This is how many years the measured difference in speed across about 160 m (after smoothing over 400 m) takes to reach a tilt of 1/500, where walls of buildings that must not crack start to suffer (Bjerrum, 1963). Dark = soon. Blank on slopes of 10 degrees or more, where the radar tilt is not reliable.",
    },
    "accel_cm_yr2": {
        "label": "Sinking speeding up or slowing down",
        "unit": "cm/year²",
        "colormap": "rdbu",
        "range": [-10, 10],
        "what_this_shows": "Curvature of each pixel's series. Red: sinking faster over the year. With only one year of data this is a first sign, not a trend.",
    },
    "mud_upstream_ha": {
        "label": "Burned steep ground draining through here",
        "unit": "ha",
        "colormap": "magma",
        "range": [0, 20],
        "what_this_shows": "Hectares of burned ground on slopes of 23 degrees or more upstream of each 60 m cell, from flow paths on the Copernicus elevation model. Bright lines are the channels mud would follow in heavy rain.",
    },
    "hv_recovery": {
        "label": "Forest recovery since the fire",
        "unit": "share",
        "colormap": "viridis",
        "range": [0, 1],
        "what_this_shows": "Share of the vegetation scattering (HV) lost in the fire (median before it minus the median of the Passes after it, except the last two) that has returned by the last two Passes, on burned 60 m blocks. Negative means it is still falling. Autumn rain can raise it without regrowth.",
    },
})

LAYERS.update({
    "strain_cm_km": {
        "label": "Ground bent or torn by the earthquake",
        "unit": "cm/km",
        "colormap": "magma",
        "range": [0, 40],
        "what_this_shows": "How fast the earthquake's ground motion (line of sight) changes from place to place, after smoothing over 400 m. Large values mean the ground was stretched, bent or torn: foundations, pipes and roads suffer there even without shaking damage. Blank where the radar lost the signal (often right on the fault).",
    },
    "post_vel_cm_month": {
        "label": "Ground still moving since the earthquake",
        "unit": "cm/month",
        "colormap": "rdbu",
        "range": [-4, 4],
        "what_this_shows": "Line-of-sight speed from a straight-line fit through every Pass after the earthquake (red: away from the satellite, blue: toward it). Ongoing motion after a quake is afterslip on the fault, settling of loose ground or a slow landslide.",
    },
})

STEEP_DEG = 23.0
FLOW_CELL_M = 60.0
NOISE_FLOOR_DB = -27.0  # HV below this in both Passes is near the radar's noise floor (water, radar shadow): no change measured


# ---------------------------------------------------------------- shared helpers


def grid_of(path) -> dict:
    with rasterio.open(path) as r:
        t = r.transform
        return {"epsg": r.crs.to_epsg(), "x0": t.c, "y0": t.f, "res": t.a, "shape": [r.height, r.width]}


def read(site_id: str, layer_id: str, date: str, sub: str = "layers") -> np.ndarray:
    with rasterio.open(config.data.local_path(f"{site_id}/{sub}/{layer_id}_{date}.tif")) as r:
        a = r.read(1).astype(np.float32)
        if r.nodata is not None and not np.isnan(r.nodata):
            a[a == r.nodata] = np.nan
    return a


def layer(m: dict, layer_id: str) -> dict | None:
    return next((l for l in m["layers"] if l["id"] == layer_id), None)


def _years(a: str, b: str) -> float:
    import datetime as dt

    return (dt.date.fromisoformat(b) - dt.date.fromisoformat(a)).days / 365.25


def block_mean(a: np.ndarray, k: int) -> np.ndarray:
    """Mean of k x k blocks, ignoring NaN; pads the edges."""
    H, W = a.shape
    Hp, Wp = -(-H // k) * k, -(-W // k) * k
    p = np.full((Hp, Wp), np.nan, np.float32)
    p[:H, :W] = a
    b = p.reshape(Hp // k, k, Wp // k, k)
    with np.errstate(invalid="ignore"):
        return np.nanmean(b, axis=(1, 3)).astype(np.float32)


# ---------------------------------------------------------------- subsidence


def _incidence(m: dict, grid: dict, height_m: float) -> np.ndarray:
    """Incidence angle (degrees) on `grid`, from the first Granule's radar-grid metadata cube (cached)."""
    from scipy.interpolate import RegularGridInterpolator

    gid = m["passes"][0]["granules"][0]
    key = f"answers/incidence_{gid}.npz"
    if not config.cache.exists(key):
        import h5py

        from saraura import cmr, remote

        p0 = m["passes"][0]["date"]
        found = [g for g in cmr.search(tuple(m["bbox"]), p0, p0, "GUNW") if g["id"] == gid]
        if not found:
            raise RuntimeError(f"Granule {gid} not found in CMR")
        base = "science/LSAR/GUNW/metadata/radarGrid"
        with h5py.File(remote.RangeFile(found[0]["h5_url"]), "r") as h:
            arrays = {k: h[f"{base}/{n}"][:] for k, n in (("inc", "incidenceAngle"), ("x", "xCoordinates"), ("y", "yCoordinates"), ("z", "heightAboveEllipsoid"))}
        np.savez_compressed(config.cache.local_path(key), **arrays)
    d = np.load(config.cache.local_path(key))
    inc, x, y, z = d["inc"], d["x"], d["y"], d["z"]
    if y[0] > y[-1]:
        y, inc = y[::-1], inc[:, ::-1, :]
    f = RegularGridInterpolator((z, y, x), inc, bounds_error=False, fill_value=None)
    H, W = grid["shape"]
    xs = grid["x0"] + (np.arange(W) + 0.5) * grid["res"]
    ys = grid["y0"] - (np.arange(H) + 0.5) * grid["res"]
    X, Y = np.meshgrid(xs, ys)
    pts = np.stack([np.full(X.size, height_m), Y.ravel(), X.ravel()], axis=1)
    return f(pts).reshape(H, W).astype(np.float32)


def _fit(t: np.ndarray, y: np.ndarray):
    """Per-pixel straight-line and quadratic fits of y (T, H, W) against t (T,), ignoring NaN."""
    T, H, W = y.shape
    Y = y.reshape(T, -1)
    w = np.isfinite(Y).astype(np.float64)
    Yz = np.where(w > 0, Y, 0.0).astype(np.float64)
    tt = t[:, None]
    S0, S1, S2 = w.sum(0), (w * tt).sum(0), (w * tt**2).sum(0)
    Sy, Sty = Yz.sum(0), (Yz * tt).sum(0)
    den = S0 * S2 - S1**2
    with np.errstate(invalid="ignore", divide="ignore"):
        b = (S0 * Sty - S1 * Sy) / den
        a = (Sy - b * S1) / S0
        res = np.where(w > 0, Yz - (a + b * tt), 0.0)
        s2 = (res**2).sum(0) / np.maximum(S0 - 2, 1)
        se = np.sqrt(s2 * S0 / den)
    # quadratic: y = c0 + c1 t + c2 t^2, acceleration = 2 c2
    M = np.stack([np.stack([S0, S1, S2]), np.stack([S1, S2, (w * tt**3).sum(0)]), np.stack([S2, (w * tt**3).sum(0), (w * tt**4).sum(0)])])
    rhs = np.stack([Sy, Sty, (Yz * tt**2).sum(0)])
    ok = S0 >= 6
    acc = np.full(Y.shape[1], np.nan)
    if ok.any():
        Mo = np.moveaxis(M[:, :, ok], 2, 0)
        ro = rhs[:, ok].T[..., None]
        sol = np.linalg.solve(Mo + np.eye(3) * 1e-9, ro)[..., 0]
        acc[ok] = 2 * sol[:, 2]
    bad = S0 < 6
    b[bad], se[bad] = np.nan, np.nan
    return b.reshape(H, W).astype(np.float32), se.reshape(H, W).astype(np.float32), acc.reshape(H, W).astype(np.float32)


TILT_WINDOW = 5        # pixels: speed is median-smoothed over 5 x 5 (400 m at 80 m) before the gradient
MAX_TILT_SLOPE_DEG = 10.0  # on steeper ground the tilt is not used: hillside motion is not vertical, and
                           # elevation-related radar delay (no tropospheric correction yet) adds noise there


def smooth(a: np.ndarray, size: int = TILT_WINDOW) -> np.ndarray:
    import warnings

    from scipy.ndimage import generic_filter

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return generic_filter(a.astype(np.float64), np.nanmedian, size=size, mode="nearest", cval=np.nan)


def tilt_years(vel_cm_yr: np.ndarray, res_m: float, limit: float = 1 / 500) -> np.ndarray:
    """Years until the tilt between neighbouring pixels reaches `limit`, from a median-smoothed speed map."""
    v = smooth(vel_cm_yr)
    gy, gx = np.gradient(v, res_m)
    rate = np.hypot(gx, gy) / 100.0  # (cm/year per m) -> per year
    with np.errstate(divide="ignore", invalid="ignore"):
        years = np.where(rate > 0, limit / rate, np.inf)
    years = np.clip(years, 0, 200).astype(np.float32)
    years[~np.isfinite(vel_cm_yr)] = np.nan
    return years


def subsidence(site_id: str, m: dict, log=print) -> dict:
    cum = layer(m, "cum_disp_cm")
    if not cum:
        raise RuntimeError("needs the cum_disp_cm layer (GUNW series)")
    dates = cum["dates"]
    last = dates[-1]
    first = m["passes"][0]["date"]
    grid = grid_of(config.data.local_path(f"{site_id}/layers/cum_disp_cm_{dates[0]}.tif"))
    height = 0.0  # incidence is read at the site's median ground height (it changes ~0.2 degrees per km of height)
    if config.data.exists(f"{site_id}/terrain/dem.f32"):
        height = float(np.median(np.fromfile(config.data.local_path(f"{site_id}/terrain/dem.f32"), "<f4")))
    inc = _incidence(m, grid, height)
    cosi = np.cos(np.radians(inc))
    los = np.stack([np.zeros(grid["shape"], np.float32)] + [read(site_id, "cum_disp_cm", d) for d in dates])
    los[0][~np.isfinite(los[1])] = np.nan
    vert = los / cosi[None]
    t = np.array([0.0] + [_years(first, d) for d in dates])
    vel, se, acc = _fit(t, vert)
    coh_l = layer(m, "coherence")
    coh = np.nanmean(np.stack([read(site_id, "coherence", d) for d in coh_l["dates"]]), axis=0) if coh_l else np.full(grid["shape"], np.nan, np.float32)
    years = tilt_years(vel, grid["res"])
    slope_l = layer(m, "slope")
    if slope_l:
        years[read(site_id, "slope", slope_l["dates"][-1]) >= MAX_TILT_SLOPE_DEG] = np.nan
    acc = smooth(acc).astype(np.float32)
    acc[~np.isfinite(vel)] = np.nan
    out = {"vert_vel_cm_yr": vel, "fit_se_cm_yr": se, "accel_cm_yr2": acc, "tilt_years_500": years, "mean_coherence": coh.astype(np.float32)}
    shown = ["vert_vel_cm_yr", "tilt_years_500", "accel_cm_yr2"]
    for name, arr in out.items():
        export.write_cog(site_id, f"{name}_{last}", arr, grid, sub="layers" if name in shown else "evidence")
    f = np.isfinite(vel)
    log(f"  evidence: incidence {np.nanmin(inc):.1f}-{np.nanmax(inc):.1f} deg; vertical speed p1 {np.nanpercentile(vel[f], 1):.1f} cm/yr, "
        f"median SE {np.nanmedian(se[f]):.2f} cm/yr; tilt under 15 years on {np.mean(years[f] < 15) * 100:.1f}% of pixels")
    return {
        "date": last,
        "grid": grid,
        "layers": [entry(n, [last], kind="physics", status="prototype") for n in shown],
        "hidden": ["fit_se_cm_yr", "mean_coherence"],
        "stats": {"incidence_deg": [round(float(np.nanmin(inc)), 1), round(float(np.nanmax(inc)), 1)], "reference_height_m": round(height)},
    }


# ---------------------------------------------------------------- wildfire


def priority_flood(z: np.ndarray):
    """Flow directions on a DEM by priority-flood (Barnes et al., 2014): every cell drains to its receiver,
    pits and flats included, ending at the grid edge or the sea (NaN or <= 0 m).
    Returns (receiver flat index or -1, processing order: receivers before donors)."""
    H, W = z.shape
    W2 = W + 2
    zp = np.full((H + 2, W2), np.nan)
    zp[1:-1, 1:-1] = z
    sea = ~np.isfinite(zp) | (zp <= 0.0)
    zl = zp.ravel().tolist()
    closed = bytearray(sea.ravel().astype(np.uint8).tobytes())
    rcv = [-1] * zp.size
    nbrs = (-W2 - 1, -W2, -W2 + 1, -1, 1, W2 - 1, W2, W2 + 1)
    heap = []
    land = np.flatnonzero(~sea.ravel())
    # seeds: land cells touching the sea or the grid edge
    seed_mask = np.zeros(zp.shape, bool)
    s = sea
    touch = s[:-2, 1:-1] | s[2:, 1:-1] | s[1:-1, :-2] | s[1:-1, 2:] | s[:-2, :-2] | s[:-2, 2:] | s[2:, :-2] | s[2:, 2:]
    seed_mask[1:-1, 1:-1] = touch & ~s[1:-1, 1:-1]
    for i in np.flatnonzero(seed_mask.ravel()).tolist():
        heap.append((zl[i], i))
        closed[i] = 1
    heapq.heapify(heap)
    order = []
    pop, push = heapq.heappop, heapq.heappush
    while heap:
        zc, c = pop(heap)
        order.append(c)
        for d in nbrs:
            n = c + d
            if closed[n]:
                continue
            closed[n] = 1
            rcv[n] = c
            zn = zl[n]
            push(heap, (zn if zn > zc else zc, n))
    # back to unpadded flat indices
    rcv_a = np.asarray(rcv, np.int64)
    order_a = np.asarray(order, np.int64)
    def unpad(ix):
        r, c = np.divmod(ix, W2)
        return (r - 1) * W + (c - 1)
    rcv_u = np.full(H * W, -1, np.int64)
    src = unpad(land)
    has = rcv_a[land] >= 0
    rcv_u[src[has]] = unpad(rcv_a[land][has])
    return rcv_u, unpad(order_a)


def accumulate(weight: np.ndarray, rcv: np.ndarray, order: np.ndarray) -> np.ndarray:
    """Sum of `weight` over every cell draining through each cell (itself included)."""
    acc = np.nan_to_num(weight.ravel().astype(np.float64)).tolist()
    r = rcv.tolist()
    for c in reversed(order.tolist()):
        t = r[c]
        if t >= 0:
            acc[t] += acc[c]
    return np.asarray(acc, np.float32).reshape(weight.shape)


def reaches(mask: np.ndarray, rcv: np.ndarray, order: np.ndarray) -> np.ndarray:
    """True for every cell whose flow path passes through a True cell of `mask` (itself included)."""
    hit = mask.ravel().astype(bool).tolist()
    r = rcv.tolist()
    for c in order.tolist():  # receivers come first
        if not hit[c]:
            t = r[c]
            if t >= 0 and hit[t]:
                hit[c] = True
    return np.asarray(hit, bool).reshape(mask.shape)


def inflow_cells(z: np.ndarray, land: np.ndarray) -> np.ndarray:
    """1 for interior land cells next to a higher land cell on the map's border: water from beyond the edge flows in
    there (the routing treats the border as an outlet, so that inflow is not counted, only flagged)."""
    H, W = z.shape
    border = np.zeros((H, W), bool)
    border[[0, -1], :] = True
    border[:, [0, -1]] = True
    out = np.zeros((H, W), np.float32)
    zz = np.where(land, z, np.nan)
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            if dr == dc == 0:
                continue
            # neighbour b = (r + dr, c + dc) of cell n = (r, c)
            n_sl = (slice(max(0, -dr), H - max(0, dr)), slice(max(0, -dc), W - max(0, dc)))
            b_sl = (slice(max(0, dr), H - max(0, -dr)), slice(max(0, dc), W - max(0, -dc)))
            with np.errstate(invalid="ignore"):
                hit = border[b_sl] & ~border[n_sl] & (zz[b_sl] > zz[n_sl])
            out[n_sl][hit] = 1
    return out


def wildfire(site_id: str, m: dict, site: dict, log=print) -> dict:
    from .dem import fetch_dem

    burn_l = layer(m, "pred_wildfire") or layer(m, "baseline_wildfire")
    if not burn_l:
        raise RuntimeError("needs a burn map (pred_wildfire or baseline_wildfire)")
    hv_l = layer(m, "hv_db")
    slope_l = layer(m, "slope")
    burned = read(site_id, burn_l["id"], burn_l["dates"][-1]) == 1
    slope = read(site_id, "slope", slope_l["dates"][-1])
    g20 = grid_of(config.data.local_path(f"{site_id}/layers/slope_{slope_l['dates'][-1]}.tif"))
    k = max(1, int(round(FLOW_CELL_M / g20["res"])))
    g60 = {**g20, "res": g20["res"] * k, "shape": [-(-g20["shape"][0] // k), -(-g20["shape"][1] // k)]}
    last = m["passes"][-1]["date"]

    burned_share = block_mean(burned.astype(np.float32), k)
    steep_burned = block_mean((burned & (slope >= STEEP_DEG)).astype(np.float32), k)
    cell_ha = g60["res"] ** 2 / 1e4
    dem60 = fetch_dem(site["bbox"], g60)
    log(f"  evidence: DEM {g60['shape'][0]} x {g60['shape'][1]} at {g60['res']:.0f} m; routing flow (priority-flood)")
    rcv, order = priority_flood(dem60.astype(np.float64))
    upstream = accumulate(steep_burned * cell_ha, rcv, order)
    drainage = accumulate(np.full(g60["shape"], cell_ha, np.float32), rcv, order)
    burned_up = accumulate(burned_share * cell_ha, rcv, order)
    land = np.isfinite(dem60) & (dem60 > 0)
    edge_up = (accumulate(inflow_cells(dem60, land), rcv, order) > 0).astype(np.float32)  # rivers entering from beyond the map
    for a in (upstream, drainage, burned_up, edge_up):
        a[~land] = np.nan

    # HV recovery on 60 m blocks (linear power, then dB)
    rec = np.full(g60["shape"], np.nan, np.float32)
    event = m.get("event_date")
    if hv_l and event:
        pre = [d for d in hv_l["dates"] if d < event]
        post = [d for d in hv_l["dates"] if d > event]
        if pre and len(post) >= 3:
            def mdb(ds):
                lin = np.nanmedian(np.stack([10 ** (read(site_id, "hv_db", d) / 10) for d in ds]), axis=0)
                return 10 * np.log10(np.maximum(block_mean(lin, k), 1e-6))
            # median of the post-fire Passes before the last two: a per-pixel minimum would pick speckle lows
            before, after, now = mdb(pre), mdb(post[:-2]), mdb(post[-2:])
            drop = before - after
            with np.errstate(invalid="ignore", divide="ignore"):
                rec = np.clip((now - after) / drop, -0.5, 1.5).astype(np.float32)
            rec[~(drop >= 1.5) | (burned_share < 0.5)] = np.nan
    # change since the previous Pass, on 60 m blocks (linear power, then dB); blocks without signal in both are blank
    dhv = np.full(g60["shape"], np.nan, np.float32)
    dhh = np.full(g60["shape"], np.nan, np.float32)
    prev = None
    hh_l = layer(m, "hh_db")
    if hv_l and hh_l and len(hv_l["dates"]) >= 2 and len(hh_l["dates"]) >= 2:
        prev, now_d = hv_l["dates"][-2], hv_l["dates"][-1]

        def bdb(name, d):
            return 10 * np.log10(np.maximum(block_mean(10 ** (read(site_id, name, d) / 10), k), 1e-6))
        hv0, hv1 = bdb("hv_db", prev), bdb("hv_db", now_d)
        dhv, dhh = hv1 - hv0, bdb("hh_db", now_d) - bdb("hh_db", prev)
        dark = (hv0 < NOISE_FLOOR_DB) & (hv1 < NOISE_FLOOR_DB)
        dhv[dark | ~land] = np.nan
        dhh[dark | ~land] = np.nan
    out = {"mud_upstream_ha": upstream, "hv_recovery": rec, "burned_share": burned_share, "steep_burned_share": steep_burned,
           "drainage_ha": drainage, "dem60": dem60.astype(np.float32), "burned_upstream_ha": burned_up, "edge_upstream": edge_up,
           "dhv60": dhv.astype(np.float32), "dhh60": dhh.astype(np.float32), "burned20": burned}
    for name in ("mud_upstream_ha", "hv_recovery", "burned_share", "steep_burned_share", "drainage_ha", "burned_upstream_ha", "edge_upstream", "dhv60", "dhh60"):
        export.write_cog(site_id, f"{name}_{last}", out[name], g60, sub="layers" if name in ("mud_upstream_ha", "hv_recovery") else "evidence")
    f = np.isfinite(rec)
    log(f"  evidence: {np.nansum(steep_burned) * cell_ha:,.0f} ha burned on slopes >= {STEEP_DEG:.0f} deg; "
        f"recovery median {np.nanmedian(rec[f]) if f.any() else float('nan'):.2f} on {f.sum():,} burned blocks")
    return {
        "date": last,
        "grid": g60,
        "grid20": g20,
        "prev_date": prev,
        "k": k,
        "arrays": out,
        "flow": (rcv, order),
        "burn_layer": burn_l["id"],
        "layers": [entry("mud_upstream_ha", [last], kind="physics", status="prototype"), entry("hv_recovery", [last], kind="physics", status="prototype")],
        "hidden": ["burned_share", "steep_burned_share", "drainage_ha"],
        "stats": {"burned_steep_ha": round(float(np.nansum(steep_burned) * cell_ha)), "burn_source": burn_l["id"]},
    }


# ---------------------------------------------------------------- earthquake

EQ_SMOOTH = 5            # pixels: the event pair's motion is median-smoothed over 5 x 5 (400 m at 80 m) before the gradient
EQ_MIN_POST = 3          # Passes after the earthquake needed for a speed
EQ_BASELINE = (0.25, 0.4)  # coherence loss for elevated / high damage when no Model is installed (team choice)


def _onto(site_id: str, layer_id: str, date: str, grid: dict, categorical: bool) -> np.ndarray:
    """A layer resampled onto `grid` (nearest for classes, average for values)."""
    from rasterio.warp import Resampling, reproject

    from .export import _transform

    out = np.full(grid["shape"], 255 if categorical else np.nan, np.uint8 if categorical else np.float32)
    with rasterio.open(config.data.local_path(f"{site_id}/layers/{layer_id}_{date}.tif")) as src:
        reproject(rasterio.band(src, 1), out, dst_transform=_transform(grid), dst_crs=f"EPSG:{grid['epsg']}",
                  dst_nodata=255 if categorical else np.nan, resampling=Resampling.nearest if categorical else Resampling.average)
    return out


def earthquake(site_id: str, m: dict, site: dict, log=print) -> dict:
    event = m.get("event_date") or site.get("event_date")
    disp_l, cum_l, coh_l = layer(m, "disp_cm"), layer(m, "cum_disp_cm"), layer(m, "coherence")
    loss_l = layer(m, "coherence_loss")
    if not (event and disp_l and cum_l and loss_l):
        raise RuntimeError("needs an event date and the GUNW layers disp_cm, cum_disp_cm and coherence_loss")
    co = loss_l["dates"][0]  # second date of the pair that spans the earthquake
    grid = grid_of(config.data.local_path(f"{site_id}/layers/disp_cm_{co}.tif"))
    last = cum_l["dates"][-1]

    # bent or torn ground: gradient of the smoothed event-pair motion
    d = smooth(read(site_id, "disp_cm", co), EQ_SMOOTH)
    gy, gx = np.gradient(d, grid["res"] / 1000)
    strain = np.hypot(gx, gy).astype(np.float32)

    # still moving: straight line through the cumulative motion of the Passes after the earthquake
    post = [x for x in cum_l["dates"] if x > co]
    vel = np.full(grid["shape"], np.nan, np.float32)
    if len(post) >= EQ_MIN_POST:
        base = read(site_id, "cum_disp_cm", co)
        y = np.stack([read(site_id, "cum_disp_cm", x) - base for x in post])
        t = np.array([_years(co, x) * 12 for x in post], np.float64)  # months
        ok = np.isfinite(y)
        n = ok.sum(0)
        tt = np.where(ok, t[:, None, None], np.nan)
        with np.errstate(invalid="ignore", divide="ignore"):
            import warnings

            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                tm, ym = np.nanmean(tt, 0), np.nanmean(y, 0)
                vel = (np.nansum((tt - tm) * (y - ym), 0) / np.nansum((tt - tm) ** 2, 0)).astype(np.float32)
        vel[n < EQ_MIN_POST] = np.nan
        vel = smooth(vel, 3).astype(np.float32)
        vel[n < EQ_MIN_POST] = np.nan
    after = [x for x in (coh_l["dates"] if coh_l else []) if x > co]
    post_coh = (np.nanmean(np.stack([read(site_id, "coherence", x) for x in after]), 0).astype(np.float32)
                if after else np.full(grid["shape"], np.nan, np.float32))

    # damage likelihood: the AI Model's class map where installed, else the coherence-loss rule
    pred_l = layer(m, "pred_earthquake")
    if pred_l and pred_l["kind"] == "prediction":
        dmg = _onto(site_id, "pred_earthquake", pred_l["dates"][-1], grid, categorical=True).astype(np.float32)
        dmg[dmg == 255] = np.nan
        source = "pred_earthquake"
    else:
        loss = read(site_id, "coherence_loss", co)
        with np.errstate(invalid="ignore"):
            dmg = np.where(np.isfinite(loss), (loss >= EQ_BASELINE[0]).astype(np.float32) + (loss >= EQ_BASELINE[1]), np.nan).astype(np.float32)
        source = "coherence_loss"
    slope_l = layer(m, "slope")
    slope = _onto(site_id, "slope", slope_l["dates"][-1], grid, categorical=False) if slope_l else np.full(grid["shape"], np.nan, np.float32)

    out = {"strain_cm_km": strain, "post_vel_cm_month": vel, "post_coherence": post_coh, "damage_class": dmg, "slope80": slope}
    shown = ["strain_cm_km", "post_vel_cm_month"]
    for name, arr in out.items():
        export.write_cog(site_id, f"{name}_{last}", arr, grid, sub="layers" if name in shown else "evidence")
    fs, fv = np.isfinite(strain), np.isfinite(vel)
    sp = (np.nanmedian(strain[fs]), np.nanpercentile(strain[fs], 99)) if fs.any() else (float("nan"),) * 2
    vp = np.nanpercentile(np.abs(vel[fv]), 95) if fv.any() else float("nan")
    log(f"  evidence: strain p50 {sp[0]:.1f}, p99 {sp[1]:.1f} cm/km; {len(post)} Passes after the quake, |speed| p95 {vp:.2f} cm/month; "
        f"damage from {source}")
    return {
        "date": last,
        "co_date": co,
        "grid": grid,
        "layers": [entry(n, [last], kind="physics", status="prototype") for n in shown],
        "hidden": ["post_coherence", "damage_class", "slope80"],
        "stats": {"damage_source": source, "co_event_date": co, "post_passes": len(post),
                  "strain_p99_cm_km": round(float(sp[1]), 1) if fs.any() else None},
    }
