# Models integrate only through files

A Model plugs into the app only by writing files: `pred_<lens>_<date>.tif` COGs into the Showcase Site's `layers/` and a Model card JSON. The API and frontend never import, load or run model code. Any framework works this way (the existing U-TAE, LightGBM, PyTorch), and Models can be rebuilt without touching the app. The trade-off is that Models can't run on an Analysis at request time; [ADR-0001](0001-ai-only-on-showcase-sites.md) already rules that out.
