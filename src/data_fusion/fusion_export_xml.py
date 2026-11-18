"""Export fused medicine records to XML."""

from pathlib import Path

from lxml import etree
import pandas as pd


def fusion_export_xml(df: pd.DataFrame, output_path: Path | str | None = None) -> Path:
    """Write fused medicines to XML (defaulting to fused_medicines.xml in cwd).

    Parameters
    ----------
    df : pandas.DataFrame
        PyDI fusion output with medicine fields, ``_id``, and
        ``_fusion_source_datasets``. Ingredients are lists of names;
        strengths are lists of (value, unit) pairs.
    output_path : pathlib.Path | str | None, optional
        Optional target XML path. Defaults to ``Path.cwd() / 'fused_medicines.xml'``.

    Returns
    -------
    pathlib.Path
        Absolute path of the written XML file. An existing file is replaced.

    Notes
    -----
    Missing fields are omitted. Multiple sources and scalar-field lists are
    joined with "; ". Multi-source values extend the input schema convention.
    """
    fields = (
        'brandName', 'activeSubstances', 'activeSubstanceCount',
        'licenceHolder', 'regulatoryStatus', 'productClass', 'atcCode',
        'generic', 'biosimilar', 'orphanMedicine', 'dosageForm', 'route',
        'strengths', 'usApprovalDate', 'euAuthorisationDate', 'caStatusDate',
    )
    boolean_fields = {'generic', 'biosimilar', 'orphanMedicine'}
    root = etree.Element('medicines')

    # Build Records
    for row in df.to_dict('records'):
        medicine = etree.SubElement(root, 'medicine')
        etree.SubElement(medicine, 'id').text = str(row['_id'])
        sources = sorted(set(row['_fusion_source_datasets']))
        etree.SubElement(medicine, 'source').text = '; '.join(sources)

        for field in fields:
            value = row[field]
            if isinstance(value, (list, tuple, set)):
                if not value:
                    continue
            elif pd.isna(value):
                continue

            element = etree.SubElement(medicine, field)
            if field == 'activeSubstances':
                for substance in value:
                    etree.SubElement(element, 'activeSubstance').text = substance
            elif field == 'strengths':
                for amount, unit in value:
                    strength = etree.SubElement(element, 'strength')
                    etree.SubElement(strength, 'value').text = format(amount, 'f')
                    if unit is not None and not pd.isna(unit):
                        etree.SubElement(strength, 'unit').text = unit
            elif field in boolean_fields:
                element.text = str(bool(value)).lower()
            elif field == 'activeSubstanceCount':
                element.text = str(int(value))
            elif isinstance(value, (list, tuple, set)):
                element.text = '; '.join(sorted(str(item) for item in value))
            else:
                element.text = str(value)

    # Write XML
    target = (
        Path(output_path).resolve()
        if output_path is not None
        else (Path.cwd() / 'fused_medicines.xml').resolve()
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    etree.ElementTree(root).write(
        str(target), encoding='UTF-8', xml_declaration=True,
        pretty_print=True,
    )
    return target
