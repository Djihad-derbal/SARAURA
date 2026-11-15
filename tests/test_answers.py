"""Questions and answers (ADR-0008): flow routing on synthetic terrain, the built answers, and the API."""
from __future__ import annotations

import json

import numpy as np
import pytest

from pipeline import answers, evidence
from saraura import config

BUILT = [s for s in ("mexico_city_subsidence", "algeria_ne_wildfire") if config.data.exists(f"{s}/answers/answers.json")]


# ---------------------------------------------------------------- flow routing


def test_priority_flood_drains_a_valley_with_a_pit_to_the_edge():
    # a valley sloping to the left edge, with a closed pit in the middle
    z = np.tile(np.arange(10, dtype=float), (7, 1)) + np.abs(np.arange(7) - 3)[:, None] * 2
    z[3, 5] = -5 + 100  # make a bump...
    z[3, 6] = 1.0       # ...and a pit lower than its surroundings
    rcv, order = evidence.priority_flood(z)
    assert set(np.unique(rcv[rcv >= 0])) <= set(range(z.size))
    # every cell reaches an outlet (receiver -1) by following receivers
    for start in range(z.size):
        c, steps = start, 0
        while rcv[c] >= 0:
            c = rcv[c]
            steps += 1
            assert steps <= z.size
    # receivers come before donors in `order`
    pos = np.empty(z.size, int)
    pos[order] = np.arange(order.size)
    donors = np.flatnonzero(rcv >= 0)
    assert np.all(pos[rcv[donors]] < pos[donors])


def test_accumulate_and_reaches():
    # a 9 x 9 valley: slopes down to the left edge and towards the middle row
    r, c = np.mgrid[0:9, 0:9]
    z = c + 0.5 * np.abs(r - 4).astype(float)
    rcv, order = evidence.priority_flood(z)
    acc = evidence.accumulate(np.ones_like(z), rcv, order)
    assert acc[4, 1] >= 7  # the valley floor next to the outlet collects its whole row at least
    assert acc.sum() >= z.size
    mask = np.zeros_like(z, bool)
    mask[4, 1] = True
    hit = evidence.reaches(mask, rcv, order)
    assert hit[4, 7]  # the head of the valley drains through the masked cell
    assert not hit[0, 0]  # an edge cell is its own outlet


def test_sea_cells_are_outlets_not_land():
    z = np.full((5, 5), 10.0)
    z[:, 0] = np.nan  # sea on the left
    rcv, order = evidence.priority_flood(z)
    assert np.all(rcv.reshape(5, 5)[:, 0] == -1)
    assert set(order.tolist()).isdisjoint({r * 5 for r in range(5)})


def test_tilt_years_from_a_speed_ramp():
    # 2 cm/year of extra sinking every 100 m: tilt rate 2e-4 per year -> 1/500 in 10 years
    v = -np.tile(np.arange(40) * 2.0 * 0.8, (40, 1)).astype(np.float32)  # 80 m pixels: 1.6 cm/yr per pixel
    y = evidence.tilt_years(v, 80.0)
    assert np.allclose(np.nanmedian(y[5:-5, 5:-5]), 10.0, rtol=0.05)


# ---------------------------------------------------------------- question files


def test_every_question_has_a_recipe_and_known_solutions():
    cat = answers.solutions()
    for q in answers._all_questions():
        assert q["recipe"] in answers.RECIPES, q["id"]
        for c in q["classes"]:
            assert set(c["solutions"]) <= set(cat), q["id"]


def test_roles_only_name_questions_of_their_lens():
    by_id = {q["id"]: q for q in answers._all_questions()}
    for lens, roles in answers.roles().items():
        for r in roles:
            assert all(by_id[q]["lens"] == lens for q in r["questions"])


# ---------------------------------------------------------------- built answers


@pytest.mark.skipif(not BUILT, reason="no answers built yet (python -m pipeline.answers --all)")
@pytest.mark.parametrize("site", BUILT)
def test_built_answers_match_their_maps(site):
    doc = json.loads(config.data.read_text(f"{site}/answers/answers.json"))
    m = json.loads(config.data.read_text(f"{site}/manifest.json"))
    layer_ids = {l["id"] for l in m["layers"]}
    assert {q["id"] for q in doc["questions"]} == {q["id"] for q in answers.questions(doc["lens"])}
    for q in doc["questions"]:
        assert q["headline"]
        if q["point_only"]:
            assert q["layer"] is None
            continue
        assert q["layer"] in layer_ids
        assert config.data.exists(f"{site}/layers/{q['layer']}_{doc['date']}.tif")
        shares = sum(c["share"] for c in q["classes"])
        assert shares == pytest.approx(1.0, abs=0.01) or shares == 0
        for c in q["classes"]:
            assert all(s in doc["solutions"] for s in c["solutions"])


@pytest.mark.skipif("mexico_city_subsidence" not in BUILT, reason="Mexico City answers not built")
def test_mexico_city_known_places():
    # Nezahualcoyotl sinks fast (published ~30 cm/yr); Polanco, on firmer ground, is steady
    neza = answers.at_point("mexico_city_subsidence", -99.015, 19.40)
    pol = answers.at_point("mexico_city_subsidence", -99.195, 19.433)
    assert neza["values"]["vel"] < -20
    assert abs(pol["values"]["vel"]) < 3
    card = {c["question"]: c for c in pol["cards"]}
    assert card["m1_safe_to_build"]["verdict"] == "good"
    assert len(card["m3_better_plots"]["alternatives"]) >= 1


@pytest.mark.skipif("algeria_ne_wildfire" not in BUILT, reason="Algeria answers not built")
def test_algeria_point_answers_have_cards_for_every_question():
    doc = json.loads(config.data.read_text("algeria_ne_wildfire/answers/answers.json"))
    top = doc["questions"][0]["ranked"]["rows"][0]  # most exposed village
    r = answers.at_point("algeria_ne_wildfire", top["path_lon"], top["path_lat"])
    cards = {c["question"]: c for c in r["cards"]}
    assert set(cards) == {q["id"] for q in doc["questions"]}
    assert cards["a1_burned_slopes"]["class"] in (2, 3)  # on the mud path itself


@pytest.mark.skipif(not BUILT, reason="no answers built")
def test_answers_api():
    from fastapi.testclient import TestClient

    from api.main import app

    c = TestClient(app)
    site = BUILT[0]
    doc = c.get(f"/answers/{site}").json()
    role = doc["roles"][0]
    r = c.get(f"/answers/{site}", params={"role": role["id"]})
    assert [q["id"] for q in r.json()["questions"]] == [q for q in role["questions"] if q in {x["id"] for x in doc["questions"]}]
    w, s, e, n = doc["bbox"]
    assert c.get(f"/answers/{site}/at", params={"lon": (w + e) / 2, "lat": (s + n) / 2}).status_code == 200
    assert c.get(f"/answers/{site}/at", params={"lon": w - 1, "lat": s - 1}).status_code == 422
    assert c.get(f"/answers/{site}", params={"role": "nobody"}).status_code == 404
    assert c.get("/answers/kamchatka_volcano").status_code == 404  # no Questions for the volcano Lens yet


@pytest.mark.skipif(not BUILT, reason="no answers built")
def test_place_search_and_map_features():
    from fastapi.testclient import TestClient

    from api.main import app

    c = TestClient(app)
    if "mexico_city_subsidence" in BUILT:
        hits = c.get("/answers/mexico_city_subsidence/places", params={"q": "nezahual"}).json()  # accents ignored
        assert any("Nezahualc" in h["name"] for h in hits)
        fc = c.get("/answers/mexico_city_subsidence/features/m4_lines_at_risk").json()
        assert fc["type"] == "FeatureCollection" and fc["features"]
        f = fc["features"][0]
        assert f["geometry"]["type"] == "LineString" and f["properties"]["color"].startswith("#")
        assert c.get("/answers/mexico_city_subsidence/features/m1_safe_to_build").status_code == 404  # no drawn items
    if "algeria_ne_wildfire" in BUILT:
        fc = c.get("/answers/algeria_ne_wildfire/features/a1_burned_slopes").json()
        assert all(f["geometry"]["type"] == "Point" and f["properties"]["label"] for f in fc["features"])


@pytest.mark.skipif("algeria_ne_wildfire" not in BUILT, reason="Algeria answers not built")
def test_a_village_pin_is_answered_for_the_village():
    doc = json.loads(config.data.read_text("algeria_ne_wildfire/answers/answers.json"))
    v = doc["questions"][0]["ranked"]["rows"][0]
    card = answers.at_point("algeria_ne_wildfire", v["lon"], v["lat"])["cards"][0]
    assert card["class"] == v["class"]
    assert v["name"] in " ".join(card["reasons"])


@pytest.mark.skipif(not BUILT, reason="no answers built")
def test_sites_lead_with_their_questions():
    from fastapi.testclient import TestClient

    from api.main import app

    sites = {s["id"]: s for s in TestClient(app).get("/sites").json()}
    for sid in BUILT:
        d = sites[sid]["decide"]
        assert d and d["questions"] and d["roles"] and d["cover_layer"].startswith("ans_")
    from pipeline.answers import questions

    for s in sites.values():  # places without questions for their Lens stay research-only
        if not questions(s.get("lens")):
            assert s["decide"] is None


# ---------------------------------------------------------------- Jijel, next questions (A5, A7, A9)


def test_stitch_rings_joins_open_ways_into_a_closed_ring():
    from pipeline.context import stitch_rings

    a = [[0, 0], [1, 0], [1, 1]]
    b = [[0, 1], [1, 1]]  # reversed piece
    c = [[0, 1], [0, 0]]
    rings = stitch_rings([a, b, c])
    assert len(rings) == 1
    assert rings[0][0] == rings[0][-1] and len(rings[0]) == 5


def test_inflow_cells_flag_ground_sloping_in_from_the_edge():
    # a plane falling from the left edge to the right edge: water enters on the left and leaves on the right
    z = np.tile(np.arange(10, 0, -1, dtype=float), (5, 1))
    inflow = evidence.inflow_cells(z, np.ones_like(z, bool))
    assert inflow[2, 1] == 1
    assert inflow[2, 8] == 0  # the low right edge is an outlet, not an inflow
    assert inflow[2, 5] == 0  # not next to the border


@pytest.mark.skipif("algeria_ne_wildfire" not in BUILT, reason="Algeria answers not built")
def test_jijel_rivers_and_dams():
    items = json.loads(config.data.read_text("algeria_ne_wildfire/answers/a7_mud_to_water_items.json"))
    by = {i["name"]: i for i in items}
    assert by["Beni Haroun Dam"]["partial"] == "yes"  # fed from far beyond the map
    assert by["Barrage de Kissir"]["class"] == 1      # west of the fire
    assert by["Barrage El Agrem"]["class"] == 3       # inside the burned hills
    top = items[0]
    card = next(c for c in answers.at_point("algeria_ne_wildfire", top["lon"], top["lat"])["cards"] if c["question"] == "a7_mud_to_water")
    assert card["verdict"] == "bad" and any("ends up in" in r for r in card["reasons"])


@pytest.mark.skipif("algeria_ne_wildfire" not in BUILT, reason="Algeria answers not built")
def test_jijel_burned_fields_and_changes_are_listed():
    doc = json.loads(config.data.read_text("algeria_ne_wildfire/answers/answers.json"))
    qs = {q["id"]: q for q in doc["questions"]}
    farms = json.loads(config.data.read_text("algeria_ne_wildfire/answers/a5_farms_burned_items.json"))
    assert farms and all(f["class"] in (1, 2) and 0 < f["burned_ha"] <= f["area_ha"] + 0.1 for f in farms)
    assert "OpenStreetMap" in qs["a5_farms_burned"]["headline"]
    if doc["evidence"].get("burn_unmapped_share"):  # a burn map that covers only part of the site: its gaps are "not mapped", never "not burned"
        classes = {c["value"]: c for c in qs["a5_farms_burned"]["classes"]}
        assert classes[4]["verdict"] == "unknown" and classes[4]["area_ha"] > 0
    changes = json.loads(config.data.read_text("algeria_ne_wildfire/answers/a9_since_last_pass_items.json"))
    assert changes and changes[0]["class"] == 1  # lost vegetation is listed first
    assert "19 Oct" in qs["a9_since_last_pass"]["headline"]
