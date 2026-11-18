# Data fusion evaluation set (Role 2)

Evaluation set for Phase III: 31 multi-source medicines (36 sampled, 5 wrong clusters excluded) with hand-verified true
values for 10 attributes each. Like the exercise `gold.xml`, each medicine is
identified by the ID of one of its records (`eval_id`). The fused record
containing that ID is found through `_fusion_sources`.

| Item | Value |
|---|---|
| Worksheet | `data/8_fusion_eval/fusion_eval_worksheet.csv` |
| Sampling script | `src/data_fusion/sample_eval_set.py` (seed 42) |
| Medicines | 31 clusters (36 sampled, 5 excluded as wrong clusters), 0 duplicate cluster IDs, 0 duplicate `eval_id`s |
| Attributes per medicine | 10 |
| Verified | 31 / 31 by Trang (rows 1–5 on 15 Nov, rows 6–36 on 18 Nov) |
| Excluded | rows 13, 16, 19, 20, 29 → `data/8_fusion_eval/fusion_eval_excluded.csv` |
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

| Sources | All clusters | Eligible | Sampled | Final |
|---|---:|---:|---:|---:|
| DPD + EMA + FDA | 502 | 495 | 12 | 12 |
| DPD + FDA | 1,388 | 1,361 | 8 | 4 |
| DPD + EMA | 314 | 252 | 8 | 8 |
| EMA + FDA | 139 | 139 | 8 | 7 |

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

   **Two-source rule (external lookup).** The reference regulator is also the origin of one of our input datasets, so its document alone could look like copying the dataset. Each row therefore needs:
   1. the primary document of the reference regulator (label PDF / EPAR), read by hand, never the dataset value;
   2. at least one source **independent of the three input datasets**: the company's official prescribing information, or a regulator outside FDA/EMA/Health Canada (TGA Australia, HPRA Ireland, MHRA/emc UK, Swissmedic). Prefix it `Independent - …`;
   3. WHO (atcddd.fhi.no) for ATC and INN.

   Status 18 Nov: 28 of 31 rows have a source independent of the three datasets. Rows 1 (Agenerase), 15 (Frova) and 32 (Ionsys) have no company label online (discontinued or not published), so their second source is another regulator than the reference one.
2. Take ATC and INN from the WHO index or EPAR "Product details". The WHO site (atcddd.fhi.no) could not be fetched from the tool, so rows 1–5 were first cross-checked against EPAR / emc SmPC / DrugBank and then confirmed by hand on the WHO index (15 Nov). Check every further row on atcddd.fhi.no.
3. Fill `gold_*`, paste the URLs into `evidence_urls`, and record anything surprising in `notes`.

   **One substance, several ATC codes.** WHO gives a substance one code per therapeutic use, so pick the code that matches the product's form, route and indication: Durezol (difluprednate eye emulsion) is S01BA16, not the dermatological D07AC19; Kesimpta (low-strength ofatumumab for MS) is L04AG12, not the oncology code L01FA used for high-strength CLL products.
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

**Excluded: wrong clusters from identity resolution (team decision, 18 Nov).** Five sampled clusters merge records of different companies' products that share an active substance, so there is no single true value. An evaluation set must be unambiguous, so they were removed (kept in `fusion_eval_excluded.csv` for the report):

| Row | Cluster | Mismatch |
|---:|---|---|
| 13 | AJ-Cytarabine (Agila Jamp) vs Cytarabine (Hospira) | different generic makers |
| 16 | Minims prednisolone eye drops (Bausch & Lomb) vs prednisolone oral solution (Pharm. Associates) | company, form, route, ATC |
| 19 | Val-Pamidronate (Valeo) vs Pamidronate (Hikma) | different generic makers |
| 20 | Xenon Xe-133 (BMS Canada) vs Xenon Xe 133 (GE Healthcare) | company, strengths |
| 29 | Cabazitaxel Teva (EU) vs Cabazitaxel (Accord, US) | different generic makers, strength |

**Pattern (IR finding):** all five FDA records carry a generic name as brand and a different licence holder from the partner record. In the sample, 5/5 generic-named clusters were wrong and all branded clusters were correct; 4 of the 5 are in the DPD+FDA stratum (4/8). The matcher appears to merge different generics that share a substance name.

## Known bias: reference jurisdiction

`eval_id` follows FDA > EMA > DPD, so 23 of the 31 rows use FDA as the reference record and 8 use EMA (none DPD). For jurisdiction-specific attributes the gold follows that record, so gold agrees more often with FDA than with DPD for dosage form (16/21 vs 10/24) and strengths (14/23 vs 9/24). Overall exact agreement is balanced (DPD 67%, EMA 69%, FDA 64%), so the gold is not copied from FDA, but a fusion strategy that prefers FDA would score somewhat higher on those attributes.

Mitigation in the report: show results separately for
- jurisdiction-neutral attributes: activeSubstances, activeSubstanceCount, atcCode, productClass, biosimilar, route;
- jurisdiction-specific attributes: brandName, licenceHolder, dosageForm, strengths;

and mention the FDA-heavy reference in the limitations.

