"""Display metadata for every layer the pipeline can write (legend, units, colormap, plain-language note).

One place, so Showcase Sites and Analyses describe the same variable the same way.
Colormaps are colourblind-safe names the tile server understands.
"""

LAYERS = {
    "hh_db": {
        "label": "Co-polarised backscatter (HH)",
        "unit": "dB",
        "colormap": "greys_r",
        "range": [-20, 0],
        "what_this_shows": "How strongly the ground reflects the radar back. Rough or built-up surfaces are bright; calm water is dark.",
    },
    "hv_db": {
        "label": "Cross-polarised backscatter (HV)",
        "unit": "dB",
        "colormap": "viridis",
        "range": [-28, -8],
        "what_this_shows": "Radar scattered by leaves and branches. Forests are bright; burned or bare land is darker.",
    },
    "hvhh_db": {
        "label": "HV/HH ratio",
        "unit": "dB",
        "colormap": "viridis",
        "range": [-16, -4],
        "what_this_shows": "Share of scattering from vegetation volume. Higher means more canopy.",
    },
    "rgb": {
        "label": "Colour composite (R = HH, G = HV, B = HH/HV)",
        "unit": "composite",
        "colormap": "rgb",
        "range": [1, 255],
        "what_this_shows": "Three radar channels as one picture, like NASA's UAVSAR Postcards. Green: forest and tall crops (strong HV). Magenta and pink: buildings and bare rough ground (strong HH, weak HV). Dark: calm water or smooth surfaces. Burned forest turns from green to purple.",
    },
    "dhv": {
        "label": "HV change since previous Pass",
        "unit": "dB",
        "colormap": "rdbu",
        "range": [-6, 6],
        "what_this_shows": "Red where vegetation scattering fell since the last Pass, blue where it rose.",
    },
    "dhh": {
        "label": "HH change since previous Pass",
        "unit": "dB",
        "colormap": "rdbu",
        "range": [-6, 6],
        "what_this_shows": "Red where the surface got darker since the last Pass (e.g. flooding of open ground), blue where brighter.",
    },
    "dhv_event": {
        "label": "HV change across the event",
        "unit": "dB",
        "colormap": "rdbu",
        "range": [-6, 6],
        "what_this_shows": "Median of the Passes after the event minus median before it. Strong drops mark lost canopy.",
    },
    "hv_mean": {
        "label": "HV mean over the season",
        "unit": "dB",
        "colormap": "viridis",
        "range": [-28, -8],
        "what_this_shows": "Average vegetation scattering across all Passes.",
    },
    "hv_std": {
        "label": "HV variability over the season",
        "unit": "dB",
        "colormap": "magma",
        "range": [0, 4],
        "what_this_shows": "How much vegetation scattering changed across Passes. Crops that grow and get harvested vary most.",
    },
    "hv_cv": {
        "label": "HV coefficient of variation",
        "unit": "ratio",
        "colormap": "magma",
        "range": [0, 1],
        "what_this_shows": "Variability relative to the mean (linear power). NISAR's crop algorithm uses it to separate crops from other land.",
    },
    "baseline_wildfire": {
        "label": "Burned (Baseline: HV drop > 1.5 dB)",
        "unit": "class",
        "colormap": "categorical",
        "range": [0, 1],
        "classes": [{"value": 1, "label": "Burned", "color": "#f97316"}],
        "what_this_shows": "The simple rule the AI Model must beat: land whose HV fell by more than 1.5 dB across the fire.",
    },
}


def entry(layer_id: str, dates: list[str], kind: str = "physics", status: str = "operational") -> dict:
    meta = LAYERS[layer_id]
    out = {"id": layer_id, "label": meta["label"], "kind": kind, "unit": meta["unit"], "colormap": meta["colormap"], "range": meta["range"], "dates": dates, "status": status}
    if "classes" in meta:
        out["classes"] = meta["classes"]
    out["what_this_shows"] = meta["what_this_shows"]
    return out
