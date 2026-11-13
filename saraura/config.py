"""Settings: project paths, storage, Earthdata token, tuning knobs."""
import os
import re
from pathlib import Path

from . import storage

ROOT = Path(__file__).resolve().parents[1]

# Where things live. Override with a path (or, once hosted, an s3:// URL).
CACHE_DIR = Path(os.environ.get("SARS_CACHE_DIR", ROOT / "cache"))
DATA_DIR = Path(os.environ.get("SARS_DATA_DIR", ROOT / "data"))
cache = storage.from_url(str(CACHE_DIR))  # re-creatable: chunk tables, raw chunks, previews, Analyses
data = storage.from_url(str(DATA_DIR))  # Showcase Site outputs: data/<site_id>/...

SITES_DIR = ROOT / "sites"
CONTRACTS_DIR = ROOT / "contracts"
MODEL_CARDS_DIR = ROOT / "ml" / "model_cards"

# NISAR collections in NASA CMR, by product and maturity. Calibrated only, never BETA (ADR-0004).
# Our names: PROVISIONAL_V1 = NISAR_L2_<P>_PROVISIONAL_V1, VALIDATED_V1 = NISAR_L2_<P>_V1.
PRODUCT_COLLECTIONS = {
    "GCOV": {"validated": "C3622241360-ASF", "provisional": "C2854338529-ASF"},
    "GUNW": {"validated": "C3622247503-ASF", "provisional": "C2854335566-ASF"},
    "SME2": {"provisional": "C2854344945-ASF"},
}
COLLECTIONS = PRODUCT_COLLECTIONS["GCOV"]  # default product for the explorer
MATURITY_TO_COLLECTION = {"provisional": "PROVISIONAL_V1", "validated": "VALIDATED_V1"}

# Zoom at which tiles switch from the 80 m layer (frequencyB) to the 10 m one.
DETAIL_MIN_ZOOM = int(os.environ.get("SARS_DETAIL_MIN_ZOOM", "13"))
FETCH_THREADS = int(os.environ.get("SARS_FETCH_THREADS", "12"))
MEMORY_CHUNKS = int(os.environ.get("SARS_MEMORY_CHUNKS", "300"))  # about 1 MB each


# Largest Analysis area per product, km², so a first (uncached) Analysis finishes in about 10 minutes.
# Measured 2026-11-13 with scripts/benchmark_area.py on 117 km² of the Nile delta, June to October:
# GCOV 0.67 s/km² (27 Granules), GUNW 1.18 s/km² (23 pairs). Re-measure on the hosting machine.
AREA_LIMIT_KM2 = {
    "GCOV": float(os.environ.get("SARS_AREA_LIMIT_GCOV_KM2", "900")),
    "GUNW": float(os.environ.get("SARS_AREA_LIMIT_GUNW_KM2", "500")),
}

# Assistant (ADR-0006). The key comes from GEMINI_API_KEY in the environment or .env.
GEMINI_MODEL = os.environ.get("SARS_GEMINI_MODEL", "gemini-3.6-flash")
# Frontend that renders /report/<id> for the PDF Report (ADR-0007).
FRONTEND_URL = os.environ.get("SARS_FRONTEND_URL", "http://127.0.0.1:3000")


def _env_file_value(name: str) -> str:
    env = ROOT / ".env"
    if env.exists():
        m = re.search(rf"^{name}=(.*)$", env.read_text(encoding="utf-8"), re.M)
        if m:
            return m.group(1).strip()
    return ""


def secret(name: str) -> str:
    """A secret from the environment, else from the project's .env file. Empty if unset."""
    return os.environ.get(name, "").strip() or _env_file_value(name)


def earthdata_token() -> str:
    tok = secret("EARTHDATA_TOKEN")
    if not tok:
        raise RuntimeError("EARTHDATA_TOKEN is not set. Copy .env.example to .env and add a token.")
    return tok
