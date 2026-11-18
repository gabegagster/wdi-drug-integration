# Tri-Dataset Clustering & Identity Resolution Baseline Report

## Overview
- **Script:** `src/identity_resolution/clustering.py`
- **Inputs:** `data/4_translated_mapforce/dpd_medicines.xml`, `ema_medicines.xml`, `fda_medicines.xml`
- **Total Correspondence Edges:** 1,938 (`DPD-EMA`: 594, `DPD-FDA`: 912, `EMA-FDA`: 432)
- **Total Entities Clustered:** 3,027
- **Total Clusters Formed:** 1,372
- **Cross-Dataset Overlapping Entities (>=2 sources):** 1,372
- **3-Way Overlapping Entities (DPD + EMA + FDA):** 283
- **Course Requirement (>= 1,000 Overlap):** **PASS (>= 1,000 requirement met)**

## Overlap Breakdown by Jurisdiction Combination
| Source Combination | Clusters | Share of Overlapping Entities |
| :--- | ---: | ---: |
| **All 3 Sources (DPD + EMA + FDA)** | 283 | 20.63% |
| **DPD + FDA (Canada & US only)** | 629 | 45.85% |
| **DPD + EMA (Canada & EU only)** | 311 | 22.67% |
| **EMA + FDA (EU & US only)** | 149 | 10.86% |
| **Total Overlapping Medicine Entities** | **1,372** | **100.00%** |

## Cluster Consistency & Multi-Mapping
- **Clusters with intra-source variations (1:N or N:M):** 0
- **Pure 1:1 / 1:1:1 Correspondences:** 100.00%

All clusters satisfy the duplicate-free constraint. Once the full-dataset correspondences from blocking and the best matcher are exported, `src/identity_resolution/clustering.py` can be re-run directly on those CSVs to generate the final Phase III entity clusters.
