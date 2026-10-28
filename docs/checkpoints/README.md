# Checkpoint construction history

This directory explains how the application was assembled, who supplied each
boundary, and what was verified before the next checkpoint. It complements the
execution register in [implementation plan](../../implementation%20plan.md).

| Checkpoint | Integration branch | Record | Status |
| --- | --- | --- | --- |
| CP0: interfaces | `checkpoint-0` | [Construction and acceptance](checkpoint-0/README.md) | APPROVED on 24 October 2026; all-four acknowledgement reported by lead |

| CP1: evidence foundation | `checkpoint-1` | [Construction and acceptance](checkpoint-1/README.md) | APPROVED on 26 October 2026; qualified lead acceptance |
| CP2: baseline vertical slice | `checkpoint-2` | [Construction and acceptance](checkpoint-2/README.md) | APPROVED on 27 October 2026; qualified baseline, lead acceptance and Windows/Linux verification |
| CP3: integrated investigation | A06 workstream `codex/a06` | [Construction so far](checkpoint-3/README.md) | WAITING; A06 scripted graph only, integration and acceptance pending |

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
