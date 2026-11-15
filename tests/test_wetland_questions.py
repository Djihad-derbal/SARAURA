"""Wetland Questions (W1-W5) on a small synthetic site, offline: a river that never dries, a floodplain that floods
for three Passes and drains on the last, reeds standing in water all season, a patch the flood reaches on the last
Pass, one lone speckle pixel, a camp on the floodplain and a track across it (ADR-0008 rules over the installed water
Model's maps, ADR-0010)."""
import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import answers, export  # noqa: E402
from saraura import config  # noqa: E402
from saraura.storage import LocalStorage  # noqa: E402

SITE = "okavango_wetland"
N = 40
GRID = {"epsg": 32734, "x0": 600000.0, "y0": 7900000.0, "res": 40.0, "shape": [N, N]}
DATES = ["2026-07-08", "2026-07-20", "2026-08-01", "2026-08-13", "2026-08-25"]
DRY, OPEN, VEG = 0, 1, 2


def _lonlat(r, c):
    return answers.Geo(GRID).lonlat(r, c)


def _maps() -> list[np.ndarray]:
    out = []
    for i in range(len(DATES)):
        a = np.full((N, N), DRY, np.uint8)
        a[:, 0:10] = OPEN                      # river: open water on every Pass
        if 1 <= i <= 3:
            a[0:30, 10:20] = OPEN              # floodplain: under water on Passes 2-4, dry again on the last
        a[30:40, 10:20] = VEG                  # reeds standing in water all season
        if i == 4:
            a[20:30, 30:36] = OPEN             # the flood reaches this patch on the last Pass
        a[5, 35] = OPEN                        # one lone speckle pixel, every Pass
        out.append(a)
    return out


@pytest.fixture()
def site(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "data", LocalStorage(tmp_path / "data"))
    monkeypatch.setattr(config, "cache", LocalStorage(tmp_path / "cache"))
    for d, a in zip(DATES, _maps()):
        export.write_cog(SITE, f"pred_wetland_{d}", a, GRID, categorical=True)
    m = {"kind": "showcase", "id": SITE, "name": "Test delta", "lens": "wetland", "bbox": [22.3, -19.7, 23.3, -18.8], "event_date": None,
         "model_card": "wetland", "generated_at": "2026-11-15T00:00:00Z", "series": [],
         "passes": [{"date": d, "collection": "VALIDATED_V1"} for d in DATES],
         "layers": [{"id": "pred_wetland", "label": "AI Model", "kind": "prediction", "unit": "class", "colormap": "categorical",
                     "range": [0, 2], "dates": DATES, "status": "prototype",
                     "classes": [{"value": 1, "label": "Open water", "color": "#2563eb"}]}]}
    config.data.write_text(f"{SITE}/manifest.json", json.dumps(m))

    def pt(name, r, c, kind):
        lon, lat = _lonlat(r, c)
        return {"type": "Feature", "properties": {"name": name, "name_local": name, "ref": "", "class": kind},
                "geometry": {"type": "Point", "coordinates": [float(lon), float(lat)]}}
    camps = {"type": "FeatureCollection", "features": [pt("Floodplain Camp", 15, 22, "camp_site"), pt("Dry Lodge", 8, 33, "lodge"),
                                                       pt("Dry Lodge annex", 8, 34, "camp_site")]}  # one place mapped twice
    places = {"type": "FeatureCollection", "features": [pt("Patch village", 26, 33, "village")]}
    lon0, lat0 = _lonlat(15, 2)
    lon1, lat1 = _lonlat(15, 37)
    tracks = {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {"name": "", "name_local": "", "ref": "", "class": "track"},
                                                         "geometry": {"type": "LineString", "coordinates": [[float(lon0), float(lat0)], [float(lon1), float(lat1)]]}}]}
    for kind, fc in (("camps", camps), ("places", places), ("tracks", tracks)):
        config.data.write_text(f"{SITE}/context/{kind}.geojson", json.dumps(fc))
    answers.build(SITE, log=lambda *a: None)  # the synthetic manifest is minimal, so it is not schema-valid
    return json.loads(config.data.read_text(f"{SITE}/answers/answers.json"))


def _q(doc, qid):
    return next(q for q in doc["questions"] if q["id"] == qid)


def _card(qid, r, c):
    lon, lat = _lonlat(r, c)
    return next(k for k in answers.at_point(SITE, float(lon), float(lat))["cards"] if k["question"] == qid)


def test_all_five_questions_are_answered(site):
    assert [q["id"] for q in site["questions"]] == ["w1_water_reach", "w2_dry_ground", "w3_hidden_water", "w4_tracks_flooded", "w5_since_last_pass"]
    assert site["evidence"]["pass_dates"] == DATES
    assert [r["id"] for r in site["roles"]][:1] == ["camp"]


def test_water_reach_classes_and_camps(site):
    assert _card("w1_water_reach", 20, 5)["label"] == "Open water all season"
    flood = _card("w1_water_reach", 15, 15)
    assert flood["label"] == "Open water most of the season" and flood["measure"]["value"] == 60
    assert _card("w1_water_reach", 10, 30)["label"] == "No open water seen"
    rows = _q(site, "w1_water_reach")["ranked"]["rows"]
    top = rows[0]
    assert top["name"] == "Floodplain Camp" and top["first_wet"] == "20 Jul" and top["now_share"] < top["peak_share"]
    assert "Dry Lodge" not in {r["name"] for r in rows}  # its only nearby water is a lone speckle pixel, dropped


def test_lone_speckle_is_dropped(site):
    assert _card("w2_dry_ground", 5, 35)["label"] == "Dry all season: build, store or drive"
    assert site["evidence"]["lone_wet_dropped_share"] > 0


def test_dry_ground_ranks_floods_by_length(site):
    short = _card("w2_dry_ground", 15, 15)
    assert short["label"] == "Short flood: graze or farm after it drops" and short["measure"]["value"] == 36
    assert _card("w2_dry_ground", 35, 15)["label"] == "Long flood: keep tracks and buildings out"  # reeds count as water here
    assert _card("w2_dry_ground", 10, 22)["label"] == "Dry, beside the flood"


def test_hidden_water_under_reeds(site):
    assert _card("w3_hidden_water", 35, 15)["label"] == "Water under reeds most of the season"
    assert _card("w3_hidden_water", 15, 15)["label"] == "Nothing to flag here"


def test_tracks_flooded(site):
    q = _q(site, "w4_tracks_flooded")
    top = q["ranked"]["rows"][0]
    assert top["class"] == 2 and top["wet_now"] == "yes" and top["first_wet"] == "8 Jul"  # the river crossing
    assert any(r["wet_now"] == "no" and r["wet_passes"] == 3 for r in q["ranked"]["rows"])  # the floodplain section
    assert all(r["name"] != "Unnamed track" for r in q["ranked"]["rows"])
    assert _card("w4_tracks_flooded", 15, 5)["label"] == "Under water most of the season"
    assert _card("w4_tracks_flooded", 35, 30)["label"] == "No flooding track here"


def test_since_last_pass(site):
    assert _card("w5_since_last_pass", 15, 15)["label"] == "Water left"
    assert _card("w5_since_last_pass", 25, 33)["label"] == "Water arrived"
    q = _q(site, "w5_since_last_pass")
    assert "receding" in q["headline"]
    assert {r["name"] for r in q["ranked"]["rows"]} >= {"Floodplain Camp", "Patch village"}
