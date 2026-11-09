# Golden standard sets validation

All unified and selected pairs were reviewed. Each dataset has zero duplicate rows,
conflicting pair labels, unlabeled rows, and invalid labels.

Percentages use unique pairs with a valid, non-conflicting `0` or `1` match label.
Pool percentages are shares of all pairs. Match and non-match percentages are
shares of reviewed pairs.

## DPD / EMA

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

## PyDI exports

Each dataset folder contains `gs_<dataset1>_<dataset2>_unified_pydi.csv`
for all unified pairs and `gs_<dataset1>_<dataset2>_select_pydi.csv`
for selected pairs. Both formats contain `id1,id2,label`, with `match`
exported as `label`.

The unified PyDI exports were checked row by row against their unified review
files, including record IDs, labels, row counts, and row order. The DPD / EMA
export contains 1,000 pairs; the DPD / FDA export contains 769 pairs; the EMA / FDA
export contains 1,729 pairs. The EMA / FDA selected PyDI export was also checked
row by row against its 500 selected review pairs.

Reproduce the statistics from the repository root:

```powershell
python src/golden_standard/gold_standard.py stats --input data/5_golden_standard_pair/dpd_ema/gs_dpd_ema_unified.csv
python src/golden_standard/gold_standard.py stats --input data/5_golden_standard_pair/dpd_ema/gs_dpd_ema_selected.csv
python src/golden_standard/gold_standard.py stats --input data/5_golden_standard_pair/dpd_fda/gs_dpd_fda_unified.csv
python src/golden_standard/gold_standard.py stats --input data/5_golden_standard_pair/dpd_fda/gs_dpd_fda_selected.csv
python src/golden_standard/gold_standard.py stats --input data/5_golden_standard_pair/ema_fda/gs_ema_fda_unified.csv
python src/golden_standard/gold_standard.py stats --input data/5_golden_standard_pair/ema_fda/gs_ema_fda_selected.csv
```
