"""List a Model's prediction layers in a Showcase Site's manifest (ADR-0005: Models plug in through files only).

A Model writes data/<site_id>/layers/pred_<lens>_<date>.tif and ml/model_cards/<name>.json. This module turns
those files into manifest layer entries, so neither the API nor the frontend needs to know any Model exists.

  python -m pipeline.predictions <site_id>   # refresh the manifest after a Model run, without rebuilding the site
"""
from __future__ import annotations

import json
import re
import sys

from saraura import config

# Fill colour for each output label; anything not listed falls back to grey.
COLORS = {
    "Burned": "#b91c1c", "No clear change": None,
    "Low damage likelihood": None, "Elevated damage likelihood": "#f59e0b", "High damage likelihood": "#b91c1c",
    "Open water": "#2563eb", "Flooded vegetation": "#06b6d4", "Dry land": None,
    "New lava": "#dc2626", "No new lava": None,
    "Maize": "#eab308", "Soybean": "#16a34a", "Other": None,
}


def card(name: str) -> dict | None:
    path = config.MODEL_CARDS_DIR / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def entries(site_id: str, lens: str, card_name: str | None) -> list[dict]:
    """Manifest layer entries for every pred_<lens>_<date>.tif present for this site."""
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
    return [{
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


def refresh(site_id: str) -> int:
    """Replace the prediction entries in an existing manifest with what is on disk."""
    sys.path.insert(0, str(config.CONTRACTS_DIR))
    from validate import check_manifest

    key = f"{site_id}/manifest.json"
    m = json.loads(config.data.read_text(key))
    m["layers"] = [l for l in m["layers"] if l["kind"] != "prediction"] + entries(site_id, m["lens"], m.get("model_card"))
    config.data.write_text(key, json.dumps(m, indent=1))
    errs = check_manifest(config.data.local_path(key))
    print(f"{key}: {sum(l['kind'] == 'prediction' for l in m['layers'])} prediction layer(s); manifest {'valid' if not errs else 'INVALID'}")
    for e in errs:
        print(f"  {e}")
    return 1 if errs else 0


if __name__ == "__main__":
    raise SystemExit(refresh(sys.argv[1]))
