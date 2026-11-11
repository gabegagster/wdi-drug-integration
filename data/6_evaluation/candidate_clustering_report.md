# Tri-Dataset Clustering & Identity Resolution (Candidate Pool Correspondences)

## Overview
- **Script:** `src/identity_resolution/clustering.py`
- **Inputs:** `data/3_fused/candidate_matches.csv` (derived from `data/7_blocking_candidates/` via `src/identity_resolution/llm_zero_shot_matcher.py --match-candidates`)
- **Total Blocker Candidates Evaluated:** 206,830
- **Deterministic Exact Pre-Filter Matches:** 1,938
- **Cross-Border Salt Variations (same brand):** 754
- **High-Confidence Fuzzy Matches:** 2,016
- **Total Positive Candidate Matches:** 4,708
- **Pruned Disjoint Substance Non-Matches:** 156,958
- **Deterministic Greedy 1:1 Correspondences:** 3,336 (resolved 1,372 intra-source candidate conflicts)
- **Total Entities Clustered:** 5,194
- **Total Multi-Source Clusters Formed:** 2,343
- **Cross-Dataset Overlapping Entities (>=2 sources):** 2,343
- **3-Way Overlapping Entities (DPD + EMA + FDA):** 502
- **Course Requirement (>= 1,000 Overlap):** **PASS (>= 1,000 requirement met)**

## Overlap Breakdown by Jurisdiction Combination
| Source Combination | Clusters | Share of Overlapping Entities |
| :--- | ---: | ---: |
| **All 3 Sources (DPD + EMA + FDA)** | 502 | 21.43% |
| **DPD + FDA (Canada & US only)** | 1,388 | 59.24% |
| **DPD + EMA (Canada & EU only)** | 314 | 13.40% |
| **EMA + FDA (EU & US only)** | 139 | 5.93% |
| **Total Overlapping Medicine Entities** | **2,343** | **100.0%** |

## Cluster Consistency & Multi-Mapping
- **Deterministic Greedy 1:1 Enforcement:** Applied per source pair before graph clustering (`sort_values(by=[score_col, "id1", "id2"], ascending=[False, True, True])`).
- **Clusters with intra-source variations (1:N or N:M):** 5 (99.79% pure 1:1:1 clusters).
- **Gain over Exact Baseline:** +971 cross-dataset clusters (+70.8%) and +219 three-way international clusters (+77.4%).
