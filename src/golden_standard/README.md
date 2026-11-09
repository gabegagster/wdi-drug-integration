# Gold-standard pairs

The script creates medicine pairs from the three XML files in
`data/4_translated_mapforce`, prepares them for manual labeling, and selects
a gold-standard set from the reviewed labels. Outputs go to
`data/5_golden_standard_pair`.

## gold_standard_pair_gen.py

### Quick start

Run from the repository root with the project environment activated.
You can replace `python` with `.venv\Scripts\python.exe`.

- **Generate pairs for review:**

  ```powershell
  python src/golden_standard/gold_standard_pair_gen.py get-pairs --dataset1 dpd --dataset2 ema --n 500 --seed 42
  ```

  Open `data/5_golden_standard_pair/gs_dpd_ema_raw.csv`. Fill `match` with `1`
  for the same medicine or `0` for different medicines. Finish labeling before
  merging and preserve the other columns.

- **Add another batch:**

  ```powershell
  python src/golden_standard/gold_standard_pair_gen.py get-pairs --dataset1 dpd --dataset2 ema --n 500 --seed 99 --exclude data/5_golden_standard_pair/gs_dpd_ema_raw.csv --output-dir data/5_golden_standard_pair/round2
  ```

  Supply all earlier review files through `--exclude` and choose a new seed
  and output folder to create another batch of unique pairs.

- **Merge labeled batches:**

  ```powershell
  python src/golden_standard/gold_standard_pair_gen.py merge --inputs data/5_golden_standard_pair/gs_dpd_ema_raw.csv data/5_golden_standard_pair/round2/gs_dpd_ema_raw.csv
  ```

- **Check counts and percentages:**

  ```powershell
  python src/golden_standard/gold_standard_pair_gen.py stats --input data/5_golden_standard_pair/gs_dpd_ema_unified.csv
  ```

- **Select the final labeled pairs:**

  ```powershell
  python src/golden_standard/gold_standard_pair_gen.py select --input data/5_golden_standard_pair/gs_dpd_ema_unified.csv --size 500 --seed 42
  ```

Dataset names are `dpd`, `ema`, and `fda`. File names use the order DPD, EMA,
FDA, so either input order for EMA and FDA produces `gs_ema_fda_raw.csv`.
Existing files are protected from overwriting; use `--output-dir` for another
export. Each command has `--help`.

### Sampling strategy

Each call samples pairs from two datasets using fixed proportions:

| Pool | Share | Count for n=500 | hard |
| --- | ---: | ---: | ---: |
| Suspected hard pairs from S1-S4 | 50% | 250 | 1 |
| Likely ordinary matches | 20% | 100 | 0 |
| Random pairs | 30% | 150 | 0 |

- Select hard pairs first, removing duplicates across strategies.
- Sample likely ordinary matches with the same normalized brand and full
  ingredient set from pairs still available after the hard-pair selection.
- Sample random pairs from the remaining combinations after removing selected
  pairs and earlier batches supplied through `--exclude`.
- Shuffle the rows and leave `match` blank for manual labeling.
- For other sizes, use `n // 2` hard pairs, `n // 5` likely ordinary matches,
  and fill the remaining places with random pairs.
- Keep the existing record IDs. A readable pair ID joins them in the fixed
  dataset order: `DPD_... <-> EMA_...`.

#### Hard-pair strategies

Medicine identity can be ambiguous because name variations and overlapping
ingredient lists produce similar-looking records. These strategies collect
pairs with that ambiguity so reviewers can assess the brand names and full
ingredient sets together.

| Strategy | Candidate conditions | Rank, highest first |
| --- | --- | --- |
| S1 | Same brand; different full ingredient sets | Ingredient-set Jaccard |
| S2 | Different brands sharing a whole word; same ingredient set | Brand-word Jaccard |
| S3 | Different brands sharing a whole word; overlapping, different ingredient sets | Brand-word Jaccard, then ingredient-set Jaccard |
| S4 | Different brands sharing character trigrams | Brand-name TF-IDF cosine |

**Normalization:** standardize case, accents, punctuation, and whitespace,
and compare ingredients as sets to handle reordered lists and repeated entries.
The resulting values preserve substance names, salt terms, brand extensions,
and numbers for review.

- Split the hard-pair quota equally across S1-S4. For 250 pairs, the targets
  are 63, 63, 62, and 62.
- Keep the highest-ranked unique pairs from each strategy, using the seed to
  break equal-score ties.
- Fill duplicate selections with the next candidates and redistribute empty
  places across the available strategies when a strategy runs short.
- Stop with an error if the available hard or likely-match candidates cannot
  fill the requested batch.

#### Similarity examples

These examples use fictional names and ingredients X, Y, and Z. Jaccard is
the number of shared items divided by the number of distinct items combined.

| Strategy | Records | Intermediate comparison | Score |
| --- | --- | --- | --- |
| S1 | `Nova: [X, Y]` and `Nova: [X, Z]` | Shared ingredients `{X}`; combined `{X, Y, Z}` | Ingredient Jaccard = `1/3` |
| S2 | `Nova Plus: [X]` and `Nova Forte: [X]` | Same ingredients; brand words `{nova, plus}` and `{nova, forte}` | Brand Jaccard = `1/3` |
| S3 | `Nova Plus: [X, Y]` and `Nova: [X]` | Brand words share `nova`; ingredients share `X` | Brand Jaccard = `1/2`; ingredient Jaccard = `1/2` |

S4 splits brand names into overlapping three-character pieces:

```text
MILLER -> mil, ill, lle, ler
MILER  -> mil, ile, ler
```

- Fit TF-IDF to the brand names from both datasets, weighting each fragment
  by its frequency within a name and its rarity across the combined names.
- For illustration, suppose shared fragments have weight 1 and the other
  fragments have weight 1.4. In the order `[mil, ler, ill, lle, ile]`:

  ```text
  MILLER -> A = [1, 1, 1.4, 1.4, 0]
  MILER  -> B = [1, 1, 0,   0,   1.4]

  cosine = (A dot B) / (length(A) * length(B))
         = 2 / (sqrt(5.92) * sqrt(3.96))
         ≈ 0.41
  ```

- Calculate the actual weights from all brand names in the two XML files,
  normalize vectors to unit length, and calculate cosine scores in sparse
  batches. Ingredient sets provide additional information during manual review.

### Review columns

| Columns | Meaning |
| --- | --- |
| `pair_id` | Readable combination of the two record IDs |
| `*_<dataset1>`, such as `brandName_dpd` | Original attributes of the first dataset |
| `*_<dataset2>`, such as `brandName_ema` | Original attributes of the second dataset |
| `hard` | Automatic pool flag: 1 = S1-S4, 0 = ordinary pool |
| `match` | Manual label: 1 = same medicine, 0 = different medicines |

The script assigns the hard flag during sampling and uses similarity scores
to rank candidates, then reviewers fill the match label for every exported pair.

Each attribute's two columns sit next to each other in raw, unified, and selected
review files. For DPD and EMA, the order begins:

```text
pair_id, id_dpd, id_ema, source_dpd, source_ema,
brandName_dpd, brandName_ema, activeSubstances_dpd, activeSubstances_ema, ...,
hard, match
```

### Merging and checking

- Merge one dataset combination at a time.
- Every input row needs a match label of `0` or `1`. Duplicate pairs must
  have the same label.
- Missing, invalid, or conflicting labels stop merging with an error listing
  the affected pair IDs so reviewers can correct the source files and retry.
- A successful merge writes `gs_<dataset1>_<dataset2>_unified.csv` and keeps
  each pair once. A pair selected through both pools retains `hard=1`.
- Add `--export-pydi` to also write `gs_<dataset1>_<dataset2>_unified_pydi.csv`
  with every merged pair as `id1,id2,label`. This export applies no selection.
- Review files use dataset suffixes for attributes and IDs. Pair IDs are
  rebuilt from the record IDs when imported. Earlier files with numeric suffixes
  can also be read.

Example error:

```text
Merging cannot be completed because of these label errors:
Missing match label: DPD_A <-> EMA_B
Different match labels (0 and 1): DPD_C <-> EMA_D
Correct the listed pairs in the input files and merge again.
```

`stats` shows pool sizes, match/non-match counts, missing or invalid labels,
duplicates, and conflicting labels. Pool percentages use all unique pairs.
Label percentages use unique pairs with valid, consistent labels.

### Final selection

`select --size N` samples from the manually labeled collection:

| Category | Share |
| --- | ---: |
| Ordinary matches: hard=0, match=1 | 20% |
| Hard-pool pairs: hard=1, either match label | 50% |
| Ordinary non-matches: hard=0, match=0 | 30% |

- Use `N // 5`, `N // 2`, and the remainder for the three counts.
- Sample hard matches and hard non-matches together.
- Resolve duplicate pairs and invalid labels, then select from pairs with
  completed binary labels.
- Report the missing count for any category that needs more labeled candidates
  to reach the requested size.

Outputs:

- `gs_<dataset1>_<dataset2>_selected.csv`: selected review rows.
- `gs_<dataset1>_<dataset2>_select_pydi.csv`: `id1,id2,label` for PyDI, with the manual
  match labels exported as `label`.


## gold_standard_combine_split.py

Combine the fully labeled unified review sets and save one shared train/validation
and test split. Use the unified review CSVs containing `hard` and `match`.

### Quick start

Run from the repository root:

```powershell
python src/golden_standard/gold_standard_combine_split.py --inputs data/5_golden_standard_pair/dpd_ema/gs_dpd_ema_unified.csv data/5_golden_standard_pair/dpd_fda/gs_dpd_fda_unified.csv data/5_golden_standard_pair/ema_fda/gs_ema_fda_unified.csv
```

The default ratios are 0.85 for train/validation and 0.15 for test, with seed 42.
To change them, supply both ratios so they sum to 1:

```powershell
python src/golden_standard/gold_standard_combine_split.py --inputs data/5_golden_standard_pair/dpd_ema/gs_dpd_ema_unified.csv data/5_golden_standard_pair/dpd_fda/gs_dpd_fda_unified.csv data/5_golden_standard_pair/ema_fda/gs_ema_fda_unified.csv --train-ratio 0.80 --test-ratio 0.20 --seed 42
```

### Outputs

The default output directory is
`data/5_golden_standard_pair/golden_standard_pair_complete/`.
Use `--output-dir` to choose another destination. Existing files are protected
from overwriting.

| File | Contents |
| --- | --- |
| `gs_pair_whole.csv` | All input pairs, with a `source_pair` column |
| `gs_pair_train_val.csv` | Development pairs for training and choosing rules or thresholds |
| `gs_pair_test.csv` | Held-out pairs for the team's final evaluation |

Source pairs are `dpd_ema`, `dpd_fda`, and `ema_fda`. Review attributes use the
shared numeric suffixes (`id1`, `id2`, `brandName1`, `brandName2`, etc.) so all
source combinations use the same columns. Manual labels remain in `match`.

### Split rules

- Stratify by the combination of `source_pair`, `hard`, and `match`, preserving
  the input proportions as closely as integer counts allow.
- Sort pairs before splitting and use a fixed seed for repeatability with the
  same inputs and software environment.
- Split individual pairs. The partitions have no shared pairs; medicine IDs
  can occur in both partitions. This evaluates held-out pairs with potentially
  familiar medicines.
- Reject duplicate pairs, incomplete labels, invalid ratios, and strata with
  fewer than two pairs. Very small requested partitions can also prevent stratification.
- Everyone should use the same saved split files. Keep test pairs untouched
  while developing blockers and matchers.

For the current 3,498 unified pairs, the default split creates 2,973 train/validation
pairs and 525 test pairs. Selecting from those unified sets beforehand would
change the input distribution.

The Python entry point is
`combine_split(inputs, output_dir=COMPLETE_DIR, train_ratio=0.85, test_ratio=0.15, seed=42)`.
It saves the three CSVs and returns `(whole, train_val, test)` as DataFrames.
