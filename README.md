# SARAURA

An open-source web app that turns NISAR radar data into maps, 3D views, time
series and reports for surface change anywhere on Earth. Built for the NASA
Space Apps Challenge 2026, "Dancing with the SARs".

Start with [PRODUCT.md](PRODUCT.md): what the product is for, how it answers questions at each place, how each
application scales, and how to set up on a new machine. Then [CONTEXT.md](CONTEXT.md) for the data facts. The build plan is [PLAN.md](PLAN.md), terms are in
[GLOSSARY.md](GLOSSARY.md), decisions are in [docs/adr/](docs/adr/), and the AI pieces are in
[ml/README.md](ml/README.md).

## Repository layout

| Folder | What it holds |
|---|---|
| `saraura/` | Shared Python package: NISAR search and chunk reader, change detection, tile rendering, storage interface |
| `api/` | FastAPI app: tiles, time series, on-demand Analyses, Assistant |
| `pipeline/` | Builds Showcase Sites from `sites/*.yaml` |
| `sites/` | One YAML per Showcase Site (contract: `contracts/site.schema.json`) |
| `contracts/` | JSON Schemas for site configs, manifests, Model cards, time series, plus `validate.py` |
| `ml/` | Models, trained offline; they plug in through files only (ADR-0005) |
| `frontend/` | Next.js web app |

## API

### Setup

1. Create a free NASA Earthdata account at https://urs.earthdata.nasa.gov
   and generate a token (Generate Token tab).
2. Copy `.env.example` to `.env` and paste the token after `EARTHDATA_TOKEN=`.
3. Install and run (Windows shown; on macOS/Linux use `.venv/bin/python`):

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
.venv/Scripts/python -m playwright install chromium   # once, for the PDF Report
.venv/Scripts/python -m uvicorn api.main:app --port 8000
```

Run every command from the repository root.

Interactive API docs are then at http://127.0.0.1:8000/docs.

### Endpoints

Study pages (Showcase Sites and finished Analyses share these; `{id}` is a site id or an `an_...` Analysis id):

| Route | What it returns |
|---|---|
| `GET /sites` | The Showcase Sites, one summary each (globe markers) |
| `GET /sites/{id}` | The full manifest: Passes, layers with legends, insights, quality notes |
| `GET /tiles/{id}/{layer}/{date}/{z}/{x}/{y}.png` | A layer on a date, coloured with its legend |
| `GET /terrain/{id}/{meta.json, dem.f32, disp_<date>.f32}` | 3D heightmap and displacement |
| `GET /timeseries/{id}?variable&lon&lat`, `POST` with a GeoJSON polygon | A variable through time at a point, or mean and spread over a polygon |
| `GET /stats/{id}?layer&date`, `POST` with a polygon | Percentiles, or area per class |
| `GET /models`, `GET /models/{lens}` | Model cards: Model and Baseline scores, labels, limits, Status |
| `GET /research/{id}/class_area?layer` | Hectares of each class of a class layer on every date (the flood pulse for a water Model) |

Explorer:

| Route | What it returns |
|---|---|
| `GET /coverage?bbox&product` | Footprints of calibrated Granules as GeoJSON (cached per 1° tile per day) |
| `GET /granules?bbox&start&end` | Granules grouped by Stack |
| `GET /browse/{granule}`, `.../preview/{pol}.png`, `POST .../prepare`, `.../tiles/{pol}/{z}/{x}/{y}.png` | One raw Granule: details, NASA preview, full-resolution tiles (`pol`: HH, HV, RGB) |
| `GET /change/{before}/{after}/{pol}/{z}/{x}/{y}.png` | Red where backscatter fell, blue where it rose |
| `GET /browse/timeseries?lon&lat` | Raw backscatter at a point for every Pass |
| `POST /jobs`, `GET /jobs/{id}`, `GET /jobs` | An Analysis of a drawn area: the site pipeline with an optional Lens (physics + Baseline, never a Model, ADR-0001). Cached by Granules, area, product and Lens |

Questions and answers (ADR-0008):

| Route | What it returns |
|---|---|
| `GET /answers/{id}` (`?role=`) | Every Question for the study: headline, classes with area, ranked list, Solutions, sources, limits |
| `GET /answers/{id}/at?lon&lat` | Each Question's answer at one spot: class, the measured numbers behind it, Solutions, and the better plots nearby |
| `GET /answers/{id}/features/{question}` | A Question's ranked items as GeoJSON lines or points with class colours, for the map |
| `GET /answers/{id}/places?q=` | Places in the study whose name matches (OpenStreetMap, both scripts, accents ignored) |

Assistant and Report:

| Route | What it returns |
|---|---|
| `GET /assistant`, `POST /assistant` | Gemini answer grounded in the study's manifest, insights, on-screen statistics and Model card (needs `GEMINI_API_KEY`; Status: prototype) |
| `POST /report/{id}` | The study as a PDF, printed from the frontend's `/report/{id}` page by headless Chromium (needs the frontend running) |

Area limits for an Analysis: 900 km² (GCOV) and 500 km² (GUNW), so a first, uncached run finishes in
about 10 minutes (measured: 0.67 and 1.18 s/km²; `scripts/benchmark_area.py`, override with
`SARS_AREA_LIMIT_GCOV_KM2` / `SARS_AREA_LIMIT_GUNW_KM2`). A repeat of the same Analysis is instant.

`POST /analysis` and the `/analysis/...` routes are the old quick change view (rules only), kept until
the frontend moves to `/jobs`. Check everything with `.venv/Scripts/python scripts/smoke_api.py`.

## Pipeline and contracts

```bash
.venv/Scripts/python contracts/validate.py                     # check every site, Model card and manifest
.venv/Scripts/python -m pipeline.run_site --all --plan         # calibrated Passes per Stack for each site
.venv/Scripts/python -m pipeline.run_site venezuela_eq --plan  # one site
.venv/Scripts/python -m pipeline.run_site algeria_ne_wildfire   # build a site into data/<site_id>/
.venv/Scripts/python -m pytest tests/                           # check built outputs
```

A first build downloads the needed radar chunks (several GB for a large site) into `cache/`;
rebuilds read from the cache and take from about 10 s to 4 minutes per site.

Team choices, stated as choices: coherence below 0.3 is masked; the wildfire Baseline marks
burned land where HV falls by more than 1.5 dB on land that was vegetated before (HV above
-20 dB); displacement is referenced to each site's `reference_area`, or to the median of all
coherent pixels when that area has too few reliable pixels.

### How it stays fast

- Each file's chunk layout is read once and saved under `cache/`.
- Pixels are fetched as individual compressed chunks, in parallel.
- Below zoom 13, tiles come from the file's built-in 80 m layer; from zoom 13
  they come from the full 10 m layer.
- Everything fetched is kept on disk, so a second view is instant.

## Questions and answers

The same NISAR evidence answers different questions for different people. Each Question is a file in
`questions/`, a rule recipe in `pipeline/answers.py` with its thresholds, sources and limits; each answer class
offers several Solutions from `solutions/catalogue.yaml` (cost, source, what to check on the ground). Roles in
`questions/roles.yaml` choose which Questions each user sees. The Study page opens on an "Ask this place" tab and
the open Question's map, with place search (cached OpenStreetMap names, accents ignored), an on-map legend, an answer
bubble at the clicked spot, and ranked items drawn as coloured lines or labelled points; the Report has a "Questions
answered" chapter. No Model runs here (ADR-0008). The wildfire Questions also run on the Washington site with no new
code (`--all`).

```bash
.venv/Scripts/python -m pipeline.answers mexico_city_subsidence   # or --all; run_site also runs it after a build
```

| Site | Question | Evidence | Headline (latest run) | Status |
|---|---|---|---|---|
| Mexico City | Is it safe to build here? | Vertical speed (line of sight / cos incidence), years to the 1/500 tilt limit, acceleration, fit error, coherence | 18% red, 38% amber, 29% blue, 16% not measurable | prototype |
| Mexico City | What can I build here? | Same | Standard buildings fit 29% of the measured ground | prototype |
| Mexico City | Are there better plots nearby? | Same, around a clicked spot | Up to 3 steadier spots within 2 km | prototype |
| Mexico City | Which Metro, rail and canal segments cross uneven sinking? | Speed along OpenStreetMap lines, per 250 m | 37 km reach 1/500 within 15 years (Metro Lines A, 5 and 12 among the worst) | prototype |
| Jijel | Which burned slopes could send mud onto villages this winter? | Burn map, slope >= 23 degrees, flow paths on Copernicus DEM (priority-flood), OSM villages | 14 villages beside a main mud path, 23 beside a smaller one | prototype |
| Jijel | Which roads should be watched or closed in heavy rain? | Same, along OSM roads | 115 sections to close, 187 to watch | prototype |
| Jijel | Where should replanting start? | Steepness, drains to people, HV recovery | 25,693 ha first | prototype |
| Jijel | Is the forest coming back? | HV recovery since the post-fire Passes | Mostly not yet, two months after the fire | prototype |
| Jijel | Which farms lost their cover? | Burn map (20 m) x OSM fields and orchards | 118 fields mostly burned, 9 partly; 163 ha of the 4,508 ha mapped; 157 not mapped by the burn map | prototype |
| Jijel | Is mud heading to the rivers and the dams? | Burned and burned-steep ground upstream (flow routing), OSM reservoirs and rivers | 7 of 26 reservoirs and river mouths have 10%+ of their catchment burned and steep; Tabellout gets the most burned steep ground | prototype |
| Jijel | What changed since the last Pass? | HV and HH change between the last two Passes, 60 m blocks, 3 dB | 58 ha lost vegetation signal, 87 ha darker; 29 patches near villages or roads | prototype |

Team choices, stated as choices: speed limits of 5 and 20 cm/year; tilt from speed smoothed over 400 m and not used
on slopes of 10 degrees or more; mud paths are channels in basins under 8 km2 with 15% (path) or 40% (main path) of
their ground burned and steep. The 1/500 tilt limit is Bjerrum (1963); the 23-degree slope is Staley et al. (2017).

## Models (ml/)

Models plug in only through files: `data/<site>/layers/pred_<lens>_<date>.tif` plus
`ml/model_cards/<lens>.json` (ADR-0005). Each is scored against a simple Baseline on ground it
did not train on (spatial blocks, or held-out Passes for the forecast). Build a site first, then:

```bash
.venv/Scripts/python ml/predict.py --site algeria_ne_wildfire            # wildfire (trained ChangeUTAE, models/change_utae.onnx)
.venv/Scripts/python ml/predict.py --site washington_sinlahekin_wildfire
.venv/Scripts/python ml/score_baseline.py --data ml/data/fires --site algeria_ne_wildfire
.venv/Scripts/python ml/score_site.py --site washington_sinlahekin_wildfire --pre 2026-06-10 2026-07-25 --post 2026-09-05 2026-10-10
.venv/Scripts/python ml/fetch_emsr.py EMSR884 && .venv/Scripts/python ml/earthquake.py
.venv/Scripts/python ml/farming.py      # needs Iowa CDL 2023-2025 in ml/data/cdl/<year>/ (URL in the script)
.venv/Scripts/python ml/wetland.py
.venv/Scripts/python ml/volcano.py
.venv/Scripts/python ml/subsidence.py
```

| Lens | Model | Labels | Score (Model vs Baseline) | Status |
|---|---|---|---|---|
| Wildfire | U-Net on pre/post-fire HH/HV composites (notebook `jijel-wildfire-full-site`, installed 2026-11-15; replaces ChangeUTAE 0.86) | Sentinel-2 burn index (proxy) | burned IoU 0.92 vs 0.33 (HV-drop rule) and 0.56 (trees), Algeria test blocks; not run on Washington | prototype |
| Earthquake | Ensemble LightGBM + U-Net on a GRU coherence anomaly (notebook export) | Copernicus EMS EMSR884 (real) | average precision 0.73 vs 0.61 (chance 0.13) | prototype |
| Farming | LightGBM on the Pass series | USDA CDL 2024+2025 rotation rule (proxy; CDL 2026 not out) | macro F1 0.86 vs 0.53 | prototype |
| Wetland | LightGBM open water + physics-guided flooded vegetation + HMM (notebook export v3) | Sentinel-2 MNDWI open water (proxy); flooded vegetation from physics, marked not reliable | open-water IoU 0.21 vs 0.013 on held-out 5 km blocks at true prevalence (balanced-sample scores were higher for every method, so this is the honest number) | prototype |
| Volcano | LightGBM on radar change statistics | Sentinel-2 hot spots (proxy) | average precision 0.073 vs 0.003 (chance) | prototype |
| Subsidence | LightGBM quantile forecast on an NSBAS series (notebook export) | Own time series (self-supervised) | RMSE 0.68 cm vs 0.63 cm: **does not beat the straight line** (its Kalman filter, 0.61, does) | prototype |

**Season maps for water Models (ADR-0010).** When a Model maps "Open water" (and optionally "Flooded vegetation")
on 2+ Passes, `python -m pipeline.predictions <site>` also derives `pred_<lens>_frequency` (share of Passes wet),
`pred_<lens>_hydroperiod` (days wet) and `pred_<lens>_onset` (days after the first Pass until first wet), and the
research plots show the flood pulse. 2-class and 3-class Models both work, with no code change.

**Models trained elsewhere (ADR-0010).** Check a notebook export before it replaces a Model:

```bash
.venv/Scripts/python ml/check_export.py path/to/export              # report: card, like-for-like score, grid, classes, dates, pulse
.venv/Scripts/python ml/check_export.py path/to/export --install    # install only if every check passes (keeps the old Model)
```

All scores, splits and limits are on each Model card. Team choices: earthquake damage =
Damaged or Destroyed buildings; volcano lava = hot on 3+ Sentinel-2 scenes within 10 km of the
vent; farming labels assume maize/soybean rotation.

## Frontend

A Next.js app (`frontend/`). Start the API first, then:

```bash
pnpm --dir frontend install
pnpm --dir frontend dev          # or: pnpm --dir frontend build && pnpm --dir frontend start
```

Open http://localhost:3000. Routes: `/` Places (decisions first), `/place/<id>` a place's questions
(`?role=&q=` to share a view), `/explore` the Research explorer, `/study/<id>` a site's research view,
`/browse` raw Granules, `/models` Model scores, `/report/<id>` the printable Report. Set `NEXT_PUBLIC_API_URL` if the API is not at `http://127.0.0.1:8000`,
and `SARS_FRONTEND_URL` on the API if the frontend is not at `http://127.0.0.1:3000` (the PDF
Report prints the frontend's `/report/{id}` page).

| Page | What it does |
|---|---|
| `/` | Globe. **Showcase**: the 7 sites as markers and cards. **Explore**: NISAR footprints in view (click one for NASA's preview), choose GCOV or GUNW, a Lens and dates, draw a box with a live km² readout against the limit, run an Analysis, recent Analyses |
| `/study/{id}` | Study page for a site or an Analysis: layers grouped by kind with Status badges and opacity, legend with units, a date bar (event marked) with time-lapse, before/after swipe, statistics for the layer on screen, a chart of the whole area or a clicked point, "Why it changed" (pipeline insights), the Assistant, data sources with ASF Vertex links. 3D view for GUNW studies: terrain and line-of-sight motion, each with its own exaggeration (k shown), a time morph between Passes, optional drape of the current layer, click for the point chart |
| `/models`, `/models/{lens}` | Every Model against its Baseline, and its full card (labels, splits, limits, Status) |
| `/report/{id}` | Print layout behind `POST /report/{id}` (summary, one section per layer, Model vs Baseline, data sources) |
| `/browse` | Raw Granules of one track: tiles, timeline, change overlay, point series |

AI layers appear only on Showcase Sites (ADR-0001). A Study page never opens on a forecast layer:
the subsidence forecast does not beat its Baseline, so Mexico City opens on the measured motion.
Charts are lightweight SVG (Plotly, about 3.5 MB, was not needed). Colormaps are colour-blind safe
(viridis, magma, red-blue diverging) and legends use the same colour stops as the tiles.

Basemap: OpenFreeMap (OpenStreetMap data). Globe imagery: NASA GIBS Blue Marble. 3D terrain:
Copernicus GLO-30 from the pipeline.

## Data

NISAR L2 GCOV (geocoded polarimetric covariance), L-band, from the Alaska
Satellite Facility DAAC via NASA Earthdata.
