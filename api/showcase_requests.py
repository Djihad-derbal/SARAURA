"""Requests for new Showcase Sites: someone picks a spot on the explorer's globe and asks the team to study it.

  POST /showcase-requests   store a request (place, point, what to study, why, optional contact)
  GET  /showcase-requests   the requested places, newest first, for the globe's "requested" pins (no contact details)

Requests are kept on this machine through the storage interface (ADR-0003) as showcase_requests/<id>.json.
Nothing is emailed or sent anywhere; the team reads them and decides which become Showcase Sites.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from saraura import config

router = APIRouter()

PREFIX = "showcase_requests"
LENSES = ("wildfire", "earthquake", "volcano", "subsidence", "wetland", "farming", "other")


class ShowcaseRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=80, description="The place, in the requester's words")
    lon: float = Field(..., ge=-180, le=180)
    lat: float = Field(..., ge=-90, le=90)
    lens: str = Field(..., pattern="^(" + "|".join(LENSES) + ")$", description="What to study there")
    role: str | None = Field(None, pattern=r"^[a-z_]{2,40}$", description="Who is asking (a Role id), if they said")
    why: str = Field("", max_length=400, description="What decision the study would help with")
    contact: str = Field("", max_length=200, description="How the team can reach them (kept private)")


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _public(doc: dict) -> dict:
    return {k: doc[k] for k in ("id", "name", "lon", "lat", "lens", "role", "why", "status", "created")}


@router.post("/showcase-requests")
def create(req: ShowcaseRequest):
    """Ask for a new Showcase Site at a point. Stored for the team; returns the request with status 'requested'."""
    body = req.model_dump()
    rid = "sr_" + hashlib.sha1(json.dumps(body, sort_keys=True).encode() + _now().encode()).hexdigest()[:12]
    doc = {"id": rid, **body, "status": "requested", "created": _now()}
    config.data.write_text(f"{PREFIX}/{rid}.json", json.dumps(doc, indent=1))
    return _public(doc)


@router.get("/showcase-requests")
def requested(limit: int = Query(100, ge=1, le=500)):
    """Requested places, newest first. Contact details are never returned."""
    docs = [json.loads(config.data.read_text(k)) for k in config.data.list(PREFIX) if k.endswith(".json")]
    return [_public(d) for d in sorted(docs, key=lambda d: d["created"], reverse=True)[:limit]]
