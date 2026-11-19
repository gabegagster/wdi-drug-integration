"""Report full-data density and consistency; read inputs and write one Markdown file.

Place in src/data_fusion and run: python -B src/data_fusion/metrics_datacentric.py
The existing loader, correspondence helper, and project requirements are reused.
"""
from __future__ import annotations

import argparse
from collections import Counter
from decimal import Decimal
import hashlib
from importlib.metadata import version
from pathlib import Path
import subprocess
import sys

from lxml import etree
import pandas as pd
from PyDI.fusion.engine import build_record_groups_from_correspondences


ATTRIBUTES = (
    'brandName', 'activeSubstances', 'activeSubstanceCount', 'licenceHolder',
    'regulatoryStatus', 'productClass', 'atcCode', 'generic', 'biosimilar',
    'orphanMedicine', 'dosageForm', 'route', 'strengths', 'usApprovalDate',
    'euAuthorisationDate', 'caStatusDate',
)
COMPARABLE = (
    'brandName', 'activeSubstances', 'activeSubstanceCount', 'licenceHolder',
    'productClass', 'atcCode', 'dosageForm', 'route', 'strengths', 'biosimilar',
)
SET_TEXT = {'activeSubstances', 'atcCode', 'dosageForm', 'route'}
TEXT = {'brandName', 'licenceHolder', 'productClass'}


def present(value):
    """False and zero are values; None, NaN, blank text and empty lists are not."""
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return value is not None and not bool(pd.isna(value))


def comparison_value(attribute, value):
    """Exact comparison after documented formatting normalization, in memory only."""
    if attribute in TEXT:
        return ' '.join(value.split()).lower()
    if attribute in SET_TEXT:
        values = value.split('; ') if isinstance(value, str) else value
        return frozenset(' '.join(item.split()).lower() for item in values)
    if attribute == 'strengths':
        # Complete strength sets: order/duplicates do not change the set of doses.
        # Preserve unit case; do not convert units or repair any source value.
        return frozenset((amount, ' '.join(unit.split()) if unit is not None else None)
                         for amount, unit in value)
    return value


def density(frame, attributes):
    counts = {a: sum(present(v) for v in frame[a]) for a in attributes}
    return counts, sum(counts.values()) / (len(frame) * len(attributes)) if len(frame) else None


def consistency(groups, attributes):
    """Count each entity once; missing attributes remain in the lecture denominator."""
    result = {}
    for attribute in attributes:
        counts = Counter(missing=0, one_value=0, agreement=0, conflict=0)
        for group in groups:
            values = [comparison_value(attribute, r[attribute]) for r in group.records
                      if present(r[attribute])]
            if not values:
                counts['missing'] += 1
            elif len(values) == 1:
                counts['one_value'] += 1
            elif len(set(values)) == 1:
                counts['agreement'] += 1
            else:
                counts['conflict'] += 1
        result[attribute] = counts
    return result


def read_fused(path):
    """Read the export format, whose combined sources extend the input XSD."""
    parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False,
                             remove_comments=True, remove_pis=True)
    tree = etree.parse(str(path), parser)
    if tree.docinfo.doctype or tree.getroot().tag != 'medicines':
        raise ValueError('Expected a medicines XML without a DTD.')
    rows = []
    for medicine in tree.getroot():
        row = dict.fromkeys(('id', 'source', *ATTRIBUTES))
        seen = set()
        if medicine.tag != 'medicine':
            raise ValueError(f'Unexpected element: {medicine.tag}')
        for node in medicine:
            name = node.tag
            if name not in row or name in seen:
                raise ValueError(f'Unknown or repeated fused attribute: {name}')
            seen.add(name)
            if name == 'activeSubstances':
                row[name] = [n.text for n in node]
                if any(n.tag != 'activeSubstance' or not present(n.text) for n in node):
                    raise ValueError('Invalid fused activeSubstances.')
            elif name == 'strengths':
                row[name] = []
                for strength in node:
                    if strength.tag != 'strength' or strength.findtext('value') is None:
                        raise ValueError('Invalid fused strength.')
                    amount = Decimal(strength.findtext('value'))
                    if not amount.is_finite():
                        raise ValueError('Non-finite fused strength.')
                    row[name].append((amount, strength.findtext('unit')))
            elif name in {'generic', 'biosimilar', 'orphanMedicine'}:
                if (node.text or '').strip() not in {'true', 'false', '1', '0'}:
                    raise ValueError(f'Invalid fused boolean: {name}')
                row[name] = node.text.strip() in {'true', '1'}
            elif name == 'activeSubstanceCount':
                row[name] = int(node.text)
            else:
                row[name] = node.text
        if not present(row['id']) or not present(row['source']):
            raise ValueError('Fused record has no ID or source.')
        rows.append(row)
    frame = pd.DataFrame(rows, columns=('id', 'source', *ATTRIBUTES), dtype=object)
    if frame.empty or frame['id'].duplicated().any():
        raise ValueError('Fused XML is empty or has duplicate IDs.')
    return frame


def align_fused(groups, fused):
    """Verify one output per group and source sets, supporting both PyDI ID formats."""
    members = {r['_id']: i for i, group in enumerate(groups) for r in group.records}
    combined = {'+'.join(r['_id'] for r in group.records): i
                for i, group in enumerate(groups)}
    mapped = []
    for row in fused.itertuples(index=False):
        index = members.get(row.id, combined.get(row.id))
        if index is None:
            raise ValueError(f'Fused ID cannot be mapped to current correspondences: {row.id}')
        if set(row.source.split('; ')) != set(groups[index].source_datasets.values()):
            raise ValueError(f'Fused source metadata differs from its group: {row.id}')
        mapped.append(index)
    if len(mapped) != len(groups) or len(set(mapped)) != len(groups):
        raise ValueError('Fused output does not contain exactly one record per current group.')
    return [len(groups[index].records) > 1 for index in mapped]


def sha256(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def pct(value):
    return 'N/A' if value is None else f'{100 * value:.2f}%'


def table(headers, rows):
    return '\n'.join(['| ' + ' | '.join(headers) + ' |',
                      '| ' + ' | '.join('---' for _ in headers) + ' |',
                      *['| ' + ' | '.join(map(str, row)) + ' |' for row in rows]])


def make_report(root, datasets, pairs, groups, fused, merged_mask, hashes, commit):
    merged = [g for g in groups if len(g.records) > 1]
    pooled = pd.concat(datasets.values(), ignore_index=True)
    matched = pd.DataFrame([r for g in merged for r in g.records], columns=pooled.columns)
    fused_merged = fused.loc[merged_mask]
    frames = {**datasets, 'All inputs': pooled, 'Fused': fused}
    densities = {name: density(frame, ATTRIBUTES) for name, frame in frames.items()}
    overview = [[name, f'{len(frame):,}', pct(densities[name][1]), pct(density(frame, COMPARABLE)[1])]
                for name, frame in frames.items()]
    for name, frame in [('Matched inputs only', matched), ('Merged output only', fused_merged)]:
        overview.append([name, f'{len(frame):,}', pct(density(frame, ATTRIBUTES)[1]),
                         pct(density(frame, COMPARABLE)[1])])
    per_attribute = [[a, *[pct(densities[n][0][a] / len(frames[n])) for n in frames]]
                     for a in ATTRIBUTES]
    cons = consistency(merged, COMPARABLE)
    cons_rows = []
    for a, c in cons.items():
        good = c['one_value'] + c['agreement']
        populated = len(merged) - c['missing']
        cons_rows.append([a, c['missing'], c['one_value'], c['agreement'], c['conflict'],
                          pct(good / len(merged)) if merged else 'N/A',
                          pct(good / populated) if populated else 'N/A'])
    lecture_score = (sum(c['one_value'] + c['agreement'] for c in cons.values()) /
                     (len(merged) * len(COMPARABLE))) if merged else None
    available_scores = [(c['one_value'] + c['agreement']) / (len(merged) - c['missing'])
                        for c in cons.values() if len(merged) > c['missing']]
    available_mean = sum(available_scores) / len(available_scores) if available_scores else None
    post_score = density(fused_merged, COMPARABLE)[1]
    largest = max(datasets, key=lambda source: len(datasets[source]))
    gain = len(fused) - len(datasets[largest])
    delta16 = 100 * (densities['Fused'][1] - densities[largest][1])
    delta10 = 100 * (density(fused, COMPARABLE)[1] - density(datasets[largest], COMPARABLE)[1])
    sources = Counter('+'.join(sorted(g.source_datasets.values()))
                      for g in groups if len(g.records) == 1)
    sources.update('+'.join(sorted(set(g.source_datasets.values()))) for g in merged)
    intra = sum(len(g.records) > len(set(g.source_datasets.values())) for g in merged)
    mismatches = sum(present(r.activeSubstanceCount) and present(r.activeSubstances) and
                     r.activeSubstanceCount != len(set(r.activeSubstances))
                     for r in fused.itertuples(index=False))
    largest_conflicts = sorted(cons, key=lambda a: cons[a]['conflict'], reverse=True)[:3]
    findings = '; '.join(f"`{a}` ({cons[a]['conflict']:,} groups)" for a in largest_conflicts)
    evidence = [[str(path.relative_to(root)) if path.is_relative_to(root) else str(path), digest]
                for path, digest in hashes.items()]
    source_provenance = '; '.join(f"{s}: weight={f.attrs['trust_score']:g}, date={f.attrs['dataset_date'] or 'unknown'}"
                                 for s, f in datasets.items())
    ref = commit if commit != 'unversioned checkout' else 'main'
    return f'''# Full-data density and consistency

**{len(pooled):,} source records → {len(fused):,} output entities, including {len(merged):,}
merged groups.** Across the 10 comparable attributes, density rises from
**{pct(density(pooled, COMPARABLE)[1])} to {pct(density(fused, COMPARABLE)[1])}** overall,
and from **{pct(density(matched, COMPARABLE)[1])} to {pct(post_score)}** within the fusion
cohort. Input consistency is **{pct(lecture_score)}** with the lecture denominator
and the missing-value policy below (**{pct(available_mean)}** when all-missing groups
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

Repository snapshot: `{commit}`. Runtime: Python {sys.version.split()[0]}, pandas
{pd.__version__}, uma-pydi {version('uma-pydi')}.

## Record coverage

- Source records: **{len(pooled):,}**; positive pairs: **{len(pairs):,}**.
- Merged groups: **{len(merged):,}**, containing **{len(matched):,}** source records.
- Unmatched records retained: **{len(groups) - len(merged):,}**.
- Full fused output: **{len(fused):,}** unique entities.
- Compared with the largest source ({largest}): **{gain:+,} entities ({100 * gain / len(datasets[largest]):+.2f}%)**.
- {intra} connected groups contain more than one record from a source. They are included
  as supplied by production matching; this analysis does not verify or change those matches.

{table(['Contributing sources', 'Output entities'], sorted(sources.items()))}

## Density

Following lecture slide 19, column density is populated cells / rows; table density is
populated cells / (rows × attributes). `id`, `source`, and provenance metadata are excluded.
`False` and numeric zero count as populated. Missing elements, nulls, blank text, and
empty lists count as missing. A nonempty list is one populated cell; density does not
claim that its contents are correct or complete.

All 16 medicine attributes are reported. The comparable 10 are the same scope as the
team's fusion experiment: {', '.join(f'`{a}`' for a in COMPARABLE)}.
The remaining six describe jurisdiction-specific dates, status and policy flags;
their absence in another jurisdiction is not automatically a data defect.

{table(['Dataset / cohort', 'Rows', 'Density: all 16', 'Density: comparable 10'], overview)}

{table(['Attribute', *frames], per_attribute)}

Full-output change versus {largest}: **{delta16:+.2f} percentage points** across all 16
attributes; **{delta10:+.2f} points** across the comparable 10. A density decrease can
coexist with wider entity coverage when sparse records from other sources are retained.
The matched-input / merged-output rows isolate the fusion cohort; they still compare
source-record rows before fusion with one row per entity afterwards.

## Consistency of the matched sources

Following lecture slides 20 and 22, compare values within connected identity groups.
Use all **{len(merged):,}** multi-record groups from the full data, excluding singletons
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
uses all {len(merged):,} entities as denominator. **Available-only score** excludes the
all-missing entities, making the denominator convention comparable to the team's PyDI
experiment. It is a second view of the same counts, not accuracy.

{table(['Attribute', 'All missing', 'One value only', '2+ values agree', 'Conflict', 'Lecture score', 'Available-only'], cons_rows)}

Mean lecture consistency (10 attributes × {len(merged):,} entities): **{pct(lecture_score)}**.
Mean available-only attribute score: **{pct(available_mean)}**.
Most conflicting attributes: {findings}.
Counts depend on the supplied matches and the explicit comparison rules. For example,
different ingredient salts or dose sets can produce a conflict without proving a source error.

## Post-fusion interpretation and checks

The merged XML has one exported value/list per attribute per entity. Under the same
lecture denominator and missing-value policy, its structural consistency is
**{pct(post_score)}** for the {len(merged):,} merged entities, exactly their comparable-10
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
- Fused `activeSubstanceCount` versus distinct ingredient-list size: **{mismatches} mismatches**.
- SHA-256 checks confirmed all listed inputs were unchanged during this run.

The fused XML extends the single-source schema, so it is read with its export format
instead of being incorrectly validated as a single-source XML. These checks establish
coverage and structural alignment, not a replay of the fusion rules or external truth.
The current export uses a representative source record ID for each group; the script
also accepts PyDI's concatenated-member ID format without splitting medicine names.
Loader provenance remains {source_provenance}. Unknown historical source dates are
not inferred from Git dates. Source weights and dates do not alter these unweighted metrics.
Previously investigated strength issues remain separate; no corrections are applied here.

For a later release, rerun this command after the matching CSV and full fused XML are
updated together. No manual refresh of table values is needed.

## References and reproducibility

- [WDI Data Fusion lecture, slides 19–22](https://www.uni-mannheim.de/media/Einrichtungen/dws/Files_Teaching/Web_Data_Integration/HWS2026/WDI06-DataFusion-HWS2026.pdf): density, consistency, accuracy and comparison rules.
- [Quality/Fusion exercise, slides 16–17 and 20](https://github.com/gabegagster/wdi-drug-integration/blob/{ref}/docs/slides/WDI-Exercise-Quality-Fusion-HWS2026.pdf): input/merged density, consistency, and gain over the largest source.
- [Team fusion experiment](https://github.com/gabegagster/wdi-drug-integration/blob/{ref}/notebooks/data_fusion_rule_experiment/report.md): the 10-attribute scope and distinction from sample accuracy.

Input fingerprints (SHA-256):

{table(['Repository path', 'SHA-256'], evidence)}
'''


def default_root():
    for candidate in (Path.cwd(), *Path(__file__).resolve().parents):
        if (candidate / 'src/data_fusion/loader.py').is_file():
            return candidate
    return Path.cwd()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-root', type=Path, default=default_root())
    parser.add_argument('--pairs', type=Path, default=Path('data/3_fused/candidate_correspondences_1to1.csv'))
    parser.add_argument('--fused', type=Path, default=Path('data/9_fusion_xml_final/fused_medicines.xml'))
    parser.add_argument('--output', type=Path, default=Path('role1_metrics.md'))
    args = parser.parse_args()
    root = args.project_root.resolve()
    pairs_path, fused_path, output = [(root / p).resolve() for p in (args.pairs, args.fused, args.output)]
    try:
        if output.suffix.lower() != '.md' or any(output.is_relative_to(root / p)
                                               for p in ('data', 'src/mapforce')):
            raise ValueError('Choose a Markdown output outside original data/schema folders.')
        sys.path.insert(0, str(root))
        from src.data_fusion.loader import load_datasets, SOURCE_FILES
        from src.data_fusion.correspondence_prep import prepare_correspondences
        paths = [root / 'data/4_translated_mapforce' / f for f in SOURCE_FILES.values()]
        paths += [pairs_path, fused_path, root / 'src/mapforce/schema/medicines.xsd']
        paths += sorted((root / 'src/mapforce/lookups').glob('*.xml'))
        paths += [root / 'src/data_fusion' / f for f in ('loader.py', 'correspondence_prep.py', 'fusion.py')]
        if output in paths or (output.exists() and any(output.samefile(p) for p in paths)):
            raise ValueError('The report output must differ from every input.')
        hashes = {path: sha256(path) for path in paths}
        print('Loading all three source XMLs and the existing fused export...', flush=True)
        datasets = load_datasets(project_root=root)
        pairs = prepare_correspondences(pairs_path, datasets)
        groups = build_record_groups_from_correspondences(list(datasets.values()), pairs, id_column='id')
        fused = read_fused(fused_path)
        merged_mask = align_fused(groups, fused)
        try:
            commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root,
                                             text=True, stderr=subprocess.DEVNULL).strip()
        except (OSError, subprocess.CalledProcessError):
            commit = 'unversioned checkout'
        report = make_report(root, datasets, pairs, groups, fused, merged_mask, hashes, commit)
        if any(sha256(path) != digest for path, digest in hashes.items()):
            raise ValueError('An input changed during the run; rerun on a stable snapshot.')
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(report, encoding='utf-8')
        print(f'Source records: {sum(len(f) for f in datasets.values()):,}; pairs: {len(pairs):,}')
        print(f'Fused entities: {len(fused):,}; merged groups: {sum(merged_mask):,}')
        print(f'Fused density: {pct(density(fused, ATTRIBUTES)[1])} (16 attributes); '
              f'{pct(density(fused, COMPARABLE)[1])} (10 comparable attributes)')
        print(f'Inputs unchanged. Report: {output}')
    except (OSError, ValueError, ImportError, etree.LxmlError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f'Metrics failed: {exc}\n')


if __name__ == '__main__':
    main()
