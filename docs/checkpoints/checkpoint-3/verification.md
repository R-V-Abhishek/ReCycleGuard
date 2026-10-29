# CP3 verification

The incoming submissions and integration repairs were reviewed against actual
stored evidence, source schemas and runtime behavior. Targeted tests cover real
C07/C08/C12 calls, all four authenticated C13 decisions, exact report/input pins,
requested-changes redrafting, recovery between decision commit and projection,
manual closure, stale-content rejection, original S06 F11/F12/F14 PDF findings,
F15 pagination, optional parser failures and commercial grouping regressions.

Fresh-root `scripts/verify_a07.py` exercises the CLI from intake/support review
through adaptive scripted investigation and qualified report to authenticated
fixture completion. The actual summary, turns, report and audit are retained in
`evidence/`. The run has three real tool actions, six scripted C10 calls, a visible
query revision and an explicit abstention; observed model tokens/cost are unknown.

Full-suite, schema, lint, package and cross-platform CI results are recorded in
`approvals.json`. The CI matrix uses native Windows/Linux and Python 3.11/3.12,
and reproduces CP2, A06 and A07 from fresh roots. Synthetic fixture reviews in
these tests are not evidence of actual team acknowledgement.
