# Golden standard sets validation

All unified and selected pairs were reviewed. Each dataset has zero duplicate rows,
conflicting pair labels, unlabeled rows, and invalid labels.

Percentages use unique pairs with a valid, non-conflicting `0` or `1` match label.
Pool percentages are shares of all pairs. Match and non-match percentages are
shares of reviewed pairs.

## DPD / EMA

Script: [gold_standard_pair_gen.py](../../src/golden_standard/gold_standard_pair_gen.py) (`stats`).
Inputs: `dpd_ema/gs_dpd_ema_unified.csv` and `dpd_ema/gs_dpd_ema_selected.csv`.
Output: console log with validation counts and pool/label percentages.

| Validation check | Unified | Selected |
| --- | ---: | ---: |
| Rows | 1,000 | 500 |
| Unique pairs | 1,000 | 500 |
| Reviewed pairs | 1,000 | 500 |
| Duplicate rows | 0 | 0 |
| Conflicting pair labels | 0 | 0 |
| Unlabeled rows | 0 | 0 |
| Invalid labels | 0 | 0 |

| Category | Unified pairs | Unified percentage | Selected pairs | Selected percentage |
| --- | ---: | ---: | ---: | ---: |
| Ordinary pool | 500 | 50.00% | 250 | 50.00% |
| Hard pool | 500 | 50.00% | 250 | 50.00% |
| Ordinary match | 198 | 19.80% | 100 | 20.00% |
| Ordinary non-match | 302 | 30.20% | 150 | 30.00% |
| Hard-pool match | 217 | 21.70% | 115 | 23.00% |
| Hard-pool non-match | 283 | 28.30% | 135 | 27.00% |

## DPD / FDA

Script: [gold_standard_pair_gen.py](../../src/golden_standard/gold_standard_pair_gen.py) (`stats`).
Inputs: `dpd_fda/gs_dpd_fda_unified.csv` and `dpd_fda/gs_dpd_fda_selected.csv`.
Output: console log with validation counts and pool/label percentages.

| Validation check | Unified | Selected |
| --- | ---: | ---: |
| Rows | 769 | 500 |
| Unique pairs | 769 | 500 |
| Reviewed pairs | 769 | 500 |
| Duplicate rows | 0 | 0 |
| Conflicting pair labels | 0 | 0 |
| Unlabeled rows | 0 | 0 |
| Invalid labels | 0 | 0 |

| Category | Unified pairs | Unified percentage | Selected pairs | Selected percentage |
| --- | ---: | ---: | ---: | ---: |
| Ordinary pool | 486 | 63.20% | 250 | 50.00% |
| Hard pool | 283 | 36.80% | 250 | 50.00% |
| Ordinary match | 122 | 15.86% | 100 | 20.00% |
| Ordinary non-match | 364 | 47.33% | 150 | 30.00% |
| Hard-pool match | 126 | 16.38% | 112 | 22.40% |
| Hard-pool non-match | 157 | 20.42% | 138 | 27.60% |

## EMA / FDA

Script: [gold_standard_pair_gen.py](../../src/golden_standard/gold_standard_pair_gen.py) (`stats`).
Inputs: `ema_fda/gs_ema_fda_unified.csv` and `ema_fda/gs_ema_fda_selected.csv`.
Output: console log with validation counts and pool/label percentages.

| Validation check | Unified | Selected |
| --- | ---: | ---: |
| Rows | 1,729 | 500 |
| Unique pairs | 1,729 | 500 |
| Reviewed pairs | 1,729 | 500 |
| Duplicate rows | 0 | 0 |
| Conflicting pair labels | 0 | 0 |
| Unlabeled rows | 0 | 0 |
| Invalid labels | 0 | 0 |

| Category | Unified pairs | Unified percentage | Selected pairs | Selected percentage |
| --- | ---: | ---: | ---: | ---: |
| Ordinary pool | 952 | 55.06% | 250 | 50.00% |
| Hard pool | 777 | 44.94% | 250 | 50.00% |
| Ordinary match | 282 | 16.31% | 100 | 20.00% |
| Ordinary non-match | 670 | 38.75% | 150 | 30.00% |
| Hard-pool match | 292 | 16.89% | 81 | 16.20% |
| Hard-pool non-match | 485 | 28.05% | 169 | 33.80% |

## Combined dataset and train/test split

Script: [gold_standard_combine_split.py](../../src/golden_standard/gold_standard_combine_split.py).
Inputs: `dpd_ema/gs_dpd_ema_unified.csv`, `dpd_fda/gs_dpd_fda_unified.csv`,
and `ema_fda/gs_ema_fda_unified.csv`.
Outputs: console log with split counts and the three CSVs listed below.

The three unified review sets are combined into **3,498 unique labeled pairs**.
The saved split uses an 85% train/validation and 15% test target, seed `42`,
and stratification by `source_pair`, `hard`, and `match`. Integer rounding gives
2,973 train/validation pairs (84.99%) and 525 test pairs (15.01%).

Files are in `golden_standard_pair_complete/`:

| File | Pairs | Share of combined set |
| --- | ---: | ---: |
| `gs_pair_whole.csv` | 3,498 | 100.00% |
| `gs_pair_train_val.csv` | 2,973 | 84.99% |
| `gs_pair_test.csv` | 525 | 15.01% |

### Counts by source pair

| Source pair | Whole | Train/validation | Test |
| --- | ---: | ---: | ---: |
| DPD / EMA | 1,000 | 850 | 150 |
| DPD / FDA | 769 | 653 | 116 |
| EMA / FDA | 1,729 | 1,470 | 259 |
| **Total** | **3,498** | **2,973** | **525** |

### Counts by pool and label

`hard=0` identifies ordinary pairs; `hard=1` identifies hard-pool pairs.
`match=1` means a match and `match=0` means a non-match.

| Source pair | Pool | Label | Whole | Train/validation | Test |
| --- | --- | --- | ---: | ---: | ---: |
| DPD / EMA | Ordinary | Match | 198 | 168 | 30 |
| DPD / EMA | Ordinary | Non-match | 302 | 257 | 45 |
| DPD / EMA | Hard | Match | 217 | 184 | 33 |
| DPD / EMA | Hard | Non-match | 283 | 241 | 42 |
| DPD / FDA | Ordinary | Match | 122 | 104 | 18 |
| DPD / FDA | Ordinary | Non-match | 364 | 309 | 55 |
| DPD / FDA | Hard | Match | 126 | 107 | 19 |
| DPD / FDA | Hard | Non-match | 157 | 133 | 24 |
| EMA / FDA | Ordinary | Match | 282 | 240 | 42 |
| EMA / FDA | Ordinary | Non-match | 670 | 570 | 100 |
| EMA / FDA | Hard | Match | 292 | 248 | 44 |
| EMA / FDA | Hard | Non-match | 485 | 412 | 73 |
| **Total** | | | **3,498** | **2,973** | **525** |

| Combined category | Whole | Train/validation | Test |
| --- | ---: | ---: | ---: |
| Ordinary pool | 1,938 | 1,648 | 290 |
| Hard pool | 1,560 | 1,325 | 235 |
| Matches | 1,237 | 1,051 | 186 |
| Non-matches | 2,261 | 1,922 | 339 |

Counts were checked directly against the three saved CSVs. Each file has
unique pair IDs and binary match labels. Train/validation and test have zero
shared pair IDs, and their union equals the whole set. The split operates on
pairs; individual medicine IDs can occur in both partitions. Train/validation
is a shared development set, and test is held out for final evaluation.

## PyDI exports

Script: [gold_standard_pair_gen.py](../../src/golden_standard/gold_standard_pair_gen.py).
Inputs: labeled review CSVs for each source pair.
Outputs in each source-pair folder:

| File | Pairs |
| --- | --- |
| `gs_<dataset1>_<dataset2>_unified_pydi.csv` | All unified pairs |
| `gs_<dataset1>_<dataset2>_select_pydi.csv` | 500 selected pairs |

Both exports contain `id1,id2,label`, with the reviewed `match` value stored as `label`.
