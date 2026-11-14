# SARAURA: project context

Read this first. It says what we are building, what is already decided, what already exists in the repo, and the facts about the data that constrain everything. Terms in **bold capitals** are defined in [GLOSSARY.md](GLOSSARY.md); the reasons behind big decisions are in [docs/adr/](docs/adr/). The build steps are in [PLAN.md](PLAN.md). The product direction (questions at each place, how each application scales) and the setup for a new machine are in [PRODUCT.md](PRODUCT.md).

Last updated: 2026-11-13.

## What SARAURA is

An open-source web app for the NASA Space Apps 2026 challenge "Dancing with the SARs". It turns NISAR radar data into maps, 3D views, time series, statistics and PDF Reports, so engineers, educators and decision-makers can study surface change without reading HDF5 files.

The site has two halves (redesigned 2026-11-14), decisions first and research second:

- **Places** (`/`, then `/place/<id>`), the main path: each place leads with the questions it answers ("Is it safe to build here?"), an "I am a…" picker, and a focused page of map plus questions with a "Who are you?" first step. Links can be shared (`?role=&q=`).
- **Research explorer** (`/explore`, plus the research view `/study/<id>`, raw Granules `/browse` and Model scores `/models`), for research and teaching: the two ways in below.

The research side has two ways in:

1. **Explore anywhere.** A globe shows every NISAR Pass as a footprint with a quicklook. A user draws an area, and an on-demand **Analysis** processes only that area. They can apply a **Lens** to get its physics layers, its **Baseline** and a "Why it changed" explanation. No AI **Model** runs here ([ADR-0001](docs/adr/0001-ai-only-on-showcase-sites.md)).
2. **Showcase Sites.** Seven curated, precomputed places, one or two per Lens, each with a trained Model, a Model card and a Model vs Baseline score.

Both open in the same **Study page**. Both can be exported as a PDF **Report**. A grounded **Assistant** explains what is on screen.

## Scope

- **One final release.** There is no v1/Next/Later split. It covers everything in the two handoff PDFs except alerts for saved areas (so no user accounts) and anything Sentinel-1.
- **Status badges:** "operational" means validated against a Baseline or reference data; "prototype" means it works but isn't validated. There is no "planned" status.
- **Done means:** the feature runs from a clean clone, in local mode, on real NISAR data, and is labelled in the README. Hosting comes later ([ADR-0003](docs/adr/0003-local-first-storage-interface.md)).

## The six Lenses and seven Showcase Sites

| Lens | Showcase Site | NISAR input | View | Model job | Labels |
|---|---|---|---|---|---|
| Earthquake | Venezuela, M7.2 + M7.5, 2026-06-24 | GUNW + GCOV | 3D | Rank 250 m **Neighborhoods** by damage probability | Copernicus EMS EMSR884 damage grades |
| Volcano | Kamchatka lava flows | GCOV + GUNW | 3D | New lava extent per Pass; flag abnormal inflation | Proxy labels |
| Subsidence / landslide | Mexico City | GUNW series | 3D | Detect accelerating points; forecast 1 to 3 Passes ahead | Self-supervised (the series itself) |
| Wildfire | North-east Algeria fires, Aug 2026 (track 109 desc.) | GCOV | 2D | Burn severity through smoke and cloud | Sentinel-2 dNBR; **ChangeUTAE already trained** |
| Wildfire | Sinlahekin Fire, Washington (ignited 2026-07-26) | GCOV | 2D | Same Model; tests whether it works on a second fire | Sentinel-2 dNBR |
| Wetland / flood | Okavango Delta | GCOV + GUNW coherence | 2D | Open water vs flooded vegetation vs dry | Proxy labels |
| Farming | US Midwest | GCOV series | 2D | Crop type before harvest | USDA CDL 2026 (2025 as proxy) |

S-band (ISRO) is in scope, but how it enters the app is decided only once the data arrives (expected 2026-11-14).

## Architecture

```
NISAR (ASF/Earthdata, AWS us-west-2)  ──►  pipeline/   ──►  data/<site_id>/  ──►  api/        ──►  frontend/
ISRO Bhoonidhi (S-band, pending)           per site         COGs, parquet,        FastAPI          Next.js
                                           from sites/*.yaml manifest.json        tiles, series,   globe, Study page,
                                                ▲            pred_<lens>_*.tif     jobs, report,    3D view, Report page
                                                │                 ▲                assistant
                                           ml/ (Models, trained offline) ─────────┘ writes files only
```

- **Folders (target):** `frontend/` (Next.js, kept), `api/`, `pipeline/`, `sites/*.yaml`, `ml/`, `data/`, `cache/`.
- **Models plug in through files only:** prediction COGs plus a Model card JSON. The app never imports model code ([ADR-0005](docs/adr/0005-models-integrate-through-files.md)).
- **Assistant:** Gemini `gemini-3.6-flash`, called server-side. It only sees the current Site or Analysis, quotes numbers but never computes them, and is badged "prototype" ([ADR-0006](docs/adr/0006-grounded-assistant.md)).
- **Report:** a Next.js `/report` page rendered to PDF by Playwright inside `api/`. There is no CSV export ([ADR-0007](docs/adr/0007-pdf-report-via-headless-chromium.md)).
- **Questions:** one evidence pass per site answers many **Questions** (`questions/*.yaml`, rule recipes in `pipeline/answers.py`), each with several cited **Solutions** (`solutions/catalogue.yaml`) and **Roles** that pick what each user sees. They are rules, not Models ([ADR-0008](docs/adr/0008-questions-as-rules-over-evidence.md)). Built for Mexico City and Jijel (2026-11-14).
- **Storage:** behind an interface: local disk now, object storage later. The Analysis area limit is a config value set from measured seconds per km² for each product.

## What already exists in the repo (updated 2026-11-13, after Phase 0)

The repo was built against an earlier plan ("three acts in Algeria"), archived at [docs/archive/PLAN-2026-11-09.md](docs/archive/PLAN-2026-11-09.md). What carries over:

| Area | Exists | Gap against the decisions above |
|---|---|---|
| `saraura/` + `api/` (was `backend/app/`) | Split done. `saraura/`: CMR search, chunk reader, change detection, rendering, storage interface. `api/`: `/granules`, previews, tiles, change tiles, `/timeseries`, `POST /analysis`, `/ai/*` | GCOV only, with no GUNW, SME2 or site/manifest routes. The ONNX Model still runs on any drawn area, which breaks ADR-0001 (fix in Phase 3). |
| `sites/`, `contracts/`, `pipeline/` | 7 site configs; JSON Schemas + `validate.py`; `run_site --plan` lists calibrated Passes per Stack | Processing steps (Phase 1). |
| Chunk reader (`gcov.py`, `remote.py`) | Reads HDF5 chunks remotely in parallel; a 20 km window takes about 2.5 s | Keep; it is the core of Tier 2 Analyses. |
| `api/assistant.py` | Claude tool loop that drives the map | Replace with the grounded Gemini Assistant (no map driving). |
| `frontend/` | Next.js, MapLibre globe + 3D terrain, timeline cross-fade, change overlay, point chart, AI panel | Still missing: Study page, Showcase/Explore modes, Lens panels, react-three-fiber 3D view, Report page, status badges. |
| `ml/` | ChangeUTAE (about 480k params), baselines, Sentinel-2 label builder, ONNX export, evaluate | Becomes the Algerian wildfire Model (burned vs stable only). Must write a `pred_wildfire_*.tif` + Model card instead of being served as ONNX. |
| `models/change_utae.onnx` | Trained: burned IoU 0.86 vs 0.67 for gradient-boosted trees | Only the "burned" class is reliable; the other classes score about 0. |
| `spike/` | Feasibility scripts | Reference only. |

## Data facts that constrain the design

- **Collections:** PROVISIONAL is the main calibrated collection. VALIDATED (`NISAR_L2_<P>_V1`) starts 2026-10-21 for GCOV and 2026-09-27 for GUNW. Both may be combined; BETA is never used ([ADR-0004](docs/adr/0004-calibrated-collections-only.md)). **Correction (2026-11-13):** PROVISIONAL is not limited to dates from June 17. In some regions it holds Granules from 2025-10-29 with the same processing version (1.0.11, CRID P05023), e.g. GUNW over Venezuela. Over Algeria and Utah it starts in late June. **Decided:** the collection decides, not the date ([ADR-0004](docs/adr/0004-calibrated-collections-only.md)).
- **CMR collection IDs:** GCOV `C2854338529-ASF` (provisional) / `C3622241360-ASF` (validated); GUNW `C2854335566-ASF` / `C3622247503-ASF`; SME2 `C2854344945-ASF` (provisional only). Kept in `saraura/config.py`.
- **Stack coverage matters more than Pass count.** A Stack's frame can just clip a site: Venezuela's 054_D_083 had the most pairs but covered 2% of the area. The pipeline ranks Stacks by coverage first (`pipeline/coverage.py`), and `run_site --plan` prints it.
- **GUNW files:** the unwrapped phase, coherence, connected components and ionosphere screen sit on an 80 m UTM grid with the same 512×512 gzip chunks as GCOV, so the same chunk reader serves both. Pixel offsets (also 80 m) and the wrapped interferogram (20 m) are present but not used yet.
- **Ionosphere must be removed.** Raw L-band pairs over Mexico City showed ±17 cm of fake motion per 12 days. Subtracting the product's `ionospherePhaseScreen` brought that to ±2 to 3 cm and gave plausible velocities (fastest sinking 1.7 cm/month).
- **LOS sign:** we use d = −phase·λ/4π (positive = toward the satellite). Mexico City's fastest motion comes out *away* (sinking), as expected; still to confirm against the product spec.
- **Speckle and noise floor:** single 20 m pixels flicker by more than 3 dB. Dark cells near −22 dB HV (the noise floor) can drop and recover between Passes. Change statistics use 100 m blocks, ignore cells below −20 dB, and require the change to persist into the next Pass.
- **Instrument gap:** no data from 2026-07-27 to 2026-08-10.
- **Repeat cycle:** 12 days per track, so roughly 10 to 12 Passes per Stack so far. Never mix Stacks in one series.
- **GCOV files:** 1.9 to 5.3 GB each, 10 m UTM grid, 512×512 gzip chunks; `frequencyB` is a ready-made 80 m overview. Grids align across dates on the same track.
- **Remote read times (from Algeria):** opening a file takes about 8 s. A 20 km window takes about 2.5 s with parallel chunk reads. A cold ten-Pass series takes about 53 s and a warm one about 2 s. AWS us-west-2 would be several times faster.
- **S-band:** comes from ISRO Bhoonidhi. Access needs registration, the API is restricted to authorized users and redistribution terms aren't stated, so we never re-host raw files. Coverage is sparse outside India.
- **Labels:** Venezuela has real damage maps (Copernicus EMS EMSR884). Kamchatka has no published lava outlines, so it uses proxy labels. Every proxy label is declared on its Model card.

## Resources and what they changed (checked 2026-11-13)

The official Resources tab list was pasted in by the team (spaceappschallenge.org fails TLS verification from this machine). Its items come first below, followed by sources we found ourselves.

| Official resource | Use for SARAURA |
|---|---|
| [NASA Earthdata Search](https://search.earthdata.nasa.gov/search) | Same CMR catalogue our pipeline queries. Use it to hand-check a site's footprints and Granule IDs. |
| [ASF Vertex](https://search.asf.alaska.edu/#/) | Hand-checks, plus an **"Open in Vertex" link** for each Granule on the Study page and in the Report's data-sources appendix (Phase 4). |
| [NISAR Data User Guide](https://nisar-docs.asf.alaska.edu/) | Already our main data reference (see below). |
| [Intro to Remote Sensing](https://www.earthdata.nasa.gov/learn/earth-observation-data-basics/remote-sensing), [Intro to SAR](https://www.earthdata.nasa.gov/learn/earth-observation-data-basics/sar) | Source for the "what this shows" layer notes and the Assistant's grounding text: wavelength, polarisation, and scattering mechanisms (surface, volume, double bounce). Link them from the Study page "Learn more". |
| [NASA ARSET trainings](https://www.earthdata.nasa.gov/data/projects/arset) | Published SAR methods to cite for our Baselines (thresholding water on HH, backscatter-change burn and flood mapping, InSAR deformation) in the README methods and the Report. |
| [NISAR StoryMaps](https://nisar.jpl.nasa.gov/applications/arcgis-storymaps/) | Floods, wildfires and subsidence match our wetland, wildfire and subsidence Lenses: a model for the Study page's story order (what happened, what radar sees, what it means). Oil slicks and glacier motion are out of scope. |
| [NISAR Applications White Papers](https://nisar.jpl.nasa.gov/applications/societal-benefit/) | Two-page "who uses this" summaries: one link per Lens on the Study page and in the Report summary, to answer "who is the target audience". |
| [UAVSAR Postcards](https://uavsar.jpl.nasa.gov/education/postcards.html) | False-colour polarimetric composites. **New layer idea:** an RGB composite (R = HH, G = HV, B = HH/HV) for every GCOV Lens, built from layers we already compute. |
| CSA [RCM](https://donnees-data.asc-csa.gc.ca/en/dataset/rcm), [RADARSAT-1](https://donnees-data.asc-csa.gc.ca/en/dataset/radarsat1), [SAR Python tutorial](https://github.com/asc-csa/Synthetic_Aperture_Radar_Tutorial) | Not used: other radars are out of scope (ADR-0002), and RADARSAT-1 ended in 2013. The tutorial is a beginner reference for the team. |
| CONAE [SAOCOM](https://catalogos.conae.gov.ar/catalogo/catalogoSatSaocomInfo.html) ([registration](https://www.argentina.gob.ar/noticias/la-informacion-saocom-cada-vez-mas-accesible)) | L-band like NISAR, so the only listed source that could independently check our L-band results. Out of scope under ADR-0002; reopening it would be a team decision. |

| Other source we found | What we took from it |
|---|---|
| [ASF NISAR Data User Guide](https://nisar-docs.asf.alaska.edu/) (source: [ua-asf/nisar-docs](https://github.com/ua-asf/nisar-docs)) | Product pages, access, tutorials |
| [PROVISIONAL known issues](https://nisar-docs.asf.alaska.edu/provisional-known-issues/) | Ionosphere residuals worse at **high latitudes** (Kamchatka, 54° N). Frequency B (our 80 m GCOV overview) has larger calibration residuals. SME2 is **not fully calibrated**, so soil moisture stays prototype. Tracks 161/174, 161/175, 169/090 and 169/091 have unusable diagnostic frames (none of ours). About 1–2% of products come from incomplete raw data. PROVISIONAL = CRID P05023 or higher; caution applies only to mixing with BETA (lower CRIDs), so our pre-June P05023 Granules are fine (ADR-0004). |
| [GUNW page](https://nisar-docs.asf.alaska.edu/gunw/) and [GUNW Product Specification (D-102272 Rev E)](https://nisar.asf.earthdatacloud.nasa.gov/NISAR-SAMPLE-DATA/DOCS/NISAR_D-102272_RevE_NASA_SDS_Product_Specification_L2_GUNW_Nov8_2024_w-sigs.pdf) | The ionosphere screen is provided **but not applied**, which confirms our correction. **Tropospheric and solid-earth-tide corrections** are provided as lookup tables and also not applied; they are the next fix for Venezuela's ±6–9 cm noise. The unwrapped `mask` carries a **water flag** (first digit), a ready-made water mask. The spec does **not** state the phase sign convention; ask on the [Earthdata Forum](https://forum.earthdata.nasa.gov/viewforum.php?f=7&keywords=NISAR) or uso@asf.alaska.edu. |
| [Copernicus EMS EMSR884](https://rapidmapping.emergency.copernicus.eu/EMSR884) (public API, fetched by `ml/fetch_emsr.py`) | Earthquake labels. 13 AOIs, but 8 were not mapped (remote-sensing limits); only Caraballeda (AOI12) and part of Caracas (AOI02) lie in our site. AOI00 is a **Sentinel-1 ground-motion map** (LOS classes up to 0.2–0.5 m): an independent check of the size of our co-seismic displacement, but not of its sign, because Sentinel-1 looked from the other direction (evening, ascending) than NISAR track 126 (descending). Used as reference only, not as input (ADR-0002). |
| Other teams' public repos (e.g. [dmanpark/dancing-with-the-sars](https://github.com/dmanpark/dancing-with-the-sars): "L-band finds flood water under vegetation that C-band maps miss") | Same idea as our wetland Lens. Confirms the event runs **14–15 Nov 2026**. |

## Secrets and setup

- `.env` holds `EARTHDATA_TOKEN` (expires 2027-01-08) and, later, the Gemini API key. It is never committed; `.env.example` is the template.
- Training machine: GTX 1660 Ti (6 GB), 16 GB RAM. Train in full precision; keep training data under about 10 GB.
