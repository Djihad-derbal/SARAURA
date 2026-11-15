"""API checks that run offline on the built sites (no network, no API keys)."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from api import assistant  # noqa: E402
from api.main import app  # noqa: E402

client = TestClient(app)
SITE = "algeria_ne_wildfire"


def _manifest(sid=SITE):
    return client.get(f"/sites/{sid}").json()


def test_sites_list_all_showcase_sites():
    ids = {s["id"] for s in client.get("/sites").json()}
    assert {p.stem for p in (ROOT / "sites").glob("*.yaml")} <= ids


def test_tiles_render_every_layer_kind():
    import morecantile

    m = _manifest()
    b = m["bbox"]
    t = morecantile.tms.get("WebMercatorQuad").tile((b[0] + b[2]) / 2, (b[1] + b[3]) / 2, 10)
    for layer in m["layers"]:
        d = layer["dates"][-1]
        r = client.get(f"/tiles/{SITE}/{layer['id']}/{d}/{t.z}/{t.x}/{t.y}.png")
        assert r.status_code == 200 and r.headers["content-type"] == "image/png", f"{layer['id']}: {r.status_code} {r.text[:100]}"


def test_stats_name_every_class():
    m = _manifest()
    d = next(l for l in m["layers"] if l["id"] == "pred_wildfire")["dates"][-1]
    s = client.get(f"/stats/{SITE}?layer=pred_wildfire&date={d}").json()
    assert {c["label"] for c in s["classes"]} >= {"Burned", "No clear change"}


def test_bad_ids_are_rejected():
    assert client.get("/sites/../secrets").status_code in (400, 404)
    assert client.get("/sites/NOT_VALID").status_code == 400
    assert client.get("/terrain/venezuela_eq/..%2F..%2F.env").status_code in (400, 404)
    assert client.get(f"/tiles/{SITE}/hv_db/not-a-date/1/1/1.png").status_code == 400


def test_models_endpoint_matches_cards():
    rows = client.get("/models").json()
    assert {r["lens"] for r in rows} == {p.stem for p in (ROOT / "ml" / "model_cards").glob("*.json")}
    assert all(r["model_score"] is not None and r["baseline_score"] is not None for r in rows)


class _FakeModels:
    def __init__(self):
        self.calls = []

    def generate_content(self, model, contents, config):
        self.calls.append({"model": model, "contents": contents, "system": config.system_instruction})
        return type("R", (), {"text": "Grounded answer."})()


class _FakeClient:
    def __init__(self):
        self.models = _FakeModels()


def test_assistant_is_grounded_in_the_study(monkeypatch):
    fake = _FakeClient()
    monkeypatch.setattr(assistant, "_client", lambda: fake)
    m = _manifest()
    d = next(l for l in m["layers"] if l["id"] == "pred_wildfire")["dates"][-1]
    r = client.post("/assistant", json={"study_id": SITE, "question": "How much burned?", "layer": "pred_wildfire", "date": d})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["generated_by"] == "AI" and "Model card" in body["grounded_on"]
    system = fake.models.calls[0]["system"]
    card = json.loads((ROOT / "ml" / "model_cards" / "wildfire.json").read_text(encoding="utf-8"))
    assert str(card["baseline"]["score"]) in system  # the Baseline travels with the Model's score
    assert m["insights"][0][:40] in system
    assert "Never invent" in system


def test_assistant_never_sees_a_model_card_for_an_analysis():
    m = {**_manifest(), "kind": "analysis", "model_card": None}
    card = json.loads((ROOT / "ml" / "model_cards" / "wildfire.json").read_text(encoding="utf-8"))
    assert "model_card" not in json.loads(assistant.context(m, None, card))


def test_analyses_carry_no_model_layers():
    """ADR-0001: every finished Analysis on disk is physics + Baseline only."""
    found = 0
    for p in (ROOT / "data").glob("an_*/manifest.json"):
        m = json.loads(p.read_text(encoding="utf-8"))
        assert m["kind"] == "analysis" and m["model_card"] is None
        assert not any(l["kind"] == "prediction" for l in m["layers"]), p.parent.name
        found += 1
    if not found:
        pytest.skip("no Analysis built yet (scripts/smoke_api.py runs one)")


def test_old_quick_view_has_no_model_option():
    """ADR-0001: the deprecated /analysis route can no longer ask for a Model."""
    from api import jobs
    from api.main import AnalysisRequest

    assert "method" not in AnalysisRequest.model_fields
    assert not hasattr(jobs, "classify_model")


def test_showcase_requests_keep_contacts_private(tmp_path, monkeypatch):
    from saraura import config
    from saraura.storage import LocalStorage

    monkeypatch.setattr(config, "data", LocalStorage(tmp_path))
    r = client.post("/showcase-requests", json={"name": "Bejaia hills", "lon": 5.05, "lat": 36.75, "lens": "wildfire",
                                                "role": "civil_protection", "why": "Winter road closures", "contact": "me@example.org"})
    assert r.status_code == 200 and r.json()["status"] == "requested" and "contact" not in r.json()
    listed = client.get("/showcase-requests").json()
    assert [x["name"] for x in listed] == ["Bejaia hills"] and "contact" not in listed[0]
    assert client.post("/showcase-requests", json={"name": "x", "lon": 500, "lat": 0, "lens": "wildfire"}).status_code == 422
