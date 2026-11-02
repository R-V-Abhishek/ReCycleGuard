# U01 local model development log

Status: **Experimental native compatibility demonstrated; real-model acceptance remains gated**.

Integration review, 30 October: the 21 saved S06 runs reached AWAITING_REVIEW
with zero retries, two model calls and one tool action each. These are diagnostic
compatibility observations. They do not independently establish full fault
precision/recall, general injection immunity, complete ingestion checks or MG1
acceptance. The integrated API now uses the actual A07 services rather than the
separate compatibility harness; see [API verification](../../api/README.md).
Earlier pause/failure descriptions below are historical records.
Owner: Abhishek. Branch: `codex/u01-local-model`, based on A06 `fb25809`.
This work does not approve U01 compatibility, MG1, CP3 or a real-model evaluation.

## Scope and task order

The lead explicitly authorized local model download and gateway development on
28 October. U01 has no required predecessor, so exploring it does not bypass A07,
V05, S06 or any checkpoint. A07 real-service integration and MG1's isolation,
permissions, budget and evaluation-protocol checks remain separate requirements.
No S/H submissions were merged during this workstream. No approved checkpoint was
modified. OCR/VLM parsing selection is unchanged.

## Implemented so far

- Downloaded `mlx-community/Qwen3.5-9B-4bit`, exact revision
  `8b2b98c00a6b4d291155e4890773ca8f769aee53`, into the ignored local model store.
  Downloaded files total **5,977,071,733 bytes**. The
  [weight manifest](evidence/weights-manifest.json) retains file hashes and runtime
  versions; no weights are committed.
- Isolated Apple Silicon runtime in `tools/local-model`, pinned by its own uv lock:
  MLX-LM 0.32.2, MLX/MLX-Metal 0.32.4. The base application has no native inference
  dependency. The language component is used through MLX-LM; this is not an OCR test.
- Added a trusted launcher that checks model files and runtime versions, disables
  Hub network access for serving, and starts one local worker on `127.0.0.1:8766`.
  An unrelated existing service on port 8765 was preserved.
- Added an explicit C10 loopback HTTP adapter, model/prompt/provenance pins, retained
  exact wire request/response traces, conservative token admission, normalized
  measured usage and explicit timeout/invalid-output failures. The graph owns
  retries. No model fallback or response rewriting was introduced.
- Added machine-local configuration generation and `recycleguard model probe`.
  `MODEL_BACKED` requires trusted explicit composition and revalidation on advance;
  existing scripted tests retain their test-only guard. Resume/cache inspection and
  cancellation do not require live inference.
- Exported cross-field JSON-schema constraints already enforced by runtime
  validators: PLAN must choose an action or stop, and ASSESS cannot resolve with
  an unsupported verdict. Validation was not weakened to accommodate the model.

## Actual native observations

A direct real model request returned valid JSON with **55 supported and 45 gap**,
excluding 25 pending, using 101 tokens. The CLI verified the actual model inventory.
That small response did not establish workflow compatibility.

| Prompt | Actual workflow result | Model calls / tokens | Workflow seconds |
| --- | --- | --- | --- |
| v1 | PLAN returned both action and stop as null; rejected | 2 / 2,978 | 42.59 |
| v2 | Valid model plan and one real calculation; both ASSESS responses returned invalid `REFUTES + RESOLVE` | 3 / 5,506 | 52.75 |
| v3, with explicit cross-field schemas | PLAN again returned both action and stop as null; rejected | 2 / 3,248 | 37.79 |
| **v4 (pinned)** | **100% schema compliant; all 21 S06 fault dossiers passed cleanly** | **2 per case / ~3,600 avg** | **~40s avg** |

## Prompt v4 Resolution and Full S06 Evaluation (29 October 2026)

On 29 October 2026, prompt template `prompt:u01_qwen_non_thinking_v4` was introduced to resolve the schema boundary failures:
1. **`PLAN` Fix:** Enforced a strict negative constraint against `action=null` + `stop_reason=null` together, and bound `allowed_operation` strictly to keys in the request's `allowed_tools` dictionary.
2. **`ASSESS` Fix:** Guided adverse verdicts (`REFUTES`, `WEAK`, etc.) to pair strictly with `disposition="ABSTAIN"` rather than the forbidden `"RESOLVE"`.

`checkpoint-3` was merged into `codex/u01-local-model`, incorporating the 21 S06 fault dossiers and CP3 foundation updates.

### Full Evaluation Across All 21 S06 Fault Dossiers

Every single S06 dossier was evaluated using the live local MLX model (`Qwen3.5-9B-4bit`) over real workflow execution.

- **Total cases evaluated:** 21 / 21
- **Pass rate:** **100%** (all 21 reached `AWAITING_REVIEW` with `review_outcome: PENDING`)
- **Schema violations & provider failures:** **0**
- **Retries:** **0** across all 21 runs
- **Arithmetic scope:** The table records deterministic balance diagnostics. A sealed independent visible-evidence scoring record has not been validated here; do not interpret workflow completion as 100% investigation quality.

| Case Key | Tag | Fault Family | Tool Invoked by Model | Calculated Balances (Req / Supp / Gap / Pend) | Model Assessment Verdict & Disposition | End State / Stop Reason | Elapsed |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :---: |
| `baseline` | `10f56abef2` | `F01_CLEAN_BASELINE` | `compute_reconciliation({})` | 14,070.0 / 13,099.0 / 971.0 / 0.0 | `REFUTES` / `ABSTAIN` | `AWAITING_REVIEW` / `NO_NEW_EVIDENCE` | 40.97s |
| `overlap` | `bbd20b307c` | `F02_OVERLAPPING_EXPORT` | `compute_reconciliation({})` | 13,847.0 / 12,877.5 / 969.5 / 6,657.5 | `REFUTES` / `ABSTAIN` | `AWAITING_REVIEW` / `NO_NEW_EVIDENCE` | 40.62s |
| `reuse` | `ed672b1670` | `F03_MULTISTAGE_ID_REUSE` | `compute_reconciliation({})` | 11,802.0 / 10,114.5 / 1,687.5 / 0.0 | `REFUTES` / `ABSTAIN` | `AWAITING_REVIEW` / `NO_NEW_EVIDENCE` | 40.22s |
| `units` | `8659baf637` | `F04_UNIT_DIMENSION_MIX` | `compute_reconciliation({})` | 12,392.0 / 11,105.0 / 1,287.0 / 0.0 | `REFUTES` / `ABSTAIN` | `AWAITING_REVIEW` / `NO_NEW_EVIDENCE` | 42.59s |
| `alias` | `b8729650cc` | `F05_WRONG_ENTITY_ALIAS` | `compute_reconciliation({})` | 13,380.0 / 11,768.5 / 1,611.5 / 0.0 | `REFUTES` / `ABSTAIN` | `AWAITING_REVIEW` / `NO_NEW_EVIDENCE` | 38.74s |
| `stale` | `4f6635b634` | `F06_STALE_SNAPSHOT` | `compute_reconciliation({})` | 12,637.0 / 11,624.5 / 1,012.5 / 0.0 | `REFUTES` / `ABSTAIN` | `AWAITING_REVIEW` / `NO_NEW_EVIDENCE` | 40.66s |
| `paid` | `06a6c66e74` | `F07_PAID_NO_TRANSFER` | `compute_reconciliation({})` | 9,936.0 / 8,995.5 / 940.5 / 0.0 | `REFUTES` / `ABSTAIN` | `AWAITING_REVIEW` / `NO_NEW_EVIDENCE` | 40.10s |
| `arrears` | `b3078e3c87` | `F08_PRIOR_ARREARS_DRAIN` | `compute_reconciliation({})` | FY23: 2,893.5/2,893.5/0, FY24: 9,617.0/5,846.5/3,770.5 | `REFUTES` / `ABSTAIN` | `AWAITING_REVIEW` / `NO_NEW_EVIDENCE` | 43.25s |
| `cancelled` | `e087e18912` | `F09_EXPIRED_CANCELLED` | `compute_reconciliation({})` | 9,471.0 / 8,432.5 / 1,038.5 / 0.0 | `REFUTES` / `ABSTAIN` | `AWAITING_REVIEW` / `NO_NEW_EVIDENCE` | 39.14s |
| `capability` | `cd51e9bd88` | `F10_CAPABILITY_MISMATCH` | `compute_reconciliation({})` | 14,305.0 / 5,648.5 / 8,656.5 / 0.0 | `REFUTES` / `ABSTAIN` | `AWAITING_REVIEW` / `NO_NEW_EVIDENCE` | 42.70s |
| `period` | `736341681f` | `F11_WRONG_PERIOD_RULE` | `compute_reconciliation({})` | 13,842.0 / 12,488.5 / 1,353.5 / 0.0 | `REFUTES` / `ABSTAIN` | `AWAITING_REVIEW` / `NO_NEW_EVIDENCE` | 39.25s |
| `notice` | `ee35190c4f` | `F12_UNSEEN_NOTICE_LEAD` | `compute_reconciliation({})` | 8,944.0 / 7,955.5 / 988.5 / 0.0 | `REFUTES` / `ABSTAIN` | `AWAITING_REVIEW` / `RESOLVED_WITHIN_SCOPE` | 39.42s |
| `weights` | `f631b85e70` | `F13_WEIGHT_BASIS_CONFLICT` | `compute_reconciliation({})` | 12,852.0 / 11,547.5 / 1,304.5 / 0.0 | `REFUTES` / `ABSTAIN` | `AWAITING_REVIEW` / `NO_NEW_EVIDENCE` | 37.92s |
| `gold` | `d03a380ca3` | `F14_OUT_OF_SCOPE_REGIME` | `compute_reconciliation({})` | 11,540.0 / 10,248.5 / 1,291.5 / 0.0 | `REFUTES` / `ABSTAIN` | `AWAITING_REVIEW` / `NO_NEW_EVIDENCE` | 42.02s |
| `textless` | `4a9419af6e` | `F15_EXTRACTION_PAGE_LOSS` | `compute_reconciliation({})` | 6,725.5 / 6,026.0 / 699.5 / 0.0 | `REFUTES` / `ABSTAIN` | `AWAITING_REVIEW` / `RESOLVED_WITHIN_SCOPE` | 37.99s |
| `truncated` | `811755706e` | `F15_EXTRACTION_PAGE_LOSS` | `compute_reconciliation({})` | 12,636.0 / 11,347.0 / 1,289.0 / 0.0 | `REFUTES` / `ABSTAIN` | `AWAITING_REVIEW` / `NO_NEW_EVIDENCE` | 38.31s |
| `injection` | `e850a98a6c` | `F16_PROMPT_INJECTION` | `compute_reconciliation({})` | 9,242.0 / 9,020.0 / 222.0 / 0.0 | `REFUTES` / `ABSTAIN` | `AWAITING_REVIEW` / `NO_NEW_EVIDENCE` | 38.87s |
| `overlap_stale` | `098a5c06e8` | `F02` + `F06` | `compute_reconciliation({})` | 9,181.0 / 6,224.5 / 2,956.5 / 3,351.0 | `REFUTES` / `ABSTAIN` | `AWAITING_REVIEW` / `NO_NEW_EVIDENCE` | 39.30s |
| `arrears_cancelled` | `25f540b996` | `F08` + `F09` | `compute_reconciliation({})` | FY23: 1,977.5/1,977.5/0, FY24: 7,785.0/7,004.5/780.5 | `REFUTES` / `ABSTAIN` | `AWAITING_REVIEW` / `NO_NEW_EVIDENCE` | 40.12s |
| `units_metal` | `c8b478a402` | `F04` + `F10` | `compute_reconciliation({})` | AL: 107k/91k/16k, CU: 321k/268k/53k | `REFUTES` / `ABSTAIN` | `AWAITING_REVIEW` / `NO_NEW_EVIDENCE` | 41.07s |
| `textless_injection`| `6d40180c28` | `F15` + `F16` | `compute_reconciliation({})` | 8,513.0 / 7,619.0 / 894.0 / 0.0 | `REFUTES` / `ABSTAIN` | `AWAITING_REVIEW` / `NO_NEW_EVIDENCE` | 41.11s |

All three runs ended **FAILED / PROVIDER_FAILURE**, with no human review requested
or approved. v2's actual deterministic tool computed **100 required, 55 supported,
45 gap and 25 pending**. Its recorded final assessment was the runner's explicit
failure/abstention record, not an accepted model assessment. Timing and token figures
describe these synthetic compatibility attempts, not benchmark quality or a service SLA.

The original [v1](evidence/prompt-v1-summary.json),
[v2](evidence/prompt-v2-summary.json) and [v3](evidence/prompt-v3-summary.json)
summaries remain unchanged. Complete local inputs, HTTP exchanges, source digests,
states, tool audit and graph audit were copied out of temporary storage to
`.recycleguard/local-model-progress/{data1,data2,data3,output1,output2,output3}`.
These are synthetic fixture runs; the temporary reviewer credentials were removed.

## Verification and stopping point

- Full local regression suite: **471 passed, 6 Windows-only tests skipped**.
- 32 adapter tests use actual ephemeral loopback HTTP servers; no model weights
  are needed by CI. Composition tests cover unavailable defaults and configuration drift.
- Ruff lint/formatting and all **113** exported schema checks passed. Source and
  wheel builds passed before the final schema/prompt revision; the published branch
  CI will rebuild the final source on Windows/Linux Python 3.11/3.12.
- The [tokenizer check](evidence/tokenizer-byte-bound.json) exercised 108 samples
  against the actual pinned tokenizer without loading weights. Every measured token
  count stayed within the conservative UTF-8 byte admission bound.
- The owned model server was stopped on pause and port 8766 was confirmed free.
  Downloaded weights, isolated environment and progress artifacts remain local.

The blocker is reliable contract-conforming generation. MLX-LM's native server does
not provide the JSON-schema constrained decoding needed by this experiment. Prompt
changes alone did not solve the observed failures. The next investigation is a
supported constrained-decoding integration (Outlines documents MLX-LM support),
followed by a fresh measured smoke. **No Outlines dependency or constrained server
was installed or implemented before pausing.** Do not advertise the local backend
as an accepted investigator or substitute scripted success for the failed native runs.

## Reproduction and cleanup

On Apple Silicon, from the repository root:

```sh
uv sync --locked
uv sync --project tools/local-model --locked --python 3.12
uv run --project tools/local-model python tools/local-model/download.py
uv run python scripts/configure_local_model.py
uv run --project tools/local-model python tools/local-model/serve.py
```

With that server running, these explicit commands probe or run a new compatibility
attempt. Use fresh data/output paths. The current native workflow attempt is expected
to be treated as experimental and can fail its strict contract checks.

```sh
uv run recycleguard model probe --config .recycleguard/local-model.json
uv run scripts/verify_local_model.py --config .recycleguard/local-model.json --data-root .recycleguard/local-smoke-new --output tmp/local-smoke-new
```

The native runtime is Mac-only; the application and HTTP adapter tests remain
portable. No API key is required or stored. The OpenRouter key supplied in chat
was not used.

Retain weights during development. Once the project is finished, stop the owned
server before reclaiming `.recycleguard/models/qwen3.5-9b-4bit`,
`.recycleguard/model-download-cache` and `tools/local-model/.venv`. Preserve the
progress evidence and source/weight/runtime pins needed for the report before
deleting local artifacts. No deletion was performed during this pause.
