"""Count normalized medicine entities and their pairwise overlap."""

import re
import unicodedata
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_DATA_DIR = REPO_ROOT / "data" / "1_raw"
PROCESSED_DIR = REPO_ROOT / "data" / "2_processed"
ENTITY_COUNT_DIR = REPO_ROOT / "data" / "3_profiling" / "entity_count"

# Remove strengths such as 20 MG, 5 MG/ML, 10%, and 1:100000.
STRENGTH_PATTERN = re.compile(
    r"\b\d+(?:[.,]\d+)?\s*"
    r"(?:MCG|UG|MG|KG|G|ML|L|IU|UNITS?|MEQ)\b"
    r"(?:\s*/\s*(?:\d+(?:[.,]\d+)?\s*)?"
    r"(?:MCG|UG|MG|KG|G|ML|L|IU|UNITS?|MEQ)\b)?"
    r"|\b\d+(?:[.,]\d+)?\s*%"
    r"|\b\d+\s*:\s*\d+\b"
)


def normalize(value, substance_list=False):
    """Apply simple text normalization and optionally sort substances."""
    if pd.isna(value):
        return ""

    items = str(value).split(";") if substance_list else [str(value)]
    normalized_items = []

    for item in items:
        text = unicodedata.normalize("NFKD", item)
        text = text.encode("ascii", "ignore").decode("ascii").upper()
        text = STRENGTH_PATTERN.sub(" ", text)
        text = re.sub(r"[^A-Z0-9]+", " ", text)
        text = " ".join(text.split())
        if text:
            normalized_items.append(text)

    if substance_list:
        return "; ".join(sorted(set(normalized_items)))
    return normalized_items[0] if normalized_items else ""


def build_entities(data, brand_column, substance_column, filename):
    """Build and save one row per normalized medicine."""
    records = []

    for brand_value, substance_value in zip(
        data[brand_column], data[substance_column]
    ):
        brand_name = normalize(brand_value)
        active_substances = normalize(substance_value, substance_list=True)

        if not brand_name or not active_substances:
            continue

        records.append(
            {
                "medicine_id": f"{brand_name}|{active_substances}",
                "normalized_brand_name": brand_name,
                "normalized_active_substances": active_substances,
            }
        )

    entities = pd.DataFrame(records)
    entities = (
        entities.groupby(
            [
                "medicine_id",
                "normalized_brand_name",
                "normalized_active_substances",
            ],
            as_index=False,
        )
        .size()
        .rename(columns={"size": "source_row_count"})
        .sort_values("medicine_id")
        .reset_index(drop=True)
    )

    output_path = ENTITY_COUNT_DIR / filename
    entities.to_csv(output_path, index=False, encoding="utf-8-sig")
    return entities, output_path


def main():
    ENTITY_COUNT_DIR.mkdir(parents=True, exist_ok=True)

    fda = pd.read_csv(
        str(RAW_DATA_DIR / "01_us_drugs_at_fda" / "Products.txt"),
        sep="\t",
        dtype="string",
        encoding="utf-8-sig",
    )[["DrugName", "ActiveIngredient"]]
    ema = pd.read_csv(
        str(RAW_DATA_DIR / "02_eu_ema_medicines" / "ema_medicines.csv"),
        dtype="string",
        encoding="utf-8-sig",
    )[["Name of medicine", "Active substance"]]
    dpd = pd.read_csv(
        str(PROCESSED_DIR / "dpd_medicines.csv"),
        dtype="string",
        encoding="utf-8-sig",
    )[["brand_name", "active_substances"]]

    fda_entities, fda_path = build_entities(
        fda, "DrugName", "ActiveIngredient", "fda_normalized_entities.csv"
    )
    ema_entities, ema_path = build_entities(
        ema,
        "Name of medicine",
        "Active substance",
        "ema_normalized_entities.csv",
    )
    dpd_entities, dpd_path = build_entities(
        dpd,
        "brand_name",
        "active_substances",
        "dpd_normalized_entities.csv",
    )

    csv_paths = [fda_path, ema_path, dpd_path]

    fda_ids = set(fda_entities["medicine_id"])
    ema_ids = set(ema_entities["medicine_id"])
    dpd_ids = set(dpd_entities["medicine_id"])

    fda_ema = fda_ids & ema_ids
    fda_dpd = fda_ids & dpd_ids
    ema_dpd = ema_ids & dpd_ids
    in_at_least_two = fda_ema | fda_dpd | ema_dpd

    lines = [
        "ENTITY COUNT REPORT",
        "Entity key: normalized brand name + sorted normalized active substances",
        "Normalization: uppercase, remove accents and dosage strengths, standardize punctuation and whitespace",
        "",
        "BASIC ROW COUNTS",
        f"Drugs@FDA: {len(fda):,}",
        f"EMA Medicines: {len(ema):,}",
        f"Health Canada DPD medicines: {len(dpd):,}",
        "",
        "NORMALIZED ENTITY COUNTS",
        f"Drugs@FDA: {len(fda_entities):,}",
        f"EMA Medicines: {len(ema_entities):,}",
        f"Health Canada DPD: {len(dpd_entities):,}",
        "",
        "PAIRWISE OVERLAP COUNTS",
        f"Drugs@FDA and EMA Medicines: {len(fda_ema):,}",
        f"Drugs@FDA and Health Canada DPD: {len(fda_dpd):,}",
        f"EMA Medicines and Health Canada DPD: {len(ema_dpd):,}",
        "",
        "UNIQUE MEDICINES FOUND IN AT LEAST TWO DATASETS",
        f"Total: {len(in_at_least_two):,}",
        "",
        "NORMALIZED ENTITY CSV FILES",
        *[path.relative_to(REPO_ROOT).as_posix() for path in csv_paths],
    ]

    report_path = ENTITY_COUNT_DIR / "entity_count_results.txt"
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("\n".join(lines))
    print(f"\nSaved report to {report_path}")


if __name__ == "__main__":
    main()
