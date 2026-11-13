"""Call every API endpoint once and check /docs lists them all (Phase 3 check).

  python scripts/smoke_api.py            # includes one real small Analysis (needs network and an Earthdata token)
  python scripts/smoke_api.py --quick    # skips the Analysis job

The Assistant and the Report may answer 503 when GEMINI_API_KEY is unset or the frontend is not
running; that counts as a pass for "the endpoint is wired", and is reported as such.
"""
import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import morecantile  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from api.main import app  # noqa: E402

SITE = "algeria_ne_wildfire"
TMS = morecantile.tms.get("WebMercatorQuad")
results: list[tuple[str, int, str]] = []
called: set[tuple[str, str]] = set()


def hit(method: str, route: str, url: str, ok=(200,), soft=(), **kw):
    t = time.time()
    r = getattr(client, method.lower())(url, **kw)
    called.add((method, route))
    state = "ok" if r.status_code in ok else "soft" if r.status_code in soft else "FAIL"
    detail = ""
    if state != "ok":
        try:
            detail = str(r.json().get("detail"))[:110]
        except Exception:
            detail = r.text[:110]
    results.append((f"{method} {url[:90]}", r.status_code, f"{state} {time.time() - t:.2f}s {detail}"))
    return r


def main():
    global client
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    args = ap.parse_args()
    client = TestClient(app)

    hit("GET", "/health", "/health")
    hit("GET", "/sites", "/sites")
    m = hit("GET", "/sites/{study_id}", f"/sites/{SITE}").json()
    L = {l["id"]: l for l in m["layers"]}
    b = m["bbox"]
    lon, lat = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
    t = TMS.tile(lon, lat, 11)
    d = L["hv_db"]["dates"][-1]
    hit("GET", "/tiles/{study_id}/{layer_id}/{date}/{z}/{x}/{y}.png", f"/tiles/{SITE}/hv_db/{d}/{t.z}/{t.x}/{t.y}.png")
    hit("GET", "/terrain/{study_id}/{name}", "/terrain/venezuela_eq/meta.json")
    var = m["series"][0]["variable"]
    hit("GET", "/timeseries/{study_id}", f"/timeseries/{SITE}?variable={var}&lon={lon}&lat={lat}")
    poly = {"type": "Polygon", "coordinates": [[[lon - 0.05, lat - 0.05], [lon + 0.05, lat - 0.05], [lon + 0.05, lat + 0.05], [lon - 0.05, lat + 0.05], [lon - 0.05, lat - 0.05]]]}
    hit("POST", "/timeseries/{study_id}", f"/timeseries/{SITE}?variable={var}", json=poly)
    pd = L["pred_wildfire"]["dates"][-1]
    hit("GET", "/stats/{study_id}", f"/stats/{SITE}?layer=pred_wildfire&date={pd}")
    hit("POST", "/stats/{study_id}", f"/stats/{SITE}?layer=hv_db&date={d}", json=poly)
    hit("GET", "/preview/{study_id}/{layer_id}/{date}.png", f"/preview/{SITE}/pred_wildfire/{pd}.png?max_size=512")
    hit("GET", "/research/{study_id}/series_by_class", f"/research/{SITE}/series_by_class?variable=hv_db&layer=pred_wildfire&date={pd}")
    hit("GET", "/research/{study_id}/change_by_date", f"/research/{SITE}/change_by_date")
    hit("GET", "/research/{study_id}/agreement", f"/research/{SITE}/agreement")
    hit("GET", "/research/{study_id}/agreement.png", f"/research/{SITE}/agreement.png?max_size=512")
    hit("GET", "/models", "/models")
    hit("GET", "/models/{lens}", "/models/wildfire")

    hit("GET", "/coverage", f"/coverage?bbox={b[0]},{b[1]},{b[2]},{b[3]}&product=GCOV")
    g = hit("GET", "/granules", f"/granules?bbox={b[0]},{b[1]},{b[2]},{b[3]}&start=2026-08-01&end=2026-09-30").json()
    gid = g["stacks"][0]["passes"][0]["id"]
    gid2 = g["stacks"][0]["passes"][-1]["id"]
    hit("GET", "/browse/{granule_id}", f"/browse/{gid}")
    hit("GET", "/granules/{granule_id}", f"/granules/{gid}")
    hit("GET", "/browse/{granule_id}/preview/{pol}.png", f"/browse/{gid}/preview/HV.png")
    hit("GET", "/granules/{granule_id}/preview/{pol}.png", f"/granules/{gid}/preview/HV.png")
    hit("POST", "/browse/{granule_id}/prepare", f"/browse/{gid}/prepare")
    hit("POST", "/granules/{granule_id}/prepare", f"/granules/{gid}/prepare")
    hit("GET", "/browse/{granule_id}/tiles/{pol}/{z}/{x}/{y}.png", f"/browse/{gid}/tiles/HV/{t.z}/{t.x}/{t.y}.png")
    hit("GET", "/change/{before_id}/{after_id}/{pol}/{z}/{x}/{y}.png", f"/change/{gid}/{gid2}/HV/{t.z}/{t.x}/{t.y}.png")
    hit("GET", "/browse/timeseries", f"/browse/timeseries?lon={lon}&lat={lat}&start=2026-08-01&end=2026-09-30")

    hit("GET", "/assistant", "/assistant")
    hit("POST", "/assistant", "/assistant", soft=(503,), json={"study_id": SITE, "question": "What burned and when?", "layer": "pred_wildfire", "date": pd})
    hit("POST", "/report/{study_id}", f"/report/{SITE}", soft=(503,))

    hit("GET", "/jobs", "/jobs")
    if not args.quick:
        # About 60 km² inside the Algeria site, GCOV with the wildfire Lens.
        req = {"bbox": [6.00, 36.72, 6.09, 36.78], "product": "GCOV", "start": "2026-07-01", "end": "2026-10-15", "lens": "wildfire", "event_date": "2026-08-26"}
        job = hit("POST", "/jobs", "/jobs", json=req).json()
        t0 = time.time()
        while job.get("status") in ("queued", "running") and time.time() - t0 < 1800:
            time.sleep(5)
            job = client.get(f"/jobs/{job['id']}").json()
        called.add(("GET", "/jobs/{analysis_id}"))
        results.append((f"GET /jobs/{job['id']}", 200, f"{'ok' if job.get('status') == 'done' else 'FAIL'} {time.time() - t0:.0f}s {job.get('message', '')[:80]}"))
        if job.get("status") == "done":
            am = client.get(f"/sites/{job['id']}").json()
            assert am["kind"] == "analysis" and am["model_card"] is None
            assert not any(l["kind"] == "prediction" for l in am["layers"]), "an Analysis must never carry a Model layer (ADR-0001)"
            results.append(("Analysis has no Model layer (ADR-0001)", 200, "ok"))
        hit("POST", "/jobs", "/jobs", ok=(400,), json={**req, "bbox": [0, 0, 5, 5]})  # over the area limit
    hit("POST", "/analysis", "/analysis", ok=(200, 400), json={"stack": "109_D_070", "bbox": [6.0, 36.72, 6.05, 36.75], "resolution_m": 80})

    docs = client.get("/openapi.json").json()["paths"]
    listed = {(meth.upper(), path) for path, ops in docs.items() for meth in ops}
    hidden = {("GET", "/tiles/{granule_id}/{pol}/{z}/{x}/{y}.png"), ("GET", "/timeseries")}  # legacy aliases
    missing = [f"{m_} {p}" for m_, p in sorted(listed - called) if not p.startswith("/analysis/")]
    width = max(len(r[0]) for r in results)
    for name, code, state in results:
        print(f"{name:<{width}}  {code}  {state}")
    print(f"\n/docs lists {len(listed)} operations; not called by this script: {missing or 'none'}")
    fails = [r for r in results if "FAIL" in r[2]]
    print(f"{len(results) - len(fails)} passed, {len(fails)} failed")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
