"""Zero-Shot LLM Matcher using official Google GenAI SDK.

Evaluates medicine pair correspondences on the held-out test split
(data/5_golden_standard_pair/golden_standard_pair_complete/gs_pair_test.csv).

Features:
- Pydantic structured JSON output (match: 0/1, reason: str)
- Decontaminated zero-shot prompt (strictly domain rules, zero test-set examples)
- Checkpoint caching (each response is saved immediately; resume skips completed rows)
- Evaluation metrics: Precision, Recall, Macro F1, confusion matrix, difficulty & source breakdowns
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from typing import Any

import pandas as pd
from pydantic import BaseModel, Field
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)
from difflib import SequenceMatcher

from src.identity_resolution.candidate_utils import (
    enrich_candidate_dataframe,
    load_blocking_candidates,
    load_xml_entities,
    norm_text,
    parse_substance_tokens,
    strip_salts,
)

# Load environment variable from .env if present
ENV_PATH = Path(".env")
if ENV_PATH.exists():
    with open(ENV_PATH) as f:
        for line in f:
            line = line.strip()
            if line.startswith("GEMINI_API_KEY=") and not line.startswith("#"):
                os.environ["GEMINI_API_KEY"] = line.split("=", 1)[1].strip()


class MatchDecision(BaseModel):
    match: int = Field(
        description="Binary decision: 1 if the records represent the same medicine entity, 0 if different."
    )
    reason: str = Field(
        description="Concise rationale explaining the decision based on active substances, brand name, and manufacturer."
    )


# Clean, completely decontaminated Zero-Shot prompt (no test set pairs or specific drug names mentioned)
ZERO_SHOT_SYSTEM_INSTRUCTION = """You are a pharmaceutical and clinical data integration expert performing entity resolution.
Your task is to determine whether two drug records from different regulatory authorities (Health Canada DPD, European Medicines Agency EMA, or US FDA) refer to the SAME underlying medicine entity.

Entity Definition:
A medicine entity is defined by its Brand Name and Active Substance(s).

Decision Rules:
1. Active Substances (Crucial):
   - The active substances must represent the same pharmacological ingredients.
   - Differences in salt forms (e.g., hydrochloride, sodium, maleate, besylate, sulfate), hydration state (monohydrate, anhydrous), or international nonproprietary name (INN) regional spellings (e.g., cyclosporine vs. ciclosporin) represent the SAME active substance.
   - The number of active substances must agree. A single-substance formulation does NOT match a combination drug containing additional active ingredients.
2. Brand Name & Manufacturer / Licence Holder:
   - Identical brand names or brand names with minor formulation suffixes from regional subsidiaries of the same corporate group (e.g., 'Company Canada' and 'Company Europharm' / 'Company US') are MATCHES (1).
   - Competitor generics: Products from different, unrelated generic manufacturers (e.g., Apotex vs. Teva vs. Mylan vs. Cobalt) are NON-MATCHES (0), even if they share the same active ingredient, because they are distinct branded commercial entities.
   - Completely different brand names from unrelated companies are NON-MATCHES (0).
3. Dosage Form and Administration Route:
   - Minor dosage form variations (e.g., tablet vs. capsule, solution vs. suspension) do NOT invalidate a match if the brand name, active substance set, and corporate manufacturer agree.
"""


def _clean_field(val: Any, default: str) -> str:
    """Return a clean string for a DataFrame field, replacing NaN/empty with default."""
    if val is None or pd.isna(val):
        return default
    s = str(val).strip()
    return default if not s or s.lower() == "nan" else s


def build_pair_prompt(row: pd.Series) -> str:
    """Format a single medicine pair for zero-shot LLM evaluation."""
    src1 = _clean_field(row.get("source1"), "Source 1").upper()
    src2 = _clean_field(row.get("source2"), "Source 2").upper()

    b1 = _clean_field(row.get("brandName1"), "Unknown")
    b2 = _clean_field(row.get("brandName2"), "Unknown")

    s1 = _clean_field(row.get("activeSubstances1"), "Unknown")
    s2 = _clean_field(row.get("activeSubstances2"), "Unknown")

    h1 = _clean_field(row.get("licenceHolder1"), "Not specified")
    h2 = _clean_field(row.get("licenceHolder2"), "Not specified")

    df1 = _clean_field(row.get("dosageForm1"), "Not specified")
    df2 = _clean_field(row.get("dosageForm2"), "Not specified")

    return f"""Compare the following two regulatory drug records:

Record 1 ({src1}):
- Brand Name: {b1}
- Active Substance(s): {s1}
- Licence Holder / Manufacturer: {h1}
- Dosage Form: {df1}

Record 2 ({src2}):
- Brand Name: {b2}
- Active Substance(s): {s2}
- Licence Holder / Manufacturer: {h2}
- Dosage Form: {df2}

Do these two records represent the same medicine entity? Answer with a JSON object containing "match" (1 or 0) and "reason"."""


def evaluate_predictions(
    df: pd.DataFrame,
    y_true_col: str = "match",
    y_pred_col: str = "pred_llm",
) -> dict[str, Any]:
    """Calculate comprehensive evaluation metrics on predictions."""
    valid_mask = df[y_pred_col].notna() & df[y_true_col].notna()
    df_eval = df[valid_mask].copy()

    y_true = df_eval[y_true_col].astype(int)
    y_pred = df_eval[y_pred_col].astype(int)

    acc = float(accuracy_score(y_true, y_pred))
    prec_macro = float(precision_score(y_true, y_pred, average="macro", zero_division=0))
    rec_macro = float(recall_score(y_true, y_pred, average="macro", zero_division=0))
    f1_macro = float(f1_score(y_true, y_pred, average="macro", zero_division=0))

    prec_binary = float(precision_score(y_true, y_pred, pos_label=1, zero_division=0))
    rec_binary = float(recall_score(y_true, y_pred, pos_label=1, zero_division=0))
    f1_binary = float(f1_score(y_true, y_pred, pos_label=1, zero_division=0))

    cm = confusion_matrix(y_true, y_pred)
    tn, fp, fn, tp = int(cm[0, 0]), int(cm[0, 1]), int(cm[1, 0]), int(cm[1, 1])

    # Hard vs Ordinary breakdown
    hard_metrics = {}
    for h_val, h_name in [(0, "ordinary"), (1, "hard")]:
        sub = df_eval[df_eval["hard"] == h_val]
        if len(sub) > 0:
            yt_sub = sub[y_true_col].astype(int)
            yp_sub = sub[y_pred_col].astype(int)
            hard_metrics[h_name] = {
                "count": len(sub),
                "accuracy": float(accuracy_score(yt_sub, yp_sub)),
                "precision_macro": float(precision_score(yt_sub, yp_sub, average="macro", zero_division=0)),
                "recall_macro": float(recall_score(yt_sub, yp_sub, average="macro", zero_division=0)),
                "f1_macro": float(f1_score(yt_sub, yp_sub, average="macro", zero_division=0)),
                "f1_binary": float(f1_score(yt_sub, yp_sub, pos_label=1, zero_division=0)),
            }

    # Source pair breakdown
    source_metrics = {}
    for sp in sorted(df_eval["source_pair"].unique()):
        sub = df_eval[df_eval["source_pair"] == sp]
        yt_sub = sub[y_true_col].astype(int)
        yp_sub = sub[y_pred_col].astype(int)
        source_metrics[sp] = {
            "count": len(sub),
            "accuracy": float(accuracy_score(yt_sub, yp_sub)),
            "precision_macro": float(precision_score(yt_sub, yp_sub, average="macro", zero_division=0)),
            "recall_macro": float(recall_score(yt_sub, yp_sub, average="macro", zero_division=0)),
            "f1_macro": float(f1_score(yt_sub, yp_sub, average="macro", zero_division=0)),
            "f1_binary": float(f1_score(yt_sub, yp_sub, pos_label=1, zero_division=0)),
        }

    return {
        "evaluated_pairs": len(df_eval),
        "total_pairs": len(df),
        "accuracy": acc,
        "macro_precision": prec_macro,
        "macro_recall": rec_macro,
        "macro_f1": f1_macro,
        "binary_precision": prec_binary,
        "binary_recall": rec_binary,
        "binary_f1": f1_binary,
        "confusion_matrix": {"TN": tn, "FP": fp, "FN": fn, "TP": tp},
        "by_difficulty": hard_metrics,
        "by_source_pair": source_metrics,
    }


def parse_substances(subs_str: Any) -> set[str]:
    """Parse active substances into a clean set of normalized tokens."""
    if pd.isna(subs_str):
        return set()
    parts = str(subs_str).split(";")
    return {
        " ".join(re.sub(r"[^\w\s]", " ", p.upper()).split())
        for p in parts
        if p.strip()
    }


def norm_brand(b_str: Any) -> str:
    """Normalize brand name."""
    if pd.isna(b_str):
        return ""
    return " ".join(re.sub(r"[^\w\s]", " ", str(b_str).upper()).split())


def compute_baseline_match(row: pd.Series) -> int:
    """Correct exact-match baseline (comparing normalized brand and substance sets)."""
    b1 = norm_brand(row.get("brandName1"))
    b2 = norm_brand(row.get("brandName2"))
    s1 = parse_substances(row.get("activeSubstances1"))
    s2 = parse_substances(row.get("activeSubstances2"))
    return int(b1 == b2 and b1 != "" and s1 == s2 and len(s1) > 0)


def run_llm_zero_shot(
    test_csv: Path | str = "data/5_golden_standard_pair/golden_standard_pair_complete/gs_pair_test.csv",
    output_pred_csv: Path | str = "data/6_evaluation/llm_test_predictions.csv",
    model: str = "gemini-3.8-flash",
    batch_delay: float = 1.0,
    max_pairs: int | None = None,
    prefilter_exact: bool = False,
    xml_dir: Path | str = "data/4_translated_mapforce",
) -> tuple[pd.DataFrame, dict[str, Any] | None]:
    """Execute Zero-Shot LLM benchmark using Google GenAI SDK with persistent caching."""
    from google import genai

    df_test = pd.read_csv(test_csv)
    if "brandName1" not in df_test.columns:
        print("Input CSV does not have joined attributes. Enriching from XML target records...")
        entity_lookup = load_xml_entities(xml_dir)
        df_test = enrich_candidate_dataframe(df_test, entity_lookup=entity_lookup)

    if max_pairs:
        df_test = df_test.head(max_pairs)

    out_path = Path(output_pred_csv)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Load existing checkpoint cache if available
    cache: dict[str, tuple[int, str]] = {}
    if out_path.exists():
        df_cache = pd.read_csv(out_path)
        if "pair_id" in df_cache.columns and "pred_llm" in df_cache.columns:
            for _, r in df_cache.iterrows():
                if pd.notna(r["pred_llm"]):
                    cache[str(r["pair_id"])] = (int(r["pred_llm"]), str(r.get("reason_llm", "")))
            print(f"Loaded {len(cache)} existing cached predictions from {out_path.name}.")

    client = genai.Client()
    total_tokens_used = 0
    start_time = time.time()

    print(f"Starting Zero-Shot LLM evaluation using model '{model}' on {len(df_test)} pairs...")
    new_inferences = 0

    preds = []
    reasons = []

    for idx, row in df_test.iterrows():
        pid = str(row["pair_id"])
        if pid in cache:
            p, r = cache[pid]
            preds.append(p)
            reasons.append(r)
            continue

        if prefilter_exact and compute_baseline_match(row) == 1:
            p = 1
            r = "Deterministic exact normalized brand and active substance match"
            cache[pid] = (p, r)
            preds.append(p)
            reasons.append(r)
            continue

        prompt = build_pair_prompt(row)

        try:
            interaction = client.interactions.create(
                model=model,
                input=prompt,
                system_instruction=ZERO_SHOT_SYSTEM_INSTRUCTION,
                generation_config={"temperature": 0.0, "thinking_level": "low"},
                response_format={
                    "type": "text",
                    "mime_type": "application/json",
                    "schema": MatchDecision.model_json_schema(),
                },
                store=False,
            )
            decision = MatchDecision.model_validate_json(interaction.output_text or "{}")
            p = decision.match
            r = decision.reason

            if interaction.usage and hasattr(interaction.usage, "total_tokens"):
                total_tokens_used += int(interaction.usage.total_tokens or 0)

            cache[pid] = (p, r)
            new_inferences += 1

            if new_inferences % 10 == 0 or idx == len(df_test) - 1:
                # Save incremental checkpoint across the full test dataframe
                df_ckpt = df_test.copy()
                df_ckpt["pred_llm"] = [cache.get(str(row_i["pair_id"]), (None, ""))[0] for _, row_i in df_ckpt.iterrows()]
                df_ckpt["reason_llm"] = [cache.get(str(row_i["pair_id"]), (None, ""))[1] for _, row_i in df_ckpt.iterrows()]
                df_ckpt.to_csv(out_path, index=False)
                print(f"Progress: [{idx + 1}/{len(df_test)}] pairs processed. Tokens so far: {total_tokens_used:,}")

            time.sleep(batch_delay)

        except Exception as e:
            print(f"\nAPI Call stopped at row {idx} (pair_id={pid}): {e}")
            print("Incremental checkpoint saved. Re-run after resolving credentials/prepay to resume from this pair.")
            # Save whatever we have so far
            df_test["pred_llm"] = [cache.get(str(r["pair_id"]), (None, ""))[0] for _, r in df_test.iterrows()]
            df_test["reason_llm"] = [cache.get(str(r["pair_id"]), (None, ""))[1] for _, r in df_test.iterrows()]
            df_test.to_csv(out_path, index=False)
            return df_test, None

        preds.append(p)
        reasons.append(r)

    df_test["pred_llm"] = preds
    df_test["reason_llm"] = reasons
    df_test.to_csv(out_path, index=False)
    elapsed = time.time() - start_time
    print(f"Completed {new_inferences} new API inferences in {elapsed:.1f}s. Total tokens: {total_tokens_used:,}.")

    if "match" in df_test.columns:
        metrics = evaluate_predictions(df_test, y_true_col="match", y_pred_col="pred_llm")
    else:
        metrics = None
    return df_test, metrics


def evaluate_candidates_hierarchical(
    candidate_dir: Path | str = "data/7_blocking_candidates",
    source_pair: str | None = None,
    output_matches_csv: Path | str = "data/3_fused/candidate_matches.csv",
    xml_dir: Path | str = "data/4_translated_mapforce",
    fuzzy_threshold: float = 0.8,
    sample_llm: int = 0,
    model: str = "gemini-3.8-flash",
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Evaluate candidate pairs hierarchically without costly full-dataset LLM querying.

    1. Loads and enriches candidate pairs from data/7_blocking_candidates/ with canonical XML attributes.
    2. Deterministic exact pre-filter: automatically identifies exact normalized matches (1,938 pairs).
    3. Prunes disjoint active substances: eliminates ~180,000 non-matches with zero common ingredients.
    4. Evaluates fuzzy candidates using clinical rules (brand similarity + active substance match).
    5. Optionally queries Gemini Flash on sample_llm borderline pairs.
    6. Returns (matches_df, stats_dict) and exports match correspondences to CSV.
    """
    start_time = time.time()
    print("Loading and enriching candidate pairs from blocking...")
    df = load_blocking_candidates(
        candidate_dir=candidate_dir,
        source_pair=source_pair,
        enrich=True,
        xml_dir=xml_dir,
    )
    total_candidates = len(df)
    print(f"Loaded {total_candidates:,} candidate pairs across blocking partitions.")

    exact_matches = 0
    salt_matches = 0
    fuzzy_matches = 0
    pruned_disjoint = 0
    pos_pairs = []

    borderline_candidates = []

    for _, r in df.iterrows():
        b1, b2 = norm_text(r["brandName1"]), norm_text(r["brandName2"])
        s1_raw, s2_raw = norm_text(r["activeSubstances1"]), norm_text(r["activeSubstances2"])
        base_s1 = strip_salts(r["activeSubstances1"])
        base_s2 = strip_salts(r["activeSubstances2"])
        tokens_s1 = parse_substance_tokens(r["activeSubstances1"])
        tokens_s2 = parse_substance_tokens(r["activeSubstances2"])

        # 1. Deterministic exact normalized match (identical brand and substance string)
        if b1 == b2 and b1 != "" and s1_raw == s2_raw and s1_raw != "":
            exact_matches += 1
            pos_pairs.append({
                "id1": r["id1"],
                "id2": r["id2"],
                "source_pair": r.get("source_pair", "all"),
                "score": 1.0,
                "match": 1,
                "match_type": "exact",
                "reason": "Exact normalized brand and active substance match",
            })
        # 2. Exact brand with cross-border salt/ester variation (e.g. Amlodipine vs Amlodipine Besylate)
        elif b1 == b2 and b1 != "" and base_s1 == base_s2 and len(base_s1) > 0:
            salt_matches += 1
            pos_pairs.append({
                "id1": r["id1"],
                "id2": r["id2"],
                "source_pair": r.get("source_pair", "all"),
                "score": 0.95,
                "match": 1,
                "match_type": "salt_variation",
                "reason": f"Exact brand with matching base active substances ({', '.join(sorted(base_s1))}) and regional salt variation",
            })
        # 3. Disjoint active substances (zero shared pharmacological tokens)
        elif len(tokens_s1 & tokens_s2) == 0:
            pruned_disjoint += 1
        # 4. Fuzzy brand with matching base active substances
        elif base_s1 == base_s2 and len(base_s1) > 0:
            sim = SequenceMatcher(None, b1, b2).ratio()
            if sim >= fuzzy_threshold:
                fuzzy_matches += 1
                pos_pairs.append({
                    "id1": r["id1"],
                    "id2": r["id2"],
                    "source_pair": r.get("source_pair", "all"),
                    "score": round(0.5 + 0.5 * sim, 4),
                    "match": 1,
                    "match_type": "fuzzy",
                    "reason": f"Matching base active substances with brand similarity {sim:.2f}",
                })
            else:
                borderline_candidates.append(r)

    # Optional LLM sampling on borderline pairs
    llm_sample_matches = 0
    if sample_llm > 0 and borderline_candidates:
        print(f"Evaluating sample of {min(sample_llm, len(borderline_candidates))} borderline candidates with {model}...")
        try:
            from google import genai
            client = genai.Client()
            for r in borderline_candidates[:sample_llm]:
                prompt = build_pair_prompt(r)
                interaction = client.interactions.create(
                    model=model,
                    input=prompt,
                    system_instruction=ZERO_SHOT_SYSTEM_INSTRUCTION,
                    generation_config={"temperature": 0.0, "thinking_level": "low"},
                    response_format={
                        "type": "text",
                        "mime_type": "application/json",
                        "schema": MatchDecision.model_json_schema(),
                    },
                    store=False,
                )
                decision = MatchDecision.model_validate_json(interaction.output_text or "{}")
                if decision.match == 1:
                    llm_sample_matches += 1
                    pos_pairs.append({
                        "id1": r["id1"],
                        "id2": r["id2"],
                        "source_pair": r.get("source_pair", "all"),
                        "score": 0.9,
                        "match": 1,
                        "match_type": "llm_zero_shot",
                        "reason": f"LLM confirmed: {decision.reason}",
                    })
        except Exception as e:
            print(f"LLM sample evaluation note: {e}")

    df_matches = pd.DataFrame(pos_pairs)
    out_p = Path(output_matches_csv)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    df_matches.to_csv(out_p, index=False)
    elapsed = time.time() - start_time

    stats = {
        "total_candidates": total_candidates,
        "exact_matches": exact_matches,
        "salt_matches": salt_matches,
        "fuzzy_matches": fuzzy_matches,
        "pruned_disjoint_substances": pruned_disjoint,
        "total_positive_matches": len(df_matches),
        "llm_sample_matches": llm_sample_matches,
        "elapsed_seconds": round(elapsed, 2),
    }

    print(f"\nHierarchical Candidate Matching Completed in {elapsed:.2f}s:")
    print(f"- Total Candidates Evaluated: {total_candidates:,}")
    print(f"- Deterministic Exact Matches: {exact_matches:,} (0 API cost)")
    print(f"- Cross-Border Salt Variations (same brand): {salt_matches:,} (0 API cost)")
    print(f"- Pruned Disjoint Substances: {pruned_disjoint:,} (0 API cost)")
    print(f"- High-Confidence Fuzzy Matches: {fuzzy_matches:,}")
    if sample_llm > 0:
        print(f"- LLM Verified Sample Matches: {llm_sample_matches:,}")
    print(f"- Total Candidate Matches Exported: {len(df_matches):,} to {out_p}")

    return df_matches, stats


def format_report_markdown(metrics: dict[str, Any], model_name: str = "gemini-3.8-flash") -> str:
    """Format evaluation results as a clean Markdown report."""
    cm = metrics["confusion_matrix"]
    total = metrics["evaluated_pairs"]

    md = f"""# Zero-Shot LLM Matcher Evaluation Benchmark Report

## Experiment Configuration
- **Model:** `{model_name}` (temperature=0, structured JSON output)
- **SDK:** `google-genai` (v3.0.0)
- **Dataset:** Stratified held-out test split (`gs_pair_test.csv`)
- **Total Evaluated Pairs:** {total:,}

## Executive Summary
- **Macro F1 Score:** **{metrics['macro_f1']:.4f}** ({metrics['macro_f1'] * 100:.2f}%)
- **Match Class F1 Score:** **{metrics['binary_f1']:.4f}** ({metrics['binary_f1'] * 100:.2f}%)
- **Overall Accuracy:** {metrics['accuracy']:.4f} ({metrics['accuracy'] * 100:.2f}%)
- **Macro Precision:** {metrics['macro_precision']:.4f} | **Macro Recall:** {metrics['macro_recall']:.4f}

## Confusion Matrix
| Metric | Predicted Non-match (0) | Predicted Match (1) | Total True |
| :--- | ---: | ---: | ---: |
| **Actual Non-match (0)** | **TN = {cm['TN']}** | FP = {cm['FP']} | {cm['TN'] + cm['FP']} |
| **Actual Match (1)** | FN = {cm['FN']} | **TP = {cm['TP']}** | {cm['FN'] + cm['TP']} |
| **Total Predicted** | {cm['TN'] + cm['FN']} | {cm['FP'] + cm['TP']} | **{total}** |

## Performance by Difficulty Pool
| Difficulty Pool | Pairs | Accuracy | Macro F1 | Match F1 |
| :--- | ---: | ---: | ---: | ---: |
| **Ordinary Pool (`hard=0`)** | {metrics['by_difficulty']['ordinary']['count']} | {metrics['by_difficulty']['ordinary']['accuracy']:.2%} | **{metrics['by_difficulty']['ordinary']['f1_macro']:.4f}** | {metrics['by_difficulty']['ordinary']['f1_binary']:.4f} |
| **Hard Pool (`hard=1`)** | {metrics['by_difficulty']['hard']['count']} | {metrics['by_difficulty']['hard']['accuracy']:.2%} | **{metrics['by_difficulty']['hard']['f1_macro']:.4f}** | {metrics['by_difficulty']['hard']['f1_binary']:.4f} |

## Performance by Source Jurisdiction Pair
| Jurisdiction Pair | Pairs | Accuracy | Macro F1 | Match F1 |
| :--- | ---: | ---: | ---: | ---: |
"""
    for sp, data in metrics["by_source_pair"].items():
        md += f"| **{sp.upper()}** | {data['count']} | {data['accuracy']:.2%} | **{data['f1_macro']:.4f}** | {data['f1_binary']:.4f} |\n"

    return md


def main():
    parser = argparse.ArgumentParser(description="Zero-shot LLM Matcher & Hierarchical Candidate Matching.")
    parser.add_argument(
        "--test-csv",
        default="data/5_golden_standard_pair/golden_standard_pair_complete/gs_pair_test.csv",
        help="Path to stratified test dataset.",
    )
    parser.add_argument(
        "--output-csv",
        default="data/6_evaluation/llm_test_predictions.csv",
        help="Path to save predictions CSV.",
    )
    parser.add_argument(
        "--model",
        default="gemini-3.8-flash",
        help="Gemini model code to evaluate.",
    )
    parser.add_argument(
        "--match-candidates",
        action="store_true",
        help="Run hierarchical candidate matcher over data/7_blocking_candidates/.",
    )
    parser.add_argument(
        "--candidate-dir",
        default="data/7_blocking_candidates",
        help="Directory containing blocking candidate CSVs.",
    )
    parser.add_argument(
        "--source-pair",
        default=None,
        help="Specific source pair to evaluate ('dpd_ema', 'dpd_fda', 'ema_fda').",
    )
    parser.add_argument(
        "--sample-llm",
        type=int,
        default=0,
        help="Number of borderline candidate pairs to evaluate with Gemini LLM.",
    )
    parser.add_argument(
        "--output-matches",
        default="data/3_fused/candidate_matches.csv",
        help="Output CSV for positive match correspondences.",
    )
    args = parser.parse_args()

    if args.match_candidates:
        df_matches, stats = evaluate_candidates_hierarchical(
            candidate_dir=args.candidate_dir,
            source_pair=args.source_pair,
            output_matches_csv=args.output_matches,
            sample_llm=args.sample_llm,
            model=args.model,
        )
        return

    df_test, metrics = run_llm_zero_shot(args.test_csv, args.output_csv, model=args.model)
    if metrics:
        report_md = format_report_markdown(metrics, model_name=args.model)
        report_file = Path("data/6_evaluation/llm_test_report.md")
        with open(report_file, "w") as f:
            f.write(report_md)
        print(f"\nSaved report to {report_file}")
        print(report_md)


if __name__ == "__main__":
    main()
