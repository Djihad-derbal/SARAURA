"""Model plug-in checks that run offline on small synthetic maps (ADR-0005, ADR-0010): season maps derived from a
water Model, the class-area (flood pulse) endpoint, and the export checker."""
import json
import shutil
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "ml"))

from fastapi.testclient import TestClient  # noqa: E402

from api.main import app  # noqa: E402
from pipeline import export, predictions  # noqa: E402
from saraura import config  # noqa: E402
from saraura.storage import LocalStorage  # noqa: E402

SITE = "okavango_wetland"
DATES = ["2026-07-01", "2026-07-13", "2026-08-06"]  # gaps of 12 and 24 days; the last Pass counts for the median, 18
GRID = {"epsg": 32734, "x0": 500000.0, "y0": 8000000.0, "res": 40.0, "shape": [4, 4]}


def _maps(three_class: bool):
    """Pixel (0,0): dry, then wet on Passes 2 and 3. (0,1): never wet. (0,2): no data on Pass 1, wet on 2.
    (0,3): flooded vegetation (2) on Pass 1 in the 3-class case, else open water."""
    fv = 2 if three_class else 1
    a = [np.zeros((4, 4), np.uint8) for _ in DATES]
    a[1][0, 0] = a[2][0, 0] = 1
    a[0][0, 2], a[1][0, 2] = 255, 1
    a[0][0, 3] = fv
    return a


def _card(three_class: bool) -> dict:
    outs = [{"value": 0, "label": "Dry land", "reliable": True}, {"value": 1, "label": "Open water", "reliable": True}]
    if three_class:
        outs.append({"value": 2, "label": "Flooded vegetation", "reliable": True})
    return {"lens": "wetland", "name": "wetland", "job": "Map water", "sites": [SITE], "outputs": outs, "status": "prototype",
            "model": {"name": "Test Model"}}


@pytest.mark.parametrize("three_class", [False, True])
def test_flood_season_counts_each_wet_pass_until_the_next(three_class):
    wet = [1, 2] if three_class else [1]
    s = predictions.flood_season(_maps(three_class), DATES, wet)
    assert s["frequency"][0, 0] == pytest.approx(2 / 3)
    assert s["hydroperiod"][0, 0] == 24 + 18
    assert s["onset"][0, 0] == 12
    assert np.isnan(s["frequency"][0, 1]) and np.isnan(s["hydroperiod"][0, 1]) and np.isnan(s["onset"][0, 1])
    assert s["frequency"][0, 2] == pytest.approx(1 / 2)  # the Pass with no data is skipped, not counted as dry
    assert s["onset"][0, 3] == 0 and s["hydroperiod"][0, 3] == 12


def _install_maps(tmp_path, monkeypatch, three_class: bool):
    monkeypatch.setattr(config, "data", LocalStorage(tmp_path / "data"))
    monkeypatch.setattr(config, "cache", LocalStorage(tmp_path / "cache"))
    for d, a in zip(DATES, _maps(three_class)):
        export.write_cog(SITE, f"pred_wetland_{d}", a, GRID, categorical=True)


@pytest.mark.parametrize("three_class", [False, True])
def test_season_maps_are_written_and_listed(tmp_path, monkeypatch, three_class):
    _install_maps(tmp_path, monkeypatch, three_class)
    out = predictions.flood_entries(SITE, "wetland", _card(three_class), DATES)
    assert [l["id"] for l in out] == ["pred_wetland_frequency", "pred_wetland_hydroperiod", "pred_wetland_onset"]
    for l in out:
        assert l["kind"] == "prediction" and l["dates"] == [DATES[-1]] and l["status"] == "prototype"
        assert config.data.exists(f"{SITE}/layers/{l['id']}_{DATES[-1]}.tif")
    # listing again without writing finds the same files
    assert predictions.flood_entries(SITE, "wetland", _card(three_class), DATES, write=False) == out


def test_no_season_maps_for_a_single_pass_or_a_dry_model(tmp_path, monkeypatch):
    _install_maps(tmp_path, monkeypatch, False)
    assert predictions.flood_entries(SITE, "wetland", _card(False), DATES[:1]) == []
    burn = {**_card(False), "outputs": [{"value": 0, "label": "No clear change"}, {"value": 1, "label": "Burned"}]}
    assert predictions.flood_entries(SITE, "wetland", burn, DATES) == []


def test_class_area_gives_the_flood_pulse(tmp_path, monkeypatch):
    _install_maps(tmp_path, monkeypatch, True)
    layer = {"id": "pred_wetland", "label": "AI Model: Test", "kind": "prediction", "unit": "class", "colormap": "categorical",
             "range": [0, 2], "dates": DATES, "status": "prototype",
             "classes": [{"value": 1, "label": "Open water", "color": "#2563eb"}, {"value": 2, "label": "Flooded vegetation", "color": "#06b6d4"}]}
    config.data.write_text(f"{SITE}/manifest.json", json.dumps({"generated_at": "2026-11-15T00:00:00Z", "layers": [layer]}))
    r = TestClient(app).get(f"/research/{SITE}/class_area")
    assert r.status_code == 200
    rows = r.json()["rows"]
    cell_ha = 40 * 40 / 1e4
    assert [x["date"] for x in rows] == DATES
    assert rows[0]["area_ha"] == {"1": 0.0, "2": cell_ha}  # Pass 1: one cell of flooded vegetation
    assert rows[1]["area_ha"]["1"] == pytest.approx(2 * cell_ha)
    assert rows[0]["analysed_ha"] == pytest.approx(15 * cell_ha)  # one cell has no data


def _export(tmp_path, card: dict, maps=None) -> Path:
    e = tmp_path / "export"
    (e / "ml" / "model_cards").mkdir(parents=True)
    (e / "ml" / "model_cards" / "wetland.json").write_text(json.dumps(card))
    src = LocalStorage(tmp_path / "src")
    for d, a in zip(DATES, maps or _maps(True)):
        key = f"{SITE}/layers/pred_wetland_{d}"
        orig = config.data
        config.data = src
        try:
            export.write_cog(SITE, key.split("/")[-1], a, GRID, categorical=True)
        finally:
            config.data = orig
    shutil.copytree(tmp_path / "src" / SITE, e / "data" / SITE)
    return e


def _real_card(**changes) -> dict:
    c = json.loads((ROOT / "ml" / "model_cards" / "wetland.json").read_text(encoding="utf-8"))
    c["outputs"] = _card(True)["outputs"]
    # fixed scores, so the test does not depend on whichever wetland Model is installed
    c["baseline"] = {"name": "Otsu threshold", "metric": "open-water IoU", "score": 0.47}
    c["model"] = {**c["model"], "metric": "open-water IoU", "score": 0.63}
    c["extra_scores"] = []
    for k, v in changes.items():
        c[k] = {**c[k], **v}
    return c


def test_export_checker_refuses_unlike_scores_and_weak_models(tmp_path, monkeypatch):
    import check_export

    monkeypatch.setattr(config, "data", LocalStorage(tmp_path / "data"))  # the site is "not built" here
    rep, *_ = check_export.check(_export(tmp_path / "a", _real_card(model={"metric": "accuracy"})))
    assert rep.failed and any("same way" in m for k, m in rep.lines if k == "FAIL")
    rep, *_ = check_export.check(_export(tmp_path / "a2", _real_card(model={"metric": "open-water IoU (held-out blocks)"})))
    assert not rep.failed and any("same samples" in m for k, m in rep.lines if k == "WARN")
    rep, *_ = check_export.check(_export(tmp_path / "b", _real_card(model={"score": 0.1})))
    assert rep.failed and any("does not beat" in m for k, m in rep.lines if k == "FAIL")
    bad = _maps(True)
    bad[0][1, 1] = 7
    rep, *_ = check_export.check(_export(tmp_path / "c", _real_card(), bad))
    assert rep.failed and any("not outputs" in m for k, m in rep.lines if k == "FAIL")


def test_export_checker_passes_a_good_export(tmp_path, monkeypatch):
    import check_export

    monkeypatch.setattr(config, "data", LocalStorage(tmp_path / "data"))
    rep, c, files = check_export.check(_export(tmp_path, _real_card()))
    assert not rep.failed, rep.lines
    assert len(files) == len(DATES)


def test_export_checker_allows_a_coarser_grid_but_not_another_projection(tmp_path, monkeypatch):
    import check_export

    data = LocalStorage(tmp_path / "data")
    monkeypatch.setattr(config, "data", data)
    fine = {**GRID, "res": 10.0, "shape": [16, 16]}  # the "built" site: a 10 m physics layer over the same 160 m square
    export.write_cog(SITE, f"hh_db_{DATES[0]}", np.zeros((16, 16), np.float32), fine)
    rep, *_ = check_export.check(_export(tmp_path / "a", _real_card()))
    assert not rep.failed, rep.lines
    assert any("own 40 m grid" in m for k, m in rep.lines if k == "WARN")
    monkeypatch.setattr(config, "data", LocalStorage(tmp_path / "data_utm33"))
    export.write_cog(SITE, f"hh_db_{DATES[0]}", np.zeros((16, 16), np.float32), {**fine, "epsg": 32733})
    rep, *_ = check_export.check(_export(tmp_path / "b", _real_card()))
    assert rep.failed and any("EPSG:32734" in m for k, m in rep.lines if k == "FAIL")


def test_errors_like_rmse_are_better_when_lower():
    import check_export

    assert check_export._lower_is_better("RMSE, cm (3 held-out Passes)")
    assert not check_export._lower_is_better("average precision (out-of-fold)")
    assert not check_export._lower_is_better("open-water IoU")
