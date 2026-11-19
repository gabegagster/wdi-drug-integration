"""End-to-end project verification and ILIAS submission packaging tool.

Performs non-destructive Phase I to Phase III verification checks, computes
full-dataset entity-expansion and attribute-density audit metrics, and
optionally builds a clean submission bundle and ZIP archive containing the
report, source code, notebooks, and an XSD-validated data subset.

Usage (from repository root):
    python3 src/package_submission.py
    python3 src/package_submission.py --package
    python3 src/package_submission.py --package --include-model
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any

import pandas as pd
from lxml import etree

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "src" / "mapforce" / "schema") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src" / "mapforce" / "schema"))

from check_schema import SAMPLE_JSON, SAMPLE_XML, validate_json, validate_xml  # noqa: E402
from src.data_fusion.correspondence_prep import prepare_correspondences  # noqa: E402
from src.data_fusion.loader import MEDICINE_ATTRIBUTES, SOURCE_FILES, load_datasets  # noqa: E402
from src.identity_resolution.llm_zero_shot_matcher import evaluate_predictions  # noqa: E402

MEMBER_SPLIT_RE = re.compile(r"; (?=(?:DPD|EMA|FDA)_)")
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
SUBSET_SCHEMA_LOCATION = "../../../src/mapforce/schema/medicines.xsd"
EVAL_BENCHMARK_ATTRIBUTES = (
    "brandName",
    "activeSubstances",
    "activeSubstanceCount",
    "licenceHolder",
    "productClass",
    "atcCode",
    "dosageForm",
    "route",
    "strengths",
    "biosimilar",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _parse_cluster_members(value: str) -> list[str]:
    if not value:
        return []
    return [part for part in MEMBER_SPLIT_RE.split(value) if part]


def _is_populated(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, (list, tuple, set)):
        return len(value) > 0
    if isinstance(value, bool):
        return True
    if isinstance(value, str):
        return value.strip() != ""
    try:
        return not pd.isna(value)
    except TypeError:
        return True


def verify_phase1() -> dict[str, Any]:
    """Verify MapForce helper UDFs, XML/JSON schemas, and processed entities."""
    udf_script = REPO_ROOT / "src" / "mapforce" / "helpers" / "udf_reference.py"
    proc = subprocess.run(
        [sys.executable, str(udf_script), "--no-coverage"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=True,
    )
    if "124/124" not in proc.stdout:
        raise RuntimeError(f"Unexpected UDF output: {proc.stdout.strip()}")

    sample_xml_res = validate_xml(SAMPLE_XML)
    sample_obj = json.loads(SAMPLE_JSON.read_text(encoding="utf-8-sig"))
    sample_json_res = validate_json(sample_obj, SAMPLE_JSON.name)

    xml_dir = REPO_ROOT / "data" / "4_translated_mapforce"
    xml_results = {}
    for source, filename in SOURCE_FILES.items():
        res = validate_xml(xml_dir / filename)
        for key in ("Duplicate IDs", "Duplicate content excluding ID", "Duplicate normalized entities"):
            if not res["schema_valid"] or res[key] != 0:
                raise RuntimeError(f"Validation failed for {filename}: {res}")
        xml_results[source] = res

    total_xml_records = sum(item["records"] for item in xml_results.values())
    if total_xml_records != 52459:
        raise RuntimeError(f"Expected 52,459 total XML records, got {total_xml_records}")

    dpd_csv = pd.read_csv(REPO_ROOT / "data" / "2_processed" / "dpd_entities.csv", dtype="string")
    ema_csv = pd.read_csv(REPO_ROOT / "data" / "2_processed" / "ema_entities.csv", dtype="string")
    if len(dpd_csv) != xml_results["DPD"]["records"] or len(ema_csv) != xml_results["EMA"]["records"]:
        raise RuntimeError("Processed entity CSV row counts do not match integrated XML counts")

    return {
        "udf_test_summary": proc.stdout.strip().splitlines()[-1],
        "sample_xml_records": sample_xml_res["records"],
        "sample_json_records": sample_json_res["records"],
        "xml_results": xml_results,
        "total_xml_records": total_xml_records,
        "dpd_processed_rows": len(dpd_csv),
        "ema_processed_rows": len(ema_csv),
    }


def verify_phase2() -> dict[str, Any]:
    """Verify gold-standard splits, blocking candidates, matcher metrics, and clusters."""
    gs_dir = REPO_ROOT / "data" / "5_golden_standard_pair" / "golden_standard_pair_complete"
    gs_whole = pd.read_csv(gs_dir / "gs_pair_whole.csv", dtype="string")
    gs_train_val = pd.read_csv(gs_dir / "gs_pair_train_val.csv", dtype="string")
    gs_test = pd.read_csv(gs_dir / "gs_pair_test.csv", dtype="string")

    if len(gs_whole) != 3498 or len(gs_train_val) != 2973 or len(gs_test) != 525:
        raise RuntimeError(
            f"Unexpected gold-standard split sizes: {len(gs_whole)}, {len(gs_train_val)}, {len(gs_test)}"
        )
    if set(gs_train_val["pair_id"]) & set(gs_test["pair_id"]):
        raise RuntimeError("Train/val and test gold-standard splits share pair_ids")

    block_dir = REPO_ROOT / "data" / "7_blocking_candidates"
    candidate_counts = {}
    for pair in ("dpd_ema", "dpd_fda", "ema_fda"):
        df_cand = pd.read_csv(block_dir / f"{pair}_candidates.csv.gz", usecols=["id1", "id2"])
        candidate_counts[pair] = len(df_cand)
    total_candidates = sum(candidate_counts.values())
    if total_candidates != 206830:
        raise RuntimeError(f"Expected 206,830 blocking candidates, got {total_candidates}")

    llm_preds = pd.read_csv(REPO_ROOT / "data" / "6_evaluation" / "llm_test_predictions.csv")
    llm_metrics = evaluate_predictions(llm_preds, y_true_col="match", y_pred_col="pred_llm")
    if round(llm_metrics["macro_f1"], 4) != 0.9485:
        raise RuntimeError(f"Expected LLM Macro F1 0.9485, got {llm_metrics['macro_f1']:.6f}")

    ml_metrics_path = REPO_ROOT / "data" / "6_evaluation" / "ml_tree_test_metrics.csv"
    plm_metrics_path = REPO_ROOT / "notebooks" / "PLM_DistilBERT" / "test_metrics.csv"
    ml_metrics = pd.read_csv(ml_metrics_path)
    plm_metrics = pd.read_csv(plm_metrics_path)
    if ml_metrics.empty or plm_metrics.empty:
        raise RuntimeError("Expected non-empty ML/PLM evaluation metrics tables")

    fused_dir = REPO_ROOT / "data" / "3_fused"
    raw_matches = pd.read_csv(fused_dir / "candidate_matches.csv")
    corr_1to1 = pd.read_csv(fused_dir / "candidate_correspondences_1to1.csv")
    clusters = pd.read_csv(fused_dir / "candidate_medicine_clusters.csv", dtype=str, keep_default_na=False)

    three_way = int((clusters["is_three_way"] == "True").sum())
    clustered_records = sum(len(_parse_cluster_members(v)) for v in clusters["all_members"])
    if len(raw_matches) != 4708 or len(corr_1to1) != 3336 or len(clusters) != 2343:
        raise RuntimeError(
            f"Unexpected candidate/cluster counts: matches={len(raw_matches)}, "
            f"1to1={len(corr_1to1)}, clusters={len(clusters)}"
        )

    return {
        "gs_whole": len(gs_whole),
        "gs_train_val": len(gs_train_val),
        "gs_test": len(gs_test),
        "blocking_counts": candidate_counts,
        "total_candidates": total_candidates,
        "llm_macro_f1": round(llm_metrics["macro_f1"], 4),
        "ml_rows": len(ml_metrics),
        "plm_best_macro_f1": round(float(plm_metrics["macro_f1"].max()), 4),
        "raw_positive_matches": len(raw_matches),
        "greedy_1to1_pairs": len(corr_1to1),
        "multi_source_clusters": len(clusters),
        "three_way_clusters": three_way,
        "clustered_records": clustered_records,
    }


def compute_full_dataset_audit(
    datasets: dict[str, pd.DataFrame],
    clusters: pd.DataFrame,
) -> dict[str, Any]:
    """Compute Conclusion Q1 (entity expansion) and Q2 (attribute density) across all records."""
    record_lookup: dict[str, dict[str, Any]] = {}
    source_ids: dict[str, set[str]] = {}
    for source, frame in datasets.items():
        source_ids[source] = set(frame["id"])
        for row in frame.to_dict("records"):
            record_lookup[row["id"]] = row

    clustered_ids: set[str] = set()
    cluster_member_lists: list[list[str]] = []
    clustered_by_source = {"DPD": 0, "EMA": 0, "FDA": 0}
    for value in clusters["all_members"]:
        members = _parse_cluster_members(value)
        cluster_member_lists.append(members)
        for member in members:
            clustered_ids.add(member)
            src = member.split("_", 1)[0]
            clustered_by_source[src] += 1

    singletons_by_source = {
        src: sorted(ids - clustered_ids) for src, ids in source_ids.items()
    }
    singleton_counts = {src: len(ids) for src, ids in singletons_by_source.items()}
    total_singletons = sum(singleton_counts.values())
    total_groups = len(clusters) + total_singletons

    dpd_total = len(datasets["DPD"])
    additional_entities = total_groups - dpd_total
    clusters_without_dpd = int((clusters["dpd_ids"] == "").sum())
    dpd_intra_reduction = clustered_by_source["DPD"] - int((clusters["dpd_ids"] != "").sum())

    all_groups = cluster_member_lists + [[mid] for ids in singletons_by_source.values() for mid in ids]

    per_attr_rows = []
    overlap_attrs = []
    for attr in MEDICINE_ATTRIBUTES:
        src_density = {
            src: sum(_is_populated(v) for v in frame[attr]) / len(frame)
            for src, frame in datasets.items()
        }
        if sum(val > 0.0 for val in src_density.values()) >= 2:
            overlap_attrs.append(attr)

        clustered_pop = sum(
            any(_is_populated(record_lookup[mid][attr]) for mid in members)
            for members in cluster_member_lists
        )
        all_pop = sum(
            any(_is_populated(record_lookup[mid][attr]) for mid in members)
            for members in all_groups
        )
        per_attr_rows.append({
            "attribute": attr,
            "dpd_density": src_density["DPD"],
            "ema_density": src_density["EMA"],
            "fda_density": src_density["FDA"],
            "fused_clusters_density": clustered_pop / len(cluster_member_lists),
            "fused_all_groups_density": all_pop / len(all_groups),
        })

    density_df = pd.DataFrame(per_attr_rows)
    all16_dpd = float(density_df["dpd_density"].mean())
    all16_ema = float(density_df["ema_density"].mean())
    all16_fda = float(density_df["fda_density"].mean())
    all16_clusters = float(density_df["fused_clusters_density"].mean())
    all16_fused = float(density_df["fused_all_groups_density"].mean())

    overlap_df = density_df[density_df["attribute"].isin(overlap_attrs)]
    overlap12_dpd = float(overlap_df["dpd_density"].mean())
    overlap12_clusters = float(overlap_df["fused_clusters_density"].mean())
    overlap12_fused = float(overlap_df["fused_all_groups_density"].mean())

    eval10_df = density_df[density_df["attribute"].isin(EVAL_BENCHMARK_ATTRIBUTES)]
    eval10_dpd = float(eval10_df["dpd_density"].mean())
    eval10_clusters = float(eval10_df["fused_clusters_density"].mean())
    eval10_fused = float(eval10_df["fused_all_groups_density"].mean())

    return {
        "dpd_entities": dpd_total,
        "ema_entities": len(datasets["EMA"]),
        "fda_entities": len(datasets["FDA"]),
        "total_input_records": sum(len(frame) for frame in datasets.values()),
        "multi_source_clusters": len(clusters),
        "clustered_records": len(clustered_ids),
        "clustered_by_source": clustered_by_source,
        "singletons_by_source": singleton_counts,
        "total_singletons": total_singletons,
        "total_groups": total_groups,
        "additional_entities_vs_dpd": additional_entities,
        "additional_pct_vs_dpd": additional_entities / dpd_total,
        "clusters_without_dpd": clusters_without_dpd,
        "dpd_intra_reduction": dpd_intra_reduction,
        "singletons_by_source_ids": singletons_by_source,
        "density_table": density_df,
        "mean_density_16_attrs": {
            "DPD": all16_dpd,
            "EMA": all16_ema,
            "FDA": all16_fda,
            "Fused_Clusters": all16_clusters,
            "Gain_Clusters_vs_DPD": all16_clusters - all16_dpd,
            "Fused_All_Groups": all16_fused,
            "Gain_vs_DPD": all16_fused - all16_dpd,
        },
        "mean_density_12_overlap_attrs": {
            "DPD": overlap12_dpd,
            "Fused_Clusters": overlap12_clusters,
            "Gain_Clusters_vs_DPD": overlap12_clusters - overlap12_dpd,
            "Fused_All_Groups": overlap12_fused,
            "Gain_vs_DPD": overlap12_fused - overlap12_dpd,
        },
        "mean_density_10_eval_attrs": {
            "DPD": eval10_dpd,
            "Fused_Clusters": eval10_clusters,
            "Gain_Clusters_vs_DPD": eval10_clusters - eval10_dpd,
            "Fused_All_Groups": eval10_fused,
            "Gain_vs_DPD": eval10_fused - eval10_dpd,
        },
    }


def verify_phase3() -> dict[str, Any]:
    """Verify XML loader provenance, correspondence prep, worksheet state, and full Q1/Q2 stats."""
    datasets = load_datasets(REPO_ROOT)
    corr_path = REPO_ROOT / "data" / "3_fused" / "candidate_correspondences_1to1.csv"
    correspondences = prepare_correspondences(corr_path, datasets)
    if (
        len(correspondences) != 3336
        or correspondences.attrs["groups"] != 2343
        or correspondences.attrs["grouped_records"] != 5194
    ):
        raise RuntimeError(f"Unexpected correspondence stats: {correspondences.attrs}")

    clusters = pd.read_csv(
        REPO_ROOT / "data" / "3_fused" / "candidate_medicine_clusters.csv",
        dtype=str,
        keep_default_na=False,
    )
    audit = compute_full_dataset_audit(datasets, clusters)

    eval_path = REPO_ROOT / "data" / "8_fusion_eval" / "fusion_eval_worksheet.csv"
    eval_df = pd.read_csv(eval_path, sep=";", dtype="string", keep_default_na=False)
    verified_rows = int(eval_df["verified_by"].str.strip().ne("").sum())
    gold_filled_rows = int(eval_df["gold_brandName"].str.strip().ne("").sum())

    final_xml_path = REPO_ROOT / "data" / "9_fusion_xml_final" / "fused_medicines.xml"
    fused_xml_count = None
    if final_xml_path.exists():
        fused_root = etree.parse(str(final_xml_path)).getroot()
        fused_ids = [
            med.findtext("id").strip()
            for med in fused_root.findall("medicine")
            if med.findtext("id")
        ]
        if len(fused_ids) != len(set(fused_ids)) or len(fused_ids) != audit["total_groups"]:
            raise RuntimeError(
                f"Unexpected final fused XML count/uniqueness: {len(fused_ids)} vs {audit['total_groups']}"
            )
        fused_xml_count = len(fused_ids)

    return {
        "correspondences_attrs": correspondences.attrs,
        "eval_worksheet_rows": len(eval_df),
        "eval_verified_rows": verified_rows,
        "eval_gold_brand_filled": gold_filled_rows,
        "fused_xml_count": fused_xml_count,
        "audit": audit,
        "eval_df": eval_df,
        "clusters_df": clusters,
    }


def _select_subset_ids(
    eval_df: pd.DataFrame,
    clusters: pd.DataFrame,
    singletons_by_source_ids: dict[str, list[str]],
    seed: int = 42,
) -> dict[str, set[str]]:
    """Select ~300 representative records across eval clusters, k>3 clusters, strata, and singletons."""
    rng = random.Random(seed)
    selected_clusters: set[str] = set(eval_df["cluster_id"].tolist())
    selected_clusters.update(clusters.loc[clusters["cluster_size"].astype(int) > 3, "cluster_id"].tolist())

    quota_map = {
        "DPD; EMA; FDA": 15,
        "DPD; FDA": 8,
        "DPD; EMA": 8,
        "EMA; FDA": 8,
    }
    for stratum, quota in quota_map.items():
        pool = sorted(set(clusters.loc[clusters["sources"] == stratum, "cluster_id"]) - selected_clusters)
        picks = rng.sample(pool, k=min(quota, len(pool)))
        selected_clusters.update(picks)

    selected_ids: dict[str, set[str]] = {"DPD": set(), "EMA": set(), "FDA": set()}
    chosen_rows = clusters[clusters["cluster_id"].isin(selected_clusters)]
    for _, row in chosen_rows.iterrows():
        for src in ("DPD", "EMA", "FDA"):
            col = f"{src.lower()}_ids"
            for mid in _parse_cluster_members(row[col]):
                selected_ids[src].add(mid)

    for src in ("DPD", "EMA", "FDA"):
        singleton_pool = sorted(singletons_by_source_ids[src])
        picks = rng.sample(singleton_pool, k=min(15, len(singleton_pool)))
        selected_ids[src].update(picks)

    return selected_ids


def _write_subset_xmls(
    target_dir: Path,
    selected_ids: dict[str, set[str]],
) -> dict[str, dict[str, Any]]:
    """Extract selected <medicine> elements into XSD-validated XML subsets."""
    target_dir.mkdir(parents=True, exist_ok=True)
    src_xml_dir = REPO_ROOT / "data" / "4_translated_mapforce"
    subset_results = {}

    for source, filename in SOURCE_FILES.items():
        src_path = src_xml_dir / filename
        tree = etree.parse(str(src_path))
        root = tree.getroot()
        wanted = selected_ids[source]

        new_root = etree.Element("medicines", nsmap={"xsi": XSI_NS})
        new_root.set(f"{{{XSI_NS}}}noNamespaceSchemaLocation", SUBSET_SCHEMA_LOCATION)

        for elem in root.findall("medicine"):
            id_el = elem.find("id")
            if id_el is not None and id_el.text and id_el.text.strip() in wanted:
                new_root.append(etree.fromstring(etree.tostring(elem)))

        out_path = target_dir / filename
        etree.indent(new_root, space="\t")
        etree.ElementTree(new_root).write(
            str(out_path),
            encoding="UTF-8",
            xml_declaration=True,
            pretty_print=True,
        )
        res = validate_xml(out_path)
        for key in ("Duplicate IDs", "Duplicate content excluding ID", "Duplicate normalized entities"):
            if not res["schema_valid"] or res[key] != 0:
                raise RuntimeError(f"Subset XML validation failed for {out_path}: {res}")
        subset_results[source] = res

    return subset_results


def _copy_code_tree(code_dir: Path, include_model: bool) -> None:
    src_dest = code_dir / "src"
    nb_dest = code_dir / "notebooks"

    def ignore_common(_directory: str, names: list[str]) -> list[str]:
        ignored = []
        for name in names:
            if name in {"__pycache__", ".ipynb_checkpoints", ".DS_Store"} or name.endswith(".pyc"):
                ignored.append(name)
        return ignored

    def ignore_notebooks(_directory: str, names: list[str]) -> list[str]:
        ignored = ignore_common(_directory, names)
        if not include_model and "best_model.zip" in names:
            ignored.append("best_model.zip")
        return ignored

    shutil.copytree(REPO_ROOT / "src", src_dest, ignore=ignore_common)
    shutil.copytree(REPO_ROOT / "notebooks", nb_dest, ignore=ignore_notebooks)
    for filename in ("requirements.txt", ".python-version", "README.md"):
        shutil.copy2(REPO_ROOT / filename, code_dir / filename)


def _write_manifest(
    manifest_path: Path,
    p1: dict[str, Any],
    p2: dict[str, Any],
    p3: dict[str, Any],
    subset_results: dict[str, dict[str, Any]],
    include_model: bool,
    fused_subset_count: int = 0,
) -> None:
    audit = p3["audit"]
    d16 = audit["mean_density_16_attrs"]
    d12 = audit["mean_density_12_overlap_attrs"]
    d10 = audit["mean_density_10_eval_attrs"]

    lines = [
        "# WDI Drug Integration Submission Manifest",
        "",
        "## Verified Clean-Run Checks",
        f"- MapForce helper oracle: {p1['udf_test_summary']}",
        f"- Integrated XML records (XSD valid, zero duplicates): DPD {p1['xml_results']['DPD']['records']:,}, "
        f"EMA {p1['xml_results']['EMA']['records']:,}, FDA {p1['xml_results']['FDA']['records']:,} "
        f"(total {p1['total_xml_records']:,})",
        f"- Gold-standard pairs: {p2['gs_whole']:,} total ({p2['gs_train_val']:,} train/val, {p2['gs_test']:,} test, 0 overlap)",
        f"- Hybrid blocking candidates: {p2['total_candidates']:,} total "
        f"(DPD/EMA {p2['blocking_counts']['dpd_ema']:,}, DPD/FDA {p2['blocking_counts']['dpd_fda']:,}, EMA/FDA {p2['blocking_counts']['ema_fda']:,})",
        f"- Best matcher test Macro F1 (cached LLM zero-shot): {p2['llm_macro_f1']:.4f}",
        f"- Greedy 1:1 correspondences validated via correspondence_prep.py: {p2['greedy_1to1_pairs']:,} edges into {p2['multi_source_clusters']:,} clusters ({p2['three_way_clusters']:,} three-way, {p2['clustered_records']:,} clustered records)",
        f"- Fusion evaluation worksheet rows: {p3['eval_worksheet_rows']} total ({p3['eval_verified_rows']} signed off, {p3['eval_gold_brand_filled']} gold rows populated)",
        "",
        "## Full-Dataset Audit Metrics (Conclusion Q1 & Q2 Reference)",
        f"- Q1 Total consolidated medicine entities: {audit['total_groups']:,} "
        f"({audit['multi_source_clusters']:,} clusters + {audit['total_singletons']:,} singletons)",
        f"- Q1 Additional entities vs. largest source (DPD {audit['dpd_entities']:,}): "
        f"+{audit['additional_entities_vs_dpd']:,} (+{audit['additional_pct_vs_dpd']:.2%})",
        f"  - Breakdown: {audit['clusters_without_dpd']:,} EMA+FDA clusters + "
        f"{audit['singletons_by_source']['EMA']:,} EMA singletons + "
        f"{audit['singletons_by_source']['FDA']:,} FDA singletons - "
        f"{audit['dpd_intra_reduction']} intra-source DPD cluster reductions",
        f"- Q2 Mean non-null density (all 16 schema attributes): "
        f"DPD {d16['DPD']:.4f}, EMA {d16['EMA']:.4f}, FDA {d16['FDA']:.4f}, "
        f"Fused multi-source clusters ({audit['multi_source_clusters']:,}) {d16['Fused_Clusters']:.4f} "
        f"({d16['Gain_Clusters_vs_DPD']:+.4f} vs. DPD), "
        f"Fused all groups ({audit['total_groups']:,}) {d16['Fused_All_Groups']:.4f} "
        f"({d16['Gain_vs_DPD']:+.4f} vs. DPD)",
        f"- Q2 Mean non-null density (12 multi-source attributes): "
        f"DPD {d12['DPD']:.4f} -> Fused clusters {d12['Fused_Clusters']:.4f} ({d12['Gain_Clusters_vs_DPD']:+.4f}), "
        f"All groups {d12['Fused_All_Groups']:.4f} ({d12['Gain_vs_DPD']:+.4f})",
        f"- Q2 Mean non-null density (10 benchmark attributes): "
        f"DPD {d10['DPD']:.4f} -> Fused clusters {d10['Fused_Clusters']:.4f} ({d10['Gain_Clusters_vs_DPD']:+.4f}), "
        f"All groups {d10['Fused_All_Groups']:.4f} ({d10['Gain_vs_DPD']:+.4f})",
        "",
        "## Curated Archive Contents",
        "- `report/`: `final_project_report_draft.pdf`, `final_project_report_draft.tex`, `references.bib`",
        f"- `code/`: `src/`, `notebooks/` (`best_model.zip` included: {include_model}), `requirements.txt`, `.python-version`, `README.md`",
        "- `data_subset/4_translated_mapforce/`: XSD-validated XML subsets "
        f"(DPD {subset_results['DPD']['records']}, EMA {subset_results['EMA']['records']}, FDA {subset_results['FDA']['records']}; "
        f"total {sum(r['records'] for r in subset_results.values())} records)",
        "- `data_subset/3_fused/`: Phase II matches, 1:1 correspondences, clusters (plus any final fused outputs if present)",
        "- `data_subset/5_golden_standard_pair/golden_standard_pair_complete/`: unified benchmark splits and report",
        "- `data_subset/6_evaluation/`: matcher and clustering evaluation reports/metrics",
        "- `data_subset/7_blocking_candidates/manifest.json` and `data_subset/8_fusion_eval/fusion_eval_worksheet.csv`",
        f"- `data_subset/9_fusion_xml_final/fused_medicines.xml`: curated subset of final fused XML ({fused_subset_count} entities from {p3['fused_xml_count'] or 0:,} total)",
        "",
    ]
    manifest_path.write_text("\n".join(lines), encoding="utf-8")


def build_submission_package(
    p1: dict[str, Any],
    p2: dict[str, Any],
    p3: dict[str, Any],
    output_dir: Path,
    include_model: bool,
) -> Path:
    """Create the clean submission directory and compressed ZIP archive."""
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Report artifacts
    report_dir = output_dir / "report"
    report_dir.mkdir(parents=True, exist_ok=True)
    for filename in (
        "final_project_report_draft.pdf",
        "final_project_report_draft.tex",
        "references.bib",
    ):
        src_file = REPO_ROOT / "docs" / "final_report" / filename
        if src_file.exists():
            shutil.copy2(src_file, report_dir / filename)

    # 2. Code & notebooks
    _copy_code_tree(output_dir / "code", include_model=include_model)

    # 3. Curated data subset
    data_dir = output_dir / "data_subset"
    selected_ids = _select_subset_ids(
        p3["eval_df"],
        p3["clusters_df"],
        p3["audit"]["singletons_by_source_ids"],
    )
    subset_results = _write_subset_xmls(data_dir / "4_translated_mapforce", selected_ids)

    fused_out = data_dir / "3_fused"
    fused_out.mkdir(parents=True, exist_ok=True)
    for filename in (
        "candidate_matches.csv",
        "candidate_correspondences_1to1.csv",
        "candidate_medicine_clusters.csv",
        "fused_medicines.xml",
        "fused_medicines_final.csv",
    ):
        candidate_file = REPO_ROOT / "data" / "3_fused" / filename
        if candidate_file.exists():
            shutil.copy2(candidate_file, fused_out / filename)
    root_fused_xml = REPO_ROOT / "fused_medicines.xml"
    if root_fused_xml.exists() and not (fused_out / "fused_medicines.xml").exists():
        shutil.copy2(root_fused_xml, fused_out / "fused_medicines.xml")

    gs_out = data_dir / "5_golden_standard_pair" / "golden_standard_pair_complete"
    gs_out.mkdir(parents=True, exist_ok=True)
    gs_src = REPO_ROOT / "data" / "5_golden_standard_pair"
    for rel in (
        "golden_standard_pair_complete/gs_pair_whole.csv",
        "golden_standard_pair_complete/gs_pair_train_val.csv",
        "golden_standard_pair_complete/gs_pair_test.csv",
        "golden standard pair dataset report.md",
    ):
        shutil.copy2(gs_src / rel, data_dir / "5_golden_standard_pair" / rel)

    eval_out = data_dir / "6_evaluation"
    eval_out.mkdir(parents=True, exist_ok=True)
    for item in (REPO_ROOT / "data" / "6_evaluation").iterdir():
        if item.is_file() and item.suffix.lower() in {".md", ".csv", ".json"}:
            shutil.copy2(item, eval_out / item.name)

    block_out = data_dir / "7_blocking_candidates"
    block_out.mkdir(parents=True, exist_ok=True)
    shutil.copy2(REPO_ROOT / "data" / "7_blocking_candidates" / "manifest.json", block_out / "manifest.json")

    fusion_eval_out = data_dir / "8_fusion_eval"
    fusion_eval_out.mkdir(parents=True, exist_ok=True)
    shutil.copy2(REPO_ROOT / "data" / "8_fusion_eval" / "fusion_eval_worksheet.csv", fusion_eval_out / "fusion_eval_worksheet.csv")

    final_xml_src = REPO_ROOT / "data" / "9_fusion_xml_final" / "fused_medicines.xml"
    fused_subset_count = 0
    if final_xml_src.exists():
        all_wanted = {mid for ids in selected_ids.values() for mid in ids}
        src_fused_root = etree.parse(str(final_xml_src)).getroot()
        subset_fused_root = etree.Element("medicines")
        for elem in src_fused_root.findall("medicine"):
            med_id = (elem.findtext("id") or "").strip()
            if med_id in all_wanted:
                subset_fused_root.append(etree.fromstring(etree.tostring(elem)))
                fused_subset_count += 1
        final_xml_out = data_dir / "9_fusion_xml_final" / "fused_medicines.xml"
        final_xml_out.parent.mkdir(parents=True, exist_ok=True)
        etree.indent(subset_fused_root, space="\t")
        etree.ElementTree(subset_fused_root).write(
            str(final_xml_out),
            encoding="UTF-8",
            xml_declaration=True,
            pretty_print=True,
        )

    _write_manifest(output_dir / "SUBMISSION_MANIFEST.md", p1, p2, p3, subset_results, include_model, fused_subset_count)

    zip_path = output_dir.parent / "wdi_drug_integration_submission.zip"
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file_path in sorted(output_dir.rglob("*")):
            if file_path.is_file():
                zf.write(file_path, arcname=file_path.relative_to(output_dir))

    return zip_path


def print_audit_summary(p1: dict[str, Any], p2: dict[str, Any], p3: dict[str, Any]) -> None:
    """Print concise verification and full-dataset audit summary to stdout."""
    audit = p3["audit"]
    d16 = audit["mean_density_16_attrs"]
    d12 = audit["mean_density_12_overlap_attrs"]
    d10 = audit["mean_density_10_eval_attrs"]

    print("=== CLEAN-RUN VERIFICATION PASSED ===")
    print(f"Phase I:  {p1['udf_test_summary']} | {p1['total_xml_records']:,} XSD-valid XML records (0 duplicates)")
    print(
        f"Phase II: {p2['gs_whole']:,} GS pairs ({p2['gs_train_val']:,} train/val, {p2['gs_test']:,} test) | "
        f"{p2['total_candidates']:,} candidates | LLM Macro F1={p2['llm_macro_f1']:.4f} | "
        f"{p2['greedy_1to1_pairs']:,} 1:1 links -> {p2['multi_source_clusters']:,} clusters ({p2['clustered_records']:,} records)"
    )
    print(
        f"Phase III: {audit['total_groups']:,} total groups ({audit['total_singletons']:,} singletons) | "
        f"Eval worksheet: {p3['eval_worksheet_rows']} rows ({p3['eval_verified_rows']} signed off, {p3['eval_gold_brand_filled']} gold filled)"
        + (f" | Final XML: {p3['fused_xml_count']:,} entities" if p3.get("fused_xml_count") else "")
    )
    print("\n=== FULL-DATASET AUDIT (CONCLUSION Q1 & Q2) ===")
    print(
        f"Q1 Additional entities vs. DPD ({audit['dpd_entities']:,}): "
        f"+{audit['additional_entities_vs_dpd']:,} (+{audit['additional_pct_vs_dpd']:.2%}) "
        f"-> {audit['total_groups']:,} total entities"
    )
    print(
        f"Q2 Mean non-null density (all 16 schema attrs): "
        f"DPD {d16['DPD']:.4f} | Clusters ({audit['multi_source_clusters']:,}) {d16['Fused_Clusters']:.4f} ({d16['Gain_Clusters_vs_DPD']:+.4f}) | "
        f"All ({audit['total_groups']:,}) {d16['Fused_All_Groups']:.4f} ({d16['Gain_vs_DPD']:+.4f})"
    )
    print(
        f"Q2 Mean non-null density (12 multi-source attrs): "
        f"DPD {d12['DPD']:.4f} | Clusters {d12['Fused_Clusters']:.4f} ({d12['Gain_Clusters_vs_DPD']:+.4f}) | "
        f"All {d12['Fused_All_Groups']:.4f} ({d12['Gain_vs_DPD']:+.4f})"
    )
    print(
        f"Q2 Mean non-null density (10 benchmark attrs): "
        f"DPD {d10['DPD']:.4f} | Clusters {d10['Fused_Clusters']:.4f} ({d10['Gain_Clusters_vs_DPD']:+.4f}) | "
        f"All {d10['Fused_All_Groups']:.4f} ({d10['Gain_vs_DPD']:+.4f})"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify project reproducibility and package ILIAS submission.")
    parser.add_argument("--package", action="store_true", help="Build submission directory and ZIP archive under dist/.")
    parser.add_argument("--include-model", action="store_true", help="Include notebooks/PLM_DistilBERT/best_model.zip in the bundle.")
    parser.add_argument("--output-dir", type=Path, default=REPO_ROOT / "dist" / "submission_package")
    args = parser.parse_args()

    p1 = verify_phase1()
    p2 = verify_phase2()
    p3 = verify_phase3()
    print_audit_summary(p1, p2, p3)

    if args.package:
        out_dir = args.output_dir.resolve()
        zip_path = build_submission_package(p1, p2, p3, out_dir, include_model=args.include_model)
        size_mb = zip_path.stat().st_size / (1024 * 1024)
        print(f"\nPackage directory: {out_dir}")
        print(f"Submission archive: {zip_path} ({size_mb:.2f} MB)")


if __name__ == "__main__":
    main()
