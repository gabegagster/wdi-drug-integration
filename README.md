# Web Data Integration: Pharmaceutical Drug Data

University of Mannheim WDI project integrating pharmaceutical drug data from
Canada, the European Union, and the United States. The central entity is a
medicine, identified through its `brandName` and full `activeSubstances` set.

## Data sources

| Source | Coverage | Raw data folder |
| --- | --- | --- |
| Health Canada DPD | Canadian drug products across regulatory statuses | `data/1_raw/03_ca_health_canada_dpd/` |
| EMA Medicines | EU-authorised medicines | `data/1_raw/02_eu_ema_medicines/` |
| Drugs@FDA | US-approved drug products | `data/1_raw/01_us_drugs_at_fda/` |

## Project phases

### Phase I: Data selection and translation

Prepare source records, consolidate products into medicine entities, and
translate them into the shared medicine schema. Integrated XML exports for
DPD, EMA, and FDA are available in `data/4_translated_mapforce/`.

The repository includes DPD, EMA, and FDA MapForce mappings, shared helper libraries,
lookup tables, XML/JSON schemas, and schema and duplicate validation.
See the [MapForce code guide](src/mapforce/README.md) for preparation and translation instructions.

#### Team & Work Split (Phase I)

* **Gabriel:** Requirements compliance, math checks, and final PDF assembly.
* **Özlem:** Use case narrative and entity overlap justification.
* **Anatole & Hai:** Data extraction and profiling (FDA, EMA, Wikidata).
* **Trang:** Target schema design and attribute intersection mapping.

### Phase II: Identity resolution

#### Gold-standard datasets

Reviewed medicine pairs cover DPD/EMA, DPD/FDA, and EMA/FDA. Each source-pair
folder contains review batches, unified and selected pairs, and PyDI exports.
The shared whole, train/validation, and test datasets are saved in
`data/5_golden_standard_pair/golden_standard_pair_complete/`.

See the [gold-standard code guide](src/golden_standard/README.md) for generation,
label checks, selection, exports, and the shared split. Dataset files and reports
under `data/5_golden_standard_pair/` are versioned.

#### Blocking, matching, and clustering

* **Blocking:** Hybrid semantic + lexical blocking (`notebooks/blocking_experiment.ipynb`, outputs in `data/7_blocking_candidates/`).
* **Matchers:** Rule-based (`notebooks/manual_matcher_experiment/`), supervised ML (`src/identity_resolution/ml_features.py`, `notebooks/ml_classifier_experiment/`, `notebooks/ml_tree_classifier_experiment/`), fine-tuned DistilBERT (`notebooks/PLM_DistilBERT/`), and zero-shot LLM (`src/identity_resolution/llm_zero_shot_matcher.py`).
* **Clustering:** Connected-components clustering (`src/identity_resolution/clustering.py`, reports in `data/6_evaluation/`).

### Phase III: Data fusion

Active data-loading, evaluation-set curation, and baseline PyDI fusion experiments:

* **Ingestion & correspondence prep:** `src/data_fusion/loader.py`, `correspondence_prep.py`, `fusion_export_xml.py` (see [handoff guide](src/data_fusion/HANDOFF.md)).
* **Fusion evaluation set:** Stratified 36-cluster worksheet in `data/8_fusion_eval/fusion_eval_worksheet.csv` (`src/data_fusion/sample_eval_set.py`, [Role 2 guide](src/data_fusion/role2_eval_set.md)).
* **Fusion experiments:** Baseline PyDI experiment skeleton in `notebooks/data_fusion_skeleton/`.

### Verification and ILIAS packaging

Run the non-destructive clean-run verification and ILIAS submission bundler from the repository root:

```bash
python3 src/package_submission.py
python3 src/package_submission.py --package
```

This checks all Phase I to III schemas, splits, correspondences, and cached evaluation metrics, prints full-dataset entity expansion and density summaries, and writes a curated submission bundle and zip archive under `dist/`.

## Reports and code guides

| Area | Results report | Code guide |
| --- | --- | --- |
| Integrated XML validation | [Schema and duplicate results](data/4_translated_mapforce/integrated%20xml%20validation.md) | [MapForce README](src/mapforce/README.md) |
| Gold-standard pairs | [Pair validation and split results](data/5_golden_standard_pair/golden%20standard%20pair%20dataset%20report.md) | [Gold-standard README](src/golden_standard/README.md) |
| MapForce helpers | | [Helper reference](src/mapforce/helpers/README.md) |

## Local setup

Use **Python 3.12**, as specified in `.python-version`. Run these commands from
the repository root in Windows PowerShell:

```powershell
py -3.12 -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
& .\.venv\Scripts\python.exe -m pip check
```

For an existing environment, start with the dependency installation command.
If installation encounters Windows path-length limits, use `uv`:

```powershell
uv pip install --python .\.venv\Scripts\python.exe -r requirements.txt
```

Dependencies include pandas, Jupyter, `lxml`, `jsonschema`, and `uma-pydi`
(imported as `PyDI`). Verify the PyDI environment with the offline smoke check:

```powershell
& .\.venv\Scripts\python.exe src/identity_resolution/check_environment.py
```

The `notebooks/` folder is for experimenting with matchers. Select the project's
`.venv` interpreter as the notebook kernel. Altova MapForce is used for the
translation mappings; see its code guide for the tested version and engine.

## Repository structure

```text
wdi-drug-integration/
├── data/
│   ├── 1_raw/                              # Source datasets and archives
│   │   ├── 01_us_drugs_at_fda/              # FDA relational tables
│   │   ├── 02_eu_ema_medicines/             # EMA medicines register
│   │   ├── 03_ca_health_canada_dpd/         # Canadian DPD tables by status
│   │   └── _archives/                      # Compressed source backups
│   ├── 2_processed/                        # Prepared product and medicine-entity tables
│   ├── 3_profiling/                        # Profiling and overlap analysis
│   │   ├── entity_count/                   # Medicine-entity counts and overlap estimates
│   │   └── ingredient_cleaning/            # Ingredient-cleaning artifacts
│   ├── 3_fused/                            # Versioned Phase II correspondences/clusters; fused outputs git-ignored
│   ├── 4_translated_mapforce/              # Integrated XML exports and validation report
│   ├── 5_golden_standard_pair/             # Reviewed pairs, PyDI exports, and pair report
│   │   ├── dpd_ema/                        # DPD/EMA review batches and exports
│   │   ├── dpd_fda/                        # DPD/FDA review batches and exports
│   │   ├── ema_fda/                        # EMA/FDA review batches and exports
│   │   └── golden_standard_pair_complete/  # Shared whole, train/validation, and test CSVs
│   ├── 6_evaluation/                       # LLM/ML evaluation reports, metrics, and MapForce HTML docs
│   ├── 7_blocking_candidates/              # Hybrid blocking candidate exports & manifest
│   └── 8_fusion_eval/                      # Phase III fusion evaluation worksheet
├── src/
│   ├── data_collection/                    # Extraction, consolidation, and profiling scripts
│   ├── mapforce/                           # Source-to-schema mappings and code guide
│   │   ├── schema/                         # XML/JSON schemas, samples, and validation script
│   │   ├── lookups/                        # Controlled vocabularies and lookup builder
│   │   └── helpers/                        # Shared mapping libraries and helper checks
│   ├── golden_standard/                    # Pair generation, review statistics, and split scripts
│   ├── identity_resolution/                # Blocking utils, ML features, LLM matcher, and clustering
│   └── data_fusion/                        # XML loader, correspondence prep, eval sampler, and XML export
├── notebooks/                              # Blocking, matcher, DistilBERT, and fusion experiments
├── docs/
│   ├── outline/                            # Project outline
│   ├── slides/                             # Course lecture and exercise slides
│   └── final_report/                       # Final-report materials (Springer LNCS)
├── .gitignore                              # Local environments, caches, and generated-file exclusions
├── .python-version                         # Python 3.12 environment version
├── requirements.txt                        # Python dependencies
└── README.md                               # Project overview and documentation links
```
