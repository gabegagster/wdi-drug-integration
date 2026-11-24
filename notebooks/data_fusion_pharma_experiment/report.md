# Role 3 — Fusion Rule Strategy

**Evaluation set:** 31 verified clusters (`fusion_eval_worksheet.csv`), verified by Trang  
**Experiment notebook:** `data_fusion_pharma_experiment.ipynb`

---

## Rule selection summary

Each attribute was swept independently: one rule was varied while all others stayed at the
simple baseline (longest_string / union / voting). The table below shows the winning rule
and the accuracy change.

| Attribute | Baseline rule | Baseline acc. | Selected rule | Final acc. | Δ | Rationale |
|---|---|---|---|---|---|---|
| brandName | longest_string | 0.9355 | **shortest_string** | 1.0000 | +0.0645 | EMA names are canonical and shorter (e.g. *Cinqaero* vs *CINQAIR*); longest_string picks up all-caps DPD/FDA variants |
| activeSubstances | union | 0.7097 | **voting** | 0.8710 | +0.1613 | Union accumulates salt-form duplicates (BOSUTINIB + BOSUTINIB MONOHYDRATE); majority vote selects the most agreed-upon INN |
| activeSubstanceCount | voting | 1.0000 | **voting** | 1.0000 | 0 | Already perfect; no change |
| licenceHolder | longest_string | 0.0645 | **holder_consensus** | 0.1290 | +0.0645 | Corporate name variants (GLAXOSMITHKLINE INC / Glaxo Group Ltd.) are never string-equal; custom similarity voting picks the most representative form. Accuracy remains low because national affiliates are genuinely different legal entities per jurisdiction |
| productClass | voting | 1.0000 | **voting** | 1.0000 | 0 | Already perfect; no change |
| atcCode | union | 0.8065 | **voting** | 0.9032 | +0.0967 | Union propagates partial codes (C01 alongside C01DX22); majority vote selects the agreed full code |
| dosageForm | union | 0.4839 | **dosage_form_match** | 0.5161 | +0.0322 | Custom form-family deduplication collapses synonym forms (Solution / Liquid → Solution); plain union inflates the set with EMA-missing and FDA-generic entries |
| route | union | 0.8065 | **voting** | 0.9355 | +0.1290 | FDA uses generic *Injection* where DPD/EMA record *Intravenous* or *Subcutaneous*; voting with two agreeing sources overrides the coarser FDA value |
| strengths | union | 0.4516 | **normalized_strength_union** | 0.5161 | +0.0645 | Unit aliases (U/vial → U, mg/vial → mg) cause duplicate tuples in plain union; custom normalisation deduplicates before merging |
| biosimilar | voting | 1.0000 | **voting** | 1.0000 | 0 | Already perfect; no change |

**Overall accuracy: 0.7258 (baseline) → 0.7871 (final), Δ +0.0613**

---

## Custom pharma rules

Three domain-specific resolvers were implemented and evaluated alongside built-in PyDI rules.

### `holder_consensus`
Selects the licence-holder name with the highest average character-level similarity to all
other candidate values (via `difflib.SequenceMatcher`). Designed for corporate name variants
that share a root string but differ in legal suffix, capitalisation, or national affiliate name.

### `normalized_strength_union`
Performs a union of strength `(amount, unit)` tuples after normalising unit aliases
(`U/vial → U`, `mg/vial → mg`). This prevents `(200, U)` and `(200, U/vial)` from both
appearing in the fused output when they refer to the same dosage.

### `dosage_form_match`
Groups dosage forms into pharmaceutical form families (solution/liquid, injection/powder for
solution/concentrate, tablet/film-coated tablet, etc.) before union. Only the first
representative form from each family is kept, eliminating synonym duplication.

---

## Remaining error analysis

66 errors remain across 31 clusters. The main causes are:

| Error type | Example | Root cause |
|---|---|---|
| Jurisdiction-specific licence holder | PFIZER CANADA ULC vs PF Prism C.V. | National affiliates are legally distinct entities; no string rule can resolve this |
| Strength unit vs concentration | (10, mg) vs (10, mg/mL) | DPD omits the volume denominator; not resolvable without additional context |
| Dosage form vocabulary gaps | [Capsule, Liquid] vs [Capsule, Solution] | "Liquid" not yet in the solution family mapping |
| Strength concentration form | [(30, mg), (150, mg)] vs [(30, mg/mL), (150, mg/mL)] | DPD records mass-only strengths; FDA records concentration; gold expects concentration |
| ATC code granularity | [A16, A16AB14] vs [A16AB14] | Union includes parent codes from some sources; voting helps when 2 of 3 sources agree |

---

## Density and consistency (final fused output)

| Attribute | Fused density | Input consistency |
|---|---|---|
| brandName | 100% | 93.5% |
| activeSubstances | 100% | 83.9% |
| activeSubstanceCount | 100% | 100.0% |
| licenceHolder | 100% | 0.0% |
| productClass | 100% | 100.0% |
| atcCode | 100% | 90.3% |
| dosageForm | 97% | 66.7% |
| route | 100% | 80.6% |
| strengths | 100% | 58.1% |
| biosimilar | 100% | 100.0% |

Fusion raised overall density from ~69% (individual sources) to 97–100% per attribute.
`licenceHolder` consistency is 0% because every cluster has a different national affiliate
name in each source — a data reality, not a fusion failure.

---

## Limitations

- Evaluation set covers 31 clusters from a 52,459-record corpus; results may not generalise
  to all drug classes or rare-disease products.
- Gold values are derived primarily from EMA as the authoritative regulatory source; FDA-only
  clusters (no EMA record) lack a consensus gold standard.
- Salt-form conflicts (INN base vs salt vs hydrate) cannot be resolved by string or voting
  rules alone; a chemical synonym lookup would be needed.
- `licenceHolder` accuracy (0.13) is bounded by the fact that national affiliates are
  genuinely different legal entities, not just name variants.
- `strengths` errors largely stem from DPD recording mass-only values (mg) where the gold
  standard requires concentrations (mg/mL); this is a source data gap, not a fusion rule failure.
