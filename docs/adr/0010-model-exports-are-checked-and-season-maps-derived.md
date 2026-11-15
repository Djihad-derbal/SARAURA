# Model exports are checked before install; water season maps are derived in the repo

Models are often trained outside the repo (a notebook on a GPU machine) and handed over as an export with the repo's own layout: `ml/model_cards/<name>.json` and `data/<site>/layers/pred_<lens>_<date>.tif` ([ADR-0005](0005-models-integrate-through-files.md)). The first wetland notebook export showed why such an export can't be copied in blindly. Its card compared a Model score from held-out blocks (0.02) against a Baseline scored on balanced samples (0.47). The maps classed a quarter of the delta as open water when Sentinel-2 saw under 1%. Its flood peaked on the first Pass.

**Decision 1.** `ml/check_export.py <export>` checks an export before it replaces a Model:
- the card is valid and matches the site's lens;
- the Model and its Baseline are scored on the **same metric**, and the Model beats it (bracketed notes on the metric may differ, with a warning);
- the maps are in the site's projection and cover its area (a coarser grid, like the 250 m Neighborhoods of the earthquake Model, is allowed with a note);
- the class values are the card's outputs;
- the dates are Passes of the site;
- for a water Model, it warns when the wet area peaks on the first Pass.

`--install` refuses an export that fails, unless `--force`. It keeps the previous card and maps in `data/<site>/previous_model/<time>/` and refreshes the manifest. It only reads JSON and GeoTIFF; nothing in an export runs.

**Decision 2.** Season products are derived in `pipeline/predictions.py` from whatever per-Pass class maps are installed, not shipped by the Model. They are made when the card has an output labelled "Open water" or "Flooded vegetation" and there are 2+ Passes:
- `pred_<lens>_frequency`: share of Passes wet;
- `pred_<lens>_hydroperiod`: days wet, each wet Pass counting until the next one;
- `pred_<lens>_onset`: days after the first Pass until first wet.

Like the class maps, they are listed as `prediction` layers. The flood pulse (hectares per class per Pass) is the research endpoint `/research/{id}/class_area`. This works the same for a 2-class (open water) and a 3-class (plus flooded vegetation) Model. A retrained or swapped Model gets these products, and the chart, with no code change, and they can never disagree with the maps shown.

**Trade-off.** The derived maps inherit every error of the class maps; their legend notes say so. A Pass with no data at a spot is skipped there rather than counted as dry.
