# Medicine XML and correspondence handoff

The two Python helpers cover XML loading, source provenance and correspondence
preparation. The current three XMLs load into **52,459 records and 18 columns**:
DPD **41,636**, EMA **2,648**, FDA **8,175**.

- **loader.py**: `load_datasets()` returns a dictionary of source DataFrames.
  It validates the XSD and project dosage-form/route vocabularies, preserving
  every field value and its Python type, including ordered ingredient and strength lists.
- **correspondence_prep.py**: `prepare_correspondences(pairs, datasets)` returns
  `id1,id2,similarity`. It validates IDs, labels, duplicate pairs and transitive groups.
  Groups may contain multiple records from the same source.

The fusion pipeline imports these functions; the final project runner can call
the same functions or command-line interfaces.

## Required inputs

Keep the two Python files together. Use the project's Python environment with
pandas, lxml and **uma-pydi 0.2.1**; verification used **Python 3.12**. The repository's
`requirements.txt` includes these dependencies. PyCharm is optional.

Both scripts need the existing project files below. `--project-root` points to
the repository containing them, regardless of where this handoff folder is saved:

```text
data/4_translated_mapforce/dpd_medicines.xml
data/4_translated_mapforce/ema_medicines.xml
data/4_translated_mapforce/fda_medicines.xml
src/mapforce/schema/medicines.xsd
src/mapforce/lookups/dosage_form.xml
src/mapforce/lookups/route.xml
src/mapforce/lookups/strength_unit.xml
```

Only `correspondence_prep.py` additionally needs a **pair CSV** supplied through
`--input`. Required columns are `id1,id2`, using the exact IDs from these XMLs.
Optional columns are `match` (1/0) and `similarity` or `score` (0–1). With `match`,
the helper keeps 1 rows and excludes 0 rows; otherwise all pairs are treated as
positive matches. Default similarity **1.0 is a pair indicator, not a probability**.

The filename is arbitrary: `candidate_medicine_clusters.csv` is not required.
A cluster-membership table containing lists of IDs is a different format; obtain
its underlying pair export before using this helper. No matching model is run.
These three handoff files contain code and instructions, not the input data.
The group must have access to the shared project files and chosen pair CSV.

## Run both scripts

From the folder containing these two Python files, replace the example paths
with the repository and pair CSV on your machine:

```bash
PROJECT_PATH="/path/to/wdi-drug-integration"
python loader.py --project-root "$PROJECT_PATH"
mkdir -p "$PROJECT_PATH/output"
python correspondence_prep.py \
  --project-root "$PROJECT_PATH" \
  --input /path/to/phase2_pairs.csv \
  --output "$PROJECT_PATH/output/correspondences.csv"
```

The loader command prints the loading summary; use `load_datasets()` to obtain
DataFrames in Python. The correspondence command loads the XMLs itself, prepares
pairs and saves `id1,id2,similarity`. It does not require a prior loader run.
`--input` is required; running the file without it gives a command-usage error.
Without `--output`, it prints only the summary. Input and output must be different
files. Identical reruns reuse the output; a differing existing file is protected.
For a different matching input, choose a new output filename.
Local PyCharm configurations named **XML Loader** and **Prepare Correspondences**
are conveniences; they are not bundled with these three files.

## Tested 1,938-pair baseline

The verified example uses the existing exact normalized-brand/full-ingredient
match export. Its prepared pair CSV is `output/correspondences.csv` in the local
project used for verification; this CSV is **not bundled with the three files**.
If the group wants this exact check, it needs access to that CSV or the original
exact-match pair export. Expected results for this baseline are:

```text
Pairs: 1,938; groups: 1,372; grouped records: 3,027
```

This is the **exact-match baseline, not the complete Phase II matching result**.
Other matching inputs can produce different counts. For final fusion, use the
team's intended Phase II pair export.

To check the prepared baseline CSV itself without writing another file, run:

```bash
python correspondence_prep.py --project-root "$PROJECT_PATH" \
  --input "$PROJECT_PATH/output/correspondences.csv"
```

## Provenance

Source file, schema and lookup paths/hashes are in `frame.attrs`. Source weights
are **1.0 each**, an explicit equal-weight baseline rather than measured accuracy.
PyDI reads `trust_score`; the lecture-style `dataset_score` is also included.

Historical source snapshot dates are unavailable, so `dataset_date`,
`source_release_date` and `source_retrieved_at` are **None**. Record-level domain
dates remain separate. Evidence-referenced metadata overrides are supported.

All **944,262 field values and types** were checked against the original XMLs;
PyDI source-weight extraction and correspondence/grouping checks also passed.
The helpers preserve the supplied medicine data and apply no corrections.

## Use in the fusion notebook

Make this handoff directory available on the notebook's Python import path:

```python
from pathlib import Path
import pandas as pd
from loader import load_datasets
from PyDI.fusion import DataFusionEngine

repo = Path("/path/to/wdi-drug-integration")
datasets = load_datasets(project_root=repo)
pairs = pd.read_csv(
    repo / "output/correspondences.csv",
    dtype={"id1": "string", "id2": "string", "similarity": "float64"},
    keep_default_na=False,
)
```

Define `strategy` as a PyDI `DataFusionStrategy` with the desired attribute rules
in the fusion notebook, then run:

```python
fused = DataFusionEngine(strategy).run(
    list(datasets.values()), pairs,
    id_column="id", include_singletons=True,
)
```

PyDI builds transitive groups. With the tested baseline,
`include_singletons=True` also retains the **49,432 unmatched records** alongside
the **1,372 matched groups**. These counts change with the matching input.

Course references: [Data Fusion lecture, slides 9–15](https://www.uni-mannheim.de/media/Einrichtungen/dws/Files_Teaching/Web_Data_Integration/HWS2026/WDI06-DataFusion-HWS2026.pdf)
and `docs/slides/WDI-Exercise-Quality-Fusion-HWS2026.pdf`, pages 4–5, in the repository.
Fusion-rule experiments, evaluation and broader quality reporting belong to the
fusion workflow beyond these two loading/preparation helpers.
