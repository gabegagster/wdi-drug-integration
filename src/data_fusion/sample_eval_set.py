"""Sample multi-source medicine clusters for the data fusion evaluation set.

Draws a stratified random sample of 30-40 multi-source clusters from the Phase II
cluster file and writes a verification worksheet with one row per medicine.
For every evaluated attribute, the worksheet shows the values of all source
records side by side (``src_<attr>``) next to an empty ``gold_<attr>`` column
that is filled in by hand from external references (DailyMed / Drugs@FDA, EMA EPAR,
Health Canada DPD, WHO INN / ATC).

No PyDI pipeline code is involved: the script only reads the clusters and the
integrated XMLs. Like the exercise evaluation set, each medicine is identified by
the ID of one of its records (``eval_id``), so the fused record can be found
through ``_fusion_sources``.

Usage (from the repository root):
    python src/data_fusion/sample_eval_set.py
    python src/data_fusion/sample_eval_set.py --n 36 --seed 42
"""

from __future__ import annotations

import argparse
import xml.etree.ElementTree as ET
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
CLUSTERS = ROOT / "data/3_fused/candidate_medicine_clusters.csv"
XML_DIR = ROOT / "data/4_translated_mapforce"
OUT_DIR = ROOT / "data/8_fusion_eval"

# Attributes verified per medicine (10). Dates are left out: each date comes from a
# single source (usApprovalDate = FDA, euAuthorisationDate = EMA, caStatusDate = DPD),
# so there is no conflict to resolve.
ATTRIBUTES = [
    "brandName", "activeSubstances", "activeSubstanceCount", "licenceHolder",
    "productClass", "atcCode", "dosageForm", "route", "strengths", "biosimilar",
]

# Target share of the sample per source combination. Three-way clusters are
# over-sampled because they contain the most conflicts.
STRATA = {
    "DPD; EMA; FDA": 0.34,
    "DPD; FDA": 0.22,
    "DPD; EMA": 0.22,
    "EMA; FDA": 0.22,
}

# Record used as the reference ID of a medicine (first source present).
EVAL_ID_PRIORITY = ["FDA", "EMA", "DPD"]


def _text(el: ET.Element | None) -> str:
    return (el.text or "").strip() if el is not None else ""


def load_records() -> dict[str, dict[str, str]]:
    """Read all three integrated XMLs into {record_id: {attribute: value}}."""
    records: dict[str, dict[str, str]] = {}
    for src in ("dpd", "ema", "fda"):
        tree = ET.parse(XML_DIR / f"{src}_medicines.xml")
        for med in tree.getroot().iter("medicine"):
            rec: dict[str, str] = {}
            for child in med:
                tag = child.tag
                if tag == "activeSubstances":
                    rec[tag] = "; ".join(_text(s) for s in child)
                elif tag == "strengths":
                    rec[tag] = "; ".join(
                        f"{_text(s.find('value'))} {_text(s.find('unit'))}".strip() for s in child
                    )
                else:
                    rec[tag] = _text(child)
            records[rec["id"]] = rec
    return records


def cluster_members(cl: pd.Series) -> dict[str, str]:
    """{source: record_id} of a cluster (IDs contain '; ', so use the per-source columns)."""
    members = {}
    for src in ("DPD", "EMA", "FDA"):
        val = cl[f"{src.lower()}_ids"]
        if isinstance(val, str) and val:
            members[src] = val
    return members


def stratified_sample(pool: pd.DataFrame, n: int, seed: int) -> pd.DataFrame:
    quotas = {k: round(share * n) for k, share in STRATA.items()}
    quotas["DPD; EMA; FDA"] += n - sum(quotas.values())  # rounding remainder
    parts = []
    for stratum, k in quotas.items():
        group = pool[pool["sources"] == stratum]
        parts.append(group.sample(n=min(k, len(group)), random_state=seed))
    sample = pd.concat(parts, ignore_index=True)
    assert sample["cluster_id"].is_unique, "duplicate cluster IDs in sample"
    return sample


def build_worksheet(sample: pd.DataFrame, records: dict[str, dict[str, str]]) -> pd.DataFrame:
    rows = []
    for _, cl in sample.iterrows():
        by_source = cluster_members(cl)
        eval_id = next(by_source[s] for s in EVAL_ID_PRIORITY if s in by_source)
        row = {
            "cluster_id": cl["cluster_id"],
            "sources": cl["sources"],
            "eval_id": eval_id,
            "reference_source": eval_id.split("_", 1)[0],
            "dpd_id": by_source.get("DPD", ""),
            "ema_id": by_source.get("EMA", ""),
            "fda_id": by_source.get("FDA", ""),
        }
        for attr in ATTRIBUTES:
            vals = [f"{s}: {records[m].get(attr, '')}" for s, m in by_source.items()
                    if records[m].get(attr, "")]
            row[f"src_{attr}"] = " | ".join(vals)
        for attr in ATTRIBUTES:
            row[f"gold_{attr}"] = ""
        row.update({"evidence_urls": "", "verified_by": "", "verified_on": "", "notes": ""})
        rows.append(row)
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--n", type=int, default=36, help="clusters to sample (30-40)")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--clusters", type=Path, default=CLUSTERS)
    parser.add_argument("--all-classes", action="store_true",
                        help="also keep veterinary / disinfectant products")
    args = parser.parse_args()
    if not 30 <= args.n <= 40:
        parser.error("--n must be between 30 and 40")

    clusters = pd.read_csv(args.clusters)
    records = load_records()

    # Eligible clusters: at least two sources, one record per source (unambiguous
    # reference), and by default human medicines only (external references exist).
    pool = clusters[clusters["is_cross_dataset"] & ~clusters["has_intra_conflict"]].copy()
    if not args.all_classes:
        human = pool.apply(lambda cl: all(records[m].get("productClass") == "Human"
                                          for m in cluster_members(cl).values()), axis=1)
        pool = pool[human]
    print(f"Eligible clusters: {len(pool):,} of {len(clusters):,}")

    sample = stratified_sample(pool, n=args.n, seed=args.seed)
    sheet = build_worksheet(sample, records)

    order = {k: i for i, k in enumerate(STRATA)}
    sheet = (sheet.assign(_o=sheet["sources"].map(order))
             .sort_values(["_o", "cluster_id"]).drop(columns="_o").reset_index(drop=True))
    sheet.insert(0, "row", range(1, len(sheet) + 1))

    assert sheet["cluster_id"].is_unique, "duplicate cluster IDs"
    assert sheet["eval_id"].is_unique, "duplicate evaluation IDs"
    assert 30 <= len(sheet) <= 40

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / "fusion_eval_worksheet.csv"
    sheet.to_csv(out, index=False)
    print(f"Sampled {len(sheet)} clusters (seed {args.seed}) -> {out.relative_to(ROOT)}")
    print(sheet["sources"].value_counts().to_string())


if __name__ == "__main__":
    main()
