"""List a Model's prediction layers in a Showcase Site's manifest (ADR-0005: Models plug in through files only).

A Model writes data/<site_id>/layers/pred_<lens>_<date>.tif and ml/model_cards/<name>.json. This module turns
those files into manifest layer entries, so neither the API nor the frontend needs to know any Model exists.

When a class Model maps water (an output labelled "Open water" or "Flooded vegetation") on two or more Passes,
three season maps are derived here from whatever maps are installed (ADR-0010), so a new or retrained Model gets
them with no code change:

  pred_<lens>_frequency   share of Passes on which the spot was under water (open or under vegetation)
  pred_<lens>_hydroperiod days under water through the season (each wet Pass counts until the next Pass)
  pred_<lens>_onset       days after the first Pass until the spot was first seen under water

  python -m pipeline.predictions <site_id>   # refresh the manifest after a Model run, without rebuilding the site
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date

import numpy as np

from saraura import config

# Fill colour for each output label; anything not listed falls back to grey.
COLORS = {
    "Burned": "#b91c1c", "No clear change": None,
    "Low damage likelihood": None, "Elevated damage likelihood": "#f59e0b", "High damage likelihood": "#b91c1c",
    "Open water": "#2563eb", "Flooded vegetation": "#06b6d4", "Dry land": None,
    "New lava": "#dc2626", "No new lava": None,
    "Maize": "#eab308", "Soybean": "#16a34a", "Other": None,
}


WET = ("Open water", "Flooded vegetation")  # output labels that count as "under water" for the season maps

# Season maps derived from a class Model's water maps: id suffix -> (label, unit, colormap, note)
FLOOD = {
    "frequency": ("How often under water", "share of Passes", "ylgnbu",
                  "Share of the radar Passes on which this spot was mapped as open water or flooded vegetation. "
                  "1 = wet on every Pass. Clear = never mapped wet in these Passes."),
    "hydroperiod": ("Days under water", "days", "ylgnbu",
                    "Roughly how many days this spot stayed under water through the season: each wet Pass counts "
                    "until the next Pass. Clear = never mapped wet."),
    "onset": ("When the water arrived", "days after first Pass", "cividis",
              "Days after the first Pass until this spot was first mapped under water. Dark = wet from the start, "
              "bright = the flood reached it late. Clear = never mapped wet."),
}


def flood_season(maps: list[np.ndarray], dates: list[str], wet: list[int]) -> dict[str, np.ndarray]:
    """Season maps from per-Pass class maps (uint8, 255 = no data). A Pass with no data at a spot is skipped there.
    Returns frequency (0-1), hydroperiod (days) and onset (days after the first Pass); NaN where never wet."""
    d = [date.fromisoformat(x) for x in dates]
    gaps = [(b - a).days for a, b in zip(d, d[1:])]
    gaps.append(int(np.median(gaps)) if gaps else 12)  # the last Pass counts for one usual repeat (12 days for NISAR)
    shape = maps[0].shape
    seen = np.zeros(shape, np.float32)
    n_wet = np.zeros(shape, np.float32)
    hydro = np.zeros(shape, np.float32)
    onset = np.full(shape, np.nan, np.float32)
    for m, gap, day in zip(maps, gaps, d):
        valid = m != 255
        is_wet = valid & np.isin(m, wet)
        seen += valid
        n_wet += is_wet
        hydro += is_wet * gap
        onset[is_wet & np.isnan(onset)] = (day - d[0]).days
    with np.errstate(invalid="ignore", divide="ignore"):
        freq = n_wet / seen
    never = n_wet == 0
    for a in (freq, hydro):
        a[never] = np.nan
    return {"frequency": freq, "hydroperiod": hydro, "onset": onset}


def flood_entries(site_id: str, lens: str, c: dict, dates: list[str], write: bool = True) -> list[dict]:
    """Derive (when `write`) and list the season maps for a class Model that maps water on 2+ Passes."""
    wet = [o["value"] for o in c.get("outputs", []) if o["label"] in WET and o.get("reliable", True)]
    if not wet or len(dates) < 2:
        return []
    last = dates[-1]
    key = lambda part: f"{site_id}/layers/pred_{lens}_{part}_{last}.tif"
    if write:
        import rasterio

        from . import export
        from .evidence import grid_of

        maps = []
        for day in dates:
            with rasterio.open(config.data.local_path(f"{site_id}/layers/pred_{lens}_{day}.tif")) as r:
                maps.append(r.read(1))
        grid = grid_of(config.data.local_path(f"{site_id}/layers/pred_{lens}_{dates[0]}.tif"))
        if any(m.shape != maps[0].shape for m in maps):
            print(f"  {site_id}: prediction maps differ in size; season maps skipped")
            return []
        for part, a in flood_season(maps, dates, wet).items():
            export.write_cog(site_id, f"pred_{lens}_{part}_{last}", a, grid)
    span = (date.fromisoformat(last) - date.fromisoformat(dates[0])).days
    top = {"frequency": 1, "hydroperiod": span + 12, "onset": max(span, 1)}
    out = []
    for part, (label, unit, cmap, note) in FLOOD.items():
        if not config.data.exists(key(part)):
            continue
        out.append({
            "id": f"pred_{lens}_{part}",
            "label": f"AI Model: {label}",
            "kind": "prediction",
            "unit": unit,
            "colormap": cmap,
            "range": [0, top[part]],
            "dates": [last],
            "status": c["status"],
            "what_this_shows": f"{note} Built from the AI Model's {len(dates)} water maps ({dates[0]} to {last}); "
                               "it inherits the Model's errors, so read its card first.",
        })
    return out


def card(name: str) -> dict | None:
    path = config.MODEL_CARDS_DIR / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def entries(site_id: str, lens: str, card_name: str | None, derive: bool = True) -> list[dict]:
    """Manifest layer entries for every pred_<lens>_<date>.tif present for this site, plus the season maps derived
    from them for a water Model (written here when `derive`)."""
    pat = re.compile(rf"^pred_{lens}_(\d{{4}}-\d{{2}}-\d{{2}})\.tif$")
    dates = sorted(m.group(1) for k in config.data.list(f"{site_id}/layers") if (m := pat.match(k.split("/")[-1])))
    c = card(card_name) if card_name else None
    if not dates or not c or site_id not in c["sites"]:
        return []
    if "prediction" in c:  # a quantity, e.g. a forecast in cm
        q = c["prediction"]
        return [{
            "id": f"pred_{lens}",
            "label": q.get("label", f"AI Model: {c['model']['name']}"),
            "kind": "prediction",
            "unit": q["unit"],
            "colormap": q["colormap"],
            "range": q["range"],
            "dates": dates,
            "status": c["status"],
            "what_this_shows": f"{c['job']}. Read the Model card for its score against the Baseline and its limits.",
        }]
    shown = [o for o in c.get("outputs", []) if o.get("reliable", True) and COLORS.get(o["label"], "#9ca3af")]
    classes = [{
        "id": f"pred_{lens}",
        "label": f"AI Model: {c['model']['name']}",
        "kind": "prediction",
        "unit": "class",
        "colormap": "categorical",
        "range": [min(o["value"] for o in c["outputs"]), max(o["value"] for o in c["outputs"])],
        "dates": dates,
        "status": c["status"],
        "classes": [{"value": o["value"], "label": o["label"], "color": COLORS.get(o["label"], "#9ca3af")} for o in shown],
        "what_this_shows": f"{c['job']}. Read the Model card for its score against the Baseline and its limits.",
    }]
    return classes + flood_entries(site_id, lens, c, dates, write=derive)


def refresh(site_id: str) -> int:
    """Replace the prediction entries in an existing manifest with what is on disk."""
    sys.path.insert(0, str(config.CONTRACTS_DIR))
    from validate import check_manifest

    key = f"{site_id}/manifest.json"
    m = json.loads(config.data.read_text(key))
    m["layers"] = [l for l in m["layers"] if l["kind"] != "prediction"] + entries(site_id, m["lens"], m.get("model_card"))
    # new Model maps: research results cached per manifest time (api/research.py) must be recomputed
    import datetime as dt

    m["generated_at"] = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    config.data.write_text(key, json.dumps(m, indent=1))
    errs = check_manifest(config.data.local_path(key))
    print(f"{key}: {sum(l['kind'] == 'prediction' for l in m['layers'])} prediction layer(s); manifest {'valid' if not errs else 'INVALID'}")
    for e in errs:
        print(f"  {e}")
    return 1 if errs else 0


if __name__ == "__main__":
    raise SystemExit(refresh(sys.argv[1]))
