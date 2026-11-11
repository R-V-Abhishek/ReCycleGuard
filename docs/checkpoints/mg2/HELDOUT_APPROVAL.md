# Held-out run approval

- **Approved by:** Abhishek, on 11 November 2026, by approving the plan that declared the run.
- **R = 2:** decided by Abhishek, with Sushanth's agreement as reported by Abhishek on 11 November
  2026. No other acknowledgement is claimed.
- **What runs:** log entry 15 (`EXPERIMENT_LOG.md`); queue `queue/t4/queue-t4-heldout.json`;
  deviations of 2026-11-11 in `PREREGISTRATION.md`.
- **Freezes:** built from the specs in `freeze-spec/` with `scripts/make_freeze.py`, kept untracked
  in `benchmarks/heldout/freeze/` and uploaded with the visible dossiers as the private Kaggle dataset
  `rvabhishek/recycleguard-heldout` on 11 November 2026. Both verified with `--strict-commit` on
  the laptop before the upload.

| Freeze | Commit | Freeze digest (sha256) |
| --- | --- | --- |
| `heldout-baseline.json` | `410ac92` | `afb89081e340135f0d72bd3f9da0e222ad17c07c459cd29eb40071d9908c3c24` |
| `heldout-classifier-only.json` | `410ac92` | `fc5e59c3793c2b8d22bc6ba4122e4fd5bfa526f9878bb7d38afbf3a75dc8b02a` |

This file records a person's decision to spend the held-out dossiers once. It is not a checkpoint
approval and does not make the result a team acknowledgement of quality.
