import io
import json
import zipfile
from pathlib import Path
import pandas as pd
import requests


repo_root = Path(__file__).resolve().parents[2]
raw_data_dir = repo_root / "data" / "1_raw"
translated_data_dir = repo_root / "data" / "2_translated"
download_dir = raw_data_dir / "openfda_ndc_downloads"

download_dir.mkdir(parents=True, exist_ok=True)
translated_data_dir.mkdir(parents=True, exist_ok=True)

manifest_url = "https://api.fda.gov/download.json"

manifest_response = requests.get(manifest_url, timeout=60)
manifest_response.raise_for_status()
manifest = manifest_response.json()

# Find all downloadable parts for the NDC dataset
partitions = manifest["results"]["drug"]["ndc"]["partitions"]
print(f"{len(partitions)} NDC file(s).")

products = []

for number, partition in enumerate(partitions, start=1):
    url = partition["file"]
    zip_path = download_dir / f"ndc_part_{number}.json.zip"

    print(f"Download file {number} of {len(partitions)}...")
    response = requests.get(url, timeout=180)
    response.raise_for_status()
    zip_path.write_bytes(response.content)

    # Read the JSON file inside the ZIP
    with zipfile.ZipFile(io.BytesIO(response.content)) as zipped_file:
        json_filename = zipped_file.namelist()[0]
        with zipped_file.open(json_filename) as json_file:
            data = json.load(json_file)

    products.extend(data.get("results", []))

print(f"Downloaded {len(products)} product records.")

# Keep useful fields and turn lists into readable text
rows = []

for product in products:
    openfda = product.get("openfda", {})

    ingredients = product.get("active_ingredients", [])
    ingredient_text = "; ".join(
        f"{item.get('name', '')} ({item.get('strength', '')})".strip()
        for item in ingredients
    )

    rows.append({
        "product_ndc": product.get("product_ndc"),
        "brand_name": product.get("brand_name"),
        "generic_name": product.get("generic_name"),
        "active_ingredients": ingredient_text,
        "manufacturer": "; ".join(openfda.get("manufacturer_name", [])),
        "dosage_form": product.get("dosage_form"),
        "route": "; ".join(product.get("route", [])),
        "marketing_start_date": product.get("marketing_start_date"),
        "marketing_category": product.get("marketing_category"),
        "application_number": product.get("application_number"),
    })

output_path = translated_data_dir / "openfda_ndc_products.csv"
pd.DataFrame(rows).to_csv(output_path, index=False, encoding="utf-8-sig")

print(f"Saved CSV to: {output_path}")
