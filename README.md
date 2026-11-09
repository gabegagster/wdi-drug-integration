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

The repository includes DPD and EMA MapForce mappings, shared helper libraries,
lookup tables, XML/JSON schemas, and schema and duplicate validation.
The FDA XML export is available; its MapForce mapping file is currently absent.
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

### Phase III: Data fusion

Planned consolidation of matched medicines into shared records.
`src/data_fusion/` and `data/3_fused/` are placeholders.

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
│   ├── 3_fused/                            # Placeholder for fused outputs
│   ├── 4_translated_mapforce/              # Integrated XML exports and validation report
│   └── 5_golden_standard_pair/             # Reviewed pairs, PyDI exports, and pair report
│       ├── dpd_ema/                        # DPD/EMA review batches and exports
│       ├── dpd_fda/                        # DPD/FDA review batches and exports
│       ├── ema_fda/                        # EMA/FDA review batches and exports
│       └── golden_standard_pair_complete/  # Shared whole, train/validation, and test CSVs
├── src/
│   ├── data_collection/                    # Extraction, consolidation, and profiling scripts
│   ├── mapforce/                           # Source-to-schema mappings and code guide
│   │   ├── schema/                         # XML/JSON schemas, samples, and validation script
│   │   ├── lookups/                        # Controlled vocabularies and lookup builder
│   │   └── helpers/                        # Shared mapping libraries and helper checks
│   ├── golden_standard/                    # Pair generation, review statistics, and split scripts
│   ├── identity_resolution/                # PyDI environment smoke check
│   └── data_fusion/                        # Placeholder for data-fusion code
├── notebooks/                              # Experiments with matchers
├── docs/
│   ├── outline/                            # Project outline
│   └── final_report/                       # Final-report materials
├── .gitignore                              # Local environments, caches, and generated-file exclusions
├── .python-version                         # Python 3.12 environment version
├── requirements.txt                        # Python dependencies
└── README.md                               # Project overview and documentation links
```
