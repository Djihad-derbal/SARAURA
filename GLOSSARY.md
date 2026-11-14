# SARAURA

An open-source web app that turns NISAR radar data into maps, 3D views, time series and statistics for surface change anywhere on Earth, with curated AI-assisted examples.

## Places and results

**Lens**:
A type of surface change (earthquake, volcano, subsidence/landslide, wildfire, wetland/flood, farming), together with its physics layers, Baseline, legend and "Why it changed" explanation.
_Avoid_: Mode, theme, the "lens page"

**Showcase Site**:
A curated, precomputed place that demonstrates one Lens and is the only place that Lens's AI Model runs.
_Avoid_: Demo site, act, story

**Analysis**:
The result of processing an area a user drew, on demand. It may carry a Lens (physics layers and Baseline), but never an AI Model.
_Avoid_: Job (backend word only), result, query

**Study page**:
The single screen layout that both a Showcase Site and an Analysis open in.
_Avoid_: Lens page, lens layout

**Report**:
The PDF export of a Showcase Site or Analysis: summary page, one section per layer, Model vs Baseline where present, and data sources. It never contains Assistant text.
_Avoid_: Export, printout

**Neighborhood**:
A fixed 250 m grid cell, the unit the earthquake Model ranks by damage probability.
_Avoid_: District, parish, block

## Data

**Granule**:
One NISAR product file (e.g. one GCOV or GUNW HDF5).
_Avoid_: Scene, image, file

**Pass**:
One NISAR acquisition date over a place; one tick on the time slider.
_Avoid_: Scene, acquisition (in UI text)

**Stack**:
All Passes over a place on the same track and direction; a time series or change layer is only ever computed within one Stack.
_Avoid_: Series (that is the output), collection

## Models and trust

**Baseline**:
The simple physics rule a Lens's Model must beat (e.g. "HV drop > 1.5 dB", Otsu threshold on HH).
_Avoid_: Benchmark, reference (when meaning this)

**Model**:
The AI model of one Lens, trained offline on its Showcase Site(s), with one job, one user and one Baseline.
_Avoid_: AI layer (that is the Model's output on the map)

**Model card**:
The public record of a Model: job, user, inputs, labels, Baseline score, Model score, limits, Status.

**Proxy label**:
A training label not observed on the ground (derived from optical imagery or hand-digitised), always declared on the Model card.

**Assistant**:
A grounded explainer that answers questions about the Showcase Site or Analysis on screen, using only its manifest, statistics, rule-based insights and Model card; it quotes numbers, never computes them.
_Avoid_: Chatbot, AI (ambiguous with Model)

**Question**:
Something a person asks of a Study ("Is it safe to build here?"), answered by a rule recipe over evidence layers with stated thresholds. It gives a map of classes, a ranked list where useful, and an answer at any clicked spot (questions/*.yaml, ADR-0008).
_Avoid_: Query, use case, AI answer

**Evidence**:
Layers derived from a site's measurements that Questions read, such as vertical speed, years to the 1/500 tilt limit, burned steep ground upstream, or forest recovery. Physics and rules only.
_Avoid_: Features (ML word)

**Solution**:
One option a Question offers for a class. It states its cost (low, medium or high), its source, and what to check on the ground (solutions/catalogue.yaml). It is a starting point, never an engineering design.
_Avoid_: Recommendation, fix

**Role**:
A kind of user (home buyer, civil protection, forestry service...) and the Questions they see first (questions/roles.yaml).
_Avoid_: Persona, user type

**Status**:
How far to trust a feature or Model: operational (validated against a Baseline or reference data) or prototype (works, not validated).
_Avoid_: Planned (there is no planned status)
