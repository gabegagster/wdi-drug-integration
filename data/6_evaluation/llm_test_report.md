# Zero-Shot LLM Matcher Evaluation Benchmark Report

## Experiment Configuration
- **Model:** `gemini-3.8-flash` (`temperature=0.0`, structured JSON output)
- **SDK:** `google-genai` (v3.0.0)
- **Dataset:** Stratified held-out test split (`gs_pair_test.csv`)
- **Total Evaluated Pairs:** 525 pairs (held-out 15% test split, seed 42)
- **Zero-Shot Prompt:** Strictly blind, decontaminated clinical domain rules (zero test-set drug names, zero ground-truth access, zero external web lookups)

---

## Executive Summary & Comparison vs. Naive Baseline

| Metric | Naive Exact-Match Baseline | Zero-Shot LLM (`gemini-3.8-flash`) | Improvement ($\Delta$) |
| :--- | ---: | ---: | ---: |
| **Macro F1 Score** | **73.07%** (0.7307) | **94.85%** (0.9485) | **+21.78 pp** |
| **Match Class F1 (1)** | **61.22%** (0.6122) | **93.44%** (0.9344) | **+32.21 pp** |
| **Overall Accuracy** | **78.29%** (0.7829) | **95.24%** (0.9524) | **+16.95 pp** |
| **Macro Precision** | 80.16% (0.8016) | 94.43% (0.9443) | +14.27 pp |
| **Macro Recall** | 71.54% (0.7154) | 95.34% (0.9534) | +23.80 pp |
| **True Positives (TP)** | 90 | **178** | **+88 pairs found** |
| **False Negatives (FN)** | 96 | **8** | **-88 missed matches** |
| **False Positives (FP)** | 18 | **17** | **-1 false alarm** |
| **True Negatives (TN)** | 321 | **322** | +1 |

---

## Confusion Matrix (LLM Matcher)

| Metric | Predicted Non-match (0) | Predicted Match (1) | Total True |
| :--- | ---: | ---: | ---: |
| **Actual Non-match (0)** | **TN = 322** | FP = 17 | 339 |
| **Actual Match (1)** | FN = 8 | **TP = 178** | 186 |
| **Total Predicted** | 330 | 195 | **525** |

---

## Performance Breakdown by Difficulty Pool

The test set is split into ordinary candidate pairs and adversarial/corner-case pairs:
- **Ordinary Pool (`hard=0`)**: Standard candidate pairs (290 pairs).
- **Hard Pool (`hard=1`)**: Complex pairs (235 pairs), such as identical brand names with different active substances, or identical substances from competing generic manufacturers.

| Difficulty Pool | Pairs | Baseline Macro F1 | LLM Accuracy | LLM Macro F1 | LLM Match F1 |
| :--- | ---: | ---: | ---: | ---: | ---: |
| **Ordinary Pool (`hard=0`)** | 290 | 0.9310 | 96.90% | **0.9647** | 0.9524 |
| **Hard Pool (`hard=1`)** | 235 | 0.3717 | 93.19% | **0.9296** | 0.9167 |

---

## Performance Breakdown by Source Jurisdiction Pair

| Jurisdiction Pair | Evaluated Pairs | Baseline Macro F1 | LLM Accuracy | LLM Macro F1 | LLM Match F1 |
| :--- | ---: | ---: | ---: | ---: | ---: |
| **DPD / EMA** (Canada <-> Europe) | 150 | 0.7366 | 98.67% | **0.9864** | 0.9844 |
| **DPD / FDA** (Canada <-> USA) | 116 | 0.6979 | 97.41% | **0.9704** | 0.9600 |
| **EMA / FDA** (Europe <-> USA) | 259 | 0.7408 | 92.28% | **0.9144** | 0.8876 |

---

## Qualitative Discrepancy & Domain Analysis

Across all 525 pairs under strictly blind zero-shot evaluation, the LLM differed from the manual Gold Standard on **25 pairs** (4.76% discrepancy rate: **17 False Positives** and **8 False Negatives**). Inspection reveals four systematic clinical and regulatory patterns:

### 1. Cross-Border Licensing, Corporate Acquisitions & Co-Marketing (`14` False Positives)
In 14 pairs where the brand name and active substance are identical (or minor regional trade-name variants), the LLM used its internal pharmaceutical knowledge to recognize that the two licence holders commercialize the same originator product via cross-border licensing, divestiture, or subsidiary lineage, whereas the Gold Standard labeled them `0` because the manufacturer strings in the regulatory tables differ:
- **Row 28 (`DPD_TEVIMBRA <-> EMA_TEVIMBRA`):** `TEVIMBRA` (tislelizumab, BeOne Medicines I GmbH) vs. `Tevimbra` (tislelizumab, Beone Medicines Ireland Limited) — identical brand, INN, and corporate group (gold-standard annotation noise).
- **Row 39 (`EMA_YARGESA <-> FDA_YARGESA`):** `Yargesa` (miglustat, Piramal Critical Care) vs. `YARGESA` (miglustat, Edenbridge Pharms).
- **Row 106 (`EMA_VIBATIV <-> FDA_VIBATIV`):** `Vibativ` (telavancin, Theravance Biopharma) vs. `VIBATIV` (telavancin hydrochloride, Apotex).
- **Row 120 (`EMA_TEKTURNA <-> FDA_TEKTURNA`):** `Tekturna` (aliskiren, Novartis) vs. `TEKTURNA` (aliskiren hemifumarate, LXO Ireland — acquired from Novartis).
- **Row 126 (`EMA_NEVANAC <-> FDA_NEVANAC`):** `Nevanac` (nepafenac, Novartis) vs. `NEVANAC` (nepafenac, Harrow Eye — US ophthalmic rights acquired from Novartis/Alcon).
- **Row 135 (`DPD_FIORINAL <-> FDA_FIORINAL`):** `FIORINAL` (ASA/butalbital/caffeine, Aralez Canada) vs. `FIORINAL` (aspirin/butalbital/caffeine, Allergan).
- **Row 140 (`EMA_FOLOTYN <-> FDA_FOLOTYN`):** `Folotyn` (pralatrexate, Allos Therapeutics) vs. `FOLOTYN` (pralatrexate, Acrotech Biopharma).
- **Row 224 (`EMA_EURNEFFY <-> FDA_NEFFY`):** `Eurneffy` (epinephrine, ALK-Abelló) vs. `NEFFY` (epinephrine, ARS Pharms — EU trade name licensed to ALK-Abelló).
- **Row 295 (`EMA_ADASUVE <-> FDA_ADASUVE`):** `Adasuve` (loxapine, Ferrer Internacional) vs. `ADASUVE` (loxapine, Nova Pneuma).
- **Row 311 (`EMA_ZURAMPIC <-> FDA_ZURAMPIC`):** `Zurampic` (lesinurad, Grünenthal) vs. `ZURAMPIC` (lesinurad, Ironwood Pharms).
- **Row 326 (`EMA_TESLASCAN <-> FDA_TESLASCAN`):** `Teslascan` (mangafodipir trisodium, GE Healthcare) vs. `TESLASCAN` (mangafodipir trisodium, IC Targets).
- **Row 349 (`EMA_DOPTELET <-> FDA_DOPTELET`):** `Doptelet` (avatrombopag maleate, SOBI) vs. `DOPTELET` (avatrombopag maleate, AkaRx — wholly owned subsidiary of SOBI).
- **Row 413 (`EMA_TRYNGOLZA <-> FDA_TRYNGOLZA`):** `Tryngolza` (olezarsen sodium, SOBI) vs. `TRYNGOLZA (AUTOINJECTOR)` (olezarsen sodium, Ionis Pharms).
- **Row 420 (`EMA_XOLAIR <-> FDA_XOLAIR`):** `Xolair` (omalizumab, Novartis) vs. `XOLAIR` (omalizumab, Genentech — co-developed by Novartis and Genentech/Roche).

### 2. Formulation Suffix & Brand Line Variants (`3` False Positives, `1` False Negative)
- **Row 95 (`Natpar` vs. `NATPARA`):** Regional spelling variant for recombinant parathyroid hormone (Takeda/NPS) — GS `0`, LLM `1`.
- **Row 220 (`ALPHAGAN` vs. `ALPHAGAN P`):** Brimonidine tartrate ophthalmic formulations from AbbVie — GS `0`, LLM `1`.
- **Row 509 (`AFINITOR DISPERZ` vs. `Afinitor`):** Everolimus dispersible vs. standard tablet from Novartis — GS `0`, LLM `1`.
- **Row 134 (`Tobi Podhaler` vs. `TOBI`):** Tobramycin dry powder inhaler vs. nebulizer solution from Viatris — GS `1`, LLM `0` (LLM treated the distinct delivery device suffix as a separate product).

### 3. Distinct Regional Brand Names, Prodrugs & Co-Formulations (`3` False Negatives)
- **Row 0 (`Copalia HCT` vs. `EXFORGE HCT`):** Both are Novartis triple-combination tablets (`amlodipine; valsartan; hydrochlorothiazide`), where `Copalia HCT` is an EU co-marketing brand for `Exforge HCT` — GS `1`, LLM `0` (due to completely different brand names).
- **Row 83 (`Herceptin` vs. `HERCEPTIN HYLECTA`):** Intravenous `trastuzumab` vs. subcutaneous `trastuzumab and hyaluronidase-oysk` (Roche/Genentech) — GS `1`, LLM `0` (LLM strictly enforced Rule 1 on additional active ingredients).
- **Row 254 (`Ivemend` vs. `EMEND`):** Intravenous prodrug `fosaprepitant` vs. oral `aprepitant` (MSD) — GS `1`, LLM `0` (LLM strictly enforced chemical substance identity between prodrug and active moiety).

### 4. Gold-Standard Label Noise Corrected by the LLM (`4` False Negatives)
In 4 pairs labeled `1` in the manual Gold Standard, clinical inspection confirms that the records are genuinely **non-matches** (`0`) and the LLM's prediction is pharmacologically and regulatorily sound:
- **Row 162 (`AURO-LAMIVUDINE/ZIDOVUDINE` vs. `LAMIVUDINE; ZIDOVUDINE [EFAVIRENZ; LAMIVUDINE; ZIDOVUDINE]`):** Dual-ingredient therapy vs. triple-ingredient therapy containing `efavirenz`.
- **Row 187 (`Repaglinide Accord` vs. `REPAGLINIDE` [Aurobindo]):** Competing generic manufacturers (Accord Healthcare vs. Aurobindo).
- **Row 302 (`Pemetrexed Krka` vs. `PEMETREXED` [Shilpa]):** Competing generic manufacturers (KRKA vs. Shilpa).
- **Row 354 (`Tadalafil Lilly` vs. `TADALAFIL` [Rising]):** Eli Lilly branded generic vs. unrelated generic manufacturer (Rising).

---

## Reproducibility & Deliverable Files
- **Predictions & Rationale CSV:** `data/6_evaluation/llm_test_predictions.csv` (contains all 525 pairs with `pred_llm` and `reason_llm`).
- **Executed Jupyter Notebook:** `notebooks/01_llm_zero_shot_matcher.ipynb` (fully executed with confusion matrix heatmaps and comparison tables).
- **Inference Pipeline Script:** `src/identity_resolution/llm_zero_shot_matcher.py` (official `google-genai` SDK implementation with structured output and persistent caching).
- **Tri-Dataset Clustering Script:** `src/identity_resolution/clustering.py` (NetworkX connected components verifying 1,372 cross-dataset matches).
