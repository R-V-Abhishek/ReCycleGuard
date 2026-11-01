# MG1 engineering note

**Not an MG1 approval.** Engineering work before the real-model runs. Everything here ran against a
loopback fake or stub runners on Windows, so none of it measures model quality.

## Decisions
- **Findings:** the model proposes findings and `workflow/finding_gate.py` gates them; numbers stay deterministic.
- **Primary metric:** `supported_case_success`. A preflight stop counts as correct only when the sole expected
  family is `F15_EXTRACTION_PAGE_LOSS`, and results are reported with and without those cases.
- **Determinism:** no seed is sent (`UNSEEDED_GREEDY`) and the prompt cache stays at size 1, both recorded in the pin,
  because neither alternative can be checked on this machine. Repeat agreement is measured on the Mac.
- **Reliability:** no Outlines dependency, since the v4 smoke had no schema failures. A retry adds a short correction
  note, because an identical prompt at temperature 0 would repeat the same reply.
- **Isolation:** the investigator runs from a wheel-only venv under `sandbox-exec`, in a root holding one visible case.
  `--isolation-disclosed` is the fallback and is recorded in `backend.txt`.

## Known limits
- `sandbox-exec` has never run. Its profile is untested and may need adjusting on the Mac.
- The largest V2 prompt is 29,731 of 31,744 bytes on a scripted worst-case path. 18 of the 24 dev cases have not been
  rerun for prompt size since the fix.
- V1 is estimated at about 150 s per run against the 120 s threshold.
- Only `pilot-0.1` has oracle records, so `s06-dev` smoke cases read `NOT_SCORED`.
- Source edits or pulls during a run make it fail the source pin, by design.

Real-model checks and their expected results: [MODEL_TEST_HANDOFF.md](MODEL_TEST_HANDOFF.md).
