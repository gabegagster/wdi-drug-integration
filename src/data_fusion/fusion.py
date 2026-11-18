"""Fuse medicine XMLs using the rules selected in the fusion experiment."""

import argparse
from collections import Counter
import logging
from pathlib import Path

import pandas as pd
from PyDI.fusion import DataFusionEngine, DataFusionStrategy, prefer_higher_trust, voting

from src.data_fusion.correspondence_prep import prepare_correspondences
from src.data_fusion.fusion_export_xml import fusion_export_xml
from src.data_fusion.loader import load_datasets


logger = logging.getLogger(__name__)


def medicine_fusion(input_path: Path | str) -> pd.DataFrame:
    """Fuse the three medicine datasets and export the final XML.

    Parameters
    ----------
    input_path : pathlib.Path or str
        Correspondence CSV with id1/id2 and optional match and similarity columns.
        Relative paths are resolved from the current working directory.

    Returns
    -------
    pandas.DataFrame
        All fused and unmatched medicines, including PyDI source-record metadata.
        XML is written to data/9_fusion_xml_final/fused_medicines.xml.

    Raises
    ------
    ValueError
        Source XMLs or correspondence IDs, labels and scores fail the existing
        loader or correspondence-preparation requirements.

    Notes
    -----
    Uses the experiment's lowercase and whitespace normalization. Fields outside
    the experiment retain PyDI's default first-available-value behavior.
    """
    project_root = Path(__file__).resolve().parents[2]
    output_path = project_root / 'data/9_fusion_xml_final/fused_medicines.xml'
    set_attributes = ['activeSubstances', 'atcCode', 'dosageForm', 'route', 'strengths']
    priority_orders = {
        'FDA': ['FDA', 'EMA', 'DPD'],
        'DPD': ['DPD', 'EMA', 'FDA'],
    }
    selected_rules = {
        'brandName': 'FDA',
        'activeSubstances': 'DPD',
        'licenceHolder': 'FDA',
        'productClass': 'Voting',
        'atcCode': 'Voting',
        'dosageForm': 'FDA',
        'route': 'Voting',
        'strengths': 'FDA',
        'biosimilar': 'Voting',
    }

    # Load Data
    logger.info('Loading medicine XMLs')
    datasets = load_datasets(project_root=project_root)
    for source, frame in datasets.items():
        logger.info('%s: %s source records', source, f'{len(frame):,}')

    logger.info('Loading correspondences: %s', input_path)
    correspondences = prepare_correspondences(input_path, datasets)
    logger.info('Prepared %s positive correspondence pairs', f'{len(correspondences):,}')

    # Normalize Fusion Inputs
    for frame in datasets.values():
        for attribute in ['brandName', 'licenceHolder', 'productClass']:
            frame[attribute] = frame[attribute].map(
                lambda value: ' '.join(value.split()).lower() if value is not None else None
            )
        for attribute in set_attributes:
            if attribute == 'strengths':
                # Preserve numeric amounts and case-sensitive strength units.
                frame[attribute] = frame[attribute].map(
                    lambda values: [(amount.normalize(), ' '.join(unit.split()) if unit is not None else None)
                                    for amount, unit in values] if values is not None else None
                )
            else:
                # Ingredients are lists; ATC codes, forms and routes are joined XML text.
                frame[attribute] = frame[attribute].map(
                    lambda value: sorted({' '.join(item.split()).lower()
                                          for item in (value.split('; ') if isinstance(value, str) else value)})
                    if value is not None else None
                )

    # Define Selected Rules
    strategy = DataFusionStrategy('Selected medicine rules')
    for attribute, rule in selected_rules.items():
        if rule == 'Voting':
            if attribute in set_attributes:
                # Vote on complete sets using hashable, consistently ordered values.
                strategy.add_attribute_fuser(
                    attribute, voting,
                    accessor=lambda row, field=attribute: tuple(sorted(row[field])) if row[field] is not None else None,
                )
            else:
                strategy.add_attribute_fuser(attribute, voting)
        else:
            strategy.add_attribute_fuser(
                attribute, prefer_higher_trust,
                trust_map={source: float(3 - rank) for rank, source in enumerate(priority_orders[rule])},
            )

    # Run Fusion
    logger.info('Running medicine fusion, including unmatched records')
    fused = DataFusionEngine(strategy).run(
        [frame.drop(columns='activeSubstanceCount') for frame in datasets.values()],
        correspondences, id_column='id', include_singletons=True,
    )
    fused['activeSubstanceCount'] = fused['activeSubstances'].map(
        lambda values: len(set(values)) if values is not None else None
    )

    # Summarize Sources
    source_counts = Counter(tuple(sorted(set(sources))) for sources in fused['_fusion_source_datasets'])
    grouped = int(fused['_fusion_sources'].map(len).gt(1).sum())
    logger.info('Output entities: %s', f'{len(fused):,}')
    logger.info('Merged entities: %s; unmatched records: %s', f'{grouped:,}', f'{len(fused) - grouped:,}')
    for sources, count in sorted(source_counts.items()):
        logger.info('%s: %s entities', ' + '.join(sources), f'{count:,}')

    # Export XML
    fusion_export_xml(fused, output_path)
    logger.info('Saved fused XML: %s', output_path)
    return fused


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input_path', type=Path, help='Positive correspondence pair CSV')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
    medicine_fusion(args.input_path)
