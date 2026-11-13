"""GUNW path: line-of-sight displacement, coherence, cumulative series, reference-area correction.

Reads the 80 m unwrapped products through the shared chunk reader. All pairs of one Stack share
the same map grid, so pairs stack without resampling.

Sign convention: NISAR GUNW unwrapped phase is converted with  d = -phase * wavelength / (4 pi),
so POSITIVE displacement means motion TOWARD the satellite (blue in the legend). This follows the
ISCE convention (positive phase = range increase). It is flagged in the manifest until checked
against the GUNW product specification on a known case (Venezuela co-seismic uplift/subsidence).
"""
from __future__ import annotations

import math

import numpy as np

from saraura import cmr, gcov, render
from saraura.config import MATURITY_TO_COLLECTION

from . import coverage, export
from .layers import LAYERS, entry

WAVELENGTH_M = 299_792_458.0 / 1.239e9  # L-band centre frequency from the GUNW file (about 0.242 m)
PHASE_TO_CM = -WAVELENGTH_M / (4 * math.pi) * 100
SIGN_NOTE = "LOS sign convention (positive = toward satellite) is assumed from ISCE; consistent with Mexico City subsiding (moving away), still to confirm against the GUNW spec"
IONO_NOTE = "ionosphere phase screen from the GUNW product subtracted from every pair"
COHERENCE_MIN = 0.3  # team choice, stated in the README; results are also shown at 0.5

LAYERS.update(
    {
        "disp_cm": {
            "label": "Line-of-sight displacement",
            "unit": "cm",
            "colormap": "rdbu",
            "range": [-30, 30],
            "what_this_shows": "How far the ground moved toward (blue) or away from (red) the satellite between two Passes.",
        },
        "cum_disp_cm": {
            "label": "Cumulative line-of-sight displacement",
            "unit": "cm",
            "colormap": "rdbu",
            "range": [-15, 15],
            "what_this_shows": "Total ground movement since the first Pass, adding up each 12-day interferogram.",
        },
        "velocity_cm_month": {
            "label": "Mean line-of-sight velocity",
            "unit": "cm/month",
            "colormap": "rdbu",
            "range": [-3, 3],
            "what_this_shows": "Average speed of ground movement. Red areas are moving away from the satellite, usually sinking.",
        },
        "coherence": {
            "label": "Interferometric coherence",
            "unit": "0-1",
            "colormap": "greys_r",
            "range": [0, 1],
            "what_this_shows": "How similar the ground looked on the two Passes. Low values mean the surface changed (damage, lava, vegetation, water) or the measurement is unreliable.",
        },
        "coherence_loss": {
            "label": "Coherence loss across the event",
            "unit": "0-1",
            "colormap": "ylorrd",
            "range": [0, 0.6],
            "what_this_shows": "Drop in coherence in the pair spanning the event compared with a quiet pair. Strong loss often marks damage or new surfaces.",
        },
        "phase_gradient": {
            "label": "Displacement gradient",
            "unit": "cm/km",
            "colormap": "magma",
            "range": [0, 20],
            "what_this_shows": "Where displacement changes sharply over short distances, which traces faults and rupture zones.",
        },
    }
)


def select_pairs(site: dict) -> list[dict]:
    """GUNW pairs on one Stack (preferred, else most pairs), one per (reference, secondary), oldest first."""
    start, end = site["dates"]
    allowed = set(site["collections"])
    found = [
        g for g in cmr.search(tuple(site["bbox"]), start, end, "GUNW")
        if MATURITY_TO_COLLECTION[g["maturity"]] in allowed and g["secondary_date"] and g["date"] >= start and g["secondary_date"] <= end
    ]
    pref = site.get("stack")
    if pref:
        found = [g for g in found if g["track"] == pref["track"] and g["direction"] == pref["direction"]]
    if not found:
        raise RuntimeError(f"No calibrated GUNW pairs over {site['id']}")
    by_stack: dict[str, dict[tuple, dict]] = {}
    for g in found:
        by_stack.setdefault(g["stack"], {}).setdefault((g["date"], g["secondary_date"]), g)
    event = site.get("event_date")
    cov = coverage.stack_coverage(found, site["bbox"])

    def score(stack):  # coverage first, then a pair spanning the event, then more pairs
        pairs = by_stack[stack]
        spans = any(a < event <= b for a, b in pairs) if event else False
        return (cov[stack] >= coverage.MIN_COVERAGE, round(cov[stack], 1), spans, len(pairs))

    stack = max(by_stack, key=score)
    if cov[stack] < coverage.MIN_COVERAGE:
        raise RuntimeError(f"Best GUNW Stack {stack} covers only {cov[stack]:.0%} of {site['id']}")
    best = by_stack[stack]
    return [best[k] for k in sorted(best)]


def _grid(first_id: str, bbox) -> tuple[dict, dict]:
    fm = gcov.index(first_id)["freqs"]["U"]
    step = abs(fm["dx"])
    w, s, e, n = bbox
    edge = np.linspace(0, 1, 9)
    lon = np.concatenate([w + (e - w) * edge, w + (e - w) * edge, np.full(9, w), np.full(9, e)])
    lat = np.concatenate([np.full(9, s), np.full(9, n), s + (n - s) * edge, s + (n - s) * edge])
    gx, gy = render._to_grid(fm["epsg"]).transform(lon, lat)
    X0 = math.floor(gx.min() / step) * step
    Y0 = math.ceil(gy.max() / step) * step
    W = int(math.ceil((gx.max() - X0) / step))
    H = int(math.ceil((Y0 - gy.min()) / step))
    return {"epsg": fm["epsg"], "x0": X0, "y0": Y0, "res": step, "shape": [H, W]}, fm


def _read(granule_id: str, term: str, grid: dict) -> np.ndarray:
    f = gcov.index(granule_id)["freqs"]["U"]
    if f["epsg"] != grid["epsg"]:
        raise RuntimeError(f"{granule_id} is in EPSG:{f['epsg']}, not {grid['epsg']}")
    H, W = grid["shape"]
    c0 = int(round((grid["x0"] - (f["x0"] - f["dx"] / 2)) / f["dx"]))
    r0 = int(round((grid["y0"] - (f["y0"] - f["dy"] / 2)) / f["dy"]))
    return gcov.read_window(granule_id, "U", term, r0, r0 + H, c0, c0 + W)


def _ref_mask(grid: dict, ref_bbox) -> np.ndarray:
    H, W = grid["shape"]
    cols, rows = np.meshgrid(np.arange(W), np.arange(H))
    x = grid["x0"] + (cols + 0.5) * grid["res"]
    y = grid["y0"] - (rows + 0.5) * grid["res"]
    from pyproj import Transformer

    lon, lat = Transformer.from_crs(grid["epsg"], 4326, always_xy=True).transform(x, y)
    w, s, e, n = ref_bbox
    return (lon >= w) & (lon <= e) & (lat >= s) & (lat <= n)


def process(site: dict, log=print) -> dict:
    sid = site["id"]
    pairs = select_pairs(site)
    keys = [(p["date"], p["secondary_date"]) for p in pairs]
    log(f"  GUNW Stack {pairs[0]['stack']}: {len(pairs)} pairs {keys[0][0]} .. {keys[-1][1]}")
    grid, _ = _grid(pairs[0]["id"], site["bbox"])
    log(f"  grid {grid['shape'][0]} x {grid['shape'][1]} at {grid['res']:.0f} m, EPSG:{grid['epsg']}")
    ref = _ref_mask(grid, site["reference_area"]) if site.get("reference_area") else None
    if ref is not None and not ref.any():
        raise RuntimeError("reference_area covers no pixel of the GUNW grid; enlarge it")

    disp, coh = [], []
    notes = [SIGN_NOTE, IONO_NOTE]
    for i, p in enumerate(pairs):
        ph = _read(p["id"], "HH/unwrappedPhase", grid)
        # L-band ionosphere adds tens of cm of fake motion (measured on Mexico City: p5-p95 of a
        # 12-day pair shrank from -17..8 cm to -1..3 cm). The product ships the screen; remove it.
        iono = _read(p["id"], "HH/ionospherePhaseScreen", grid)
        ph = ph - np.where(np.isfinite(iono), iono, 0.0)
        cc = _read(p["id"], "HH/coherenceMagnitude", grid)
        comp = _read(p["id"], "HH/connectedComponents", grid)
        d = ph * PHASE_TO_CM
        # Keep only the largest connected component: separately unwrapped regions can be offset by
        # whole phase cycles (12 cm each), which no single reference can fix.
        labels = comp[np.isfinite(comp) & (comp > 0)].astype(np.int64)
        main = np.bincount(labels).argmax() if labels.size else 0
        d[~(comp == main)] = np.nan
        good = np.isfinite(d) & (cc >= COHERENCE_MIN)
        r = d[ref & good] if ref is not None else np.array([])
        if r.size >= 20:
            d = d - np.median(r)
        elif good.sum() >= 100:  # fall back to the scene: assumes most of the area did not move
            d = d - np.median(d[good])
            notes.append(f"pair {keys[i][0]}>{keys[i][1]}: referenced to the median of all coherent pixels "
                         f"({'reference_area had too few reliable pixels' if ref is not None else 'no reference_area'})")
        else:
            notes.append(f"pair {keys[i][0]}>{keys[i][1]}: too few coherent pixels to reference; values are relative only")
        disp.append(d.astype(np.float32))
        coh.append(cc.astype(np.float32))
        log(f"  read pair {i + 1}/{len(pairs)} {keys[i][0]} > {keys[i][1]}")
    disp, coh = np.stack(disp), np.stack(coh)
    masked = disp.copy()
    masked[coh < COHERENCE_MIN] = np.nan

    layers, stats = [], {}
    sec_dates = [k[1] for k in keys]
    for t, d in enumerate(sec_dates):
        export.write_cog(sid, f"coherence_{d}", coh[t], grid)
    layers.append(entry("coherence", sec_dates))
    if site["lens"] == "wetland":
        # Over water and flooded vegetation, interferometric phase reflects the water, not ground
        # motion; this Lens uses GUNW for coherence only.
        notes.append("wetland Lens: GUNW used for coherence only; phase over water is not ground motion")
        passes = {}
        for p, (a, b) in zip(pairs, keys):
            e = passes.setdefault(b, {"date": b, "collection": MATURITY_TO_COLLECTION[p["maturity"]], "stack": p["stack"], "granules": []})
            e["granules"].append(p["id"])
        return {"passes": [passes[d] for d in sorted(passes)], "layers": layers, "series": [], "stats": {}, "notes": notes, "grid": grid}
    for t, d in enumerate(sec_dates):
        export.write_cog(sid, f"disp_cm_{d}", masked[t], grid)
    layers.append(entry("disp_cm", sec_dates))

    # Cumulative displacement along the chain of consecutive pairs; a missing link stops the chain.
    breaks = [f"{a[1]} -> {b[0]}" for a, b in zip(keys, keys[1:]) if a[1] != b[0]]
    if breaks:
        notes.append(f"chain breaks at {', '.join(breaks)}: cumulative series restarts there")
    cum = np.zeros_like(disp[0])
    cum_dates, cum_stack = [], []
    for t in range(len(keys)):
        if t and keys[t][0] != keys[t - 1][1]:
            cum = np.zeros_like(cum)
        cum = cum + np.nan_to_num(disp[t], nan=0.0)
        out = cum.copy()
        out[~np.isfinite(masked[t])] = np.nan
        cum_dates.append(keys[t][1])
        cum_stack.append(out)
        export.write_cog(sid, f"cum_disp_cm_{keys[t][1]}", out, grid)
    layers.append(entry("cum_disp_cm", cum_dates))
    cum_stack = np.stack(cum_stack)

    days = np.array([(np.datetime64(d) - np.datetime64(keys[0][0])).astype(int) for d in cum_dates], np.float32)
    if len(days) >= 3:
        x = days - days.mean()
        y = np.where(np.isfinite(cum_stack), cum_stack, np.nan)
        with np.errstate(all="ignore"), np.testing.suppress_warnings() as sup:
            sup.filter(RuntimeWarning)
            slope = np.nansum(x[:, None, None] * (y - np.nanmean(y, 0)), 0) / np.sum(x**2)
        vel = (slope * 30.44).astype(np.float32)
        vel[np.isfinite(cum_stack).sum(0) < 3] = np.nan
        export.write_cog(sid, f"velocity_cm_month_{cum_dates[-1]}", vel, grid)
        layers.append(entry("velocity_cm_month", [cum_dates[-1]]))
        if np.isfinite(vel).any() and site["lens"] in ("subsidence", "volcano"):  # steady motion only means something there
            stats["fastest_sinking_cm_month"] = round(float(np.nanpercentile(vel, 1)), 2)
            stats["share_sinking_1cm_month"] = round(float(np.nanmean(vel < -1)), 4)

    event = site.get("event_date")
    co = [t for t, k in enumerate(keys) if event and k[0] < event <= k[1]]
    if co:
        t = co[0]
        quiet = [u for u, k in enumerate(keys) if u != t and (k[1] < event or k[0] >= event)]
        if quiet:
            q = min(quiet, key=lambda u: abs(u - t))
            loss = np.clip(coh[q] - coh[t], 0, 1).astype(np.float32)
            export.write_cog(sid, f"coherence_loss_{keys[t][1]}", loss, grid)
            layers.append(entry("coherence_loss", [keys[t][1]]))
            notes.append(f"coherence loss compares the event pair {keys[t][0]}>{keys[t][1]} with the quiet pair {keys[q][0]}>{keys[q][1]}")
        gy, gx = np.gradient(disp[t], grid["res"] / 1000)
        grad = np.hypot(gx, gy).astype(np.float32)
        export.write_cog(sid, f"phase_gradient_{keys[t][1]}", grad, grid)
        layers.append(entry("phase_gradient", [keys[t][1]]))
        d = masked[t]
        if np.isfinite(d).any():
            stats["coseismic_max_toward_cm"] = round(float(np.nanpercentile(d, 99.5)), 1)
            stats["coseismic_max_away_cm"] = round(float(np.nanpercentile(d, 0.5)), 1)
        stats["coseismic_masked_share"] = round(float(np.mean(~np.isfinite(d))), 3)

    series = [export.write_series(sid, "cum_disp_cm", cum_stack, cum_dates, grid, grid_m=160)]
    series[0]["unit"] = "cm"
    if ref is not None:
        stats["reference_residual_cm"] = round(float(np.nanstd(masked[:, ref])), 2) if np.isfinite(masked[:, ref]).any() else None

    passes = {}
    for p, (a, b) in zip(pairs, keys):
        for d in (a, b):
            e = passes.setdefault(d, {"date": d, "collection": MATURITY_TO_COLLECTION[p["maturity"]], "stack": p["stack"], "granules": []})
            if p["id"] not in e["granules"]:
                e["granules"].append(p["id"])
    stats["masked_share_gunw"] = round(float(np.mean(~np.isfinite(masked))), 3)
    return {"passes": [passes[d] for d in sorted(passes)], "layers": layers, "series": series, "stats": stats, "notes": notes, "grid": grid,
            "cum": {d: cum_stack[i] for i, d in enumerate(cum_dates)}}
