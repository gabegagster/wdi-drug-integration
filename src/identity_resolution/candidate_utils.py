"""Utilities for candidate loading, attribute joining, and entity resolution pre-filtering.

Integrates blocking candidate pairs from data/7_blocking_candidates/ with the
rich canonical XML records from data/4_translated_mapforce/ for matching and clustering.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import pandas as pd


def norm_text(val: Any) -> str:
    """Normalize text by converting to upper case and condensing whitespace."""
    if val is None or pd.isna(val):
        return ""
    return " ".join(re.sub(r"[^\w\s]", " ", str(val).upper()).split())


def parse_substances(subs_str: Any) -> set[str]:
    """Parse active substances into a clean set of normalized tokens."""
    if val_is_empty(subs_str):
        return set()
    parts = str(subs_str).split(";")
    return {
        " ".join(re.sub(r"[^\w\s]", " ", p.upper()).split())
        for p in parts
        if p.strip()
    }


def val_is_empty(val: Any) -> bool:
    """Return True if val is None, NaN, or whitespace."""
    return val is None or pd.isna(val) or not str(val).strip()


def load_xml_entities(
    xml_dir: Path | str = "data/4_translated_mapforce",
) -> dict[str, dict[str, Any]]:
    """Parse canonical XML datasets and return a dictionary keyed by entity ID.

    Returns:
        Dictionary mapping entity ID (e.g. 'DPD_3TC|LAMIVUDINE') to record dict:
        {
            'id': str,
            'source': 'DPD' | 'EMA' | 'FDA',
            'brandName': str,
            'activeSubstances': str (semicolon-separated),
            'activeSubstancesSet': set[str],
            'licenceHolder': str,
            'dosageForm': str,
            'route': str,
        }
    """
    xml_path = Path(xml_dir)
    entity_lookup: dict[str, dict[str, Any]] = {}

    sources = [("dpd", "DPD"), ("ema", "EMA"), ("fda", "FDA")]
    for file_stem, src_code in sources:
        fpath = xml_path / f"{file_stem}_medicines.xml"
        if not fpath.exists():
            continue

        tree = ET.parse(fpath)
        root = tree.getroot()
        for med in root.findall("medicine"):
            mid_el = med.find("id")
            if mid_el is None or not mid_el.text:
                continue
            mid = mid_el.text.strip()

            brand_el = med.find("brandName")
            brand = brand_el.text.strip() if brand_el is not None and brand_el.text else ""

            subs_el = med.find("activeSubstances")
            subs_list: list[str] = []
            if subs_el is not None:
                for sub in subs_el.findall("activeSubstance"):
                    if sub.text and sub.text.strip():
                        subs_list.append(sub.text.strip())
            subs_str = "; ".join(subs_list)

            holder_el = med.find("licenceHolder")
            holder = holder_el.text.strip() if holder_el is not None and holder_el.text else ""

            dosage_el = med.find("dosageForm")
            dosage = dosage_el.text.strip() if dosage_el is not None and dosage_el.text else ""

            route_el = med.find("route")
            route = route_el.text.strip() if route_el is not None and route_el.text else ""

            entity_lookup[mid] = {
                "id": mid,
                "source": src_code,
                "brandName": brand,
                "activeSubstances": subs_str,
                "activeSubstancesSet": parse_substances(subs_str),
                "licenceHolder": holder,
                "dosageForm": dosage,
                "route": route,
            }

    return entity_lookup


def enrich_candidate_dataframe(
    df: pd.DataFrame,
    entity_lookup: dict[str, dict[str, Any]] | None = None,
    xml_dir: Path | str = "data/4_translated_mapforce",
) -> pd.DataFrame:
    """Join canonical XML entity attributes onto candidate pairs (id1, id2).

    Produces DataFrame with columns expected by build_pair_prompt:
    [pair_id, source1, brandName1, activeSubstances1, licenceHolder1, dosageForm1,
     source2, brandName2, activeSubstances2, licenceHolder2, dosageForm2, ...]
    """
    if "brandName1" in df.columns and "brandName2" in df.columns:
        # Already enriched
        return df

    if entity_lookup is None:
        entity_lookup = load_xml_entities(xml_dir)

    df_out = df.copy()

    # Generate pair_id if missing
    if "pair_id" not in df_out.columns:
        df_out["pair_id"] = [
            f"{r['id1']}___{r['id2']}" for _, r in df_out.iterrows()
        ]

    # Map attributes for id1
    rec1 = [entity_lookup.get(str(x), {}) for x in df_out["id1"]]
    df_out["source1"] = [r.get("source", "DPD") for r in rec1]
    df_out["brandName1"] = [r.get("brandName", "") for r in rec1]
    df_out["activeSubstances1"] = [r.get("activeSubstances", "") for r in rec1]
    df_out["licenceHolder1"] = [r.get("licenceHolder", "") for r in rec1]
    df_out["dosageForm1"] = [r.get("dosageForm", "") for r in rec1]

    # Map attributes for id2
    rec2 = [entity_lookup.get(str(x), {}) for x in df_out["id2"]]
    df_out["source2"] = [r.get("source", "EMA") for r in rec2]
    df_out["brandName2"] = [r.get("brandName", "") for r in rec2]
    df_out["activeSubstances2"] = [r.get("activeSubstances", "") for r in rec2]
    df_out["licenceHolder2"] = [r.get("licenceHolder", "") for r in rec2]
    df_out["dosageForm2"] = [r.get("dosageForm", "") for r in rec2]

    return df_out


def load_blocking_candidates(
    candidate_dir: Path | str = "data/7_blocking_candidates",
    source_pair: str | None = None,
    enrich: bool = True,
    xml_dir: Path | str = "data/4_translated_mapforce",
) -> pd.DataFrame:
    """Load candidate pairs from data/7_blocking_candidates/.

    Args:
        candidate_dir: Directory containing candidate CSVs.
        source_pair: Optional filter ('dpd_ema', 'dpd_fda', 'ema_fda').
        enrich: If True, joins XML attributes onto candidate pairs.
        xml_dir: Directory containing target XMLs for attribute enrichment.

    Returns:
        Concatenated (and optionally enriched) DataFrame of candidate pairs.
    """
    cand_path = Path(candidate_dir)
    files = []
    if source_pair:
        files = [cand_path / f"{source_pair}_candidates.csv.gz"]
    else:
        files = [
            cand_path / "dpd_ema_candidates.csv.gz",
            cand_path / "dpd_fda_candidates.csv.gz",
            cand_path / "ema_fda_candidates.csv.gz",
        ]

    dfs = []
    for fp in files:
        if fp.exists():
            df = pd.read_csv(fp)
            dfs.append(df)

    if not dfs:
        return pd.DataFrame(columns=["source_pair", "id1", "id2"])

    combined = pd.concat(dfs, ignore_index=True)

    if enrich:
        entity_lookup = load_xml_entities(xml_dir)
        combined = enrich_candidate_dataframe(combined, entity_lookup=entity_lookup)

    return combined
