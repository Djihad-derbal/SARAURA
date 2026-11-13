"""Download and unpack the Copernicus EMS damage products for an activation (labels for the earthquake Model).

  python ml/fetch_emsr.py EMSR884

Writes ml/data/<code lower>/raw/*.zip and ml/data/<code lower>/x/<product>/. Products marked
"not feasible" by Copernicus (no download path) are skipped. Data: Copernicus Emergency Management
Service (c) European Union; cite it wherever the labels or scores are shown.
"""
import json
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = "https://rapidmapping.emergency.copernicus.eu/backend/dashboard-api/public-activations/?code={code}"


def fetch(code: str) -> list[Path]:
    out = ROOT / "ml" / "data" / code.lower()
    (out / "raw").mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(API.format(code=code), timeout=60) as r:
        act = json.load(r)["results"][0]
    (out / "activation.json").write_text(json.dumps(act, indent=1), encoding="utf-8")
    done = []
    for aoi in act["aois"]:
        for p in aoi["products"]:
            url = p.get("downloadPath")
            if not url:
                continue
            z = out / "raw" / url.rsplit("/", 1)[-1]
            if not z.exists() or z.stat().st_size == 0:
                print(f"downloading {z.name}")
                urllib.request.urlretrieve(url, z)  # follows the redirect to the file store
            dest = out / "x" / z.stem
            if not dest.exists():
                with zipfile.ZipFile(z) as f:
                    for m in f.namelist():  # refuse paths that would escape the folder
                        if Path(m).is_absolute() or ".." in Path(m).parts:
                            raise ValueError(f"unsafe path in {z.name}: {m}")
                    f.extractall(dest)
            done.append(dest)
    print(f"{len(done)} products in {out / 'x'}")
    return done


if __name__ == "__main__":
    fetch(sys.argv[1] if len(sys.argv) > 1 else "EMSR884")
