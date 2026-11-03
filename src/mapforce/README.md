# Altova MapForce Data Mapping: Target Schema & Helper Functions

This directory contains the Phase I data translation assets for integrating pharmaceutical drug data from **Drugs@FDA (US)**, **EMA Medicines (EU)**, and **Health Canada DPD (CA)**.

## Team quick start

1. Clone or pull the complete repository, keeping its folder structure. The DPD and EMA input CSVs are versioned at the paths listed below.
2. Use Altova MapForce with the **Built-in** execution engine. The current mappings were tested in MapForce 2027; compatibility with older versions has not been verified.
3. Open [dpd_mapping.mfd](dpd_mapping.mfd) or [ema_mapping.mfd](ema_mapping.mfd). Both mappings already import [wdi_helpers.mfd](helpers/wdi_helpers.mfd) and [wdi_mapping_functions.mfd](helpers/wdi_mapping_functions.mfd). Their functions should load automatically in the Libraries pane; no personal/global library installation or manual rewiring is needed.
4. Select **Output**, then save the generated XML under `data/4_translated_mapforce/` using the destination below. Run the validator in section 4 afterward.

All paths in this document beginning with `src/` or `data/` are relative to the repository root. Mapping imports, schema references, CSV inputs, and output destinations are relative to each `.mfd` file, so the checkout can live in any directory. Keep the libraries alongside the mappings; do not copy just the main `.mfd` to another location.

| Mapping | Input (repository-relative) | Output (repository-relative) | Verified records |
| :--- | :--- | :--- | ---: |
| DPD | `data/2_processed/dpd_entities.csv` | `data/4_translated_mapforce/dpd_medicines.xml` | 41,636 |
| EMA | `data/2_processed/ema_entities.csv` | `data/4_translated_mapforce/ema_medicines.xml` | 2,648 |

If functions appear missing, check that both helper files exist and their relative imports resolve before attempting to rewire anything.

---

## 1. Directory Structure

```text
src/mapforce/
├── dpd_mapping.mfd             # Complete DPD mapping
├── ema_mapping.mfd             # Complete EMA mapping with substance fallback
├── schema/
│   ├── medicines.xsd           # Shared target XML Schema (16 attributes + metadata)
│   ├── medicines.schema.json   # JSON Schema equivalent
│   ├── sample_medicines.xml    # Minimal dummy sample demonstrating all conventions
│   ├── sample_medicines.json   # Equivalent JSON dummy sample
│   └── check_schema.py         # Validator for XSD/JSON samples & output files
├── lookups/
│   ├── lookup.xsd              # XML Schema for lookup files
│   ├── build_lookups.py        # Python script generating lookups from observed raw values
│   ├── regulatory_status.xml   # Harmonized regulatory statuses (Authorised, Withdrawn, etc.)
│   ├── product_class.xml       # Product classes (Human, Veterinary, Disinfectant)
│   ├── dosage_form.xml         # Standardized dosage forms (Tablet, Capsule, Injection, etc.)
│   ├── route.xml               # Standardized administration routes (Oral, Intravenous, etc.)
│   └── strength_unit.xml       # Standardized measurement units (mg, mL, %, U/mL, etc.)
└── helpers/
    ├── README.md               # UDF reference and usage instructions
    ├── wdi_helpers.mfd         # Altova MapForce UDF library for Built-in execution
    ├── build_helpers_mfd.py    # Generator & simulator for wdi_helpers.mfd
    ├── wdi_mapping_functions.mfd # Named functions used by the main diagrams
    ├── build_mapping_functions.py # Generator for the named-function library
    ├── wdi_helpers.xslt        # Reusable XSLT 3.0 / 2.0 helper function library
    ├── udf_reference.py        # Python test oracle & dataset coverage audit
    └── udf_test_cases.csv      # 124 unit tests covering all functions and edge cases
```

---

## 2. Integrated Target Schema (`medicines.xsd` / `medicines.schema.json`)

The target schema represents a **medicine entity** (`brandName` + `activeSubstances`) from one jurisdiction. It contains the 16 attributes agreed upon in Table 2 of the project outline, plus `id` and `source` metadata needed by PyDI for Phase II (Identity Resolution) and Phase III (Data Fusion):

```xml
<medicines>
  <medicine>
    <id>FDA_VERKAZIA|CYCLOSPORINE</id>
    <source>FDA</source>
    <brandName>VERKAZIA</brandName>
    <activeSubstances>
      <activeSubstance>CYCLOSPORINE</activeSubstance>
    </activeSubstances>
    <activeSubstanceCount>1</activeSubstanceCount>
    <licenceHolder>HARROW EYE</licenceHolder>
    <regulatoryStatus>Authorised</regulatoryStatus>
    <productClass>Human</productClass>
    <generic>false</generic>
    <dosageForm>Emulsion</dosageForm>
    <route>Ophthalmic</route>
    <strengths>
      <strength>
        <value>0.1</value>
        <unit>%</unit>
      </strength>
    </strengths>
    <usApprovalDate>2021-06-23</usApprovalDate>
  </medicine>
</medicines>
```

### Key Conventions
1. **Omit Missing Values:** Do not emit empty tags like `<atcCode/>`. If a field is missing in the source, omit the element entirely.
2. **Repeating Elements:** Lists use wrapper elements:
   * `<activeSubstances>` containing repeated `<activeSubstance>`
   * `<strengths>` containing repeated `<strength>` with `<value>` (numeric) and `<unit>` (string)
3. **Controlled Vocabularies:**
   * `regulatoryStatus`: `Authorised`, `Suspended`, `Pending`, `Withdrawn`, `Application withdrawn`, `Refused`
   * `productClass`: `Human`, `Veterinary`, `Disinfectant`
4. **Dates:** ISO 8601 format (`YYYY-MM-DD`).

### Entity Consolidation Rules (Pre-Mapping Aggregations)

When consolidating multiple source product or application records into a single medicine entity (`brandName` + `activeSubstances`), all sources (Drugs@FDA, Health Canada DPD, EMA) follow these shared aggregation conventions:

| Attribute Group | Target Attribute(s) | Consolidation Policy | Rationale & Resolution Rule |
| :--- | :--- | :--- | :--- |
| **Booleans** | `generic` (FDA), `biosimilar` (DPD), `orphanMedicine` (EMA) | **Unanimity (FDA `generic`) / Any-positive (DPD `biosimilar`)** | **FDA `generic`:** Uses **Option 2 (Unanimity)**: `true` if all contributing applications are `ANDA`; `false` if all are `NDA`/`BLA`; **omitted** (`null`) if mixed (`NDA` and `ANDA`). The ~375 mixed entities represent authorized generics or co-branded innovator/generic submissions and are intentionally omitted as *Not Missing At Random (NMAR)* since neither boolean value is strictly true. <br>**DPD `biosimilar`:** Uses **Option 1 (Any-positive)**: `true` if any contributing DIN is approved as a biosimilar, since biosimilarity is a regulatory drug-line designation in Canada. |
| **Single-Valued Text** | `licenceHolder` (FDA `SponsorName`, DPD `manufacturer`) | **Plurality Vote (`mode_first`) + Tie-Breaking** | The sponsor/manufacturer with the most contributing product records is chosen. Ties are broken deterministically: select the owner of the record with the highest regulatory status (Authorised/Marketed > Withdrawn/Cancelled), then the most recent status/approval date. |
| **Status Hierarchy** | `regulatoryStatus` | **Precedence Ranking** (`bestRegulatoryStatus`) | Highest-precedence active status wins: $\text{Authorised} > \text{Suspended} > \text{Pending} > \text{Withdrawn} > \text{Application withdrawn} > \text{Refused}$. |
| **Product Class** | `productClass` | **Human-Precedence** (`stdProductClass`) | Prioritizes `Human` if both `Human` and `Veterinary`/`Disinfectant` products coexist under the same entity key. |
| **Multi-Valued Lists** | `dosageForm`, `route` | **Deduplicated Set Union** (`dosageFormList`, `routeList`) | Unique values standardized, deduplicated, sorted alphabetically, and joined with `"; "` (e.g., `"Liquid; Solution"`). |
| **Strengths** | `strengths` | **Pair Union** (`strengthValue` + `strengthUnit`) | All distinct numeric `(value, unit)` pairs across all contributing products are preserved as repeated `<strength>` elements. |
| **Dates** | `usApprovalDate`, `euAuthorisationDate`, `caStatusDate` | **Earliest Approval / Latest Active Status** | Approval date takes the earliest approval across contributing records. Status date takes the latest status date among records sharing the highest status rank. |

---

## 3. Mapper Plug-in Specifications

### A. Drugs@FDA Mapper (`fda_mapping.mfd`)

Specification only: `fda_mapping.mfd` has not been added to this repository yet.

* **Source Tables:**
  * Join `Products.txt` with `Applications.txt` on `ApplNo` (note: 11 product rows have no matching `ApplNo` in `Applications.txt`, and 1 row `ApplNo=221337` `MEDICAL AIR, USP` has an empty `ActiveIngredient`—drop empty `ActiveIngredient` when consolidating entities, just like `entity_count.py`).
  * Join `MarketingStatus.txt` and `MarketingStatus_Lookup.txt` on `MarketingStatusID`.
  * When pre-consolidating products into medicine entities, split `Products.Form` into `fdaFormPart(Form)` and `fdaRoutePart(Form)` *before* joining distinct values across products with `"; "`.
* **Field Connections:**
  * `id`: `concat("FDA_", medicine_id)` (or `concat("FDA_", DrugName, "|", ActiveIngredient)`)
  * `source`: Constant `"FDA"`
  * `brandName`: `DrugName`
  * `activeSubstances`: `tokenize(ActiveIngredient, ';')`
  * `activeSubstanceCount`: `count(activeSubstances)`
  * `licenceHolder`: `SponsorName`
  * `regulatoryStatus`: `bestRegulatoryStatus(MarketingStatusDescription)` (or `stdRegulatoryStatus` for single value)
  * `productClass`: `stdProductClass(ApplType)` $\rightarrow$ `"Human"` (or constant `"Human"` if `ApplNo` is missing from `Applications.txt`)
  * `dosageForm`: `dosageFormList(dosage_forms)` (or `stdDosageForm(fdaFormPart(Form))` per product)
  * `route`: `routeList(routes)` (or `stdRoute(fdaRoutePart(Form))` per product; handles both `,` and `;` separators)
  * `generic`: Under Option 2 (Unanimity): `true` when all applications are `ANDA`, `false` when all are `NDA`/`BLA`, omitted when mixed. Map directly from consolidated boolean/flag, or via `equal(generic, "true")`.
  * `strengths`: For each token in `tokenize(Strength, ';')`, map `strengthValue` $\rightarrow$ `value` and `strengthUnit` $\rightarrow$ `unit`. (Note: for the ~37 fixed-dose combination products with slash between masses like `600MG/90MG`, pre-split `/` into `; ` so each active substance strength gets mapped to its own `<strength>` element).
  * `usApprovalDate`: Earliest non-empty `substring(SubmissionStatusDate, 1, 10)` where `SubmissionStatus = "AP"` (note: 8 `AP` rows in `Submissions.txt` have an empty `SubmissionStatusDate`).

### B. Health Canada DPD Mapper (`dpd_mapping.mfd`)

* **Source Table:** `data/2_processed/dpd_entities.csv` (41,636 normalized medicine entities covering 58,137 products).
* **Preparation:** `src/data_collection/dpd_extract.ipynb` creates the product and older medicine tables; `src/data_collection/dpd_consolidate.py` consolidates them into `dpd_entities.csv` with IDs matching the entity profiling output.
* **Extraction Caveat:** The notebook currently imports `medicine_key.py`, which is absent from this checkout. Restore that project module before rerunning extraction; installing a Python package does not replace it. The existing `dpd_entities.csv` can be used directly for mapping without rerunning extraction.
* **Output:** `data/4_translated_mapforce/dpd_medicines.xml`.
* **Paths:** The input and output paths in the mapping are relative to `src/mapforce/dpd_mapping.mfd`, so they do not depend on a particular user's checkout location.
* **Current Status:** All specified DPD fields are wired, including `activeSubstanceCount`, `dosageForm`, `route`, and repeating `strengths`. The substance count uses the source medicine row as its aggregation context. `splitStrengths` supplies tokens, which are filtered through `exists(strengthValue(token))` before creating records; each retained token supplies its own value and unit. A row-level count/filter omits the optional `strengths` wrapper when no supported numeric token exists. The filtering and pairing remain visible in the main diagram rather than being hidden in a structured-output UDF.
* **Full Export Verified (2026-10-29):** The manual MapForce export passed XSD validation with 41,636 medicines and 41,636 unique IDs, all with source `DPD`. There were no substance-count mismatches or empty strength wrappers. It contained 100,094 strength records, all with values and units, across 41,574 medicines. The refactored export was byte-for-byte identical to the earlier full export. Duplicate comparison exports and temporary test/probe mappings were subsequently removed; the canonical output remains `dpd_medicines.xml`.
* **Required Field Connections:**
  * `id`: `makeMedicineId("DPD", medicine_id)`
  * `source`: Constant `"DPD"`
  * `brandName`: `brand_name`
  * `activeSubstances`: `getActiveSubstances(active_substances, "", "; ")`
  * `activeSubstanceCount`: `count(activeSubstances)`
  * `licenceHolder`: `licence_holder`
  * `regulatoryStatus`: `bestRegulatoryStatus(current_status)`
  * `productClass`: `stdProductClass(product_class)`
  * `atcCode`: `stdAtcCode(atc_code)`
  * `biosimilar`: `yesNoToBoolean(biosimilar)`
  * `dosageForm`: `dosageFormList(dosage_forms)`
  * `route`: `routeList(routes)`
  * `strengths`: For each supported token from `splitStrengths(strengths)`, map `strengthValue` $\rightarrow$ `value` and `strengthUnit` $\rightarrow$ `unit`; omit the wrapper when the supported-token count is zero.
  * `caStatusDate`: `status_date` (latest status date among contributing products with the best regulatory status, not the earliest `approval_date`).

### C. EMA Medicines Mapper (`ema_mapping.mfd`)

* **Source Table:** `data/2_processed/ema_entities.csv`, with one row per normalized brand name and sorted ingredient set, following the DPD pre-consolidated-input pattern.
* **Output:** `data/4_translated_mapforce/ema_medicines.xml`.
* **Entity IDs:** `makeMedicineId("EMA", medicine_id)` produces `EMA_<normalized brand>|<normalized substances>`, using the same normalization as `entity_count.py` and DPD consolidation.
* **Prepared Input:** The 2,746 original rows contain 2,689 rows with usable ingredients after recovering 28 through INN fallback and excluding 57 with neither substance field. Consolidating 41 additional records produces 2,648 medicine rows. Original EMA product numbers are retained in `ema_product_numbers`; `source_record_count` and `inn_fallback_count` record their contributions.
* **Aggregation:** Regulatory status follows the shared precedence hierarchy. Brand and licence holder use plurality voting, with ties resolved by best status, latest update, latest authorisation date, and original EMA ID. Approval dates use the earliest contributing date. Product class uses Human precedence. ATC codes are combined and deduplicated. Generic uses unanimity, with mixed or unknown values omitted; biosimilar and orphan flags use any-positive aggregation.
* **Ingredient Lists:** Primary ingredients take precedence over INN during preparation. Lists are split on semicolons, deduplicated by their normalized ingredient names, and ordered consistently while retaining an original spelling for each ingredient. Comma-containing biological descriptions remain intact.
* **Mapping Connections:** The mapping reads the medicine key and consolidated fields, counts substance tokens in the source-row context, and maps Yes/No flags through `yesNoToBoolean`. Combined ATC values pass through `stdAtcCode`; dates pass through `parseAuthorisationDate`. The target XML schema and output destination are preserved.
* **Verification (2026-11-03):** The manual MapForce export passed XSD validation with 2,648 records and 2,648 unique IDs, all with source `EMA`. Every ID matched the prepared medicine key, with no missing or unexpected IDs, repeated brand-and-substance combinations, ingredient-count errors, or empty value elements. ATC codes were present in 2,214 records. The prepared input retains all 2,689 contributing EMA IDs.
* **Run:** Reload `ema_mapping.mfd` from disk, select **Output**, and save the XML. Expect 2,648 unique IDs prefixed with `EMA_` and built from brand and substances. Existing gold-standard samples using the earlier EMA IDs should be regenerated after the new export.


---

## 4. Verification & Validation

Install the dependencies from the repository root using the same Python environment as the project:

```bash
python -m pip install -r requirements.txt
```

`check_schema.py` is already implemented. It requires `lxml` for XML/XSD validation and `jsonschema` for JSON validation; both are included in `requirements.txt` and imported even when validating only XML.

Use a project virtual environment with a Python version supported by the dependencies. For XML validation alone, install `lxml` and `jsonschema` with `python -m pip install lxml jsonschema`; the full requirements also include notebook and data-preparation tools. Jupyter is optional for mapping existing CSVs and validating exports. Dependency build failures depend on the selected Python version and available wheels; they do not imply that MapForce needs a C++ compiler.

To validate generated XML or JSON output files against the target schema (commands run from the repository root):

```bash
# Validate sample instances
python src/mapforce/schema/check_schema.py

# Validate DPD output after exporting it from MapForce
python src/mapforce/schema/check_schema.py data/4_translated_mapforce/dpd_medicines.xml

# Validate EMA output after exporting it from MapForce
python src/mapforce/schema/check_schema.py data/4_translated_mapforce/ema_medicines.xml

# Run the 124 UDF unit tests and dataset coverage audit
python src/mapforce/helpers/udf_reference.py

# Run only the helper unit tests
python src/mapforce/helpers/udf_reference.py --no-coverage
```

For Windows PowerShell, use `& .\.venv\Scripts\python.exe` in place of `python` to explicitly select the project's virtual environment.

XML validation checks structure, required elements, unique IDs, controlled values, and data types against `medicines.xsd`. It does not prove that the mapping is complete: substance count, dosage form, route, and strengths are optional in the XSD. Before accepting a final export, also check that it contains 41,636 medicine records with the expected `DPD_` IDs and that the available dosage forms, routes, strengths, and substance counts are preserved. Helper unit tests exercise shared functions; they do not execute the complete DPD mapping in MapForce. MapForce's own mapping validation also does not establish that runtime execution completes successfully.
