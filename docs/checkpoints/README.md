# Checkpoint construction history

This directory explains how the application was assembled, who supplied each
boundary, and what was verified before the next checkpoint. It complements the
execution register in [implementation plan](../../implementation%20plan.md).

| Checkpoint | Integration branch | Record | Status |
| --- | --- | --- | --- |
| CP0: interfaces | `checkpoint-0` | [Construction and acceptance](checkpoint-0/README.md) | APPROVED on 24 October 2026; all-four acknowledgement reported by lead |

| CP1: evidence foundation | `checkpoint-1` | [Construction and acceptance](checkpoint-1/README.md) | APPROVED on 26 October 2026; qualified lead acceptance |
| CP2: baseline vertical slice | `checkpoint-2` | [Construction and acceptance](checkpoint-2/README.md) | APPROVED on 27 October 2026; qualified baseline, lead acceptance and Windows/Linux verification |
| CP3: integrated investigation | `checkpoint-3` | [Construction and acceptance](checkpoint-3/README.md) | CLOSED 29 October 2026 on lead's explicit request; qualified offline scope, real services with scripted C10; no four-person acknowledgement ([ledger](checkpoint-3/approvals.json)) |
| CP4: prototype | `checkpoint-4` (tag `checkpoint-4-approved-2026-11-01`) | [Construction and acceptance](checkpoint-4/README.md) | APPROVED 1 November 2026; candidate `b5a9831`; lead-reported all-four acknowledgement; scripted prototype scope |
| MG1 / CP5 | `checkpoint-5` | not yet created | MG1 APPROVED, CONDITIONAL (setup only; see `mg1/APPROVAL.md`); CP5 not started; approval rests with Sushanth and Abhishek only; all evaluation includes the real model (see `EXECUTION_PLAN.md`) |

[U01 local model development](model-gateway/README.md) is a separate, paused
workstream toward MG1. Early native attempts (prompts v1-v3) failed strict contracts; prompt v6
is the current pin. MG1 is conditionally approved for setup only (`mg1/APPROVAL.md`).

For every subsequent checkpoint, create `checkpoint-N/` with:

1. A construction/acceptance record: purpose, exact task and PR/commit inputs,
   dependency order, component connections, integration decisions, tests and limits.
2. One contribution entry per member, separating their submitted work from repairs
   performed during integration. Do not attribute someone else's code to an owner.
3. A boundary/artifact digest manifest and the exact technical candidate commit.
4. An approval ledger containing actual acknowledgements and evidence references.
   CI and merged PRs are not substitutes for the required human acknowledgement.
5. Explicit next-task readiness. Never promote a dependent task based only on dates.

Retain historical evidence. Corrections after acceptance create a new candidate,
refresh affected digests/tests, and reopen acceptance rather than overwriting a
previous approval. Keep benchmark answers outside runtime artifacts.
