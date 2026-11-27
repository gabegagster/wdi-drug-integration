"""Audit trail verifier for the blind Zero-Shot LLM evaluation.

Reads the 17 raw subagent JSONL transcripts in data/6_evaluation/audit/subagent_transcripts/
and independently verifies without external API calls that:
1. Every raw transcript contains zero tool calls across all logged steps.
2. Every raw transcript's step-0 input prompt matches byte-for-byte a prompt reconstructed
   strictly from the 4 non-label attributes (brandName, activeSubstances, licenceHolder,
   dosageForm) plus source tag in gs_pair_test.csv (zero ground-truth columns or IDs).
3. All 17 raw transcripts have timestamps strictly within the sealed workspace window
   (2026-11-09T14:53:01Z to 2026-11-09T15:31:07Z) and contain no leaked API keys/secrets.
4. Parsing the step-1 JSON arrays directly from the 13 completed raw transcripts covers
   indices 0..524 with zero gaps or overlaps and matches data/6_evaluation/llm_test_predictions.csv
   100% verbatim on both pred_llm and reason_llm across all 525 rows.
5. Re-evaluating those raw transcript predictions against gs_pair_test.csv reproduces the
   exact reported metrics (Macro F1 = 0.9485, Accuracy = 0.9524, TN=322, FP=17, FN=8, TP=178).
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.identity_resolution.llm_zero_shot_matcher import _clean_field, evaluate_predictions

SECRET_PATTERN = re.compile(r"(AIza[0-9A-Za-z_\-]{20,}|AQ\.Ab[0-9A-Za-z_\-]{10,}|GEMINI_API_KEY|OPENAI_API_KEY|sk-[A-Za-z0-9]{16,})")


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _reconstruct_prompt(df_test: pd.DataFrame, inv: dict) -> str:
    header = inv["prompt_header"]
    start, end = int(inv["start_index"]), int(inv["end_index"])
    mode = inv["format_mode"]

    pair_blocks: list[str] = []
    for idx in range(start, end + 1):
        row = df_test.iloc[idx]
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

        r1 = (
            f"Record 1 ({src1}): Brand Name: {b1} | Active Substance(s): {s1} | "
            f"Licence Holder / Manufacturer: {h1} | Dosage Form: {df1}"
        )
        r2 = (
            f"Record 2 ({src2}): Brand Name: {b2} | Active Substance(s): {s2} | "
            f"Licence Holder / Manufacturer: {h2} | Dosage Form: {df2}"
        )
        if mode == "multi_pair":
            pair_blocks.append(f"=== PAIR INDEX {idx} ===\n{r1}\n{r2}")
        else:
            pair_blocks.append(f"{r1}\n{r2}")

    body = "\n\n".join(pair_blocks) if mode == "multi_pair" else pair_blocks[0]
    prompt = f"{header}\n{body}"
    if inv.get("trailing_newline"):
        prompt += "\n"
    return prompt


def main() -> int:
    audit_dir = PROJECT_ROOT / "data/6_evaluation/audit"
    transcripts_dir = audit_dir / "subagent_transcripts"
    protocol_path = audit_dir / "workspace_sealing_protocol.jsonl"
    audit_path = audit_dir / "blind_subagent_audit.json"
    agent_def_path = audit_dir / "blind_zero_shot_matcher_agent.md"
    test_csv_path = PROJECT_ROOT / "data/5_golden_standard_pair/golden_standard_pair_complete/gs_pair_test.csv"
    pred_csv_path = PROJECT_ROOT / "data/6_evaluation/llm_test_predictions.csv"

    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    df_test = pd.read_csv(test_csv_path)
    df_pred = pd.read_csv(pred_csv_path)

    # 1. File integrity, agent restrictions, and raw workspace-sealing protocol checks
    assert _sha256_file(agent_def_path) == audit["blind_subagent_definition_sha256"], "Agent definition SHA-256 mismatch!"
    assert _sha256_file(test_csv_path) == audit["artifact_sha256"]["gs_pair_test.csv"], "gs_pair_test.csv SHA-256 mismatch!"
    assert _sha256_file(pred_csv_path) == audit["artifact_sha256"]["llm_test_predictions.csv"], "llm_test_predictions.csv SHA-256 mismatch!"

    agent_text = agent_def_path.read_text(encoding="utf-8")
    assert "run_command" not in agent_text and "write_file" not in agent_text and "edit_file" not in agent_text

    # Parse raw parent-transcript sealing & restoration protocol directly
    protocol_raw = protocol_path.read_text(encoding="utf-8")
    assert not SECRET_PATTERN.findall(protocol_raw), "Potential secret found in workspace_sealing_protocol.jsonl!"
    protocol_steps = [json.loads(line) for line in protocol_raw.splitlines() if line.strip()]
    assert [s["step_index"] for s in protocol_steps] == [461, 462, 614, 615, 616], "Unexpected protocol step indices!"

    seal_cmd = protocol_steps[0]["tool_calls"][0]["args"]["CommandLine"]
    for sealed_item in ("data/5_golden_standard_pair", "data/6_evaluation", "notebooks/01_llm_zero_shot_matcher.ipynb"):
        assert sealed_item in seal_cmd, f"Expected {sealed_item} in sealing command!"
    assert "shutil.rmtree" in seal_cmd and "/tmp/wdi_vault.tar.gz" in seal_cmd
    assert "Command exited with code 0." in protocol_steps[1]["content"]
    assert "Sealed ground-truth and evaluation files outside workspace." in protocol_steps[1]["content"]

    restore_tools = {tc["name"]: tc["args"] for tc in protocol_steps[2]["tool_calls"]}
    assert restore_tools.get("manage_subagents", {}).get("Action") == "kill_all"
    assert "tar -xzf /tmp/wdi_vault.tar.gz" in restore_tools["run_command"]["CommandLine"]
    assert "Successfully killed 4 subagent(s)" in protocol_steps[3]["content"]

    seal_ts = protocol_steps[1]["created_at"]
    restore_ts = protocol_steps[2]["created_at"]

    # Confirm exact set of raw transcript files on disk
    disk_files = sorted(p.name for p in transcripts_dir.glob("*.jsonl"))
    expected_files = sorted(f"{inv['conversation_id']}.jsonl" for inv in audit["invocations"])
    assert disk_files == expected_files, f"Transcript file set mismatch: {disk_files} vs {expected_files}"

    # 2. Directly inspect all 17 raw subagent JSONL transcripts
    raw_preds: dict[int, tuple[int, str]] = {}
    total_steps_checked = 0
    total_tool_calls = 0
    used_count = 0

    for inv in audit["invocations"]:
        cid = inv["conversation_id"]
        tpath = transcripts_dir / f"{cid}.jsonl"
        raw_text = tpath.read_text(encoding="utf-8")

        # Privacy check: ensure no API keys or secrets are present
        secrets = SECRET_PATTERN.findall(raw_text)
        assert not secrets, f"Potential secret found in {tpath.name}: {secrets}"

        steps = [json.loads(line) for line in raw_text.splitlines() if line.strip()]
        assert len(steps) >= 2, f"Expected >=2 steps in {tpath.name}"
        total_steps_checked += len(steps)

        # Verify zero tool calls across every step in the raw JSONL
        for st in steps:
            tcs = st.get("tool_calls") or []
            total_tool_calls += len(tcs)
            assert len(tcs) == 0, f"Tool calls found in {cid} step {st.get('step_index')}: {tcs}"
            ts = st.get("created_at")
            assert seal_ts <= ts <= restore_ts, f"Step timestamp {ts} in {cid} outside sealed window [{seal_ts}, {restore_ts}]!"

        # Verify step 0 prompt in the raw JSONL matches 4-attribute reconstruction byte-for-byte
        step0_content = steps[0]["content"]
        match_msg = re.search(r"priority=MESSAGE_PRIORITY_HIGH content=(.*)\n</SYSTEM_MESSAGE>$", step0_content, re.S)
        assert match_msg is not None, f"Could not parse step-0 SYSTEM_MESSAGE in {cid}"
        actual_prompt = match_msg.group(1)
        reconstructed_prompt = _reconstruct_prompt(df_test, inv)
        assert actual_prompt == reconstructed_prompt, f"Raw step-0 prompt mismatch in {cid} ({inv['role']})!"
        assert hashlib.sha256(actual_prompt.encode("utf-8")).hexdigest() == inv["prompt_sha256"]

        # Parse step-1 JSON predictions directly from completed raw transcripts
        if inv["status"] == "completed_used":
            used_count += 1
            assert len(steps) == 2, f"Completed blind run {cid} had {len(steps)} steps (expected 2)!"
            s1_text = steps[1]["content"].strip()
            if s1_text.startswith("```"):
                s1_text = re.sub(r"^```(?:json)?\s*|\s*```$", "", s1_text, flags=re.S)
            parsed = json.loads(s1_text)
            expected_indices = list(range(int(inv["start_index"]), int(inv["end_index"]) + 1))
            got_indices = [int(item["index"]) for item in parsed]
            assert got_indices == expected_indices, f"Index mismatch in {cid}: {got_indices[:5]} vs {expected_indices[:5]}"
            for item in parsed:
                idx = int(item["index"])
                assert idx not in raw_preds, f"Duplicate prediction for index {idx}"
                raw_preds[idx] = (int(item["match"]), str(item["reason"]))

    # 3. Verify complete 0..524 coverage and 100% verbatim agreement with llm_test_predictions.csv
    assert len(raw_preds) == 525 and set(raw_preds.keys()) == set(range(525)), "Incomplete coverage of 0..524!"
    assert len(df_pred) == 525
    assert df_pred["pair_id"].tolist() == df_test["pair_id"].tolist(), "Pair ordering mismatch vs gs_pair_test.csv!"

    for idx in range(525):
        p_raw, r_raw = raw_preds[idx]
        p_csv = int(df_pred.iloc[idx]["pred_llm"])
        r_csv = str(df_pred.iloc[idx]["reason_llm"])
        assert p_raw == p_csv, f"Prediction mismatch at row {idx}: raw={p_raw} vs csv={p_csv}"
        assert r_raw == r_csv, f"Rationale mismatch at row {idx}: raw={r_raw!r} vs csv={r_csv!r}"

    # 4. Re-compute benchmark metrics directly from raw transcript predictions
    df_eval = df_test.copy()
    df_eval["pred_from_raw_logs"] = [raw_preds[i][0] for i in range(525)]
    metrics = evaluate_predictions(df_eval, y_true_col="match", y_pred_col="pred_from_raw_logs")
    cm = metrics["confusion_matrix"]
    assert (cm["TN"], cm["FP"], cm["FN"], cm["TP"]) == (322, 17, 8, 178)

    print("PASS: Raw subagent JSONL audit trail verified end-to-end.")
    print(f"  - Raw subagent transcripts verified: {len(disk_files)} files ({used_count} completed, {total_steps_checked} total steps)")
    print(f"  - Tool calls executed across all raw logs: {total_tool_calls}")
    print(f"  - Sealed execution window: {seal_ts} .. {restore_ts}")
    print(f"  - Raw step-0 prompts matching 4-attribute reconstruction byte-for-byte: {len(audit['invocations'])}/{len(audit['invocations'])}")
    print(f"  - Raw step-1 outputs matching llm_test_predictions.csv verbatim: 525/525 (pred_llm and reason_llm)")
    print(f"  - Re-computed metrics: Macro F1={metrics['macro_f1']:.4f}, Accuracy={metrics['accuracy']:.4f}, CM={cm}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
