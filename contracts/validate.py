"""Validate SARAURA contract files: Showcase Site configs, manifests, Model cards, time-series parquet.

Usage (from the repo root):
    python contracts/validate.py                      # every sites/*.yaml, ml/model_cards/*.json, data/*/manifest.json
    python contracts/validate.py sites/venezuela_eq.yaml contracts/examples/manifest.json

The kind of each file is inferred from its name and location. Exit code 1 if anything fails.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CALIBRATED_START = dt.date(2025, 10, 29)  # earliest Granule in any PROVISIONAL collection; the collection, not the date, decides (ADR-0004)


def _registry() -> Registry:
    reg = Registry()
    for p in HERE.glob("*.schema.json"):
        reg = reg.with_resource(p.name, Resource.from_contents(json.loads(p.read_text(encoding="utf-8"))))
    return reg


REGISTRY = _registry()


def _validator(name: str) -> Draft202012Validator:
    schema = json.loads((HERE / f"{name}.schema.json").read_text(encoding="utf-8"))
    return Draft202012Validator(schema, registry=REGISTRY, format_checker=FormatChecker())


def _schema_errors(name: str, doc) -> list[str]:
    return [f"{'/'.join(map(str, e.absolute_path)) or '<root>'}: {e.message}" for e in _validator(name).iter_errors(doc)]


def _d(s: str) -> dt.date:
    return dt.date.fromisoformat(s)


def _inside(inner, outer) -> bool:
    return outer[0] <= inner[0] < inner[2] <= outer[2] and outer[1] <= inner[1] < inner[3] <= outer[3]


def check_site(path: Path) -> list[str]:
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    errs = _schema_errors("site", doc)
    if errs:
        return errs
    w, s, e, n = doc["bbox"]
    if not (w < e and s < n):
        errs.append("bbox: must be [lon_min, lat_min, lon_max, lat_max] with min < max")
    if doc["id"] != path.stem:
        errs.append(f"id: '{doc['id']}' must equal the file name '{path.stem}'")
    start, end = map(_d, doc["dates"])
    if start >= end:
        errs.append("dates: start must be before end")
    if start < CALIBRATED_START:
        errs.append(f"dates: start {start} is before the earliest calibrated Granule ({CALIBRATED_START}); BETA data is never used")
    if end > dt.date.today():
        errs.append(f"dates: end {end} is in the future")
    if "event_date" in doc and not start <= _d(doc["event_date"]) <= end:
        errs.append("event_date: must fall inside dates")
    if "event_end_date" in doc and not ("event_date" in doc and _d(doc["event_date"]) <= _d(doc["event_end_date"]) <= end):
        errs.append("event_end_date: needs event_date, and must fall between it and the end of dates")
    if "reference_area" in doc and not _inside(doc["reference_area"], doc["bbox"]):
        errs.append("reference_area: must lie inside bbox")
    if (e - w) * (n - s) > 4.0:
        errs.append("bbox: larger than 4 square degrees; Showcase Sites should be focused")
    return errs


def check_manifest(path: Path) -> list[str]:
    doc = json.loads(path.read_text(encoding="utf-8"))
    errs = _schema_errors("manifest", doc)
    if errs:
        return errs
    dates = [p["date"] for p in doc["passes"]]
    if dates != sorted(dates):
        errs.append("passes: must be sorted oldest first")
    for layer in doc["layers"]:
        missing = sorted(set(layer["dates"]) - set(dates))
        if layer["kind"] == "prediction" and dates:  # a forecast may point past the last Pass
            missing = [d for d in missing if d <= dates[-1]]
        if missing:
            errs.append(f"layers/{layer['id']}: dates {missing} are not Pass dates")
        if layer["kind"] == "prediction" and not layer["id"].startswith("pred_"):
            errs.append(f"layers/{layer['id']}: prediction layer ids must start with pred_ (ADR-0005)")
        lo, hi = layer["range"]
        if lo >= hi:
            errs.append(f"layers/{layer['id']}: range must be [low, high]")
    base = path.parent
    if base.name != "examples":  # real outputs: the files must exist
        for layer in doc["layers"]:
            for d in layer["dates"]:
                if not (base / "layers" / f"{layer['id']}_{d}.tif").exists():
                    errs.append(f"layers/{layer['id']}_{d}.tif: file missing")
        for s in doc["series"]:
            if not (base / s["path"]).exists():
                errs.append(f"{s['path']}: file missing")
    return errs


def check_model_card(path: Path) -> list[str]:
    doc = json.loads(path.read_text(encoding="utf-8"))
    errs = _schema_errors("model_card", doc)
    if not errs and doc["name"] != path.stem:
        errs.append(f"name: '{doc['name']}' must equal the file name '{path.stem}'")
    if not errs:
        for site in doc["sites"]:
            if not (ROOT / "sites" / f"{site}.yaml").exists():
                errs.append(f"sites: no sites/{site}.yaml")
    return errs


def check_parquet(path: Path) -> list[str]:
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError:
        return ["pyarrow is not installed; cannot check parquet"]
    schema = json.loads((HERE / "timeseries.schema.json").read_text(encoding="utf-8"))
    want = {c: pa.type_for_alias(t) for c, t in schema["x-arrow-types"].items()}
    table = pq.read_table(path)
    got = {f.name: f.type for f in table.schema}
    errs = [f"column {c}: expected {t}, found {got.get(c, 'missing')}" for c, t in want.items() if got.get(c) != t]
    extra = sorted(set(got) - set(want))
    if extra:
        errs.append(f"unexpected columns: {extra}")
    if not errs:
        v = _validator("timeseries")
        for row in table.slice(0, 200).to_pylist():
            row["date"] = row["date"].isoformat()
            errs += [e.message for e in v.iter_errors(row)]
    return errs[:20]


def kind_of(path: Path) -> str:
    if path.suffix in (".yaml", ".yml"):
        return "site"
    if path.suffix == ".parquet":
        return "parquet"
    if path.name == "manifest.json" or path.name.startswith("manifest"):
        return "manifest"
    if "model_card" in path.parts or path.parent.name == "model_cards" or path.name.startswith("model_card"):
        return "model_card"
    raise ValueError(f"Cannot tell what kind of contract file {path} is")


CHECKS = {"site": check_site, "manifest": check_manifest, "model_card": check_model_card, "parquet": check_parquet}


def default_files() -> list[Path]:
    return (
        sorted((ROOT / "sites").glob("*.yaml"))
        + sorted((ROOT / "ml" / "model_cards").glob("*.json"))
        + sorted((ROOT / "data").glob("*/manifest.json"))
        + sorted((HERE / "examples").glob("*.json"))
    )


def main(argv: list[str]) -> int:
    files = [Path(a) for a in argv] or default_files()
    failed = 0
    for f in files:
        errs = CHECKS[kind_of(f)](f)
        rel = f.resolve().relative_to(ROOT) if f.resolve().is_relative_to(ROOT) else f
        if errs:
            failed += 1
            print(f"FAIL {rel}")
            for e in errs:
                print(f"     {e}")
        else:
            print(f"ok   {rel}")
    print(f"\n{len(files) - failed}/{len(files)} valid")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
