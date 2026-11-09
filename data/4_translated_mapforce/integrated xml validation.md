# Integrated XML validation

Validation checks the integrated schema and duplicates within each input file.
Duplicate counts are extra rows beyond the first record in each group.

Script: [check_schema.py](../../src/mapforce/schema/check_schema.py).
Inputs: `dpd_medicines.xml`, `ema_medicines.xml`, and `fda_medicines.xml`
in `data/4_translated_mapforce/`.
Output: console log with record counts, unique IDs, schema validity, and duplicate counts.

| Validation check | dpd_medicines.xml | ema_medicines.xml | fda_medicines.xml |
| --- | ---: | ---: | ---: |
| Records | 41,636 | 2,648 | 8,175 |
| Unique IDs | 41,636 | 2,648 | 8,175 |
| Schema valid | True | True | True |
| Duplicate IDs | 0 | 0 | 0 |
| Duplicate content excluding ID | 0 | 0 | 0 |
| Duplicate normalized entities | 0 | 0 | 0 |

## Duplicate checks

- IDs must be unique within each file.
- Content duplicates share every exported attribute except ID. List order is preserved.
- Entity duplicates share source, normalized brand name, and normalized ingredient set.
- Entity normalization folds case and accents, replaces punctuation with spaces, and collapses whitespace.
- Ingredient order and repeated ingredients do not affect entity keys. Strengths are retained in names.

These checks do not detect every semantic duplicate or verify mapping completeness.
Cross-source matches are evaluated during identity resolution.
