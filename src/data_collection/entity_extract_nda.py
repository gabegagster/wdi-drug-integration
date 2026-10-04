from pathlib import Path

import pandas as pd

repo_root = Path(__file__).resolve().parents[2]
translated_data_dir = repo_root / "data" / "2_translated"
input_file = translated_data_dir / "openfda_ndc_products.csv"

translated_data_dir.mkdir(parents=True, exist_ok=True)

df = pd.read_csv(input_file)

# Check missing
missing = pd.DataFrame({
    "missing_count": df.isna().sum(),
    "missing_percent": (df.isna().mean() * 100).round(2),
})

print(missing)

ingredients = set()

for value in df["active_ingredients"].dropna():
    for item in value.split(";"):
        name = item.split(" (", 1)[0].strip()
        if name:
            ingredients.add(name)

ingredient_list = sorted(ingredients, key=str.casefold)

print(f"Unique active ingredients: {len(ingredient_list)}")

output_file = translated_data_dir / "openfda_active_ingredients.txt"
output_file.write_text("\n".join(ingredient_list), encoding="utf-8")

print(f"Ingredient list saved to: {output_file}")
