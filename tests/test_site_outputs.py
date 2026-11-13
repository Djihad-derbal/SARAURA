"""Phase 1 checks on generated Showcase Site outputs (data/<site_id>/).

For every site that has been built: the manifest is valid, every layer file it lists exists,
is a COG in one CRS with the expected value range, and the physical sanity checks hold.
Sites that have not been built yet are skipped, so this runs on a fresh clone too.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest
import rasterio
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "contracts"))
from validate import check_manifest, check_parquet  # noqa: E402

SITES = sorted(p.stem for p in (ROOT / "sites").glob("*.yaml"))


def _manifest(site_id: str) -> dict:
    path = ROOT / "data" / site_id / "manifest.json"
    if not path.exists():
        pytest.skip(f"{site_id} not built yet (python -m pipeline.run_site {site_id})")
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("site_id", SITES)
def test_manifest_valid(site_id):
    _manifest(site_id)
    assert check_manifest(ROOT / "data" / site_id / "manifest.json") == []


@pytest.mark.parametrize("site_id", SITES)
def test_layers_are_cogs_in_one_crs(site_id):
    m = _manifest(site_id)
    crs = set()
    for layer in m["layers"]:
        for d in layer["dates"]:
            path = ROOT / "data" / site_id / "layers" / f"{layer['id']}_{d}.tif"
            with rasterio.open(path) as ds:
                assert ds.overviews(1) or max(ds.shape) < 1024, f"{path.name} has no overviews"
                assert ds.profile.get("tiled"), f"{path.name} is not tiled"
                crs.add(ds.crs.to_epsg())
    assert len(crs) <= 2, f"layers use several CRSs: {crs}"  # GCOV and GUNW grids may differ in zone only at edges


@pytest.mark.parametrize("site_id", SITES)
def test_value_ranges_plausible(site_id):
    m = _manifest(site_id)
    limits = {"hh_db": (-45, 25), "hv_db": (-50, 15), "coherence": (0, 1.0001), "slope": (0, 90), "baseline_wildfire": (0, 1)}
    for layer in m["layers"]:
        if layer["id"] not in limits:
            continue
        lo, hi = limits[layer["id"]]
        d = layer["dates"][-1]
        with rasterio.open(ROOT / "data" / site_id / "layers" / f"{layer['id']}_{d}.tif") as ds:
            a = ds.read(1, masked=True).compressed()
        a = a[np.isfinite(a)]
        assert a.size, f"{layer['id']}_{d} is empty"
        p1, p99 = np.percentile(a, [1, 99])
        assert lo <= p1 and p99 <= hi, f"{layer['id']}_{d}: 1-99% range {p1:.2f}..{p99:.2f} outside {lo}..{hi}"


@pytest.mark.parametrize("site_id", SITES)
def test_series_parquet(site_id):
    m = _manifest(site_id)
    for s in m["series"]:
        assert check_parquet(ROOT / "data" / site_id / s["path"]) == []


@pytest.mark.parametrize("site_id", SITES)
def test_displacement_near_zero_at_reference(site_id):
    m = _manifest(site_id)
    site = yaml.safe_load((ROOT / "sites" / f"{site_id}.yaml").read_text(encoding="utf-8"))
    ids = {l["id"]: l for l in m["layers"]}
    if "cum_disp_cm" not in ids or "reference_area" not in site:
        pytest.skip("no displacement or no reference area")
    from rasterio.warp import transform_bounds
    from rasterio.windows import from_bounds

    d = ids["cum_disp_cm"]["dates"][-1]
    with rasterio.open(ROOT / "data" / site_id / "layers" / f"cum_disp_cm_{d}.tif") as ds:
        b = transform_bounds("EPSG:4326", ds.crs, *site["reference_area"])
        a = ds.read(1, window=from_bounds(*b, ds.transform), masked=True).compressed()
    a = a[np.isfinite(a)]
    if a.size < 3:
        pytest.skip("too few reliable pixels in the reference area")
    assert abs(np.median(a)) < 1.0, f"reference area median {np.median(a):.2f} cm, expected about 0"


@pytest.mark.parametrize("site_id", SITES)
def test_terrain_files_match_meta(site_id):
    m = _manifest(site_id)
    if "terrain" not in m:
        pytest.skip("2D site")
    base = ROOT / "data" / site_id / "terrain"
    meta = json.loads((base / "meta.json").read_text(encoding="utf-8"))
    n = meta["shape"][0] * meta["shape"][1] * 4
    assert max(meta["shape"]) <= 512
    assert (base / "dem.f32").stat().st_size == n
    for d in meta["dates"]:
        assert (base / f"disp_{d}.f32").stat().st_size == n


@pytest.mark.parametrize("site_id", SITES)
def test_layers_cover_the_site(site_id):
    """The main radar layer must hold data over most of the site (Venezuela once covered 2%)."""
    m = _manifest(site_id)
    ids = {l["id"]: l for l in m["layers"]}
    main = next((k for k in ("hv_db", "coherence") if k in ids), None)
    if main is None:
        pytest.skip("no main radar layer")
    d = ids[main]["dates"][-1]
    with rasterio.open(ROOT / "data" / site_id / "layers" / f"{main}_{d}.tif") as ds:
        a = ds.read(1)
    share = float(np.isfinite(a).mean())
    assert share >= 0.5, f"{main}_{d} has data on only {share:.0%} of the site grid"


@pytest.mark.parametrize("site_id", SITES)
def test_rgb_composite(site_id):
    m = _manifest(site_id)
    layer = next((l for l in m["layers"] if l["id"] == "rgb"), None)
    if layer is None:
        pytest.skip("no GCOV composite for this site")
    with rasterio.open(ROOT / "data" / site_id / "layers" / f"rgb_{layer['dates'][-1]}.tif") as ds:
        assert ds.count == 3 and ds.dtypes[0] == "uint8" and ds.nodata == 0
        a = ds.read(out_shape=(3, 256, 256))
    valid = a.min(axis=0) > 0
    assert valid.mean() > 0.3, "composite is mostly nodata"
    for b in range(3):
        assert np.ptp(np.percentile(a[b][valid], [5, 95])) > 20, f"band {b + 1} is flat: stretch is wrong"


@pytest.mark.parametrize("site_id", SITES)
def test_prediction_layer_and_model_card(site_id):
    """Phase 2 check: each Showcase Site shows its Model's output, and the card carries both scores."""
    m = _manifest(site_id)
    preds = [l for l in m["layers"] if l["kind"] == "prediction"]
    assert preds, "no prediction layer: run the Model for this Lens (ml/)"
    for layer in preds:
        for d in layer["dates"]:
            assert (ROOT / "data" / site_id / "layers" / f"{layer['id']}_{d}.tif").exists()
    card = json.loads((ROOT / "ml" / "model_cards" / f"{m['model_card']}.json").read_text(encoding="utf-8"))
    assert site_id in card["sites"]
    assert card["baseline"]["score"] is not None and card["model"]["score"] is not None
    assert card["labels"]["source"] and card["limits"] and card["status"] in ("operational", "prototype")
