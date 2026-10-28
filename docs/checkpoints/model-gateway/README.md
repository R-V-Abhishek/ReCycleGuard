# U01 local model development log

Status: **IN PROGRESS; paused at the lead's request on 28 October 2026**.
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
