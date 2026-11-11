# Tri-Dataset Clustering & Identity Resolution (Candidate Pool Correspondences)

## Overview
- **Script:** `src/identity_resolution/clustering.py`
- **Inputs:** `data/3_fused/candidate_matches.csv` (derived from `data/7_blocking_candidates/` via `src/identity_resolution/llm_zero_shot_matcher.py --match-candidates`)
- **Total Blocker Candidates Evaluated:** 206,830
- **Deterministic Exact Pre-Filter Matches:** 1,938
- **Pruned Disjoint Substance Non-Matches:** 179,578
- **High-Confidence Candidate Matches:** 3,353
- **Greedy 1:1 Correspondences:** 2,354
- **Total Entities Clustered:** 3,698
- **Total Clusters Formed:** 1,676
- **Cross-Dataset Overlapping Entities (>=2 sources):** 1,676
- **3-Way Overlapping Entities (DPD + EMA + FDA):** 342
- **Course Requirement (>= 1,000 Overlap):** **PASS (>= 1,000 requirement met)**

## Overlap Breakdown by Jurisdiction Combination
| Source Combination | Clusters | Share of Overlapping Entities |
| :--- | ---: | ---: |
| **All 3 Sources (DPD + EMA + FDA)** | 342 | 20.41% |
| **DPD + FDA (Canada & US only)** | 830 | 49.52% |
| **DPD + EMA (Canada & EU only)** | 329 | 19.63% |
| **EMA + FDA (EU & US only)** | 175 | 10.44% |
| **Total Overlapping Medicine Entities** | **1,676** | **100.0%** |

## Cluster Consistency & Multi-Mapping
- **Greedy 1:1 Enforcement:** Applied per source pair before graph clustering.
- **Clusters with intra-source variations (1:N or N:M):** 3 (99.82% pure 1:1:1 clusters).
- **Gain over Exact Baseline:** +304 cross-dataset clusters (+22.2%) and +59 three-way international clusters (+20.8%).
