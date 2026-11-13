"""Load and validate Showcase Site configs (sites/<id>.yaml, contract: contracts/site.schema.json)."""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

from saraura import config

sys.path.insert(0, str(config.CONTRACTS_DIR))
from validate import check_site  # noqa: E402


class InvalidSite(ValueError):
    pass


def path_for(site: str) -> Path:
    """Accept a site id or a path to its YAML."""
    p = Path(site)
    return p if p.suffix in (".yaml", ".yml") else config.SITES_DIR / f"{site}.yaml"


def load(site: str) -> dict:
    p = path_for(site)
    if not p.exists():
        raise FileNotFoundError(f"No site config at {p}")
    errs = check_site(p)
    if errs:
        raise InvalidSite(f"{p.name} is invalid:\n  " + "\n  ".join(errs))
    doc = yaml.safe_load(p.read_text(encoding="utf-8"))
    doc.setdefault("model_card", doc["lens"])
    return doc


def all_ids() -> list[str]:
    return sorted(p.stem for p in config.SITES_DIR.glob("*.yaml"))
