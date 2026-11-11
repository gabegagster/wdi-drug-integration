"""Tri-dataset connected-components clustering and overlap validation.

Consolidates pairwise match correspondences across Health Canada (DPD),
European Medicines Agency (EMA), and US FDA into unified medicine clusters.
Verifies the course requirement of >= 1,000 cross-dataset overlapping entities.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import networkx as nx
import pandas as pd


def get_source_from_id(entity_id: str) -> str:
    """Extract dataset source prefix from entity ID (e.g. 'DPD_123' -> 'DPD')."""
    if entity_id.startswith("DPD_"):
        return "DPD"
    elif entity_id.startswith("EMA_"):
        return "EMA"
    elif entity_id.startswith("FDA_"):
        return "FDA"
    return "UNKNOWN"


def enforce_greedy_one_to_one(
    match_pairs: pd.DataFrame,
    score_col: str = "score",
) -> tuple[pd.DataFrame, int]:
    """Enforce strict 1:1 matching greedily by descending confidence score.

    Iterates through candidate match correspondences and eliminates 1:N or N:M
    conflicts per source pair.

    Returns:
        tuple of (filtered_df, removed_conflicts_count).
    """
    df = match_pairs.copy()
    if "match" in df.columns:
        df = df[df["match"] == 1]

    if score_col not in df.columns:
        df[score_col] = 1.0

    # Ensure source_pair exists or infer from IDs
    if "source_pair" not in df.columns:
        df["source_pair"] = [
            f"{get_source_from_id(str(r['id1'])).lower()}_{get_source_from_id(str(r['id2'])).lower()}"
            for _, r in df.iterrows()
        ]

    df = df.sort_values(by=score_col, ascending=False)

    kept_rows = []
    removed_conflicts = 0

    for _, group in df.groupby("source_pair"):
        matched_left: set[str] = set()
        matched_right: set[str] = set()
        for _, row in group.iterrows():
            id1, id2 = str(row["id1"]), str(row["id2"])
            if id1 not in matched_left and id2 not in matched_right:
                matched_left.add(id1)
                matched_right.add(id2)
                kept_rows.append(row)
            else:
                removed_conflicts += 1

    df_kept = pd.DataFrame(kept_rows)
    return df_kept, removed_conflicts


def cluster_correspondences(
    match_pairs: pd.DataFrame | Sequence[tuple[str, str]],
    output_csv: Path | str | None = None,
    enforce_one_to_one: bool = False,
) -> tuple[pd.DataFrame, dict[str, int | float]]:
    """Cluster pairwise match correspondences using connected components.

    Args:
        match_pairs: DataFrame with ['id1', 'id2'] columns (optionally 'match' where match=1),
                     or a sequence of (id1, id2) tuples.
        output_csv: Optional destination path for cluster mappings.
        enforce_one_to_one: If True, applies greedy conflict resolution to ensure 1:1 matching.

    Returns:
        tuple of (clusters_df, metrics_dict).
    """
    graph = nx.Graph()
    conflicts_resolved = 0

    if isinstance(match_pairs, pd.DataFrame):
        df_edges = match_pairs.copy()
        if "match" in df_edges.columns:
            df_edges = df_edges[df_edges["match"] == 1]

        if enforce_one_to_one:
            df_edges, conflicts_resolved = enforce_greedy_one_to_one(df_edges)

        for _, row in df_edges.iterrows():
            id1, id2 = str(row["id1"]), str(row["id2"])
            graph.add_edge(id1, id2)
    else:
        for pair in match_pairs:
            graph.add_edge(str(pair[0]), str(pair[1]))

    components = list(nx.connected_components(graph))
    # Sort clusters descending by size, then by first ID for determinism
    components.sort(key=lambda c: (-len(c), sorted(c)[0]))

    cluster_rows = []
    intra_source_conflicts = 0

    for idx, comp in enumerate(components, start=1):
        cluster_id = f"CLUSTER_{idx:05d}"
        members = sorted(comp)
        sources = [get_source_from_id(m) for m in members]
        distinct_sources = sorted(set(sources))

        # Check for intra-source duplicates (1:N or N:M links)
        source_counts = {s: sources.count(s) for s in distinct_sources}
        has_intra_conflict = any(cnt > 1 for cnt in source_counts.values())
        if has_intra_conflict:
            intra_source_conflicts += 1

        dpd_ids = [m for m in members if m.startswith("DPD_")]
        ema_ids = [m for m in members if m.startswith("EMA_")]
        fda_ids = [m for m in members if m.startswith("FDA_")]

        cluster_rows.append({
            "cluster_id": cluster_id,
            "cluster_size": len(members),
            "source_count": len(distinct_sources),
            "sources": "; ".join(distinct_sources),
            "is_cross_dataset": len(distinct_sources) >= 2,
            "is_three_way": len(distinct_sources) == 3,
            "has_intra_conflict": has_intra_conflict,
            "dpd_ids": "; ".join(dpd_ids) if dpd_ids else None,
            "ema_ids": "; ".join(ema_ids) if ema_ids else None,
            "fda_ids": "; ".join(fda_ids) if fda_ids else None,
            "all_members": "; ".join(members),
        })

    clusters_df = pd.DataFrame(cluster_rows)

    # Compute key evaluation metrics
    total_clusters = len(clusters_df)
    cross_dataset_clusters = int((clusters_df["source_count"] >= 2).sum()) if total_clusters else 0
    three_way_clusters = int((clusters_df["source_count"] == 3).sum()) if total_clusters else 0

    dpd_ema_only = int(
        (clusters_df["sources"] == "DPD; EMA").sum()
    ) if total_clusters else 0
    dpd_fda_only = int(
        (clusters_df["sources"] == "DPD; FDA").sum()
    ) if total_clusters else 0
    ema_fda_only = int(
        (clusters_df["sources"] == "EMA; FDA").sum()
    ) if total_clusters else 0

    metrics = {
        "total_clusters": total_clusters,
        "total_nodes_clustered": graph.number_of_nodes(),
        "total_correspondence_edges": graph.number_of_edges(),
        "cross_dataset_overlap_entities": cross_dataset_clusters,
        "three_way_overlap_entities": three_way_clusters,
        "dpd_ema_pairwise_only": dpd_ema_only,
        "dpd_fda_pairwise_only": dpd_fda_only,
        "ema_fda_pairwise_only": ema_fda_only,
        "intra_source_conflict_clusters": intra_source_conflicts,
        "conflicts_resolved": conflicts_resolved,
        "requirement_1000_met": bool(cross_dataset_clusters >= 1000),
    }

    if output_csv:
        out_path = Path(output_csv)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        clusters_df.to_csv(out_path, index=False)
        print(f"Saved {len(clusters_df)} clusters to {out_path}")

    return clusters_df, metrics


def print_clustering_report(metrics: dict[str, int | float]) -> str:
    """Print and return a formatted markdown evaluation report."""
    status_icon = "PASS (>= 1,000 requirement met)" if metrics["requirement_1000_met"] else "FAIL (< 1,000)"

    report = f"""# Tri-Dataset Clustering & Identity Resolution Report

## Overview
- **Total Correspondence Edges:** {metrics['total_correspondence_edges']:,}
- **Total Entities Clustered:** {metrics['total_nodes_clustered']:,}
- **Total Clusters Formed:** {metrics['total_clusters']:,}
- **Cross-Dataset Overlapping Entities (>=2 sources):** {metrics['cross_dataset_overlap_entities']:,}
- **3-Way Overlapping Entities (DPD + EMA + FDA):** {metrics['three_way_overlap_entities']:,}
- **Course Requirement (>= 1,000 Overlap):** **{status_icon}**

## Overlap Breakdown by Jurisdiction Combination
| Source Combination | Clusters | Share of Overlapping Entities |
| :--- | ---: | ---: |
| **All 3 Sources (DPD + EMA + FDA)** | {metrics['three_way_overlap_entities']:,} | {metrics['three_way_overlap_entities'] / max(1, metrics['cross_dataset_overlap_entities']):.1%} |
| **DPD + FDA (Canada & US only)** | {metrics['dpd_fda_pairwise_only']:,} | {metrics['dpd_fda_pairwise_only'] / max(1, metrics['cross_dataset_overlap_entities']):.1%} |
| **DPD + EMA (Canada & EU only)** | {metrics['dpd_ema_pairwise_only']:,} | {metrics['dpd_ema_pairwise_only'] / max(1, metrics['cross_dataset_overlap_entities']):.1%} |
| **EMA + FDA (EU & US only)** | {metrics['ema_fda_pairwise_only']:,} | {metrics['ema_fda_pairwise_only'] / max(1, metrics['cross_dataset_overlap_entities']):.1%} |
| **Total Overlapping Medicine Entities** | **{metrics['cross_dataset_overlap_entities']:,}** | **100.0%** |

## Cluster Consistency & Multi-Mapping
- **Clusters with intra-source variations (1:N or N:M):** {metrics['intra_source_conflict_clusters']:,}
"""
    return report


def main():
    parser = argparse.ArgumentParser(description="Tri-dataset connected components clustering.")
    parser.add_argument(
        "--inputs",
        nargs="+",
        help="Input CSV file(s) containing pairwise matches ('id1', 'id2', and optionally 'match').",
    )
    parser.add_argument(
        "--output",
        default="data/3_fused/medicine_clusters.csv",
        help="Output CSV file path for cluster assignments.",
    )
    parser.add_argument(
        "--enforce-one-to-one",
        action="store_true",
        help="Apply greedy 1:1 conflict resolution before clustering.",
    )
    args = parser.parse_args()

    if not args.inputs:
        print("No inputs supplied. Running offline smoke check with synthetic data...")
        synthetic_pairs = [
            ("DPD_1", "FDA_1"),
            ("FDA_1", "EMA_1"),  # forms 3-way cluster
            ("DPD_2", "FDA_2"),  # 2-way cluster
            ("DPD_3", "EMA_3"),  # 2-way cluster
            ("EMA_4", "FDA_4"),  # 2-way cluster
            ("DPD_5a", "FDA_5"),
            ("DPD_5b", "FDA_5"),  # 1:N variant cluster
        ]
        clusters_df, metrics = cluster_correspondences(
            synthetic_pairs, enforce_one_to_one=args.enforce_one_to_one
        )
        print(print_clustering_report(metrics))
        print("PASS: clustering smoke test completed.")
        return

    dfs = [pd.read_csv(p) for p in args.inputs]
    combined_df = pd.concat(dfs, ignore_index=True)
    clusters_df, metrics = cluster_correspondences(
        combined_df, output_csv=args.output, enforce_one_to_one=args.enforce_one_to_one
    )
    report_text = print_clustering_report(metrics)
    print(report_text)


if __name__ == "__main__":
    main()
