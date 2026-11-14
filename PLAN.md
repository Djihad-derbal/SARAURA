# SARAURA: build plan

Written 2026-11-13. Supersedes the earlier plan, archived at [docs/archive/PLAN-2026-11-09.md](docs/archive/PLAN-2026-11-09.md).
Background is in [CONTEXT.md](CONTEXT.md), terms in [GLOSSARY.md](GLOSSARY.md) and decisions in [docs/adr/](docs/adr/).

**Rule for every step:** a step is done only when it runs from a clean clone in local mode, on real NISAR data, and has its Status (operational or prototype) recorded in the README.

## Phase 0: Contracts and restructure

Agree the formats first so that pipeline, ML, API and frontend can work in parallel.

1. **Site config schema** in `sites/*.yaml`, one file per Showcase Site (7). Change from the handoff: replace `collection_suffix` with `collections: [PROVISIONAL_V1, VALIDATED_V1]`, and allow several Showcase Sites per Lens.
2. **`manifest.json` schema**, shared by Showcase Sites and Analyses. Add a source collection and Stack (track + direction) for each date, and a Status for each layer.
3. **Time-series parquet** (`pixel_id, lon, lat, date, variable, value, sigma, valid`) and the **Model card JSON**, both as in the Engineering Handoff.
4. **Model file contract:** `data/<site_id>/layers/pred_<lens>_<date>.tif` plus `ml/model_cards/<lens>.json` ([ADR-0005](docs/adr/0005-models-integrate-through-files.md)).
5. **Split `backend/` into `api/` and `pipeline/`.** Keep the chunk reader (`gcov.py`, `remote.py`) as a shared package both can import. Rename "scene" to Granule or Pass in code and routes.
6. **Storage interface** (`get`/`put`/`exists`/`url`) with a local-disk implementation, used for `data/` and `cache/` ([ADR-0003](docs/adr/0003-local-first-storage-interface.md)).

Check: a JSON Schema exists for each contract, and a validator script passes on one hand-written example of each.

**Status (2026-11-13): done.**
- `contracts/`: four schemas plus `validate.py`. It passes on 7 sites, the wildfire Model card and 2 example manifests, and rejects BETA collections, pre-June-17 dates, a reference area outside the bbox, and a prediction layer on an Analysis.
- `saraura/`, `api/` and `pipeline/` replace `backend/`. The venv moved to `.venv/` at the root. Routes use `/granules`, and the old cache stays valid.
- `pipeline.run_site --plan` checked real coverage: every site has 9 to 11 calibrated Passes. Utah and Venezuela each have exactly one pre-event Pass on some Stacks. (Later corrected in Phase 1: those Stacks barely covered the sites, Utah was replaced, and Stacks are now ranked by coverage.)
- Not done: GUNW/SME2 Pass search, since the CMR collection IDs are needed (Phase 1 step 1).

## Phase 1: Pipeline (Showcase Sites)

`python pipeline/run_site.py sites/<site>.yaml` produces COGs, parquet and a manifest with no manual steps.

1. **Fetch:** search across both calibrated collections, then stream the Granules. Reuse the chunk reader.
2. **GCOV path:** HH/HV in dB, HV/HH, change layers, temporal mean/std/CV.
3. **GUNW path:** line-of-sight displacement, coherence, cumulative series by chaining pairs, reference-area correction, flag on a broken chain. Confirm group paths on one file first.
4. **DEM:** Copernicus GLO-30 crop, slope, heightmaps (512×512 max) for the 3D sites.
5. **Export:** COGs with overviews, parquet, manifest, and data-quality notes (Passes, gaps, masked share).
6. Run all 7 sites. Order: Algeria wildfire (data already proven) → Venezuela → Mexico City → Kamchatka → Washington wildfire → Okavango → US Midwest.

Check: one test per Lens confirms the COGs exist and have the right CRS and value range, matching the manifest. Sanity checks: displacement ≈ 0 at the reference area, low HH over water.

**Status (2026-11-13): all 7 sites built from real data; 40 tests pass (9 not applicable to a given site); 17/17 contract files valid.**
- Built: Algeria wildfire, Washington wildfire, Venezuela earthquake (18 Passes from March), Kamchatka volcano, Mexico City subsidence (27 GUNW pairs from Nov 2025), Okavango wetland, US Midwest farming (15 Passes from April). Outputs total about 11 GB in `data/` (the longer date ranges added Passes).
- Sites may set `event_end_date` so a long-burning fire is compared after it stopped growing (Washington: Baseline went from 4,968 to 13,332 ha).
- Pipeline modules: `gcov.py`, `gunw.py` (ionosphere correction, largest connected component, reference area with scene-median fallback), `dem.py` (Copernicus GLO-30, slope, heightmaps), `export.py`, `insights.py`, `coverage.py`. Tests are in `tests/test_site_outputs.py`.
- **Utah replaced** (decided 2026-11-13): no calibrated Pass covered the Cottonwood Fire area before it started. The second wildfire site is now the Sinlahekin Fire, Washington (three Stacks with 100% coverage and 3 to 4 pre-fire Passes).
- Not yet: the "low HH over water" sanity test, SME2 processing, the Venezuela reference area (it falls back to the scene median), and choosing a second coherence threshold.
- From the challenge Resources (see CONTEXT.md): an RGB polarimetric composite layer (R = HH, G = HV, B = HH/HV) for GCOV Lenses; tropospheric and solid-earth-tide corrections for GUNW; the GUNW water flag as the water mask; a high-latitude ionosphere caveat for Kamchatka.

## Phase 2: Models (ml/)

Each Model writes prediction COGs and a Model card, and reports its score against its Baseline.

| Lens | Template | Baseline | First step |
|---|---|---|---|
| Wildfire | Existing ChangeUTAE | HV drop > 1.5 dB | Re-export as `pred_wildfire_*.tif` (burned vs stable only); then test on Washington (Sinlahekin) without retraining |
| Earthquake | Pixel classifier (LightGBM) | Coherence-loss threshold | Rasterise EMSR884 grades into 250 m Neighborhoods |
| Farming | Time-series model | Coefficient-of-variation rule | Clip USDA CDL to the site |
| Wetland | Pixel classifier | Otsu on HH | Build proxy labels (optical water index + hand-digitised) |
| Volcano | Pixel classifier | Backscatter-change threshold | Hand-digitise lava extent from Sentinel-2 (proxy) |
| Subsidence | Time-series forecast | Straight-line extrapolation | Hold out the last 1 to 3 Passes as the test set |

Check: every Model card has a Baseline score, a Model score, the label source (proxy or not), its limits and a Status.

**Status (2026-11-13): done, all 6 Models.** `tests/test_site_outputs.py` checks every site has a prediction layer and every card has both scores (53 pass, 10 not applicable).

| Lens | Labels | Metric | Model | Baseline | Beats Baseline? |
|---|---|---|---|---|---|
| Wildfire | Sentinel-2 dNBR (proxy) | burned IoU | 0.86 Algeria / 0.36 Washington (not retrained) | 0.21 / 0.18 | Yes |
| Earthquake | Copernicus EMSR884 (real) | average precision | 0.50 (0.43–0.56) | 0.43 | Yes, modestly |
| Farming | CDL 2024+2025 rotation rule (proxy) | macro F1 | 0.86 (0.85 before harvest) | 0.53 | Yes |
| Wetland | Sentinel-2 MNDWI (proxy) | open-water IoU | 0.63 | 0.47 (Otsu on HH) | Yes |
| Volcano | Sentinel-2 hot spots (proxy) | average precision | 0.073 (IoU 0.10) | 0.003 (chance 0.003) | Yes, but weak overall |
| Subsidence | Own time series (self-supervised) | RMSE, cm | 1.20 | 1.09 | **No** |


Earthquake (`ml/fetch_emsr.py EMSR884`, then `ml/earthquake.py`):
- Labels: Copernicus EMS EMSR884 building grades (real labels). Only Caraballeda (AOI12) and part of Caracas (AOI02) fall inside the site: 1,469 labelled 250 m Neighborhoods, 142 with Damaged/Destroyed buildings.
- LightGBM on location-free features (coherence before/across/after, coherence loss and recovery, HH/HV change, pre-event backscatter, slope). Displacement size and gradient were dropped: with 2.5 km blocks they inflated the score to 0.59, which fell to 0.41 with 5 km blocks (the Model was learning distance from the fault).
- Average precision, 5 km spatial blocks, 5 shifted layouts: **Model 0.50 (0.43–0.56)**, Baseline (mean coherence loss, best threshold) 0.43, chance 0.10. A modest but consistent gain.
- Output `pred_earthquake_2026-07-04.tif`: low / elevated / high damage likelihood per Neighborhood.

Farming (`ml/farming.py`; Iowa CDL from `nassgeodata.gmu.edu/nass_data_cache/byfips/CDL_<year>_19.zip`):
- CDL 2026 is not published (the NASS service accepts up to 2025). Labels: rotation rule on CDL 2024 + 2025 (switched → switches back; same twice → keeps it). Checked on 2025 from 2023 + 2024: 86% right on 95% of pixels. Label kind: proxy.
- Macro F1 (maize / soybean / other), 2 km spatial blocks: **Model 0.86 (full season), 0.85 (Passes to 31 Aug, before harvest)**; Baseline (HV CV rule) 0.53. The Model is near the 86% label ceiling.

Subsidence (`ml/subsidence.py`):
- Last 3 Passes held out. RMSE: **Model 1.20 cm vs straight-line Baseline 1.09 cm on test; 0.77 vs 0.75 on validation. The Model does not beat the Baseline.** Atmospheric noise (~1 cm per interferogram) dominates 12–36 day forecasts, and every pixel of a date shares it, so there are only ~40 independent training examples. Tried and rejected: a larger LightGBM (1.41), spatial smoothing (worse at every scale), ridge blend (1.23).
- Writes a 12-day forecast `pred_subsidence_2026-10-25.tif`; the card says to use the Baseline. Contracts now allow a numeric `prediction` block on cards and forecast dates past the last Pass.

Wetland (`ml/wetland.py`): open water only (optical labels cannot see water under reeds), labels from Sentinel-2 within 4 days of 3 Passes. Open-water IoU, 5 km blocks, balanced samples: **Model 0.63, Otsu on HH 0.47**; per date 0.54/0.42, 0.73/0.65, 0.51/0.25. Writes `pred_wetland_<date>` for all 10 Passes.

Volcano (`ml/volcano.py`): labels are Sentinel-2 hot spots (NHI_SWIR > 0, bright B12, within 10 km of the vent, hot on 3+ scenes). Two label rules were rejected first: both indices fired on 71% of the window, and one-scene hot spots spread in all directions (cloud). The final 2,443 hot pixels lie 1–4 km N/NE of the vent, matching KVERT reports. Average precision, 1.5 km blocks: **Model 0.073, HH-change Baseline 0.003 = chance**. Map: 2.7 km² of new lava within 10 km of the vent.
- `ml/predict.py --site <id>` writes `pred_wildfire_<last Pass>.tif`; `pipeline/predictions.py` lists any `pred_*` file plus its Model card in the manifest (also run by `run_site`), so the app never loads model code.
- Burned IoU against Sentinel-2 proxy labels (dNBR ≥ 0.27 on vegetation):

  | Where | Model | Baseline (HV drop > 1.5 dB) |
  |---|---|---|
  | Algeria, held-out test cells | 0.86 (precision 0.90, recall 0.95) | 0.21 (precision 0.85, recall 0.21) |
  | Washington, whole site, not retrained | 0.36 (precision 0.91, recall 0.37) | 0.18 (precision 0.52, recall 0.22) |

- Scripts: `ml/score_baseline.py` (same held-out cells as `evaluate.py`), `ml/score_site.py` (transfer test on a new site).
- Open: Washington labels may count late-summer drying as burned (to check against the official perimeter); fine-tuning on Washington would raise recall but leave no unseen fire for testing.

## Phase 3: API (api/)

1. FastAPI with TiTiler mounted (or the existing tile reader where it is faster). Routes: `/sites`, `/sites/{id}`, `/tiles`, `/terrain`, `/timeseries` (point and polygon), `/stats`, `/models/{lens}`.
2. Explorer, tier 1: `/coverage` (CMR footprints, cached per tile and day) and `/browse/{granule_id}`.
3. Explorer, tier 2: `POST /jobs`, `GET /jobs/{id}` and job tiles/series. Each job produces an Analysis with an optional Lens, which applies physics + Baseline and never a Model. Results are cached by hash of (Granules, bbox, product, Lens).
4. **Fix ADR-0001 violation:** remove the "Neural model" option from Analyses in the current code.
5. Rule-based insights (3 to 5 sentences per result) and a "what this shows" note per layer.
6. **Assistant:** `POST /assistant`. Replace `assistant.py` with Gemini `gemini-3.6-flash`. Its context is the current manifest, stats, insights and Model card; it has no map-driving tools. The model name and API key live in config ([ADR-0006](docs/adr/0006-grounded-assistant.md)).
7. **Report:** `POST /report` uses Playwright to render the frontend `/report` page to PDF ([ADR-0007](docs/adr/0007-pdf-report-via-headless-chromium.md)).
8. **Area limit:** benchmark seconds per km² for GCOV and GUNW, then write the per-product limits to config.

Check: a smoke-test script calls every endpoint once, and `/docs` lists them all.

**Status (2026-11-13): done.** `scripts/smoke_api.py` calls all 32 operations listed in `/docs` (30 pass; the Assistant and the Report answer 503 by design until `GEMINI_API_KEY` is set and the frontend runs). `tests/test_api.py` adds 9 offline checks (62 tests pass in total).
- `api/study.py`: `/sites`, `/sites/{id}`, `/tiles/{id}/{layer}/{date}/...` (rio-tiler, legend from the manifest; 0.06–0.1 s per tile warm), `/terrain`, `/timeseries/{id}` (point GET, polygon POST), `/stats/{id}` (whole or polygon), `/models`, `/models/{lens}`. TiTiler itself was not needed: rio-tiler (its engine) is called directly.
- Explorer: `/coverage` (GeoJSON footprints, cached per 1° tile per day), `/browse/{granule}` plus preview, prepare, tiles and point series. The old `/granules/...` and `/tiles/{granule}/...` paths stay as aliases until Phase 4.
- `api/analyses.py`: `POST /jobs` runs `pipeline.run_site.run(kind="analysis")` on an ad-hoc site. The id is a hash of (Granules, bbox, product, Lens, event dates); jobs run one at a time. The resolution is picked by area (20/40/80 m). Tested on a real 60 km² wildfire Analysis: 50 s, with Baseline layer, no Model layer.
- **ADR-0001 fixed:** the "Neural model" option is gone from the old `/analysis` route and from `api/jobs.py`; tests guard it.
- Insights and "what this shows" notes come from the pipeline manifest; an Analysis without a Lens now also reports its largest lasting change.
- `api/assistant.py`: Gemini (`config.GEMINI_MODEL`), grounded on manifest, insights, on-screen layer statistics and (Showcase only) the Model card, with no tools. Tested with a stand-in client; **not yet run against Gemini (no key)**.
- `api/report.py`: Playwright prints `FRONTEND_URL/report/{id}` once `body[data-report-ready]` appears. Chromium is installed; **waits on the Phase 4 `/report` page**.
- Area limits measured (`scripts/benchmark_area.py`, 117 km², uncached): GCOV 0.67 s/km², GUNW 1.18 s/km², so the limits are **900 km² (GCOV) and 500 km² (GUNW)** for a first run of about 10 minutes.

## Phase 4: Frontend (frontend/, Next.js)

1. Globe with **Showcase** and **Explore** modes. Showcase shows markers for the 7 sites. Explore shows footprints, filter chips, quicklooks, polygon drawing with a live km² readout against the limit, and a recent-Analyses list.
2. **Study page**, shared by Sites and Analyses: layer list with opacity, legend with units, time slider (one tick per Pass, event date marked), analysis panel (Plotly chart + stats), "Why it changed" box, Status badges.
3. **3D view** (react-three-fiber) for earthquake, volcano, subsidence and any GUNW Analysis: exaggeration slider showing k, time morph, draped layers, click returns lon/lat.
4. 2D extras: before/after swipe on all 2D Lenses, time-lapse for flood and farming, AI layer toggle on Showcase Sites only.
5. Model card page; Assistant panel; **`/report` page** with print CSS (summary page → one section per layer → Model vs Baseline → data sources appendix, with no Assistant text).
6. Loading, empty and error states; colourblind-safe palettes; check the layout on a phone.
7. From the challenge Resources: an "Open in ASF Vertex" link for each Granule, a "Learn more" link to NASA's SAR intro, and one NISAR Applications White Paper link per Lens (also in the Report).

Check: click through all 7 sites and one Analysis per product on desktop and phone, and export one Report from each.

**Status (2026-11-13): done.**
- Pages: `/` (Showcase and Explore), `/study/[id]`, `/models`, `/models/[lens]`, `/report/[id]`, `/browse` (the old explorer, minus its retired AI panel). Typecheck, lint and production build are clean.
- Clicked through in headless Chromium: all 7 sites, a GCOV and a GUNW Analysis, `/browse`, Models, a Model card, the swipe (Algeria composite, 20 Aug vs 1 Sep), 3D (Venezuela), Explore drawing (km² over the limit is refused), and phone layouts (390 px). No console errors.
- PDF Reports generated through `POST /report`: Venezuela (12 pages, 12 s), Algeria (9 pages, 7 s), Mexico City (6 s).
- Assistant answers live from Gemini (`gemini-3.6-flash`), grounded; slow from this machine (about 1 to 1.5 minutes per answer), so the panel says so while it waits. Thinking is set to "low" and the output budget to 4,096 tokens, after an 800-token cap cut answers off.
- Fixes found on the way: MapLibre's CSS beat Tailwind's layered `absolute` on map containers (maps were 0 px tall); whole-area series were too slow (Python loop over 13 million rows; now vectorised, 6 s, then cached: 0.02 s); previews and whole-area series are cached per file version; Study pages never open on the subsidence forecast; Report cover is the radar colour composite.
- Plotly was not used: the SVG chart covers the time series and is far lighter.

**Revision (2026-11-13, after review):**
- Explore is the main mode and opens first. The globe has 3D terrain (AWS Terrain Tiles) with hillshade and atmosphere, and tilts as you zoom. Site chips fly into each Showcase Site in 3D, and site markers stay visible in both modes. Study maps open tilted over terrain with the radar layer draped on it, with a flat-map switch; the three.js view is now "Ground-motion 3D".
- New research plots (`api/research.py`, shown on the Study page and in the Report): time series inside each AI/Baseline class (e.g. Venezuela high-damage Neighborhoods moved about 14.5 cm vs 2.6 cm for low; maize vs soybean growth curves), area of strong change per Pass, AI vs Baseline agreement map and areas, histograms per layer, and a Pass timeline with collections, gap and data coverage.
- NASA GIBS context: MODIS Terra true colour before and after the event (clouds and smoke vs radar), and a Blue Marble locator map.
- PDF Report rebuilt as a research document: summary with facts table and locator; framed maps with coordinates, scale bar and north arrow; Results; Analysis; layer atlas with distributions; Model card in paper colours; Methods, quality notes (grouped), glossary, reuse and citation, Granule appendix. Sections flow across pages (no half-empty pages), and maps are height-capped.
- Fixed a start-up race: parallel first requests failed importing rasterio; the API now imports the GDAL libraries at start-up.

## Phase 4b: Questions and answers (2026-11-14)

One evidence pass per site, many Questions, several Solutions each (ADR-0008). Built for Mexico City (4 Questions) and Jijel (4).

**Status (2026-11-14): done, prototype.** 73 tests pass (11 new in `tests/test_answers.py`); 40/40 contract files valid.
- Contracts: `question`, `solutions`, `roles` schemas; the manifest gains the `answer` layer kind; `validate.py` checks that solution IDs exist and that roles match the Lens.
- `pipeline/evidence.py`: vertical speed using the GUNW incidence angle cube (37 to 40 degrees over Mexico City), fit error, acceleration, years to 1/500 tilt; priority-flood flow routing on a 60 m DEM, burned steep ground upstream, HV recovery.
- `pipeline/context.py`: OpenStreetMap lines, places and roads, fetched once per site and cached.
- `pipeline/answers.py`: 8 recipes, answer maps, ranked lists, `at_point` explanations; `run_site` runs it after a build.
- API `/answers/{id}` and `/answers/{id}/at`; Study page "Ask this place" panel (roles, questions, clicked-spot card with Solutions, ranked lists that fly the map); Report chapter "Questions answered". PDFs: Mexico City 13 pages, Jijel 14 pages.
- Checks against what is known: Nezahualcoyotl sinks 30 cm/yr and Tlahuac 23 cm/yr (published rates up to about 40); Polanco is steady; Metro Lines A and 12 are among the worst segments.
- Found on the way: the Next.js dev server blocked the Report page's scripts for `127.0.0.1` (the API's default frontend URL), so the PDF never became ready in dev; fixed with `allowedDevOrigins`.
- Ease of use (same day): the Study page opens on the Ask tab and the first Question's map; sidebar split into Ask / Map layers / Data and more; place search; on-map legend (collapsible on phones); answer bubble at the clicked spot; road, line and village answers drawn as coloured vector lines and labelled points instead of pixels; the layer fades as you zoom in so streets show; a tapped village is answered for the village. Checked on desktop and a 375 px phone.
- Site structure (same day): decisions first, research second. `/` is a Places landing page (cards led by each place's first question, an "I am a…" picker that deep-links to a role's questions, research and education links below); `/place/<id>` is map plus questions with a "Who are you?" step and shareable `?role=&q=`; the globe moved to `/explore` as the Research explorer; `/study/<id>` became the research view (layers, charts, then questions). `/sites` now carries each place's questions, roles and cover map. Fixed on the way: a layer picked by hand was overridden by the open question's map.
- Theme (same day): earth-science look. Deep-ocean palette with one teal "radar" accent (chosen so it never reads as the amber "caution" class on answer maps), Space Grotesk headings, graticule and topographic-contour backdrops; an animated hero (dotted Earth turning, NISAR on a tilted orbit with its swath, pulsing radar footprints), count-up figures, scroll reveals, card lift with a radar scan line, a sliding nav pill and an orbiting logo mark. Every animation stops under `prefers-reduced-motion`. The printed Report keeps paper colours (accent now dark teal).
- Home page as a scroll story (same day): a WebGL Earth (react-three-fiber) wearing NASA Blue Marble by day and Black Marble city lights by night, with a teal atmosphere and NISAR on its orbit, stays behind the page and flies between a horizon (hero "Earth, through NISAR's eye"), a whole planet (intro with count-up figures), a corner locator turned to each chapter's place, and a close-up for the short chapters. Chapters are sticky, scroll-driven isometric scenes: Mexico City (radar scan, the ground sinks into a bowl, buildings tilt, the Metro line steps and cracks open, then the answer colours) and Jijel (fire mapped through smoke, ash, rain sends mud down the channel to the village and road, then barriers, a road closure and saplings), then Washington; each chapter shows the live API headline and buttons into its place page and roles. Textures are kept in `frontend/public/textures/` (public domain, from GIBS).
- Chapter themes: each chapter has its own mood, cross-faded as it takes the screen: Mexico City at dusk (sodium skyline, dust, interferogram fringes contracting over the sinking bowl), Jijel in embers (heat glow, smoke, a burned ridge), Washington in misty pines. Accent, lines, page colour and the Earth's atmosphere all follow (registered CSS colour properties, so they fade); the hero and closing stay in space teal.
- Not yet: Questions for the other Lenses, flooding for Mexico City (needs a GCOV run), the official soil zones, well locations, and a check against GNSS.

## Phase 5: S-band (decide on 2026-11-14)

Once the data arrives: check which Showcase Sites it covers, whether its format matches the L-band spec, and its licence. Then decide between an L-vs-S comparison on the sites it covers, adding it to the explorer, or a dedicated S-band site. Record the decision as an ADR.

## Phase 6: Release

1. README: summary, setup, data sources (collections, Granule IDs, DEM, label sources), methods per Lens, thresholds stated as team choices (coherence: 0.3 plus one other value), feature/Status table, limits.
2. Update both handoff PDFs to match the decisions in [docs/adr/](docs/adr/).
3. Hosting: deferred. When it happens, the workers go to AWS us-west-2 and storage switches to object storage, as configuration changes.

## Open questions

- S-band integration (Phase 5).
- The exact US Midwest farming site bbox, and whether CDL 2026 is published yet.
- The second coherence-threshold value to show alongside 0.3.
