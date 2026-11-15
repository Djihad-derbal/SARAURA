"""Earthquake Questions (E1-E4) on a small synthetic site, offline: a fault that tears the ground, a slope that keeps
sliding, a damaged town and a road across the fault (ADR-0008 rules; the damage class comes from the Baseline rule
here because no Model map is installed)."""
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

SITE = "venezuela_eq"
N = 40
GRID = {"epsg": 32619, "x0": 700000.0, "y0": 1170000.0, "res": 80.0, "shape": [N, N]}
PRE, CO = "2026-06-10", "2026-07-04"
POST = ["2026-07-16", "2026-07-28", "2026-08-09", "2026-08-21"]


def _lonlat(r, c):
    return answers.Geo(GRID).lonlat(r, c)


def _layer(lid, dates, kind="physics", unit="cm", cmap="rdbu", rng=(-10, 10)):
    return {"id": lid, "label": lid, "kind": kind, "unit": unit, "colormap": cmap, "range": list(rng), "dates": dates, "status": "prototype"}


@pytest.fixture()
def site(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "data", LocalStorage(tmp_path / "data"))
    monkeypatch.setattr(config, "cache", LocalStorage(tmp_path / "cache"))
    cols = np.arange(N)[None, :].repeat(N, 0)
    rows = np.arange(N)[:, None].repeat(N, 1)
    co_disp = np.where(cols < 20, 20.0, -20.0).astype(np.float32)  # the fault at column 20 tears the ground by 40 cm
    export.write_cog(SITE, f"disp_cm_{CO}", co_disp, GRID)
    cum = {PRE: np.zeros((N, N), np.float32), CO: co_disp.copy()}
    for i, d in enumerate(POST, 1):
        slide = np.where(rows < 10, -1.5 * i, 0.0)  # rows 0-9 slide 1.5 cm every 12 days (about 3.8 cm/month)
        cum[d] = (co_disp + slide).astype(np.float32)
    for d, a in cum.items():
        export.write_cog(SITE, f"cum_disp_cm_{d}", a, GRID)
        export.write_cog(SITE, f"coherence_{d}", np.full((N, N), 0.6, np.float32), GRID)
    loss = np.where(rows >= 30, 0.5, 0.05).astype(np.float32)  # rows 30-39: buildings lost their coherence
    export.write_cog(SITE, f"coherence_loss_{CO}", loss, GRID)
    export.write_cog(SITE, f"slope_{POST[-1]}", np.where(rows < 10, 30.0, 5.0).astype(np.float32), GRID)
    dates = [PRE, CO] + POST
    m = {"kind": "showcase", "id": SITE, "name": "Test quake", "lens": "earthquake", "bbox": [-67.4, 10.3, -66.4, 10.8], "event_date": "2026-06-24",
         "model_card": "earthquake", "generated_at": "2026-11-15T00:00:00Z", "passes": [{"date": d} for d in dates], "series": [],
         "layers": [_layer("disp_cm", [CO]), _layer("cum_disp_cm", dates), _layer("coherence", dates, unit="0-1", cmap="greys_r", rng=(0, 1)),
                    _layer("coherence_loss", [CO], unit="0-1", cmap="magma", rng=(0, 1)),
                    _layer("slope", [POST[-1]], kind="context", unit="deg", cmap="viridis", rng=(0, 45))]}
    config.data.write_text(f"{SITE}/manifest.json", json.dumps(m))

    def pt(name, r, c, kind="town"):
        lon, lat = _lonlat(r, c)
        return {"type": "Feature", "properties": {"name": name, "name_local": name, "ref": "", "class": kind},
                "geometry": {"type": "Point", "coordinates": [float(lon), float(lat)]}}
    places = {"type": "FeatureCollection", "features": [pt("Damaged town", 35, 8), pt("Sliding village", 4, 30, "village"), pt("Quiet hamlet", 20, 5, "hamlet")]}
    lon0, lat0 = _lonlat(24, 2)
    lon1, lat1 = _lonlat(24, 37)
    roads = {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {"name": "Coast road", "name_local": "", "ref": "T-1", "class": "trunk"},
                                                        "geometry": {"type": "LineString", "coordinates": [[float(lon0), float(lat0)], [float(lon1), float(lat1)]]}}]}
    for kind, fc in (("places", places), ("roads", roads), ("lines", {"type": "FeatureCollection", "features": []})):
        config.data.write_text(f"{SITE}/context/{kind}.geojson", json.dumps(fc))
    answers.build(SITE, log=lambda *a: None)
    return json.loads(config.data.read_text(f"{SITE}/answers/answers.json"))


def _q(doc, qid):
    return next(q for q in doc["questions"] if q["id"] == qid)


def _card(qid, r, c):
    lon, lat = _lonlat(r, c)
    return next(k for k in answers.at_point(SITE, float(lon), float(lat))["cards"] if k["question"] == qid)


def test_all_four_questions_are_answered(site):
    assert [q["id"] for q in site["questions"]] == ["e1_inspect_first", "e2_rebuild_where", "e3_still_moving", "e4_lifelines_crossed"]
    assert site["evidence"]["damage_source"] == "coherence_loss"
    assert [r["id"] for r in site["roles"]][:1] == ["civil_protection"]


def test_inspect_first_ranks_the_damaged_town(site):
    q = _q(site, "e1_inspect_first")
    assert q["ranked"]["rows"][0]["name"] == "Damaged town" and q["ranked"]["rows"][0]["high_share"] > 50
    assert "Baseline" in q["headline"]
    assert _card("e1_inspect_first", 35, 8)["label"] == "Check first"


def test_rebuild_where_flags_the_torn_strip(site):
    on_fault, far = _card("e2_rebuild_where", 15, 20), _card("e2_rebuild_where", 20, 3)
    assert on_fault["label"] == "Special study before rebuilding" and on_fault["measure"]["value"] > 30
    assert far["label"] == "Rebuild to the seismic code"


def test_still_moving_finds_the_slide(site):
    slide, steady = _card("e3_still_moving", 4, 30), _card("e3_still_moving", 25, 30)
    assert slide["label"] == "Still moving" and 3 < slide["measure"]["value"] < 5
    assert steady["label"] == "Steady"
    assert _q(site, "e3_still_moving")["ranked"]["rows"][0]["name"] == "Sliding village"


def test_lifelines_flags_the_road_across_the_fault(site):
    q = _q(site, "e4_lifelines_crossed")
    top = q["ranked"]["rows"][0]
    assert top["name"] == "T-1 (Coast road)" and top["class"] == 2
    near = _card("e4_lifelines_crossed", 24, 20)
    assert near["label"] == "Inspect before full use"
    assert _card("e4_lifelines_crossed", 5, 5)["label"] == "No flagged road or line here"
