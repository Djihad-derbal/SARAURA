"""Add Passes a Model's maps need to a built site's manifest, from NASA's catalogue only (no pixels downloaded).

    python -m pipeline.catalogue_passes <site_id>

A site built from interferograms only lists the dates of its pairs. A Model can map other Passes (it read the
backscatter for them elsewhere, e.g. in a notebook). This looks up each missing date's calibrated GCOV Granules on
the site's Stack in the catalogue and records the Pass, so the manifest is valid and the map's date picker can
show it (ADR-0004: collection recorded per Pass; ADR-0005: Models plug in through files).
"""
from __future__ import annotations

import json
import sys

from saraura import config

from . import predictions, sites
from .run_site import MATURITY_TO_COLLECTION, granules_for


def add_missing(site_id: str) -> list[str]:
    key = f"{site_id}/manifest.json"
    m = json.loads(config.data.read_text(key))
    have = {p["date"] for p in m["passes"]}
    need = sorted({d for l in m["layers"] for d in l["dates"]} - have)
    if not need:
        return []
    site = sites.load(site_id)
    stack = m["passes"][0]["stack"] if m["passes"] else None
    found = [g for g in granules_for(site, "GCOV") if g["date"] in need and (stack is None or g["stack"] == stack)]
    added = []
    for d in need:
        gs = [g for g in found if g["date"] == d]
        if not gs:
            continue
        m["passes"].append({"date": d, "collection": MATURITY_TO_COLLECTION[gs[0]["maturity"]], "stack": gs[0]["stack"],
                            "granules": sorted({g["id"] for g in gs})})
        added.append(d)
    m["passes"].sort(key=lambda p: p["date"])
    config.data.write_text(key, json.dumps(m, indent=1))
    return added


def main(site_id: str) -> int:
    added = add_missing(site_id)
    print(f"{site_id}: added Passes {', '.join(added) or 'none'} from the catalogue")
    return predictions.refresh(site_id)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
