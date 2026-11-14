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

Everything here is physics or rules on measured layers; no Model runs (ADR-0001, ADR-0005).
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

STEEP_DEG = 23.0
FLOW_CELL_M = 60.0


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
    land = np.isfinite(dem60) & (dem60 > 0)
    upstream[~land] = np.nan
    drainage[~land] = np.nan

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
    out = {"mud_upstream_ha": upstream, "hv_recovery": rec, "burned_share": burned_share, "steep_burned_share": steep_burned,
           "drainage_ha": drainage, "dem60": dem60.astype(np.float32)}
    for name in ("mud_upstream_ha", "hv_recovery", "burned_share", "steep_burned_share", "drainage_ha"):
        export.write_cog(site_id, f"{name}_{last}", out[name], g60, sub="layers" if name in ("mud_upstream_ha", "hv_recovery") else "evidence")
    f = np.isfinite(rec)
    log(f"  evidence: {np.nansum(steep_burned) * cell_ha:,.0f} ha burned on slopes >= {STEEP_DEG:.0f} deg; "
        f"recovery median {np.nanmedian(rec[f]) if f.any() else float('nan'):.2f} on {f.sum():,} burned blocks")
    return {
        "date": last,
        "grid": g60,
        "k": k,
        "arrays": out,
        "flow": (rcv, order),
        "burn_layer": burn_l["id"],
        "layers": [entry("mud_upstream_ha", [last], kind="physics", status="prototype"), entry("hv_recovery", [last], kind="physics", status="prototype")],
        "hidden": ["burned_share", "steep_burned_share", "drainage_ha"],
        "stats": {"burned_steep_ha": round(float(np.nansum(steep_burned) * cell_ha)), "burn_source": burn_l["id"]},
    }
