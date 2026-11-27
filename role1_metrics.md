# Full-data density and consistency

**52,459 source records → 49,608 output entities, including 2,343
merged groups.** Across the 10 comparable attributes, density rises from
**93.18% to 94.33%** overall,
and from **85.07% to 99.48%** within the fusion
cohort. Input consistency is **73.21%** with the lecture denominator
and the missing-value policy below (**73.69%** when all-missing groups
are excluded per attribute). These are completeness/agreement measures, not accuracy.

## Run and inputs

Place `metrics_datacentric.py` in `src/data_fusion/` of the repository. With the project's
Python environment (Python 3.11+) and `requirements.txt` installed, run from the repository root:

```sh
python -B src/data_fusion/metrics_datacentric.py
```

This writes/replaces `role1_metrics.md` at the repository root. It reads the three full
XMLs in `data/4_translated_mapforce/`, production pairs in
`data/3_fused/candidate_correspondences_1to1.csv`, and
`data/9_fusion_xml_final/fused_medicines.xml`. No sample or earlier 1,938-pair baseline
is used. The cluster CSV is unnecessary: PyDI builds the same connected groups from pairs.
The script reuses `loader.py` and `correspondence_prep.py`; it does not run fusion.

For a script outside the checkout or a later fusion export:

```sh
python -B /path/to/metrics_datacentric.py --project-root /path/to/wdi-drug-integration
python -B src/data_fusion/metrics_datacentric.py --fused data/9_fusion_xml_final/fused_medicines.xml --output role1_metrics.md
```

Relative input/output arguments resolve from the project root. Rerunning updates this
single report; input files are never rewritten. Use `--pairs` to select a different
correspondence CSV when the team changes the matches, together with its matching fused XML.

Repository snapshot: `417382702ba28bf4628887b4cd5d7c00f50956ad`. Runtime: Python 3.12.10, pandas
2.3.3, uma-pydi 0.2.1.

## Record coverage

- Source records: **52,459**; positive pairs: **3,336**.
- Merged groups: **2,343**, containing **5,194** source records.
- Unmatched records retained: **47,265**.
- Full fused output: **49,608** unique entities.
- Compared with the largest source (DPD): **+7,972 entities (+19.15%)**.
- 5 connected groups contain more than one record from a source. They are included
  as supplied by production matching; this analysis does not verify or change those matches.

| Contributing sources | Output entities |
| --- | --- |
| DPD | 39429 |
| DPD+EMA | 314 |
| DPD+EMA+FDA | 502 |
| DPD+FDA | 1388 |
| EMA | 1692 |
| EMA+FDA | 139 |
| FDA | 6144 |

## Density

Following lecture slide 19, column density is populated cells / rows; table density is
populated cells / (rows × attributes). `id`, `source`, and provenance metadata are excluded.
`False` and numeric zero count as populated. Missing elements, nulls, blank text, and
empty lists count as missing. A nonempty list is one populated cell; density does not
claim that its contents are correct or complete.

All 16 medicine attributes are reported. The comparable 10 are the same scope as the
team's fusion experiment: `brandName`, `activeSubstances`, `activeSubstanceCount`, `licenceHolder`, `productClass`, `atcCode`, `dosageForm`, `route`, `strengths`, `biosimilar`.
The remaining six describe jurisdiction-specific dates, status and policy flags;
their absence in another jurisdiction is not automatically a data defect.

| Dataset / cohort | Rows | Density: all 16 | Density: comparable 10 |
| --- | --- | --- | --- |
| DPD | 41,636 | 73.64% | 97.82% |
| EMA | 2,648 | 65.36% | 67.04% |
| FDA | 8,175 | 66.49% | 78.03% |
| All inputs | 52,459 | 72.11% | 93.18% |
| Fused | 49,608 | 73.19% | 94.33% |
| Matched inputs only | 5,194 | 69.93% | 85.07% |
| Merged output only | 2,343 | 90.28% | 99.48% |

| Attribute | DPD | EMA | FDA | All inputs | Fused |
| --- | --- | --- | --- | --- | --- |
| brandName | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% |
| activeSubstances | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% |
| activeSubstanceCount | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% |
| licenceHolder | 100.00% | 86.82% | 100.00% | 99.33% | 99.44% |
| regulatoryStatus | 100.00% | 98.90% | 96.75% | 99.44% | 99.60% |
| productClass | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% |
| atcCode | 78.41% | 83.61% | 0.00% | 66.45% | 68.79% |
| generic | 0.00% | 100.00% | 95.50% | 19.93% | 19.80% |
| biosimilar | 100.00% | 100.00% | 0.00% | 84.42% | 87.61% |
| orphanMedicine | 0.00% | 100.00% | 0.00% | 5.05% | 5.34% |
| dosageForm | 99.99% | 0.00% | 88.88% | 93.21% | 95.43% |
| route | 99.94% | 0.00% | 92.78% | 93.78% | 95.75% |
| strengths | 99.85% | 0.00% | 98.64% | 94.62% | 96.26% |
| usApprovalDate | 0.00% | 0.00% | 91.36% | 14.24% | 15.05% |
| euAuthorisationDate | 0.00% | 76.47% | 0.00% | 3.86% | 4.08% |
| caStatusDate | 100.00% | 0.00% | 0.00% | 79.37% | 83.92% |

Full-output change versus DPD: **-0.44 percentage points** across all 16
attributes; **-3.49 points** across the comparable 10. A density decrease can
coexist with wider entity coverage when sparse records from other sources are retained.
The matched-input / merged-output rows isolate the fusion cohort; they still compare
source-record rows before fusion with one row per entity afterwards.

## Consistency of the matched sources

Following lecture slides 20 and 22, compare values within connected identity groups.
Use all **2,343** multi-record groups from the full data, excluding singletons
because those provide no cross-record agreement evidence. Compare the 10 attributes
above; jurisdiction-specific fields are excluded for the same reason as in the team experiment.

For comparison only, text is lowercased and whitespace collapsed; ingredient names,
ATC codes, dosage forms and routes are compared as complete sets. Strengths are exact
sets of `(Decimal amount, unit)` pairs, ignoring order and duplicate pairs; unit case
is preserved. No spelling, ingredient-salt, unit-conversion or approximate equivalence
is inferred. Original frames and files are unchanged by these comparison keys.

Missing-value policy: omit missing source values from comparisons. An entity with one
available value is non-conflicting but has no corroboration. An all-missing attribute
has no non-conflicting value, so contributes zero to the numerator. **Lecture score**
uses all 2,343 entities as denominator. **Available-only score** excludes the
all-missing entities, making the denominator convention comparable to the team's PyDI
experiment. It is a second view of the same counts, not accuracy.

| Attribute | All missing | One value only | 2+ values agree | Conflict | Lecture score | Available-only |
| --- | --- | --- | --- | --- | --- | --- |
| brandName | 0 | 0 | 1717 | 626 | 73.28% | 73.28% |
| activeSubstances | 0 | 0 | 1517 | 826 | 64.75% | 64.75% |
| activeSubstanceCount | 0 | 0 | 2334 | 9 | 99.62% | 99.62% |
| licenceHolder | 0 | 62 | 20 | 2261 | 3.50% | 3.50% |
| productClass | 0 | 0 | 2314 | 29 | 98.76% | 98.76% |
| atcCode | 107 | 1506 | 593 | 137 | 89.59% | 93.87% |
| dosageForm | 9 | 780 | 925 | 629 | 72.77% | 73.05% |
| route | 5 | 647 | 1307 | 384 | 83.40% | 83.58% |
| strengths | 0 | 464 | 626 | 1253 | 46.52% | 46.52% |
| biosimilar | 0 | 1527 | 815 | 1 | 99.96% | 99.96% |

Mean lecture consistency (10 attributes × 2,343 entities): **73.21%**.
Mean available-only attribute score: **73.69%**.
Most conflicting attributes: `licenceHolder` (2,261 groups); `strengths` (1,253 groups); `activeSubstances` (826 groups).
Counts depend on the supplied matches and the explicit comparison rules. For example,
different ingredient salts or dose sets can produce a conflict without proving a source error.

## Post-fusion interpretation and checks

The merged XML has one exported value/list per attribute per entity. Under the same
lecture denominator and missing-value policy, its structural consistency is
**99.48%** for the 2,343 merged entities, exactly their comparable-10
density. There are no remaining competing source rows in this representation.
This number does **not** independently demonstrate correct conflict resolution.
Cross-source agreement after selecting one value is not measurable from this export;
correctness must be assessed against the reviewed evaluation set by the evaluation work.
The existing 31-group experiment's accuracy/density figures are sample results and
are not substituted for these full-data metrics.

- All three source XMLs passed the existing loader's schema and lookup checks.
- Pair IDs resolve to current source records; PyDI groups cover every source record.
- Fused IDs are unique, and each current group has exactly one output record.
- Each output's contributing source names agree with its source group.
- Fused `activeSubstanceCount` versus distinct ingredient-list size: **0 mismatches**.
- SHA-256 checks confirmed all listed inputs were unchanged during this run.

The fused XML extends the single-source schema, so it is read with its export format
instead of being incorrectly validated as a single-source XML. These checks establish
coverage and structural alignment, not a replay of the fusion rules or external truth.
The current export uses a representative source record ID for each group; the script
also accepts PyDI's concatenated-member ID format without splitting medicine names.
Loader provenance remains DPD: weight=1, date=unknown; EMA: weight=1, date=unknown; FDA: weight=1, date=unknown. Unknown historical source dates are
not inferred from Git dates. Source weights and dates do not alter these unweighted metrics.
Previously investigated strength issues remain separate; no corrections are applied here.

For a later release, rerun this command after the matching CSV and full fused XML are
updated together. No manual refresh of table values is needed.

## References and reproducibility

- [WDI Data Fusion lecture, slides 19–22](https://www.uni-mannheim.de/media/Einrichtungen/dws/Files_Teaching/Web_Data_Integration/HWS2026/WDI06-DataFusion-HWS2026.pdf): density, consistency, accuracy and comparison rules.
- [Quality/Fusion exercise, slides 16–17 and 20](https://github.com/gabegagster/wdi-drug-integration/blob/417382702ba28bf4628887b4cd5d7c00f50956ad/docs/slides/WDI-Exercise-Quality-Fusion-HWS2026.pdf): input/merged density, consistency, and gain over the largest source.
- [Team fusion experiment](https://github.com/gabegagster/wdi-drug-integration/blob/417382702ba28bf4628887b4cd5d7c00f50956ad/notebooks/data_fusion_rule_experiment/report.md): the 10-attribute scope and distinction from sample accuracy.

Input fingerprints (SHA-256):

| Repository path | SHA-256 |
| --- | --- |
| data/4_translated_mapforce/dpd_medicines.xml | 4284113924a4878364ee5b148a16b9f3bce6c2be61acb685123eb5d9cb35046f |
| data/4_translated_mapforce/ema_medicines.xml | 6607951202961152ae83310f8229dcc307500e87d7ce8d27122d8d579841d5dc |
| data/4_translated_mapforce/fda_medicines.xml | 6117eac369bad9ee64b478c6cc2dd750a936ba3a9cc9e04d8e2368ea80c2ad18 |
| data/3_fused/candidate_correspondences_1to1.csv | f63789421f14f6260532db69bf0410035dbf738efe0b048dd890ab35b18b033d |
| data/9_fusion_xml_final/fused_medicines.xml | e382a5a6ae47bcaa1fe7262fa89c6d2b6f63e0e0cdaceb02426ad9d997e87264 |
| src/mapforce/schema/medicines.xsd | 24658456278c329b102dfea0be1e7e2a1124588adfef5f87d1d45d4efe51f0ae |
| src/mapforce/lookups/dosage_form.xml | 5c12585242c5929c84f173f69a79cb484a1f97c68876533aef452eb9b1ea9a8c |
| src/mapforce/lookups/product_class.xml | 3dd8a13812152227ab71427b8dab51ac047b48a6763d9c07d35211883a19a711 |
| src/mapforce/lookups/regulatory_status.xml | 346e93c41b9b6d71e7111b4a2ce33c3d9c6477b09b7bd9b234fd378b86ae4e9c |
| src/mapforce/lookups/route.xml | 3ef732551ae6aac06787c2100710230cd8f42876c77ccaf53197cf8d0bb214e3 |
| src/mapforce/lookups/strength_unit.xml | 1c2122474fe1b5a8a26f5720977353507d4446a6c07575f4495651c1faf12e37 |
| src/data_fusion/loader.py | fdc90ae9ee09830f4de303a161c67ae9fe9c1330a8a6f969b128b6c9798bfb47 |
| src/data_fusion/correspondence_prep.py | de5b011284817298f31fb260df7f0f05971ae416623e06b5936d804e93296eeb |
| src/data_fusion/fusion.py | b818add3160ee471284f4019e2c407f73229d0cb0a4d5ded691d15dc7cf26ecb |
