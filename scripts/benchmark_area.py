"""Measure seconds per km² of a first (uncached) Analysis per product, and suggest area limits.

  python scripts/benchmark_area.py [--bbox W S E N] [--target-s 600]

Runs one GCOV and one GUNW Analysis through POST /jobs on an area no Showcase Site touches, so the
radar chunks are not cached yet. The suggested limit is the area a first Analysis covers in
--target-s seconds; put it in saraura/config.py (AREA_LIMIT_KM2) or the SARS_AREA_LIMIT_*_KM2
environment variables. Results go to cache/benchmark_area.json.
"""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from api.analyses import area_km2  # noqa: E402
from api.main import app  # noqa: E402
from saraura import config  # noqa: E402


def run(client, req):
    t0 = time.time()
    r = client.post("/jobs", json=req)
    if r.status_code != 200:
        return {"error": r.json().get("detail")}
    job = r.json()
    while job.get("status") in ("queued", "running"):
        time.sleep(5)
        job = client.get(f"/jobs/{job['id']}").json()
    return {"id": job["id"], "status": job["status"], "seconds": round(time.time() - t0, 1), "message": job.get("message"), "granules": job.get("granules")}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bbox", nargs=4, type=float, default=[31.00, 30.60, 31.11, 30.70], help="default: Nile delta, about 120 km²")
    ap.add_argument("--start", default="2026-06-17")
    ap.add_argument("--end", default="2026-10-31")
    ap.add_argument("--target-s", type=float, default=600)
    args = ap.parse_args()
    client = TestClient(app)
    km2 = area_km2(args.bbox)
    out = {"bbox": args.bbox, "area_km2": round(km2, 1), "target_s": args.target_s, "runs": {}}
    for product in ("GCOV", "GUNW"):
        res = run(client, {"bbox": args.bbox, "product": product, "start": args.start, "end": args.end, "name": f"Benchmark {product}"})
        if res.get("status") == "done":
            res["s_per_km2"] = round(res["seconds"] / km2, 3)
            res["suggested_limit_km2"] = int(round(args.target_s / res["s_per_km2"], -1))
        out["runs"][product] = res
        print(product, json.dumps(res))
    config.cache.write_text("benchmark_area.json", json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
