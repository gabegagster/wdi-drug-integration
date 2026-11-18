from pathlib import Path

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_DATA_DIR = REPO_ROOT / "data" / "1_raw"
INGREDIENT_DIR = REPO_ROOT / "data" / "3_profiling" / "ingredient_cleaning"


def save_unique_ingredients(df, column, output_file):
    ingredients = (
        df[column]
        .dropna()
        .str.split(";")
        .explode()
        .str.strip()
        .str.upper()  # Standardize case before removing duplicates
    )

    ingredients = (
        ingredients[ingredients.ne("")]
        .drop_duplicates()
        .sort_values()
    )

    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        for ingredient in ingredients:
            f.write(ingredient + "\n")

    print(f"Saved {len(ingredients)} unique ingredients to {output_file}")
    return ingredients.tolist()


def main():
    INGREDIENT_DIR.mkdir(parents=True, exist_ok=True)

    # US dataset: tab-separated TXT file
    us_df = pd.read_csv(
        RAW_DATA_DIR / "01_us_drugs_at_fda" / "Products.txt",
        sep="\t",
        usecols=["ActiveIngredient"],
        dtype="string",
        encoding="utf-8-sig",
    )

    save_unique_ingredients(
        us_df,
        "ActiveIngredient",
        INGREDIENT_DIR / "US_active_ingredients.txt",
    )

    # EU dataset: CSV file
    eu_df = pd.read_csv(
        RAW_DATA_DIR / "02_eu_ema_medicines" / "ema_medicines.csv",
        usecols=["Active substance"],
        dtype="string",
        encoding="utf-8-sig",
    )

    save_unique_ingredients(
        eu_df,
        "Active substance",
        INGREDIENT_DIR / "EU_active_ingredients.txt",
    )


if __name__ == "__main__":
    main()
