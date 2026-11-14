# Questions are rules over shared evidence, not new Models

People don't come to SARAURA asking for a velocity map. They ask "is it safe to build here?", "which roads should close when it rains?" or "where should replanting start?". We answer those **Questions** with rule recipes that read one shared set of **evidence** layers per site. We don't train a Model per question. Each Question is a YAML file (`questions/*.yaml`) holding its thresholds, classes, sources and limits. Each class lists **Solutions** from a cited catalogue (`solutions/catalogue.yaml`), and every Solution says what to check on the ground. **Roles** (`questions/roles.yaml`) pick which Questions each kind of user sees.

We chose rules over a multi-output Model for three reasons:
- **Explainability.** Every answer can be traced to a measured number and a stated threshold, at any spot.
- **Little ground truth.** Questions such as "years until cracking" have no labels to train on.
- **Easy scaling.** A new Question is one file and at most one recipe in `pipeline/answers.py`. Recipes are physics, so they also run on another site of the same Lens.

Validated Models are still used as evidence where they exist. The wildfire burn map comes from the Model on Showcase Sites, and an answer layer never runs a Model itself (ADR-0001).

Consequences:
- Answer layers have their own manifest kind, `answer`, which is allowed on Analyses too.
- Thresholds are visible and labelled as team choices, or come from published sources: Bjerrum's 1/500 tilt limit, and Staley et al.'s burned ground on slopes of 23° or more.
- The Study page and the Report present answers as a screening that tells you where to look and what to check, never as an engineering report.
