"""Load the three medicine XMLs into schema-validated, PyDI-ready DataFrames."""
from __future__ import annotations

import argparse
from datetime import date, datetime
from decimal import Decimal
import hashlib
import math
from pathlib import Path
import re
import sys

from lxml import etree
import pandas as pd

# Works in the repository root or this local sibling handoff folder.
PROJECT_ROOT = Path(__file__).resolve().parent
if not (PROJECT_ROOT / 'src/mapforce/schema/medicines.xsd').is_file():
    PROJECT_ROOT = PROJECT_ROOT.parent / 'wdi-drug-integration'
DEFAULT_XML_DIR = PROJECT_ROOT / 'data/4_translated_mapforce'
DEFAULT_SCHEMA = PROJECT_ROOT / 'src/mapforce/schema/medicines.xsd'
DEFAULT_LOOKUP_DIR = PROJECT_ROOT / 'src/mapforce/lookups'
SOURCE_FILES = {'DPD': 'dpd_medicines.xml', 'EMA': 'ema_medicines.xml', 'FDA': 'fda_medicines.xml'}
REFERENCE_COUNTS = {'DPD': 41636, 'EMA': 2648, 'FDA': 8175}
DATE_FIELDS = {'usApprovalDate', 'euAuthorisationDate', 'caStatusDate'}
BOOLEANS = {'generic', 'biosimilar', 'orphanMedicine'}
LOOKUP_FILES = {'dosageForm': 'dosage_form.xml', 'route': 'route.xml', 'strengthUnit': 'strength_unit.xml'}
MEDICINE_ATTRIBUTES = (
    'brandName', 'activeSubstances', 'activeSubstanceCount', 'licenceHolder',
    'regulatoryStatus', 'productClass', 'atcCode', 'generic', 'biosimilar',
    'orphanMedicine', 'dosageForm', 'route', 'strengths', 'usApprovalDate',
    'euAuthorisationDate', 'caStatusDate',
)
COLUMNS = ('id', 'source', *MEDICINE_ATTRIBUTES)

# Explicit equal-weight baseline; historical snapshot dates are unknown.
SOURCE_METADATA = {source: dict(trust_score=1.0, release_date=None, retrieved_at=None,
                               evidence=None) for source in SOURCE_FILES}

def _parse_xml(raw: bytes, path: Path):
    parser = etree.XMLParser(resolve_entities=False, no_network=True,
                             load_dtd=False, recover=False,
                             remove_comments=True, remove_pis=True)
    try:
        tree = etree.fromstring(raw, parser=parser).getroottree()
    except etree.XMLSyntaxError as exc:
        raise ValueError(f'{path}: malformed XML: {exc}') from exc
    if tree.docinfo.doctype:
        raise ValueError(f'{path}: DTD declarations are forbidden')
    return tree


def _schema(path: Path):
    raw = path.read_bytes()
    tree = _parse_xml(raw, path)
    ns = {'xs': 'http://www.w3.org/2001/XMLSchema'}
    if tree.xpath('//xs:import | //xs:include | //xs:redefine', namespaces=ns):
        raise ValueError(f'{path}: external schema references are forbidden')
    return etree.XMLSchema(tree), hashlib.sha256(raw).hexdigest()


def _text(element):
    value = element.text
    if value is None or not value.strip():
        raise ValueError(f'<{element.tag}> must not be empty or whitespace-only')
    return value


def _lookups(directory):
    vocabularies, metadata = {}, {}
    for field, filename in LOOKUP_FILES.items():
        path = (Path(directory) / filename).resolve()
        raw = path.read_bytes()
        tree = _parse_xml(raw, path)
        if tree.getroot().tag != 'lookup' or tree.getroot().get('name') != field:
            raise ValueError(f'{path}: expected lookup {field}')
        entries = tree.getroot().findall('entry')
        if not entries or any('std' not in e.attrib or 'raw' not in e.attrib for e in entries):
            raise ValueError(f'{path}: malformed or empty lookup')
        values = {e.get('std') for e in entries if e.get('std')}
        if field != 'strengthUnit':
            values = {part for value in values for part in value.split('; ')}
        vocabularies[field] = values
        metadata[field] = {'file': str(path), 'sha256': hashlib.sha256(raw).hexdigest()}
    return vocabularies, metadata


def _record(medicine, expected_source, vocabularies):
    row = dict.fromkeys(COLUMNS)
    for element in medicine:
        name = element.tag
        if name not in row:
            raise ValueError(f'Unknown medicine attribute: {name}')
        if name == 'activeSubstances':
            row[name] = [_text(child) for child in element]
        elif name == 'strengths':
            row[name] = []
            for strength in element:
                value = Decimal(_text(strength.find('value')).strip())
                unit_node = strength.find('unit')
                unit = None if unit_node is None else _text(unit_node)
                row[name].append((value, unit))
        else:
            value = _text(element)
            if name in BOOLEANS:
                row[name] = value.strip() in ('true', '1')
            elif name == 'activeSubstanceCount':
                row[name] = int(value)
            elif name in DATE_FIELDS:
                if re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', value) is None:
                    raise ValueError(f'{name} must use YYYY-MM-DD: {value!r}')
                date.fromisoformat(value)
                row[name] = value
            elif name in ('dosageForm', 'route'):
                parts = value.split('; ')
                if any(part not in vocabularies[name] for part in parts):
                    raise ValueError(f'Unknown {name} value: {value!r}')
                if parts != sorted(set(parts)):
                    raise ValueError(f'{name} must be alphabetically ordered without duplicates: {value!r}')
                row[name] = value
            else:
                row[name] = value
    if row['source'] != expected_source:
        raise ValueError(f"{row['id']}: expected source {expected_source}, got {row['source']}")
    if not row['id'].startswith(expected_source + '_'):
        raise ValueError(f"{row['id']}: ID prefix does not match source {expected_source}")
    return row


def load_source(xml_path, expected_source, schema_path=DEFAULT_SCHEMA, *,
                lookup_dir=DEFAULT_LOOKUP_DIR):
    """Return one source frame; optional missing values are Python None.

    Strings (including dates) retain their XML text. Numeric and boolean XML
    whitespace is collapsed according to XSD semantics. Strengths are ordered
    lists of (Decimal, optional unit) pairs. All columns use object dtype.
    Strength units retain their source text; schema-legal absent units remain None.
    Dates and lookup vocabularies follow the stricter project conventions.
    """
    if expected_source not in SOURCE_FILES:
        raise ValueError(f'Unsupported source: {expected_source}')
    path, xsd_path = Path(xml_path).resolve(), Path(schema_path).resolve()
    validator, schema_hash = _schema(xsd_path)
    vocabularies, lookup_metadata = _lookups(lookup_dir)
    raw = path.read_bytes()
    tree = _parse_xml(raw, path)
    try:
        validator.assertValid(tree)
    except etree.DocumentInvalid as exc:
        raise ValueError(f'{path}: XSD validation failed: {exc}') from exc
    if tree.getroot().tag != 'medicines' or not len(tree.getroot()):
        raise ValueError(f'{path}: expected a nonempty medicines document')
    rows = []
    for position, medicine in enumerate(tree.getroot(), start=1):
        try:
            rows.append(_record(medicine, expected_source, vocabularies))
        except ValueError as exc:
            raise ValueError(f"{path}: record {position}, ID={medicine.findtext('id')!r}: {exc}") from exc
    frame = pd.DataFrame(rows, columns=COLUMNS, dtype=object)
    if frame['id'].duplicated().any():
        raise ValueError(f'{path}: duplicate IDs')
    frame.attrs.update(dataset_name=expected_source, id_column='id',
                       source_file=str(path), source_sha256=hashlib.sha256(raw).hexdigest(),
                       schema_file=str(xsd_path), schema_sha256=schema_hash,
                       schema_validated=True, loader_format='medicine-xml-v1',
                       project_contract_validated=True, lookup_files=lookup_metadata)
    return frame


def _source_metadata(source, overrides):
    if not isinstance(overrides, dict) or set(overrides) - set(SOURCE_METADATA[source]):
        raise ValueError(f'{source}: use trust_score, release_date, retrieved_at and evidence')
    meta = {**SOURCE_METADATA[source], **overrides}
    score = meta['trust_score']
    if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score) or not 0 <= score <= 1:
        raise ValueError(f'{source}: trust_score must be finite and between 0 and 1')
    release, retrieved = meta['release_date'], meta['retrieved_at']
    if release is not None:
        if not isinstance(release, str) or date.fromisoformat(release).isoformat() != release:
            raise ValueError(f'{source}: release_date must be YYYY-MM-DD')
    if retrieved is not None:
        if not isinstance(retrieved, str):
            raise ValueError(f'{source}: retrieved_at must be an ISO timestamp string')
        parsed = datetime.fromisoformat(retrieved.replace('Z', '+00:00'))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError(f'{source}: retrieved_at needs a timezone')
    if (score != 1.0 or release is not None or retrieved is not None) and (
            not isinstance(meta['evidence'], str) or not meta['evidence'].strip()):
        raise ValueError(f'{source}: non-default weights/dates require an evidence reference')
    return meta


def load_datasets(project_root=None, *, xml_dir=None, source_metadata=None):
    """Return {'DPD': frame, 'EMA': frame, 'FDA': frame}; never repair source values.

    Missing cells are None; strengths are ordered (Decimal, unit) pairs.
    Provenance is in frame.attrs, preserving all 18 medicine columns.
    source_metadata optionally overrides the inline per-source weights/dates.
    """
    root = Path(project_root or PROJECT_ROOT).resolve()
    directory = Path(xml_dir) if xml_dir is not None else root / 'data/4_translated_mapforce'
    metadata = source_metadata or {}
    if set(metadata) - set(SOURCE_FILES):
        raise ValueError('Metadata must name only DPD, EMA or FDA')
    datasets = {}
    for source, filename in SOURCE_FILES.items():
        meta = _source_metadata(source, metadata.get(source, {}))
        frame = load_source(directory / filename, source, root / 'src/mapforce/schema/medicines.xsd',
                            lookup_dir=root / 'src/mapforce/lookups')
        frame.attrs.update(trust_score=float(meta['trust_score']),
            dataset_score=float(meta['trust_score']), dataset_date=meta['release_date'],
            source_release_date=meta['release_date'], source_retrieved_at=meta['retrieved_at'],
            metadata_evidence=meta['evidence'],
            trust_policy='equal_weight_baseline' if meta['trust_score'] == 1.0 else 'evidence_referenced_weight',
            source_date_status='unknown' if meta['release_date'] is None and meta['retrieved_at'] is None else 'evidence_referenced')
        datasets[source] = frame
    ids = [record_id for frame in datasets.values() for record_id in frame['id']]
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate IDs across sources')
    return datasets


def summarize_datasets(datasets):
    result = {}
    for source, frame in datasets.items():
        mismatch = sum(row.activeSubstanceCount is not None and
                       row.activeSubstanceCount != len(row.activeSubstances)
                       for row in frame.itertuples(index=False))
        result[source] = dict(records=len(frame), unique_ids=frame['id'].nunique(),
                              columns=len(frame.columns),
                              strength_entries=sum(len(s) for s in frame['strengths'] if s is not None),
                              substance_count_mismatches=mismatch)
    return result


def print_summary(datasets):
    """Show the loaded records and source metadata without loading them again."""
    print('XML loading complete')
    for source, frame in datasets.items():
        print(f"{source}: {len(frame):,} records; {len(frame.columns)} columns; "
              f"weight={frame.attrs['trust_score']}; source date={frame.attrs['dataset_date'] or 'unknown'}")
    print(f'Total: {sum(len(frame) for frame in datasets.values()):,} records')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-root', type=Path, default=PROJECT_ROOT)
    parser.add_argument('--xml-dir', type=Path)
    args = parser.parse_args()
    try:
        datasets = load_datasets(args.project_root, xml_dir=args.xml_dir)
        print_summary(datasets)
        return 0
    except (OSError, ValueError, etree.LxmlError) as exc:
        print(f'Load failed: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
