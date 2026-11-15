# Data fusion evaluation set (Role 2)

Evaluation set for Phase III: 36 multi-source medicines with hand-verified true
values for 10 attributes each. Like the exercise `gold.xml`, each medicine is
identified by the ID of one of its records (`eval_id`). The fused record
containing that ID is found through `_fusion_sources`.

| Item | Value |
|---|---|
| Worksheet | `data/8_fusion_eval/fusion_eval_worksheet.csv` |
| Sampling script | `src/data_fusion/sample_eval_set.py` (seed 42) |
| Medicines | 36 clusters, 0 duplicate cluster IDs, 0 duplicate `eval_id`s |
| Attributes per medicine | 10 |
| Verified | 5 / 36 (rows 1–5, 15 Nov) |
| Freeze | 21 Nov |

## 1. Sampling

**Input clusters.** `data/3_fused/medicine_clusters.csv` is git-ignored, so regenerate it from `main` before running the script:

```bash
python src/identity_resolution/llm_zero_shot_matcher.py --match-candidates
python src/identity_resolution/clustering.py --inputs data/3_fused/candidate_matches.csv \
       --output data/3_fused/medicine_clusters.csv --enforce-one-to-one
python src/data_fusion/sample_eval_set.py          # --n 30..40, --seed
```

This reproduces the candidate clustering report: 4,708 matches and 2,343 multi-source clusters (502 three-way).

**Eligible clusters: 2,247.** A cluster qualifies if it:
- comes from at least two sources;
- has exactly one record per source, so the reference is unambiguous (this drops 5 clusters with intra-source conflicts);
- is a human medicine in every source, so external references exist (this drops veterinary and disinfectant products).

**Stratified by source combination.** Three-way clusters are over-sampled because they contain the most conflicts:

| Sources | All clusters | Eligible | Sampled |
|---|---:|---:|---:|
| DPD + EMA + FDA | 502 | 495 | 12 |
| DPD + FDA | 1,388 | 1,361 | 8 |
| DPD + EMA | 314 | 252 | 8 |
| EMA + FDA | 139 | 139 | 8 |

**Reference record (`eval_id`).** This is the FDA record if the cluster has one, otherwise EMA, otherwise DPD. Its source is the *reference jurisdiction* for the jurisdiction-specific attributes below.

**Note: the sample depends on the cluster file.** If the team switches to another Phase II matcher, cluster IDs change. Keep this sample and look medicines up by `eval_id`, not by `cluster_id`.

## 2. Attributes and gold-value conventions

The worksheet shows all source values side by side (`src_<attr>`) next to the hand-filled `gold_<attr>`.

| Attribute | Gold value | Main reference |
|---|---|---|
| `brandName` | Brand as registered in the reference jurisdiction | Drugs@FDA / DailyMed, EMA EPAR, DPD |
| `activeSubstances` | WHO INN of the active moiety, lowercase, no salt/hydrate, `; `-separated | WHO INN, EPAR |
| `activeSubstanceCount` | Number of active substances | label |
| `licenceHolder` | Holder in the reference jurisdiction (Drugs@FDA applicant, EU MAH, DPD company) | Drugs@FDA, EPAR, DPD |
| `productClass` | Human / Veterinary | regulator |
| `atcCode` | Full WHO ATC code (7 characters) | WHO ATC/DDD index, EPAR |
| `dosageForm` | Project vocabulary (`src/mapforce/lookups/dosage_form.xml`), all forms of the product, `; `-separated | label |
| `route` | Project vocabulary (`route.xml`) | label |
| `strengths` | Distinct strengths in the label: amount per unit for solids/powders, concentration (mg/mL) for liquids | label section 3 / DPD |
| `biosimilar` | true / false | EPAR, FDA Purple Book (351(k) = biosimilar) |

**Not evaluated.** Dates are left out because each date comes from one source only (FDA, EMA or DPD), so there is no conflict to resolve. `regulatoryStatus`, `generic` and `orphanMedicine` are left out because they are defined per jurisdiction, and a single true value would be arbitrary.

**Recommended evaluation functions** for the fusion notebook:
- `tokenized_match`: brand, holder, substances, dosage form, route, strengths;
- exact match: ATC, count, product class, biosimilar.

## 3. Verification procedure

1. Open the reference regulator's record for `eval_id` (Drugs@FDA / DailyMed label, EMA EPAR page, or DPD product monograph).

   **Evidence policy: regulator first, company label as backup.** Allowed sources:
   - FDA (accessdata.fda.gov, fda.gov, DailyMed), EMA (ema.europa.eu), Health Canada (pdf.hres.ca, dhpp.hpfb-dgpsa.ca), WHO ATC (atcddd.fhi.no);
   - as backup only, the company's official prescribing information (approved label or product monograph), never marketing pages.

   No third-party databases or aggregators (DrugBank, PharmaCompass, Drugs.com, Wikipedia). In `evidence_urls`, prefix each link with its source, e.g. `FDA label: …`, `Company label (backup): …`.
2. Take ATC and INN from the WHO index or EPAR "Product details". The WHO site (atcddd.fhi.no) could not be fetched from the tool, so rows 1–5 were first cross-checked against EPAR / emc SmPC / DrugBank and then confirmed by hand on the WHO index (15 Nov). Check every further row on atcddd.fhi.no.
3. Fill `gold_*`, paste the URLs into `evidence_urls`, and record anything surprising in `notes`.
4. Set `verified_by` and `verified_on`.

Rows 1–5 were drafted with Claude-assisted web lookups and are marked "to be reviewed by Trang". They are not final until a human has opened the evidence links.

## 4. Findings so far (rows 1–5)

**Typical source conflicts the fusion must resolve:**
- **Generic route:** the FDA source says `Injection` where the true route is *Intravenous* (Cinqair) or *Subcutaneous* (Hemlibra).
- **Dosage-form granularity:** Cinqair is "Solution" in DPD and "Injection" in FDA.
- **Strengths:** the same quantity is written differently (`200 U` vs `200 U/vial`), and vial amounts are mixed with concentrations (Hemlibra).
- **Salt in substance names:** e.g. bosutinib vs bosutinib monohydrate. The INN rule makes these equal.

**Jurisdiction-specific values are correct in every source, not conflicts:**
- EU brand *Cinqaero* vs US *Cinqair*.
- Licence holders differ by country in every cluster (e.g. Roche Registration Ltd vs Genentech).

**Elelyso:** the EU authorisation was refused (2012). The EMA record correctly says `Refused`.

**Possible wrong clusters to check during verification** (same substance, different manufacturers, so possibly distinct products):

| Row | Cluster |
|---:|---|
| 13 | AJ-Cytarabine vs Hospira Cytarabine |
| 16 | Minims Prednisolone vs Pharm Assoc |
| 19 | Val-Pamidronate vs Hikma |
| 20 | Xenon Xe-133 (BMS vs GE Healthcare) |
| 29 | Cabazitaxel Teva vs Accord |

**Keep them.** Their gold describes the `eval_id` product, so they also show how identity-resolution errors propagate into fusion. Note the issue in `notes`.

