# Medicine fusion

`fusion.py` applies the selected experiment rules to the three medicine XMLs
and the supplied correspondence pairs. It retains unmatched records.

## Run

Run from the repository root using the project environment:

```powershell
.\.venv\Scripts\python.exe -m src.data_fusion.fusion data/3_fused/candidate_correspondences_1to1.csv
```

Or call the function from Python:

```python
from src.data_fusion.fusion import medicine_fusion

fused = medicine_fusion('data/3_fused/candidate_correspondences_1to1.csv')
```

Configure Python logging at INFO level to see progress when calling the function.
The command-line entry point configures logging automatically.

## Inputs and output

- `input_path`: correspondence CSV containing `id1,id2`; optional labels and
  scores follow [the existing preparation guide](HANDOFF.md). The current
  pair export is `data/3_fused/candidate_correspondences_1to1.csv`.
- Source XMLs: `data/4_translated_mapforce/`, read through `loader.load_datasets()`.
- Output: `data/9_fusion_xml_final/fused_medicines.xml`, replaced on reruns.
  The function also returns the complete PyDI DataFrame.
- Logs: loaded records, prepared positive pairs, total entities, merged groups,
  unmatched records and entity counts by contributing dataset combination.

## Selected rules

| Attributes | Rule |
|---|---|
| `brandName`, `licenceHolder`, `dosageForm`, `strengths` | FDA → EMA → DPD |
| `activeSubstances` | DPD → EMA → FDA |
| `productClass`, `atcCode`, `route`, `biosimilar` | Voting with equal source weights |
| `activeSubstanceCount` | Count unique fused `activeSubstances` |

The experiment evaluates these ten attributes using the reviewed worksheet.
Six additional schema fields remain outside the study:

| Excluded fields | Reason |
|---|---|
| `usApprovalDate`, `euAuthorisationDate`, `caStatusDate` | Each field belongs to one source's jurisdiction, so it has no cross-source conflict to resolve |
| `regulatoryStatus`, `generic`, `orphanMedicine` | Values depend on the jurisdiction; a single gold value requires a jurisdiction policy |

For example, US approval and EU authorisation dates describe different events,
and a medicine can have different regulatory statuses in Canada and the EU.
These exclusions follow the [evaluation-set guide](role2_eval_set.md).

Preprocessing follows the experiment: lowercase and clean whitespace in the
tested text/list attributes, split joined XML fields into lists, and preserve
Decimal strength amounts and case-sensitive units. Set voting compares complete
sets. Other medicine fields use PyDI's default first-available-value behavior;
these fields were outside the rule-selection study.

See the [experiment report](../../notebooks/data_fusion_rule_experiment/report.md)
for scores, custom methods, examples and tie-breaker decisions.

## Full-data run results

Verified with `data/3_fused/candidate_correspondences_1to1.csv` and the three
current XMLs. This run exports the complete integrated dataset, including
unmatched records.

| Measure | Count |
|---|---:|
| Input records | 52,459 |
| Positive correspondence pairs | 3,336 |
| Output entities | 49,608 |
| Merged groups | 2,343 |
| Unmatched records | 47,265 |

| Contributing datasets | Output entities |
|---|---:|
| DPD | 39,429 |
| EMA | 1,692 |
| FDA | 6,144 |
| DPD + EMA | 314 |
| DPD + FDA | 1,388 |
| EMA + FDA | 139 |
| DPD + EMA + FDA | 502 |
| **Total** | **49,608** |

Source combinations describe group membership. For example, a DPD + FDA
entity contains records from both datasets, and individual attributes follow
their selected rules. Full-output checks confirmed unique entity IDs and
substance counts matching the exported ingredient lists.

The [31-group experiment](../../notebooks/data_fusion_rule_experiment/report.md)
achieved 84.52% strict accuracy and 92.26% adaptive accuracy. These accuracy
scores apply to the reviewed sample; the full-data run above has no complete
gold dataset for accuracy measurement.

## Provenance and XML

The returned `_fusion_sources` contains original record IDs and
`_fusion_source_datasets` contains their dataset names. Correspondence edges
remain in the input CSV. `fusion_export_xml()` writes nested ingredients and
strengths, PyDI's entity ID and contributing dataset names in `<source>`.

The fused XML extends the original single-source schema conventions through
combined IDs, multiple source names and normalized text/codes. The pipeline
validates the source XMLs through the loader; it does not validate the final
XML against the original single-source XSD.
