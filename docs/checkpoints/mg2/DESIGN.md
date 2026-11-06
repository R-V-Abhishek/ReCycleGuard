# MG2: a minimal multi-agent architecture (design)

Status: design and requirements only. Nothing here is implemented, run or approved. No result is claimed.
Branch `codex/multi-agent-mg2`, from `changes_to_deterministic_engine_and_final_tunining`.

## Question

On the same pinned local model (Qwen3.5-9B-4bit, non-thinking, greedy), does a minimal multi-agent
architecture add measurable value over (a) the deterministic engine alone and (b) single-agent prompt v7?
Architecture is the only variable. A "no lift" result is a valid result.

## Agreed requirements

| # | Decision |
|---|---|
| R1 | Primary metric `supported_case_success`. False positives per case and invalid-output rate are co-primary (they are what the model still affects). Calls, tokens and wall time are reported, not pass/fail. |
| R2 | Bar: M2 beats the better of D0 and S1 on tuning-16, and does not regress on checking-8. If D0 is at or near 16/16 on tuning-16, report "no headroom" and judge M2 on false-positive reduction and checking-8 generalization. Measure D0 first. |
| R3 | The deterministic engine is frozen. Only bugs proved by the baseline run are fixed; each is logged separately and applied to every arm. |
| R4 | Code, tests (scripted and recorded ports) and runbooks are built here. Real-model sweeps run on the PC; run folders are committed as in MG1. |
| R5 | The Reader reads only text-bearing observations (memo, ledger narration, notices), in bounded chunks, with a hard cap on calls per case (start N=6, set from prompt-size measurements). |
| R6 | Claim kinds come only from `docs/design/CONTRACTS.md` and the public family definitions. Nothing under `benchmarks/` (recipes, case ids) is read for design. checking-8 is never opened or tuned on. |
| R7 | Work is committed locally on `codex/multi-agent-mg2`; nothing is pushed until asked. The graphify configuration is its own `chore` commit (done: 435c9e4). |

## Facts found while designing (from code, not from old summaries)

- `gate_finding_proposals` (`workflow/finding_gate.py`) and `FindingProposal` (`contracts/workflow.py`) already give a
  deterministic gate with citation, digit, authority, duplicate and `CONTRADICTED_BY_CALCULATION` checks. The Analyst reuses both unchanged.
- `retrieval/claim_checks.py` already reads observation **text** deterministically (regex) for F11, F12, F14 and F16.
  So the Reader is not the only path to text. Its marginal value is **paraphrase and layout variation the regexes miss**
  (the generalization question R6 and checking-8 test), not text access as such. The deterministic checks stay and win a family.
- Phases are hard-coded to `PLAN` and `ASSESS`: `local_model.py` (`_SCHEMAS`, `phase_rules: Literal["PLAN","ASSESS"]`, a prompt must
  have rules for exactly those two), and `WorkflowRunner._model` picks `PlanProposal` or `AssessmentProposal` by phase. New phases need a
  new prompt-file shape and a schema entry, not a copy of the old path.
- `WorkflowRunner._external` gives retries, budgets, audit and per-attempt records to any call routed through `_model`; MG2 reuses that rather than a second loop.
- Baseline on this branch (laptop, `uv run pytest tests/unit`): 634 passed, 6 skipped, **1 failed**:
  `tests/unit/test_trial_tooling.py::test_the_replay_opens_thinking_only_on_recorded_prompts_and_labels_it`.
  `scripts/replay_reasoning.py::attempts` requires `model-calls.jsonl` next to `result.json`; the test writes only `result.json`.
  This is a test/tooling mismatch in the branch's latest commit, unrelated to the agents. Not fixed here (R3); logged.
  Integration tests (`tests --ignore=tests/unit`): 493 passed.

## Architecture

```
observations ──► [text selector, deterministic] ──► Reader (agent 1, quarantined)
                                                         │ claims {kind, ref, span}
                                          [span verifier, deterministic: span must occur verbatim]
                                                         │ verified claim kinds + refs (no prose)
 calculation facts ─────────────────────────────────────►│
                                                         ▼
                                                   Analyst (agent 2) ──► FindingProposal[]
                                                         │
                                          gate_finding_proposals (existing, deterministic)
                                                         │
 deterministic findings (existing, always win a family) ─┴──► report
```

### Agent 1: Reader (quarantined)
- Sees raw text of selected observations in chunks. No tools, no finding access, no calculation access.
- Output: `list[Claim]`, `Claim = {kind: ClaimKind, observation_ref, span_start, span_end}`; `kind` is a closed enum from public family definitions.
- Verifier (deterministic): the observation must exist and be in the chunk shown; the quote must occur verbatim in that observation's text; the kind must be in the enum. Quoted text is never forwarded or stored in a report.
- Anything that fails verification is dropped and counted (`reader_claims_dropped`), never repaired.
- Injected text can only produce a claim of a kind. It cannot reach a tool, a permission or the Analyst as prose.

### Agent 2: Analyst
- Input: deterministic calculation facts (buckets, pending, issues, census counts), the verified claims as `(kind, observation_ref)` pairs, the closed family list. No document prose.
- One call per case, no tool loop. Output: `list[FindingProposal]` (existing contract). Citable ids: verified observation refs and calculation ids only.
- It can only add findings in families the deterministic engine has not already decided, or abstain.

### Judge: existing gate, not an agent
Unchanged. A proposal contradicted by the swept deterministic universe is rejected with `CONTRADICTED_BY_CALCULATION`.

### Budget
At most N Reader calls (R5) plus one Analyst call per case, plus the existing per-call retry (one, with the error-path note). Compare V1 at 6-7 calls and 154-223 s.

## Integration points (smallest coherent change)

1. `contracts/workflow.py`: `ClaimKind`, `Claim`, `ReaderProposal`, `AnalystProposal` (list of `FindingProposal`).
2. `local_model.py`: allow phases `READ` and `ANALYZE` alongside `PLAN` and `ASSESS`; `_SCHEMAS` entries; a new prompt file type `mg2_*` whose `phase_rules` cover READ and ANALYZE. V1/V2 prompt files and pins are untouched.
3. `workflow/runner.py`: `_model` dispatches by phase to the right response model; a new `_agents` node (READ chunks, verify, ANALYZE) beside `_investigate`, selected by a new experiment variant `MULTI_AGENT`. V1/V2 stay selectable for the A/B.
4. `investigation.py`: `_run_evidence` and `_gated_findings` take proposals and allowed refs from the new node; `_findings` and `_clean_finding` unchanged.
5. Recorded/scripted port tests for the new phases, then regenerate schemas and OpenAPI, and update `docs/design/CONTRACTS.md`.

## Arms

| Arm | Runs |
|---|---|
| D0 | Deterministic engine only (no model). The real floor. |
| S1 | Single-agent v7, same code and pins. |
| M2 | Reader + Analyst + Gate. |
| M2-nr | Analyst only (ablation: does the Reader help?). |
| M3 (optional) | M2 + Verifier, only if M2 shows false positives. |

At least two repeats per arm on tuning-16 with the same slots and pins; one frozen checking-8 run for the winning arm only.
Report `supported_case_success` two ways (deterministic-only vs full via `t3_model_influence`), false positives, invalid-output rate, calls, tokens and wall time.

## Out of scope / limits

- No model-quality claim from scripted or recorded runs.
- n=16 with 1-2 cases per family: intervals are wide. The existing deterministic checks are benchmark-informed; M2 is designed without that access (R6).
- Real runs need the PC with the model.

## Baseline

Laptop, no model: unit 634 passed / 6 skipped / 1 failed (above); integration 493 passed.
Post-fix tuning-16 numbers for D0 and S1 are unmeasured until the PC runs.

## Implementation status

Built and tested on the laptop with scripted ports and the loopback fixture server. No real model has run.

- Agents: `src/recycleguard/agents/{models,reader,analyst,pipeline}.py`.
- Phases `READ` and `ANALYZE` in `local_model.py`; `WorkflowRunner._investigate_agents`; request field `agents` and variants `V3_READER_ANALYST_*`, `V3_ANALYST_ONLY_*` in `investigation.py`; API run variants `READER_ANALYST` and `ANALYST_ONLY`; gate reason `NO_VERIFIED_CLAIM`.
- Prompt `prompts/mg2_reader_analyst_v1.json`, protocol, two sweeps and `RUNBOOK.md`. Schemas, OpenAPI and CONTRACTS section 6.5 updated.
- Tests: `tests/unit/test_agents.py`, `tests/integration/test_agents_workflow.py`. Full suite: 1308 passed, 6 skipped, 1 failed (the failure that was already there, above).
- Not done: any real-model run (D0, S1, M2, M2-nr), checking-8, and the optional Verifier arm (M3).
- Open: the pre-existing `replay_reasoning.attempts` test mismatch is unfixed by design (R3).
