# Zero-Shot LLM Evaluation: Blind Execution Audit Trail

This audit trail documents how the 525 predictions in [llm_test_predictions.csv](llm_test_predictions.csv) were produced on 2026-11-09 and provides the raw subagent execution transcripts so teammates and graders can inspect inputs, outputs, and tool usage directly.

## Context and Transparency Note

Direct API calls from [llm_zero_shot_matcher.py](../../src/identity_resolution/llm_zero_shot_matcher.py) via `google-genai` failed on 2026-11-09 with `HTTP 402 RESOURCE_EXHAUSTED` due to a depleted Google Cloud prepayment balance. An initial multi-agent run (`pair_matcher`) was audited and rejected after detecting ground-truth file reads and web searches in its logs. All 525 pairs were then re-evaluated from scratch using a locked-down Antigravity subagent definition (`blind_zero_shot_matcher`, `Model="flash"`).

Two methodological limitations of this audit trail are stated openly:
- **Unsigned local logs:** The files under [subagent_transcripts/](audit/subagent_transcripts/) are raw Antigravity JSONL logs exported from the local execution environment; they are inspectable audit artifacts, not third-party cryptographically signed API receipts.
- **Batched subagent execution vs. direct SDK:** Pairs were evaluated in isolated batches of 1 to 75 pairs under the Antigravity subagent harness rather than 525 standalone single-pair `google-genai` calls, so API-layer Pydantic JSON schema enforcement was not active during inference (Gemini 3.6+ models ignore custom `temperature` overrides and run at default sampling regardless). The standalone `google-genai` pipeline remains available in [llm_zero_shot_matcher.py](../../src/identity_resolution/llm_zero_shot_matcher.py) for independent API re-execution.

## What Can Be Independently Verified From the Raw Logs

- **Raw subagent logs included:** All 17 unmodified `blind_zero_shot_matcher` transcripts (13 completed runs covering indices 0 to 524 plus 4 killed timeout/stream-interrupted retries) are stored in [audit/subagent_transcripts/](audit/subagent_transcripts/).
- **Tool restrictions:** [blind_zero_shot_matcher_agent.md](audit/blind_zero_shot_matcher_agent.md) omitted `run_command`, `write_file`, `edit_file`, MCP tools, and child subagents, and explicitly instructed the model to execute zero tool calls.
- **Zero tool calls in every raw log:** Every JSON step across all 17 raw `.jsonl` files has zero entries in `tool_calls`. Every one of the 13 completed runs consists strictly of step 0 (`SYSTEM_MESSAGE` input) and step 1 (`PLANNER_RESPONSE` JSON array output).
- **Byte-for-byte four-attribute inputs:** Step 0 of every raw `.jsonl` transcript matches byte-for-byte a prompt reconstructed strictly from four non-label columns (`brandName`, `activeSubstances`, `licenceHolder`, `dosageForm`) plus source (`DPD`, `EMA`, `FDA`) in `gs_pair_test.csv`. Columns `match`, `hard`, `id1`, `id2`, and `pred_baseline` never appear in any input prompt.
- **Sealed workspace window:** Verbatim parent-transcript steps 461, 462, 614, 615, and 616 are archived in [workspace_sealing_protocol.jsonl](audit/workspace_sealing_protocol.jsonl). They record archiving `data/5_golden_standard_pair`, `data/6_evaluation`, `notebooks/01_llm_zero_shot_matcher.ipynb`, and `scratch` to `/tmp/wdi_vault.tar.gz` and deleting them from the workspace (`2026-11-09T14:53:01Z` to `14:53:15Z`, exit code 0), then restoring them only after terminating all remaining blind subagents with `kill_all` (`2026-11-09T15:31:07Z` to `15:31:27Z`). Every step timestamp across all 17 raw subagent transcripts falls strictly inside that sealed window.
- **Verbatim 525-row match:** Parsing the step-1 JSON arrays directly from the 13 completed raw transcripts reproduces `pred_llm` and `reason_llm` verbatim for all 525 rows of [llm_test_predictions.csv](llm_test_predictions.csv) and yields `Macro F1 = 0.9485` (`Accuracy = 95.24%`, `TN = 322`, `FP = 17`, `FN = 8`, `TP = 178`).

## Raw Subagent Transcript Index (2026-11-09 UTC)

| Pair Indices | Role | Raw Transcript File | Status | Steps | Tool Calls |
| :--- | :--- | :--- | :--- | ---: | ---: |
| 0 to 74 | Blind Evaluator 00-74 | [f5363fea.jsonl](audit/subagent_transcripts/f5363fea-180c-4c8e-89df-ae3a0b693eed.jsonl) | Completed (used) | 2 | 0 |
| 75 to 149 | Blind Evaluator 75-149 | [58502bc2.jsonl](audit/subagent_transcripts/58502bc2-60b3-43dd-acf0-7c849cfabb1a.jsonl) | Completed (used) | 2 | 0 |
| 150 to 224 | Blind Evaluator 150-224 | [1758d824.jsonl](audit/subagent_transcripts/1758d824-4514-483c-b437-305af4afb181.jsonl) | Killed (superseded) | 2 | 0 |
| 225 to 299 | Blind Evaluator 225-299 | [2679a713.jsonl](audit/subagent_transcripts/2679a713-27fb-4e0f-b8ac-615748df4d2d.jsonl) | Completed (used) | 2 | 0 |
| 300 to 374 | Blind Evaluator 300-374 | [226566eb.jsonl](audit/subagent_transcripts/226566eb-0239-40bb-9752-0050a8554598.jsonl) | Completed (used) | 2 | 0 |
| 375 to 449 | Blind Evaluator 375-449 | [6fe38796.jsonl](audit/subagent_transcripts/6fe38796-e0e1-4541-ad20-4ddac03cf3f5.jsonl) | Completed (used) | 2 | 0 |
| 450 to 524 | Blind Evaluator 450-524 | [ae8fbdbe.jsonl](audit/subagent_transcripts/ae8fbdbe-4f74-4cc4-b74c-1ffcf77ba107.jsonl) | Completed (used) | 2 | 0 |
| 150 to 224 | Blind Evaluator 150-224 Retry | [9e1e9b06.jsonl](audit/subagent_transcripts/9e1e9b06-c640-4dd3-9bde-5cf46f4910f8.jsonl) | Killed (stream interrupted) | 6 | 0 |
| 150 to 174 | Blind Evaluator 150-174 | [34517090.jsonl](audit/subagent_transcripts/34517090-5ea3-48bc-9f82-e3ccc0bbb3c4.jsonl) | Completed (used) | 2 | 0 |
| 175 to 199 | Blind Evaluator 175-199 | [5e52fc15.jsonl](audit/subagent_transcripts/5e52fc15-b451-494e-a1cb-808b995480d5.jsonl) | Completed (used) | 2 | 0 |
| 200 to 224 | Blind Evaluator 200-224 | [190d2e84.jsonl](audit/subagent_transcripts/190d2e84-bb62-4f29-af7f-d23c06916d0d.jsonl) | Killed (superseded) | 2 | 0 |
| 200 to 212 | Blind Evaluator 200-212 | [320b7a5b.jsonl](audit/subagent_transcripts/320b7a5b-e62c-49e1-91bc-ac2bd1416b67.jsonl) | Completed (used) | 2 | 0 |
| 213 to 224 | Blind Evaluator 213-224 | [8311b8c3.jsonl](audit/subagent_transcripts/8311b8c3-b364-480a-8fed-72e3ba9bd57c.jsonl) | Killed (superseded) | 2 | 0 |
| 213 | Blind Evaluator 213 | [70374db8.jsonl](audit/subagent_transcripts/70374db8-7313-4635-9b65-1b51494d370d.jsonl) | Completed (used) | 2 | 0 |
| 214 to 219 | Blind Evaluator 214-219 | [c194579a.jsonl](audit/subagent_transcripts/c194579a-4016-40a8-bce9-38ca03d27b8e.jsonl) | Completed (used) | 2 | 0 |
| 220 | Blind Evaluator 220 | [c4c50c4f.jsonl](audit/subagent_transcripts/c4c50c4f-63dd-4505-881c-f9b0356c7967.jsonl) | Completed (used) | 2 | 0 |
| 221 to 224 | Blind Evaluator 221-224 | [8df6cdbb.jsonl](audit/subagent_transcripts/8df6cdbb-156e-4af0-af67-c5fa45476fd8.jsonl) | Completed (used) | 2 | 0 |

## Reproducible Audit Command

Run the offline verifier against the raw JSONL transcripts and [llm_test_predictions.csv](llm_test_predictions.csv):

```bash
python3 src/identity_resolution/verify_blind_llm_proof.py
```
