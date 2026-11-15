"""Questions and answers for a Study (ADR-0008): what each Question found across the site, and the answer to
every Question at one clicked spot. Reads pipeline/answers.py output files; nothing runs a Model."""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Query

from saraura import config

from .study import ID, manifest

router = APIRouter()


def _doc(study_id: str) -> dict:
    if not ID.fullmatch(study_id):
        raise HTTPException(400, "Malformed id")
    key = f"{study_id}/answers/answers.json"
    if not config.data.exists(key):
        manifest(study_id)  # 404 with the usual message if the study itself is missing
        raise HTTPException(404, f"No Questions answered for {study_id} yet (python -m pipeline.answers {study_id})")
    return json.loads(config.data.read_text(key))


@router.get("/answers/{study_id}")
def answers(study_id: str, role: str | None = Query(None, pattern=r"^[a-z_]+$")):
    """Every Question for this study: headline, classes with area, ranked list, solutions, sources and limits.
    With `role`, only that role's Questions, in its order."""
    doc = _doc(study_id)
    from pipeline import answers as engine

    topics = {q["id"]: q.get("topic") for q in engine.questions(doc.get("lens"))}  # read live from questions/*.yaml
    doc = {**doc, "questions": [{**q, "topic": topics.get(q["id"])} for q in doc["questions"]]}
    if role:
        r = next((x for x in doc["roles"] if x["id"] == role), None)
        if r is None:
            raise HTTPException(404, f"No role {role}; roles: {[x['id'] for x in doc['roles']]}")
        by_id = {q["id"]: q for q in doc["questions"]}
        doc = {**doc, "questions": [by_id[q] for q in r["questions"] if q in by_id]}
    return doc


@router.get("/answers/{study_id}/places")
def places(study_id: str, q: str = Query(..., min_length=2, max_length=60)):
    """Neighbourhoods, towns and villages of this study whose name matches (OpenStreetMap, accents ignored)."""
    _doc(study_id)
    from pipeline import answers as engine

    return engine.search_places(study_id, q)


@router.get("/answers/{study_id}/features/{question}")
def features(study_id: str, question: str):
    """A Question's ranked items as GeoJSON (lines or points) with class colours, for drawing on the map."""
    _doc(study_id)
    if not ID.fullmatch(question):
        raise HTTPException(400, "Malformed question id")
    from pipeline import answers as engine

    try:
        return engine.features(study_id, question)
    except FileNotFoundError:
        raise HTTPException(404, f"No map features for {question}")


@router.get("/answers/{study_id}/at")
def answers_at(study_id: str, lon: float = Query(..., ge=-180, le=180), lat: float = Query(..., ge=-90, le=90)):
    """Each Question's answer at one spot: class, the measured numbers behind it, solutions, and for
    'better plots' the ranked alternatives nearby."""
    doc = _doc(study_id)
    w, s, e, n = doc.get("bbox") or manifest(study_id)["bbox"]
    if not (w <= lon <= e and s <= lat <= n):
        raise HTTPException(422, "That spot is outside this study's area")
    from pipeline import answers as engine

    return engine.at_point(study_id, lon, lat)
