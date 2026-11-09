# MapForce translation

The mappings translate DPD, EMA, and FDA medicine entities into the shared
`medicines.xsd` schema for identity resolution and data fusion. Each XML record
represents one medicine from one source, with `id`, `source`, and the 16
integrated attributes.

## Quick start

Keep the repository folder structure and use the MapForce **Built-in** engine.
The mappings were tested in MapForce 2027; older versions have not been verified.

- **Export DPD, EMA, or FDA:**

  Open `dpd_mapping.mfd`, `ema_mapping.mfd`, or `fda_mapping.mfd`, select **Output**, and save to the
  destination below. All mappings import `helpers/wdi_helpers.mfd` (and DPD/EMA also import
  `helpers/wdi_mapping_functions.mfd`). Keep those files beside the mappings so
  their relative imports resolve. If functions are missing, check the imports
  and files in the Libraries pane.

| Source | Prepared input | Integrated output | Current records |
| --- | --- | --- | ---: |
| DPD | `data/2_processed/dpd_entities.csv` | `data/4_translated_mapforce/dpd_medicines.xml` | 41,636 |
| EMA | `data/2_processed/ema_entities.csv` | `data/4_translated_mapforce/ema_medicines.xml` | 2,648 |
| FDA | Drugs@FDA tables; see preparation below | `data/4_translated_mapforce/fda_medicines.xml` | 8,175 |

  `fda_mapping.mfd` defines the mapping from prepared FDA entities to the integrated schema. The FDA XML export
  is available for validation and downstream processing.

- **Validate all integrated XML files:**

  ```powershell
  python src/mapforce/schema/check_schema.py data/4_translated_mapforce/dpd_medicines.xml data/4_translated_mapforce/ema_medicines.xml data/4_translated_mapforce/fda_medicines.xml
  ```

- **Validate the XML and JSON samples:**

  ```powershell
  python src/mapforce/schema/check_schema.py
  ```

- **Rebuild the JSON sample after editing XML:**

  ```powershell
  python src/mapforce/schema/check_schema.py --regen-json
  ```

- **Check helper functions:**

  ```powershell
  python src/mapforce/helpers/udf_reference.py
  python src/mapforce/helpers/udf_reference.py --no-coverage
  ```

  The first command runs 124 helper cases and a dataset coverage audit. The
  second runs the helper cases alone. These checks exercise helper functions;
  export each mapping in MapForce to verify its complete execution.

Run commands from the repository root. Replace `python` with
`.venv\Scripts\python.exe` to use the project environment. Install dependencies
with `python -m pip install -r requirements.txt`; validation requires `lxml`
and `jsonschema`. Jupyter is optional when mapping existing CSVs.

## Files

| Location | Purpose |
| --- | --- |
| `dpd_mapping.mfd`, `ema_mapping.mfd`, `fda_mapping.mfd` | Source-to-schema mappings |
| `schema/medicines.xsd`, `schema/medicines.schema.json` | Integrated XML and JSON schemas |
| `schema/sample_medicines.xml`, `schema/sample_medicines.json` | Equivalent sample records |
| `schema/check_schema.py` | Schema validation and duplicate-check console logs |
| `lookups/` | Regulatory status, product class, dosage form, route, and strength-unit vocabularies |
| `lookups/build_lookups.py` | Build lookup files from observed source values |
| `helpers/README.md` | Function reference and library instructions |
| `helpers/build_helpers_mfd.py`, `helpers/build_mapping_functions.py` | Generate the Built-in helper libraries |
| `helpers/wdi_helpers.xslt` | XSLT 3.0 / 2.0 helper library |
| `helpers/udf_reference.py`, `helpers/udf_test_cases.csv` | Python oracle, coverage audit, and helper cases |

Paths beginning with `src/` or `data/` are relative to the repository root.
Mapping inputs, imports, schema references, and destinations resolve relative
to each `.mfd` file.

## Integrated schema

Required attributes are `id`, `source`, `brandName`, and `activeSubstances`.
IDs use a source prefix, such as `DPD_<medicine key>`, and must be unique within
each XML file. Sources are `DPD`, `EMA`, and `FDA`.

| Convention | Representation |
| --- | --- |
| Missing values | Omit the element |
| Ingredients | `activeSubstances` containing repeated `activeSubstance` elements |
| Strengths | `strengths` containing repeated `strength` elements with numeric `value` and optional `unit` |
| Dates | `YYYY-MM-DD` |
| Booleans | `true` or `false` |
| Dosage forms and routes | Standardized lookup values, deduplicated and sorted, joined with `; ` |
| Regulatory status | Authorised, Suspended, Pending, Withdrawn, Application withdrawn, Refused |
| Product class | Human, Veterinary, Disinfectant |

XML-to-JSON conversion turns list wrappers into arrays and numeric and boolean
fields into JSON numbers and booleans. The default validation run also checks
that both sample representations are equivalent.

## Entity preparation and mapping

Consolidate source products into medicine entities before mapping. The entity
key combines normalized brand name and sorted active substances.

| Attribute | Consolidation or mapping rule |
| --- | --- |
| `id` | Source prefix plus prepared medicine key; DPD and EMA use `makeMedicineId` |
| `source` | Source constant |
| `brandName`, `licenceHolder` | Plurality vote; ties use regulatory status and source-specific date/ID ordering |
| `activeSubstances` | Split and deduplicate ingredients while preserving usable source spellings |
| `activeSubstanceCount` | Count ingredients in the source medicine row context |
| `regulatoryStatus` | Authorised > Suspended > Pending > Withdrawn > Application withdrawn > Refused |
| `productClass` | Human takes precedence when classes are combined |
| `atcCode` | Standardize codes; combine and deduplicate where applicable |
| `dosageForm`, `route` | Standardize through lookups and combine distinct values |
| `strengths` | Preserve distinct numeric value/unit pairs; filter unsupported tokens before creating elements |
| Approval dates | Earliest contributing approval date |
| `caStatusDate` | Latest status date among products with the best regulatory status |

### DPD

`src/data_collection/dpd_extract.ipynb` prepares product tables, and
`src/data_collection/dpd_consolidate.py` consolidates 58,137 products into
41,636 entities. IDs match the normalized entity profiling output. The extraction
notebook imports `medicine_key.py`, which is absent from this checkout; restore
that module before rerunning extraction. The prepared CSV can be mapped directly.

`getActiveSubstances` reads semicolon-separated ingredients. `yesNoToBoolean`
maps biosimilar flags using any-positive aggregation. `splitStrengths` supplies
supported tokens to `strengthValue` and `strengthUnit`; omit the wrapper when
no supported numeric token remains. Keep the token filter and value/unit pairing
visible in the main diagram. Map `status_date` to `caStatusDate`.

The 2026-10-29 export contained 100,094 strength records across 41,574 medicines,
with values and units present, and no substance-count errors or empty strength
wrappers. The refactored mapping produced an identical export.

### EMA

`data/2_processed/ema_entities.csv` consolidates 2,746 original rows. INN fallback
recovers ingredients for 28 rows; 57 rows lack both ingredient fields. The 2,689
usable rows consolidate to 2,648 entities. Original product numbers and contribution
counts remain in `ema_product_numbers`, `source_record_count`, and `inn_fallback_count`.

Primary ingredients take precedence over INN. Split on semicolons and preserve
comma-containing biological descriptions. Entity IDs follow the same normalization
as DPD and `entity_count.py`. Brand and licence-holder ties use best status,
latest update, latest authorisation date, and original EMA ID. Generic uses
unanimity; mixed or unknown values are omitted. Biosimilar and orphan flags use
any-positive aggregation. Dates pass through `parseAuthorisationDate`.

The 2026-11-03 export matched all prepared entity IDs, contained 2,214 records
with ATC codes, and preserved all 2,689 contributing EMA product IDs in preparation.
Gold-standard files using earlier EMA IDs need regeneration when entity IDs change.

### FDA

Join `Products.txt` to `Applications.txt` on `ApplNo`, then join marketing status
and its lookup. Eleven products have no matching application. Exclude products
with empty ingredients, including `ApplNo=221337` (`MEDICAL AIR, USP`).

Split `Products.Form` with `fdaFormPart` and `fdaRoutePart` before aggregating.
FDA product class maps to Human. Generic is true when all applications are ANDA,
false when all are NDA/BLA, and omitted for mixed applications. The approximately
375 mixed entities have an intentionally missing generic value.

Pre-split combination strengths such as `600MG/90MG` into separate mass tokens
before strength parsing. Use the earliest nonempty approval submission date with
`SubmissionStatus=AP`; eight AP rows have missing dates.

## Validation checks

Schema validation checks required fields, structure, controlled values, data types,
and XML ID uniqueness. Duplicate checks run on both XML and JSON inputs:

- Duplicate IDs within a file.
- Duplicate exported content after excluding ID, preserving list order.
- Duplicate entities using source, normalized brand name, and normalized ingredient set.

Entity normalization folds case and accents, replaces punctuation with spaces,
and collapses whitespace. Ingredient order and repeated ingredients do not affect
the key. Strengths in names are retained. These checks describe the implemented
comparison; source preparation additionally removes strength tokens when building
its entity keys.

Counts represent extra rows beyond the first record in a duplicate group. Up to
five groups are printed per check. Schema errors or duplicates produce a nonzero
exit code. Results are printed to the console.

The report is available at
[Integrated XML validation](../../data/4_translated_mapforce/integrated%20xml%20validation.md).
Passing these checks establishes schema conformance and uniqueness under the
specified keys. Check source coverage and attribute preservation separately:
substance count, dosage form, route, and strengths are optional in the schema.
Cross-source medicine correspondence is assessed during identity resolution.
