# MG1 approval (conditional)

- **Status:** APPROVED, CONDITIONAL. Scope: `REAL_MODEL_SETUP_ONLY`. No quality claim.
- **Date:** 2 November 2026 (Asia/Kolkata).
- **Decision recorded by:** Abhishek, team lead, through this project conversation, on the basis of
  the prompt v6 reliability run (40 of 48 trials not FAILED, 83%).
- **Acknowledgment basis:** the lead's own instruction ("Approve that"). Acknowledgment by Sampreeth,
  Sushanth or Vedantha is **not** asserted and has not been reported.

## What approval covers
The real-model setup: pinned model and runtime, loopback server, host sandbox with probes
(624 of 624 denied in the v6 run), trial coordinator with ledger, seals, kill switch and resume,
scorer, and logging. Evidence: [results](MODEL_TEST_RESULTS.md), `runs/*`.

## Criteria that were NOT met (accepted by the lead as a conditional pass, plan fallback F3)
| Criterion | Result |
| --- | --- |
| Reach AWAITING_REVIEW or qualified stop >= 90% | 40/48 (83%); V1 24/24, V2 16/24 |
| V1 mean wall time <= 120 s | 154 s |
| Schema-valid responses >= 95% of calls | not re-measured for v6; V2 observation-id failures remain |
| Determinism / repeat agreement | not run |

All 8 V2 failures are invented observation ids rejected by the server. Held-out results must report
this failure rate as a result, not hide it. V2 showed no lift over V1 on the dev cases.

## Retained qualifications
- Prompt v6 was designed after seeing dev failures; the dev numbers are not held-out evidence.
- No held-out case has been run or opened.
- CP5 and later gates remain unapproved.
