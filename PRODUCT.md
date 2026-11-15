# SARAURA: the product, how we got here, and where it goes next

Read this first when you pick the project up on a new machine. It explains what the product is for, how it answers questions at each place, what is built, and how each application can grow.

The other documents go deeper:
- [CONTEXT.md](CONTEXT.md): the data facts and constraints.
- [PLAN.md](PLAN.md): the build phases and their status.
- [GLOSSARY.md](GLOSSARY.md): what each **Capitalised Term** means.
- [docs/adr/](docs/adr/): the reasons behind big decisions.
- [README.md](README.md): setup and commands.

Last updated: 2026-11-15 (Space Apps 2026 runs 14–15 Nov 2026). The code described here is on the branch `phase-4b-questions-and-story`. It reaches `main` once PR #1 is merged.

---

## 1. The product in one paragraph

SARAURA turns NASA-ISRO **NISAR** radar into **answers to plain questions** that people actually have about a place, for example:
- "Is it safe to build here?"
- "Which burned slopes could send mud onto villages this winter?"

Each answer comes with three things:
- the reason behind it;
- several practical options, each with its cost and source;
- what to check on the ground.

The radar passes every 12 days, through cloud, smoke and darkness, so the answers can be renewed on that cycle. The site has two halves, **decisions first, research second**:

| Half | Who it is for | Where |
|---|---|---|
| **Places and decisions** (main) | Home buyers, city and transport operators, civil protection, foresters, councils | `/` (scroll story), `/place/<id>` (map plus questions) |
| **Research explorer** (second) | Researchers, teachers, students | `/explore` (globe, any area), `/study/<id>`, `/browse` (raw Granules), `/models` (AI Models vs Baselines) |

---

## 2. How we got here (the decisions in this conversation, in order)

| # | What was asked | What we decided | Why |
|---|---|---|---|
| 1 | Study one phenomenon in one area deeply and turn it into decisions | Turn the measurements into decisions people can act on, not just maps | Judges and users care about "so what?", not about the phase of a radar signal |
| 2 | "An app that tells me where to build", and similar ideas | Recommended **"Build Here?"**, a ground check for any plot, with Mexico City as the demo. Other ideas were kept for later: a least-risk route planner, solar siting in the Sahara, "where not to rebuild", watching existing assets, where to replant | Mexico City has the longest motion series (28 GUNW Passes) and the clearest risk |
| 3 | Can several Models work in one area? | Yes, in four ways: **stack** (several layers), **combine** (one score), **chain** (one output feeds another, e.g. burn map × slope = mud risk), **vote**. Combining and chaining create new insight | Single-Lens sites could only answer one question |
| 4 | Models that answer many questions with many solutions | Don't grow the Models. **Compute evidence once per area, let many small question recipes read it, and give several cited solutions per answer.** The Assistant only puts answers into words | Few labels; every answer stays traceable to a layer; easy to explain |
| 5 | Scale the idea to the other sites | One formula behind every question: **Risk = Hazard × Exposure × Vulnerability**. Questions are **files, not code**. Five directions of growth (section 6) | Makes the idea repeatable at every site |
| 6 | Specify Mexico City and Jijel | Defined questions M1–M9 and A1–A9, their users, seasons, scales and missing evidence. Built **M1–M4 and A1–A4** first | The hackathon order: shared engine, then the two flagship places |
| 7 | "Start building" | Built the questions engine end to end: contracts, evidence, recipes, API, Ask panel, Report chapter, tests ([ADR-0008](docs/adr/0008-questions-as-rules-over-evidence.md)) | |
| 8 | More user friendly, nicer map | Opens on the questions; place search; answer bubble at the tapped spot; roads and lines drawn as coloured vectors; the layer fades as you zoom in; a legend that folds away on phones | |
| 9 | Re-craft the UX: decisions per area first, research second | Split the site: `/place/<id>` for decisions, `/explore` and `/study/<id>` for research; "Who are you?" as the first step; shareable links `?role=&q=` | The decision features are the product; research is the proof behind them |
| 10 | Earth-science look with animation | Deep-ocean palette with a teal "radar" accent (never amber, so it can't be confused with the caution colour on answer maps); Space Grotesk headings; graticule and contour backdrops | |
| 11 | A big Earth hero, one application per scroll | A scroll story: a 3D NASA Earth ("Earth, through NISAR's eye") that flies to each place, with animated isometric scenes for Mexico City (sinking city) and Jijel (after the fire), and buttons straight into each place's questions | Shows what the radar solves before asking anyone to read a map |
| 12 | A theme per chapter | City at dusk (Mexico City), embers (Jijel), misty pines (Washington). Colours, buttons and the Earth's glow fade between them | Each application feels like its own subject |
| 13 | Scale the Algeria fire application | Built A5 (farms), A7 (rivers and dams) and A9 (since the last Pass): the questions the current data can answer. A6 needs a GUNW run, A8 spring Passes | Each new question reuses the evidence pass; two new recipes plus OSM fields and water |
| 14 | Integrate the Okavango wetland Model (notebook export) | Built W1–W5 over the installed water maps: where the flood reached, safe ground, water under reeds, tracks that flood, change since the last Pass. Lone wet pixels are dropped first; the answers say they read an AI Model's maps | The third flagship place, and the first whose questions read a Model's maps on every Pass rather than one burn or damage map |
| 15 | Install the Jijel notebook U-Net | Converted its burn mask into `pred_wildfire_2026-09-25.tif` plus a card (sites: Jijel only), checked and installed with `ml/check_export.py`, rebuilt A1–A9 | Burned IoU 0.92 against 0.33 for the HV-drop Baseline on the same test blocks. Washington loses its AI burn map (the new Model was never run there) and keeps the Baseline |

---

## 3. How the question answering works

```
NISAR Passes ──► EVIDENCE (computed once per site) ──► QUESTIONS (rule recipes) ──► ANSWER + SOLUTIONS ──► ROLES pick what each user sees
                 speed, tilt, burn, slope, flow,        questions/*.yaml +             map, verdict, reasons,     questions/roles.yaml
                 HV recovery, OpenStreetMap context     pipeline/answers.py           ranked lists, options       (home buyer, civil protection…)
                                                                                      solutions/catalogue.yaml
```

### The three layers
1. **Evidence** (`pipeline/evidence.py`, `pipeline/context.py`) is computed once per site from the radar, the elevation model and OpenStreetMap:
   - visible layers go to `data/<site>/layers/`;
   - helper layers go to `data/<site>/evidence/`.
2. **Questions** (`questions/*.yaml`) are small, published rules. Each file states:
   - its evidence, thresholds and classes;
   - a colour, verdict and meaning per class;
   - its solutions and sources;
   - its limits and status.

   The rule itself is a named **recipe** in `pipeline/answers.py`.
3. **Solutions** (`solutions/catalogue.yaml`): about 30 options, each with what it is, its cost level, its source and what to check on the ground. Each answer class lists the solutions that fit it.

**Roles** (`questions/roles.yaml`) choose which questions each kind of user sees first, and in what order.

### Why rules, not Models ([ADR-0008](docs/adr/0008-questions-as-rules-over-evidence.md))
- **Rules travel; Models don't.** The first wildfire Model scored IoU 0.86 in Algeria and 0.36 in Washington, but the burned-slope rules ran on Washington with no new code.
- **Every answer is explainable.** "Red because uneven sinking reaches the 1/500 crack limit in 9 years" is easy to defend.
- **Adding a question is cheap.** It is one YAML file if an existing recipe fits, or one YAML file plus one Python recipe if not. No training is needed.

### The rules that keep it honest
- **It screens; it doesn't certify.** Every answer ends with "what to check on the ground".
- Each solution names its source (a building code, the USGS, a paper) and its cost level.
- When the evidence is weak (low coherence, a poor fit, a slope too steep to judge), the answer is **"not measurable"**, never a guess.
- Pixels are 20–80 m, so an answer judges a neighbourhood or a large plot, not a single house.
- There is only about one year of data, so trend questions (speeding up or slowing down) are flagged as noisy.

### The API (`api/answers.py`)
| Route | Returns |
|---|---|
| `GET /answers/{site}?role=` | All questions, roles, solutions and summary headlines for a place |
| `GET /answers/{site}/at?lon=&lat=` | The answer to every question at one spot, with reasons; tapping a village pin answers for that village |
| `GET /answers/{site}/places?q=` | Place search (works with or without accents) |
| `GET /answers/{site}/features/{question}` | Ranked roads, lines or villages as GeoJSON for the map |

Rebuild the answers after a site build with `python -m pipeline.answers <site>` or `--all`. `run_site` also does this automatically.

---

## 4. The applications today (built, status "prototype")

### Mexico City: "Where is it safe to build, and what needs fixing?" (subsidence)
- **Data:** 28 GUNW Passes from Nov 2025 to Oct 2026, over about 1,850 km².
- **Evidence:**
  - **Vertical speed:** line-of-sight speed divided by cos(incidence), with the incidence taken from the GUNW cube (37–40°).
  - **Fit:** a straight-line fit per pixel, plus a quadratic fit for acceleration.
  - **Tilt years:** the years until uneven sinking reaches Bjerrum's 1/500 crack limit. Computed from speed median-smoothed over 5×5 pixels (400 m); slopes of 10° or more are masked.

| Question | Rule (main thresholds) | Result today |
|---|---|---|
| **M1 Is it safe to build here?** | Red: tilt reaches 1/500 in under 15 years, or sinking faster than 20 cm/yr. Amber: under 50 years, or faster than 5 cm/yr, or speeding up by more than 15 cm/yr². Not measurable: coherence below 0.3 or fit error above 3 cm/yr | 18% red, 38% amber, 29% blue, 16% not measurable |
| **M2 What can I build here?** | Same evidence, mapped to building and foundation types | Foundation and height advice per spot |
| **M3 Are there better plots nearby?** | Tap a spot: the steadiest ground within 2 km, up to 3 results at least 400 m apart | Ranked alternatives with distances |
| **M4 Which Metro, rail and canal segments cross uneven sinking?** | OpenStreetMap lines cut into 250 m segments; years until 1/500 along each one | 37 km of line under 15 years; Metro Lines A and 12 among the worst |

- **Sanity checks against published values:** Nezahualcóyotl sinks about 30 cm/yr and Tláhuac about 23 cm/yr (published rates go up to about 40), while Polanco is steady.
- **Roles:**
  - home buyer or family;
  - developer or architect;
  - Metro, rail and canal operators;
  - urban planning;
  - civil protection;
  - insurer or bank.

### Jijel, Algeria: "After the fire, before the rains" (wildfire)
- **Data:** 11 GCOV Passes from Jun to Oct 2026, over about 3,500 km² of the Petite Kabylie coast. The burn map comes from the notebook U-Net installed on 15 Nov (`jijel-wildfire-full-site`: burned IoU 0.92 on held-out test blocks, against 0.56 for gradient-boosted trees and 0.33 for the HV-drop Baseline, same blocks). It maps only land that was vegetated before the fire, so 42% of the site has no class and counts as not burned. It finds 61,718 ha burned; the previous ChangeUTAE map, kept in `data/algeria_ne_wildfire/previous_model/`, found 58,618 ha and agrees with it at IoU 0.85.
- **Evidence:**
  - **Flow routing:** priority-flood routing (Barnes 2014) on the 60 m Copernicus elevation model.
  - **Mud sources:** burned steep ground (23° or more, Staley 2017) upstream of each channel.
  - **Mud paths:** channels (10 ha or more draining through them) in small basins (800 ha or less), where at least 15% of the basin is burned and steep for a mud path, or at least 40% and 10 ha for a main mud path.
  - **HV recovery:** the share of the lost vegetation signal that has returned, using medians of Passes.

| Question | Rule | Result today |
|---|---|---|
| **A1 Which burned slopes could send mud onto villages?** | Villages within 250 m of a mud path | 14 villages beside a main mud path, 23 beside a smaller one; 32,104 ha of burned steep slopes are mud sources |
| **A2 Which roads should be watched or closed in heavy rain?** | 500 m road sections crossing a mud path, ranked | 115 sections to close in heavy rain, 187 to watch |
| **A3 Where should replanting start?** | Burned patches ranked by steepness, what lies downhill, and whether they are already recovering | 25,693 ha to replant first |
| **A4 Is the forest coming back?** | Recovering: 30% or more of the lost HV has returned; slow: 10–30%; requires a drop of at least 1.5 dB | Median recovery 0.02: almost nothing has come back yet |
| **A5 Which farms lost their cover?** | Each OpenStreetMap field, orchard and meadow gets the share of its mapped 20 m pixels that burned: mostly (50% or more), partly (10–50%), not burned; not mapped when the burn map covers under half of it | 118 fields mostly burned and 9 partly: 163 ha of the 4,508 ha mapped, 58 ha of it orchards. 157 fields (354 ha) lie mostly outside the burn map (harvested or bare before the fire) and are marked "not mapped", not "not burned". OSM maps only part of the farms |
| **A7 Is mud heading to the rivers and the dams?** | Burned and burned-steep ground upstream of every river (800 ha or more), reservoir and river mouth; heavy at 10% or more of the catchment burned and steep, some at 3–10%. Catchments fed from beyond the map are marked partial. Tapping a spot says which dam or river mouth its rain ends in | 7 of 26 reservoirs and mouths heavy, led by the mouth near El Kennar (31%); Tabellout gets the most burned steep ground of any dam (1,790 ha, partial); about 189 km of river heavy |
| **A9 What changed since the last Pass?** | HV and HH change between the last two Passes on 60 m blocks; 3 dB is about four times the Pass-to-Pass noise (0.7 dB HV). Classes: vegetation fell, surface darker, surface brighter, vegetation rose; lone blocks dropped | 19 Oct to 31 Oct: 58 ha lost vegetation signal and 87 ha turned darker, 29 of those patches near villages or roads; 1,921 ha brighter, mostly wet soil after rain |

- **Roles:**
  - civil protection;
  - forestry service;
  - local council;
  - public works (roads);
  - farmer or agricultural services (A5);
  - dam and water agency (A7);
  - national park.

### Washington (Sinlahekin Fire): the same questions on another fire
The A1–A5, A7 and A9 question files ran with **no new code**: A7 ranks Conners Lake first among the reservoirs (1,184 ha of burned steep ground upstream) and A9 finds 169 ha of lost vegetation signal between 5 and 17 Oct. It found no mapped village within 250 m of a mud path, and 3,151 ha of burned steep slopes as mud sources. This is the proof that the questions travel.

### Okavango Delta: "Where does the flood go, and where is it safe?" (wetland)
- **Data:** 11 GCOV Passes from 26 Jun to 5 Nov 2026 on track 172, over about 10,500 km² of the central delta. The water maps come from the AI Model trained in the notebook `saraura-wetland-okavango-v3` (LightGBM open water, physics-guided flooded vegetation, HMM through the season): open-water IoU 0.21 against 0.01 for the Otsu Baseline, held-out 5 km blocks at true prevalence. The flooded-vegetation class is supported by physics only (no labels exist under canopy).
- **Evidence** (`evidence.wetland`, on the maps' 40 m grid): each Pass's class map with lone wet pixels dropped (fewer than 5 of the 3×3 block wet; about 30% of wet pixels are such speckle); share of Passes with open water and with water under vegetation; days under water; distance to this season's water.
- **Context:** OpenStreetMap camps, lodges and airstrips (87) and tracks (2,738), new kinds `camps` and `tracks` in `pipeline/context.py`. Place search and the spot heading include camps.

| Question | Rule | Result today |
|---|---|---|
| **W1 Where did the flood reach this season?** | Open water on no Pass / some / half or more / 90% or more; camps, airstrips and villages ranked by open water within 500 m | 196 km² on 26 Jun, peak 1,098 km² on 13 Aug, 480 km² on 5 Nov; 48 camps, airstrips and villages reached, led by Little Vumbura, Guma Lagoon and Kadizora |
| **W2 Where is it safe to graze, farm or build a track?** | Dry all season and over 200 m from water; dry but within 200 m; under water 36 days or less (graze, flood-recession farming); longer | 37% dry and away from water, 43% beside it, 4% short flood, 16% long flood |
| **W3 Where is water hiding under reeds and papyrus?** | Water under vegetation on some Passes / half or more | Peak 576 km² on 6 Sep, 39% of all water mapped that day; 435 km² on most Passes |
| **W4 Which tracks and roads go under water, and when?** | 500 m sections; under water on a Pass when a fifth of the section is; listed from 2 Passes; red at half the Passes | 414 km under water on most Passes, 174 km on some; 392 km still under water on 5 Nov |
| **W5 Where did the water arrive or leave since the last Pass?** | Last two Passes; changed patches of at least 5 of 9 pixels | 24 Oct to 5 Nov: 29 km² drained, 9 km² newly flooded: receding |

- **Caveat to say out loud:** on the three dates with Sentinel-2, the maps show 8 to 17 times more open water than optical does. Part is shallow water among grass that optical misses, part is smooth dry ground. W1 says so in its limits, and the page footer says the answers read an AI Model's maps (`model_evidence` in `answers.json`, also used for Jijel's and Venezuela's Model maps).
- **Roles:** safari camp or lodge operator; herder or farmer; district council and roads; water authority and wetland managers; wildlife and parks; land board and planning.

---

## 5. The website as it is now

| Page | What it does |
|---|---|
| `/`, the scroll story | **Hero:** a 3D Earth (NASA Blue Marble by day, Black Marble city lights by night, NISAR on its orbit) under "Earth, through NISAR's eye".<br>**Intro:** figures that count up.<br>**Chapter 01, Mexico City:** a sinking-city scene in three acts (scan, sink and crack, answer colours).<br>**Chapter 02, Jijel:** an after-fire scene in three acts (fire under radar, rain and mud, barriers, a road sign and saplings).<br>**Chapter 03, Washington.**<br>Each chapter has its own theme, real headlines from the API and buttons into its questions. The page ends with an "I am a…" picker, how it works, research links and other sites. |
| `/place/<id>` | The decision page: a "Who are you?" step, question cards, the map with the answer layer, a bubble at the tapped spot with reasons and options, ranked lists that fly the map, place search, shareable links and a PDF. |
| `/explore`, `/study/<id>`, `/browse`, `/models` | Research: the globe with every Pass, drawing an area for an Analysis, layers, charts, Models vs Baselines and the PDF Report. |

**Key frontend files:**
- `frontend/components/landing/`: `Landing.tsx`, `Globe3D.tsx`, `Ambience.tsx` and `scenes/`.
- `frontend/components/study/`: `StudyPage.tsx`, `AskPanel.tsx` and `StudyMap.tsx`.
- `frontend/components/SiteNav.tsx`.
- Theme colours are in `frontend/app/globals.css`; the chapter themes are at the end of that file.
- Earth images are in `frontend/public/textures/` (public domain).

---

## 6. How to scale each solution further

### 6.1 The five directions of growth (they apply to every place)
| Direction | How | Cost |
|---|---|---|
| **More questions** | New YAML files that reuse the same evidence; a new recipe only when the rule is genuinely new | Small |
| **More places** | Physics-based questions run on any site or drawn Analysis. Model-based ones stay on Showcase Sites ([ADR-0001](docs/adr/0001-ai-only-on-showcase-sites.md)) | Medium: a site build, plus OpenStreetMap |
| **More users** | Same evidence, new roles in `roles.yaml` (water authority, insurer, aid agency…) | Very small |
| **More time** | Re-answer after every 12-day Pass. "What changed since the last Pass" becomes its own question and an alert feed | Medium |
| **More hazards** | Hazards already in the data with no question yet: landslides, ground cracks, dam and levee movement, coastal erosion, sand encroachment | Medium |

### 6.2 Mexico City: next questions
| # | Question | Evidence | Solutions | Needs |
|---|---|---|---|---|
| M5 | Which wells should pump less? | Speed and acceleration around wells | Reduce or move pumping, add recharge | CONAGUA well locations |
| M6 | Where does water pool in the rainy season? | GCOV flooding, plus low spots sinking faster than their surroundings | Raise ground floors, drains, pumping points | **A GCOV run over the city** |
| M7 | Where may cracks open in the ground? | Steep tilt at the edge of the lake clay | Permit limits, surveys before building | Official soil-zone map (hills, transition, lake) |
| M8 | Is the western hillside moving? | Motion on slopes over 15° | Drainage, retaining walls, moving homes out of ravines | Already in the data |
| M9 | What changed since the last Pass? | New Pass vs the trend | Who to notify | Pass-by-Pass rebuilds |

- **New users:** the water authority (SACMEX / CONAGUA) for M5, M6 and M9; Metro for M4 and M9; civil protection for M6–M9.
- **Scales:**
  - plot: decision card and PDF;
  - neighbourhood (colonia): share in each colour and the worst streets;
  - borough (alcaldía): a ranking for budgets;
  - the whole basin: how the sinking spreads.
- **Other cities:** the same questions work in other sinking cities (Jakarta, Tehran, Bangkok, Houston).
- **Validation to add:** GNSS stations; the official soil zones, to show where the ground behaves worse than its zone suggests.

### 6.3 Jijel: next questions

A5, A7 and A9 are **built** (section 4). A6 and A8 wait for data.

| # | Question | Evidence | Solutions | Needs |
|---|---|---|---|---|
| A5 ✅ | Which farms lost their cover? | Burn map × fields | List for compensation, burned hectares per field | Field boundaries |
| A6 | Did a slope move after rain? | Coherence loss + backscatter change on slopes (+ GUNW) | Inspection, evacuation, road closure | A GUNW run (forest coherence is low in the rainy season, so flag it) |
| A7 ✅ | Is mud heading to the rivers and the Beni Haroun dam? | Burned share of each basin above Oued El Kebir and Beni Haroun | Sediment traps, reservoir watch | Already possible from the flow routing |
| A8 | Where is fuel building up before next summer? | HV regrowth of shrubs near villages | Firebreaks, clearing near homes, where to place firefighting teams | Spring Passes |
| A9 ✅ | What changed since the last Pass? | New Pass vs previous | Who to notify | Pass-by-Pass rebuilds |

- **The fire year:**
  - **winter rains:** A1, A2, A6 and A7, updated every Pass; the radar sees through winter cloud;
  - **spring:** A3 and A4;
  - **May–June:** A8;
  - **fire season:** new burn mapping through smoke;
  - **year 2:** a full recovery curve.
- **New users:** the dam and water agency (ANBT) for A7, now a role; farmers and the agricultural services for A5.
- **Next for these questions:** the real field map from the agricultural services would replace OpenStreetMap in A5; a larger elevation model would close A7's partial catchments (Beni Haroun, El Kebir); A9 should keep a change only if the next Pass confirms it.
- **Scales:**
  - slope or field: decision card;
  - commune: ranked lists;
  - wilaya: the winter plan;
  - north-east Algeria: the same questions for Béjaïa, Skikda, El Tarf and Tizi Ouzou, which burn almost every summer;
  - Mediterranean: any burned forest in Greece, Türkiye or Portugal.
- **Optional:** rainfall from NASA GPM would set *when* to close a road. That is a team choice.

### 6.4 Washington: validation
The USGS publishes post-fire debris-flow hazard maps for western US fires. Comparing our A1 mud paths with theirs for the Sinlahekin Fire would be **real external validation** of the burned-slope rules.

### 6.5 The other Showcase Sites (questions designed, not built)
| Site | Questions | Solutions | Evidence |
|---|---|---|---|
| **Venezuela (earthquake)** | Which neighbourhoods to inspect first? Where not to rebuild? Is the ground still moving? Which roads and lifelines crossed moving ground? | Inspection order, relocation or special design, lifeline checks | Richest site: displacement, coherence loss, phase gradient, damage Model with real labels (EMSR884) |
| **Kamchatka (volcano)** | Where is new lava going? Is the volcano swelling? Which valleys would carry mudflows (lahars)? | Close trails, raise the alert level, keep camps out of valleys | Ground motion, coherence; the lava Model is weak (AP 0.07), so lean on physics; ionosphere noise is worse up north |
| **Okavango (wetland)** ✅ built as W1–W5 (section 4) | Next: which airstrips close, and when; does a camp's access hold in a big flood year (needs a second season) | Move camps and herds early; dry-land ranking | Water Model maps; only one season so far |
| **US Midwest (farming)** | What is in each field before harvest? When was each harvested? Which fields stayed waterlogged? | Harvest estimates, insurance checks, drainage priorities | Crop Model (F1 0.86 before harvest), HV series |

**The cheapest live demo of scaling:** add questions for one more site with YAML files only, reusing existing recipes where possible. Washington already proves this for fires. Venezuela and Okavango each needed new recipes in `pipeline/answers.py`; a second wetland would now need YAML only.

### 6.6 What gets in the way at scale
- **Some thresholds depend on the place.** The 1/500 crack limit holds broadly, but a dangerous flood depends on local building types.
- **Exposure data is thin in places.** OpenStreetMap is weak in rural Africa and Kamchatka.
- **Responsibility.** Every answer must say it is a screening, not an engineering report.
- **Compute.** A drawn GUNW Analysis is capped at about 500 km², so whole cities need precomputing.
- **Data length.** Only about one year exists; trend questions need a second year.
- **Combined scores need their own check.** Each Model was scored alone; a combined verdict needs its own reference, such as known cracked buildings or recorded flooded streets.

---

## 7. Suggested next steps (in order)

1. **Merge PR #1** into `main` so the laptop clone has everything by default.
2. **Demo polish:** run through `/` → Mexico City → "Is it safe to build here?" → tap Nezahualcóyotl → Jijel → "Which villages are at risk?" → a village pin → PDF.
3. **One more place with questions**, to show scaling: Venezuela ("where not to rebuild", "inspect first") has the richest evidence.
4. **M6 flooding for Mexico City**, once a GCOV run is done.
5. **External checks:** the USGS debris-flow maps (Washington) and GNSS (Mexico City).
6. **"Since last Pass"** feed and alerts.
7. **S-band:** decide how it enters the app once ISRO data arrives (PLAN Phase 5).

---

## 8. Moving to another machine

GitHub only has the code. Almost all of the ~36 GB on the old PC is downloaded radar data:

| Folder | Size on the old PC | What to do |
|---|---|---|
| `cache/` | 16.6 GB | Don't copy. It refills itself. |
| `data/` | 11.9 GB | Optional. Copy only `mexico_city_subsidence`, `algeria_ne_wildfire` and `washington_sinlahekin_wildfire` (about 4.2 GB) to skip rebuilding. |
| `ml/data` and similar | about 6 GB | Only for retraining Models. Trained Models are in `models/` on GitHub. |
| `.venv`, `frontend/node_modules`, `frontend/.next` | about 2 GB | Don't copy. They are machine-specific and get rebuilt. |
| `.env` | tiny | **Copy by hand, privately** (USB, not email or chat). It holds `EARTHDATA_TOKEN`, which expires about 60 days after it is made. |

**Setup:**
```bash
git clone https://github.com/Djihad-derbal/Dancing-with-SARs-NASA.git
cd Dancing-with-SARs-NASA
python -m venv .venv && .venv/Scripts/python -m pip install -r requirements.txt   # macOS/Linux: .venv/bin/python
.venv/Scripts/python -m playwright install chromium                              # once, for the PDF Report
cd frontend && npm install
```

**Data:** either copy the three site folders into `data/`, or rebuild them with `python -m pipeline.run_site <site>`, which downloads from NASA and also builds the answers. Then start the API and the frontend as in the README. Leave at least 10 GB free.

**Not in git:** `.claude/` (local tool settings, such as the browser-preview configs). Recreate them only if you need them.

---

## 9. Where things live

| What | Where |
|---|---|
| Site definitions | `sites/*.yaml` |
| Questions, roles, solutions | `questions/*.yaml`, `questions/roles.yaml`, `solutions/catalogue.yaml` |
| Schemas and validation | `contracts/*.schema.json`, `contracts/validate.py` |
| Evidence, context, answers | `pipeline/evidence.py`, `pipeline/context.py`, `pipeline/answers.py` |
| Site build | `pipeline/run_site.py` |
| API | `api/` (`answers.py`, `study.py`, `main.py`) |
| Frontend | `frontend/` (Next.js 16; read `frontend/AGENTS.md` first: this Next.js version has breaking changes) |
| Models | `ml/` (training), `models/` (exported) |
| Tests | `tests/` (`test_answers.py` covers the questions engine) |
| Decisions | `docs/adr/` (ADR-0008 is the questions engine) |
