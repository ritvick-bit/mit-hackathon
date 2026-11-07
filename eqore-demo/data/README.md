# Synthetic reference artifacts and local runtime data

The repository includes a small, explicit set of synthetic reference artifacts:

- `challenge-design-v03.json`: frozen independent challenge design, public scenario snapshots, model-generation provenance and the original engine source used for BEFORE comparisons.
- `challenge-results-before-v03.json` and `challenge-live-before-v03.json`: preserved failures required by the regression tests.
- Four `v04` evaluation reports: targeted baseline tests, whole-project baseline runs, existing independent challenge checks, and two selected live phase decisions.
- `phases-v04.png`: an interface example from an isolated Riverbend retest scenario.
- `pm-message-vision-v05.json`: one fresh ChatGPT summary/observation trace for the authored synthetic field-note image, with source and state-preservation checks. It is not a full-project live evaluation.

The three frozen challenge artifacts are test fixtures. Preserve their bytes; integrity checks reference their hashes. Their observations and contacts are synthetic. Model provenance records are historical execution evidence, not reusable credentials or fresh model outputs.

SQLite databases, backups, new reports and other generated files are ignored. Each clone creates its own database and project progress on first startup. Reference JSON reports are not automatically imported into that database; use the Evaluation lab to generate local results.

Older validation reports described in the project history remain in the original development workspace and are not all included here.
