"""Validate integrated medicine XML/JSON files and report duplicate records."""

import argparse
from collections import defaultdict
import json
from pathlib import Path
import re
import unicodedata

import jsonschema
from lxml import etree


HERE = Path(__file__).resolve().parent
XSD = HERE / "medicines.xsd"
JSON_SCHEMA = HERE / "medicines.schema.json"
SAMPLE_XML = HERE / "sample_medicines.xml"
SAMPLE_JSON = HERE / "sample_medicines.json"
LISTS = {"activeSubstances": "activeSubstance", "strengths": "strength"}
BOOLS = {"generic", "biosimilar", "orphanMedicine"}


def medicine_to_dict(element):
    """Convert one schema-valid XML medicine to a JSON-compatible record."""
    record = {}
    for child in element:
        if not isinstance(child.tag, str):
            continue
        tag = child.tag
        if tag == "strengths":
            strengths = []
            for strength in child:
                if not isinstance(strength.tag, str):
                    continue
                item = {}
                for part in strength:
                    if not isinstance(part.tag, str):
                        continue
                    if part.tag == "value":
                        value = float(part.text)
                        item[part.tag] = int(value) if value.is_integer() else value
                    else:
                        item[part.tag] = part.text
                strengths.append(item)
            record[tag] = strengths
        elif tag in LISTS:
            record[tag] = [item.text for item in child if isinstance(item.tag, str)]
        elif tag == "activeSubstanceCount":
            record[tag] = int(child.text)
        elif tag in BOOLS:
            record[tag] = child.text.strip() in ("true", "1")
        else:
            record[tag] = child.text
    return record


def xml_to_json(xml_path):
    """Read medicine XML and return its equivalent JSON object."""
    root = etree.parse(str(xml_path)).getroot()
    return {"medicines": [medicine_to_dict(item) for item in root
                          if isinstance(item.tag, str)]}


def normalize_text(value):
    """Normalize case, accents, punctuation, and whitespace for duplicate keys."""
    text = unicodedata.normalize("NFKD", value).casefold()
    text = "".join(char for char in text if not unicodedata.combining(char))
    return " ".join(re.sub(r"[\W_]+", " ", text).split())


def check_duplicates(records):
    """Return extra-row counts for IDs, record content, and source-specific entity keys."""
    groups = {"Duplicate IDs": defaultdict(list),
              "Duplicate content excluding ID": defaultdict(list),
              "Duplicate normalized entities": defaultdict(list)}

    # Group Records
    for record in records:
        record_id = record["id"]
        attributes = {key: value for key, value in record.items() if key != "id"}
        content_key = json.dumps(attributes, sort_keys=True, ensure_ascii=False)
        substances = tuple(sorted({normalize_text(value) for value in record["activeSubstances"]}))
        entity_key = (record["source"], normalize_text(record["brandName"]), substances)
        groups["Duplicate IDs"][record_id].append(record_id)
        groups["Duplicate content excluding ID"][content_key].append(record_id)
        groups["Duplicate normalized entities"][entity_key].append(record_id)

    # Count Extra Rows
    counts = {}
    for name, values in groups.items():
        duplicates = [ids for ids in values.values() if len(ids) > 1]
        counts[name] = sum(len(ids) - 1 for ids in duplicates)
        print(f"{name}: {counts[name]:,} extra rows ({len(duplicates):,} groups)")
        for ids in duplicates[:5]:
            print("  " + "; ".join(ids[:5]))
    return counts


def validate_xml(xml_path):
    """Validate XML against the XSD and return schema and duplicate-check results."""
    schema = etree.XMLSchema(etree.parse(str(XSD)))
    document = etree.parse(str(xml_path))
    valid = schema.validate(document)
    for error in list(schema.error_log)[:20]:
        print(f"  line {error.line}: {error.message}")
    records = [medicine_to_dict(item) for item in document.getroot()
               if isinstance(item.tag, str)]
    print(f"XSD {'OK' if valid else 'FAILED'}: {xml_path.name} ({len(records):,} medicines)")
    print(f"Unique IDs: {len({record['id'] for record in records}):,}")
    duplicates = check_duplicates(records)
    return {"file": xml_path.name, "records": len(records), "schema_valid": valid,
            "unique_ids": len({record['id'] for record in records}), **duplicates}


def validate_json(obj, label):
    """Validate a JSON medicine object and return schema and duplicate-check results."""
    schema = json.loads(JSON_SCHEMA.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(
        schema, format_checker=jsonschema.Draft202012Validator.FORMAT_CHECKER)
    errors = list(validator.iter_errors(obj))
    for error in errors[:20]:
        print(f"  {list(error.path)}: {error.message}")
    if errors:
        raise ValueError(f"JSON Schema validation FAILED: {label}")
    records = obj["medicines"]
    print(f"JSON OK: {label} ({len(records):,} medicines)")
    print(f"Unique IDs: {len({record['id'] for record in records}):,}")
    duplicates = check_duplicates(records)
    return {"file": label, "records": len(records), "schema_valid": True,
            "unique_ids": len({record['id'] for record in records}), **duplicates}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", type=Path)
    parser.add_argument("--regen-json", action="store_true", help="Rebuild the JSON sample from XML")
    args = parser.parse_args(argv)
    results = []

    try:
        # Update Sample
        if args.regen_json:
            sample = xml_to_json(SAMPLE_XML)
            SAMPLE_JSON.write_text(json.dumps(sample, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            print(f"Saved {SAMPLE_JSON.name}")

        # Validate Files
        paths = args.paths or [SAMPLE_XML, SAMPLE_JSON]
        for path in paths:
            if path.suffix.lower() == ".json":
                result = validate_json(json.loads(path.read_text(encoding="utf-8-sig")), path.name)
            else:
                result = validate_xml(path)
            results.append(result)

        # Compare Samples
        if not args.paths:
            sample = json.loads(SAMPLE_JSON.read_text(encoding="utf-8-sig"))
            if sample != xml_to_json(SAMPLE_XML):
                raise ValueError("XML and JSON samples differ; run with --regen-json")
            print("XML and JSON samples are equivalent")

        # Check Results
        failed = any(not item["schema_valid"] or item["Duplicate IDs"]
                     or item["Duplicate content excluding ID"] or item["Duplicate normalized entities"]
                     for item in results)
        if failed:
            parser.exit(1, "Validation FAILED: schema errors or duplicates found\n")
    except (OSError, ValueError, TypeError, KeyError, etree.LxmlError) as error:
        parser.exit(1, f"Validation FAILED: {error}\n")


if __name__ == "__main__":
    main()
