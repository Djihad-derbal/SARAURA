# SARAURA: NASA Space Apps 2026 submission

Challenge: **[Dancing with the SARs](https://www.spaceappschallenge.org/2026/challenges/dancing-with-the-sars/)** (Earth Science, Advanced).

This file holds the text for each field of the Space Apps project page, in the order the
[Project Submission Guide](https://www.spaceappschallenge.org/resources/project-submission-guide/) lists them.
Copy each section into the matching field. All content is in English, as the guide requires.

| Field | Where it is below |
|---|---|
| Project Name | [1](#1-project-name) |
| High-Level Project Summary | [2](#2-high-level-project-summary) |
| Link to Project Demo | [3](#3-link-to-project-demo) |
| Link to Final Project | [4](#4-link-to-final-project) |
| Detailed Project Description | [5](#5-detailed-project-description) |
| Use of Super Intelligence (SI) | [6](#6-use-of-super-intelligence-si) |
| NASA Data | [7](#7-nasa-data) |
| Space Agency Partner Data and Other References | [8](#8-space-agency-partner-data-and-other-references) |

The checklist before pressing "Submit for Judging" is at the [end](#before-you-press-submit-for-judging).

---

## 1. Project Name

SARAURA: NISAR radar, turned into answers

## 2. High-Level Project Summary

SARAURA is an open-source web app that turns NASA-ISRO NISAR radar into plain answers to the questions people
actually ask about a place. Examples are "Is it safe to build here?", "Which burned slopes could send mud onto
villages this winter?" and "Where did the flood reach this season?". NISAR sees the ground through cloud, smoke and
darkness every 12 days, but its files are multi-gigabyte HDF5 that few decision-makers can open. SARAURA reads them
directly from NASA Earthdata and measures surface change: ground sinking (InSAR), burned forest and flooding
(L-band HH/HV backscatter). It then answers published, rule-based questions on top of those measurements. Each answer
gives its reason, several costed and cited options, and what to check on the ground. It says "not measurable" when the
radar evidence is weak. Three places are fully worked: Mexico City (subsidence), Jijel in Algeria after the August
2026 fires, and the Okavango Delta (seasonal flood). The same fire questions also ran on a second fire in Washington
State with no new code. A research explorer lets anyone draw an area anywhere on Earth, run an Analysis and export a
PDF Report. This answers the challenge's call for an open, user-friendly tool that translates complex radar
observations into actionable insights, for decision-makers as well as scientists, educators and the public.

## 3. Link to Project Demo

30-second video (1080p, English captions, no voice-over):

https://github.com/Djihad-derbal/SARAURA/blob/main/demo/saraura_demo_30s.mp4

The video is a screen recording of the running app, made by [`demo/record.py`](demo/record.py) and
[`demo/build.py`](demo/build.py). It shows the Jijel, Okavango and Mexico City question pages.

## 4. Link to Final Project

https://github.com/Djihad-derbal/SARAURA

The repository holds the full source (Python pipeline and API, Next.js frontend, trained Models, question and
solution files), setup instructions ([README.md](README.md)), the product write-up ([PRODUCT.md](PRODUCT.md)), the
data facts ([CONTEXT.md](CONTEXT.md)), the design decisions ([docs/adr/](docs/adr/)) and each Model's card with its
score against a Baseline ([ml/model_cards/](ml/model_cards/)).

## 5. Detailed Project Description

### What it does

SARAURA has two halves: **decisions first, research second**.

**Places and decisions** (`/` and `/place/<id>`). A visitor picks a place and says who they are (home buyer, civil
protection, farmer, safari-camp operator, dam agency and so on). They then see only the questions that matter to
them. They tap any spot or search a village by name to get:

- a verdict in traffic-light colours;
- the measured numbers behind it;
- several practical options, each with its cost level and source (a building code, the USGS, a paper);
- what to check on the ground.

Ranked lists (villages, road sections, fields, camps, reservoirs) fly the map to each item. Every view has a shareable
link and a PDF.

| Place | Hazard | Example questions and today's answers |
|---|---|---|
| Mexico City | Subsidence (28 GUNW Passes, Nov 2025 to Oct 2026) | **Is it safe to build here?** 18% red, 38% amber, 29% blue, 16% not measurable. **Which Metro, rail and canal segments cross uneven sinking?** 37 km reach the 1/500 tilt limit within 15 years, with Metro Lines A and 12 among the worst. Nezahualcóyotl sinks about 30 cm/yr, in line with published rates |
| Jijel, Algeria | Wildfire, August 2026 (11 GCOV Passes) | **Which burned slopes could send mud onto villages?** 14 villages beside a main mud path, 23 beside a smaller one. **Which roads to close in heavy rain?** 115 sections to close, 187 to watch. **Is mud heading to the dams?** 7 of 26 reservoirs and river mouths have 10% or more of their catchment burned and steep. Also: where to replant first, is the forest coming back, which farms lost their cover, what changed since the last Pass |
| Washington State, USA | Sinlahekin Fire, July 2026 | The same fire questions with **no new code**, which shows the questions travel. Conners Lake ranks first among reservoirs |
| Okavango Delta, Botswana | Seasonal flood (11 GCOV Passes, Jun to Nov 2026) | **Where did the flood reach?** From 196 km² in June to a peak of 1,098 km² on 13 Aug, reaching 48 camps, airstrips and villages. **Where is water hiding under reeds?** Up to 576 km² that optical satellites cannot see. **Which tracks flood, and when?** 414 km under water on most Passes |

**Research explorer** (`/explore`, `/study/<id>`, `/browse`, `/models`). This half is for scientists, teachers and
students:

- a globe showing every calibrated NISAR footprint with NASA's quicklook;
- drawing an area anywhere and running an on-demand Analysis;
- layers with legends and units, before/after swipe, time-lapse and point or polygon time series;
- a 3D terrain view of line-of-sight motion;
- raw Granule browsing in HH, HV and an RGB polarimetric composite;
- every AI Model compared with a simple Baseline;
- a PDF Report;
- a grounded Assistant that explains what is on screen.

Seven Showcase Sites cover six Lenses: earthquake (Venezuela), volcano (Kamchatka), subsidence (Mexico City), wildfire
(Algeria and Washington), wetland (Okavango) and farming (US Midwest).

### How it works

```
NISAR on NASA Earthdata ─► pipeline: evidence once per site ─► questions (published rules) ─► answer + options ─► roles pick what each user sees
 (GCOV, GUNW; ASF DAAC)     speed, tilt, burn, slope, flow,      questions/*.yaml +            map, verdict,        questions/roles.yaml
                            water frequency, OpenStreetMap       pipeline/answers.py           reasons, sources
```

1. **Reading NISAR without downloading it.** The app searches NASA's CMR for calibrated (PROVISIONAL and VALIDATED)
   GCOV and GUNW Granules. It reads only the 512×512 compressed HDF5 chunks it needs, remotely and in parallel. A 20 km
   window takes about 2.5 s from a 2 to 5 GB file, and every chunk is cached.
2. **Physics first.** Each phenomenon is measured with established SAR methods:
   - **Subsidence:** InSAR time series from GUNW unwrapped phase, with the product's ionosphere screen subtracted.
     This cut fake motion over Mexico City from ±17 cm to ±2 to 3 cm per 12 days. Line of sight is converted to
     vertical with the incidence angle, and pixels with coherence below 0.3 are masked.
   - **Wildfire:** loss of L-band HV volume scattering on land that was vegetated before the fire.
   - **Water:** open water is dark (specular reflection). Water under vegetation is bright in HH (double bounce).
   - **Change:** HV and HH differences on 60 m blocks, with a 3 dB threshold, about four times the measured
     Pass-to-Pass noise.
3. **AI Models where they help, always scored against a Baseline** on ground they did not train on:
   - wildfire U-Net: burned IoU 0.92, against 0.33 for the HV-drop rule;
   - Okavango water Model: open-water IoU 0.21, against 0.01 for Otsu thresholding, at true prevalence;
   - earthquake damage ensemble on real Copernicus EMS labels: average precision 0.73, against 0.61;
   - farming Model: macro F1 0.86, against 0.53.

   The subsidence forecast does **not** beat a straight line, and the app says so. Each Model has a public card with
   its labels, splits and limits.
4. **Questions are files, not code.** Each question is a YAML file: evidence, thresholds, classes, cited options,
   limits and status, plus a named rule recipe. Adding a question to a new place is often one file. Rules
   (Risk = Hazard × Exposure × Vulnerability) are explainable and travel between places; trained Models often don't.
5. **Honesty rules.** Every answer is a screening, not an engineering report. Weak evidence gives "not measurable",
   never a guess. Pixel size (20 to 80 m) and the one-year record are stated as limits.

**Physical drivers we see in the data**, as the challenge asks:

- **Mexico City:** groundwater pumping compacts the old lake clays. Sinking is fastest on the former lakebed
  (Nezahualcóyotl, Tláhuac) and near zero on the volcanic hills (Polanco). Uneven sinking, not sinking itself,
  cracks buildings and rail lines.
- **Jijel:** fire removes the leaves and branches that cause HV volume scattering, so HV drops sharply. Two months on,
  almost none of the lost HV signal has returned. Bare, steep, burned slopes are where winter rain will start mud
  and debris flows. Late-October brightening is mostly wet soil after rain: water raises the dielectric constant.
- **Okavango:** the flood pulse comes from the Angolan highlands' rains months earlier. It arrives in the dry season,
  peaks in August and recedes by November. L-band passes through reeds and papyrus and finds water optical sensors
  miss.

**Polarizations:** HV for vegetation structure (burn and recovery), HH for water and double bounce, and the
HH/HV ratio in an RGB composite (R = HH, G = HV, B = HH/HV) for reading land cover. InSAR phase from GUNW gives
centimetre-scale motion.

### Benefits and what we hope to achieve

- **For people who must decide:** civil protection gets a ranked list of villages and roads before the rains. A family
  can check a plot before buying. A dam agency sees which reservoirs will receive burned sediment. A safari camp or
  herder knows which tracks will flood and when. Answers can be renewed every 12-day Pass, through cloud and smoke,
  when optical satellites are blind.
- **For science and teaching:** raw NISAR becomes explorable in a browser, with methods, thresholds and Model scores
  in the open.
- **Scaling:** the same questions run on new places (proved on a second fire). New users need only a new role, and
  hazards already in the data (landslides, coastal erosion, levee movement) need only new question files. The
  next steps are an alert feed after each Pass and external checks: USGS debris-flow maps and GNSS stations.

### Tools, languages, hardware and software

- **Languages:** Python and TypeScript.
- **Backend and pipeline:** FastAPI, h5py, NumPy, rasterio and GDAL (Cloud-Optimized GeoTIFFs), Playwright with
  headless Chromium for PDF Reports.
- **ML:** PyTorch (U-Net, ChangeUTAE), LightGBM, ONNX Runtime, plus HMM smoothing over Passes.
- **Frontend:** Next.js, React, MapLibre GL, react-three-fiber (3D Earth and terrain), SVG charts.
- **Hardware:** a laptop with a GTX 1660 Ti (6 GB) for training. Data is read from NASA Earthdata (AWS us-west-2).
- **License:** MIT ([LICENSE](LICENSE)).

## 6. Use of Super Intelligence (SI)

> Review this section before submitting: it must describe what the team actually did. Judges don't see this field,
> but they see the SI markings in the project.

Yes. SI tools were used in these ways:

- **Code and documentation:** the team used Claude Code (Anthropic) as a coding assistant to write and refactor code,
  tests and documentation. Commits it contributed to carry a `Co-Authored-By: Claude` line in the git metadata, and
  the README states this.
- **In the app:** the optional Assistant panel calls Google Gemini server-side. It only sees the current place's
  manifest, statistics and Model card. It quotes numbers but never computes them, and it is badged "prototype".
- **Machine-learning Models** (U-Net, LightGBM, HMM, ChangeUTAE) were trained on NISAR data and are scored against
  simple Baselines on held-out ground. Their cards in `ml/model_cards/` state their labels, splits and limits, and
  the app labels AI layers as Model output.
- **No SI-generated images, video or audio.** The demo video is a scripted screen recording of the real app. The globe
  imagery is NASA Blue Marble and Black Marble. No NASA logos or branding were generated or modified.

## 7. NASA Data

- **NISAR L2 GCOV** (Geocoded Polarimetric Covariance, L-band, HH and HV): PROVISIONAL `C2854338529-ASF` and
  VALIDATED `C3622241360-ASF`. Used for wildfire, wetland, farming and volcano backscatter, and for the explorer.
- **NISAR L2 GUNW** (Geocoded Unwrapped Interferogram): PROVISIONAL `C2854335566-ASF` and VALIDATED
  `C3622247503-ASF`. Used for subsidence and earthquake displacement, coherence, and the ionosphere phase screen.
- **NISAR L2 SME2** (soil moisture, PROVISIONAL `C2854344945-ASF`): explored and kept as prototype, since it is not
  fully calibrated.
- All of the above were accessed through **NASA Earthdata** (CMR search, Earthdata Login) from the
  **Alaska Satellite Facility DAAC**, with [ASF Vertex](https://search.asf.alaska.edu/) and
  [Earthdata Search](https://search.earthdata.nasa.gov/) for hand checks. Each Granule links back to Vertex in the app.
- **NASA GIBS:** Blue Marble shaded relief and VIIRS Black Marble for the 3D Earth.
- **Documentation and learning resources:**
  - [ASF NISAR Data User Guide](https://nisar-docs.asf.alaska.edu/) and its PROVISIONAL known-issues page;
  - the GUNW Product Specification (JPL D-102272 Rev E);
  - Earthdata [Intro to SAR](https://www.earthdata.nasa.gov/learn/earth-observation-data-basics/sar) and
    [Intro to Remote Sensing](https://www.earthdata.nasa.gov/learn/earth-observation-data-basics/remote-sensing);
  - [NASA ARSET](https://www.earthdata.nasa.gov/data/projects/arset) SAR trainings (thresholding, change detection,
    InSAR);
  - [NISAR Applications White Papers](https://nisar.jpl.nasa.gov/applications/societal-benefit/) and
    [StoryMaps](https://nisar.jpl.nasa.gov/applications/arcgis-storymaps/);
  - [UAVSAR polarimetric postcards](https://uavsar.jpl.nasa.gov/education/postcards.html), which inspired the RGB
    composite.

## 8. Space Agency Partner Data and Other References

**Space Agency Partners**

- **ISRO:** NISAR is a joint NASA-ISRO mission, and all radar in SARAURA comes from it. NISAR S-band (ISRO, via
  Bhoonidhi) was planned; it had not arrived in time to integrate, so this release uses L-band only.
- **ESA / Copernicus:**
  - Sentinel-2 optical imagery, used only for proxy training labels (dNBR burn index, MNDWI water) and context;
  - Copernicus DEM GLO-30, for slopes, flow routing and 3D terrain;
  - Copernicus Emergency Management Service rapid mapping
    [EMSR884](https://rapidmapping.emergency.copernicus.eu/EMSR884), for real earthquake damage labels in Venezuela.

**Other data**

- **OpenStreetMap** (© OpenStreetMap contributors, ODbL): villages, roads, rail and Metro lines, fields, rivers,
  reservoirs, camps and tracks. Basemap tiles from **OpenFreeMap**.
- **USDA NASS Cropland Data Layer** 2024 and 2025: farming proxy labels.

**Methods and thresholds cited**

- Bjerrum (1963): the 1/500 angular-distortion limit for building damage.
- Staley et al. (2017), USGS: the 23° slope threshold for post-fire debris flows.
- Barnes, Lehman and Mulla (2014): priority-flood depression filling, for flow routing.
- The USGS and building codes cited per option in [`solutions/catalogue.yaml`](solutions/catalogue.yaml).

**Software (all open source)**

Python, FastAPI, NumPy, h5py, rasterio/GDAL, PyTorch, LightGBM, ONNX Runtime, Playwright, Next.js, React, MapLibre GL,
three.js and react-three-fiber. Fonts are from Google Fonts (Space Grotesk, IBM Plex Sans and Mono, Orbitron; SIL Open
Font License). The full list is in `requirements.txt` and `frontend/package.json`.

---

## Before you press "Submit for Judging"

The deadline is **Sunday 15 November 2026, 11:59 p.m., local time of your Local Event** (for the Universal Event:
the Team Owner's local time). Work saved after it is not judged.

- [ ] Every required field above is filled in on the team's Project page, in English.
- [ ] The repository link and the demo video link open in a **private browser window** with no login.
- [ ] The demo is 30 seconds or less (it is exactly 30.0 s).
- [ ] The video and project show no one under 18.
- [ ] All team members are confirmed at the same Local Event.
- [ ] Tick "Terms and Conditions" and "Confirm All Work is Original", then press **Submit for Judging**.
- [ ] Optional: upload the video to YouTube as well, for a faster player than GitHub's.

Judges score **Impact, Creativity, Validity, Relevance and Presentation**
([Judging and Awards Guide](https://www.spaceappschallenge.org/resources/judging-awards-guide/)).
