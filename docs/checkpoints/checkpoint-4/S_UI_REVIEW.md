# S_ui architecture and API review

Date: 31 October 2026. Base: `S_ui` at `00b2d01`.
Delivery branch: `codex/s-ui-api-review`.

## Changes

- Abhishek's integration review adds explicit API response models, generated
  OpenAPI response schemas, recent-run lookup and frozen run configuration.
  Cancellation of an idle run does not require a model runner. Review scheduling
  checks worker availability before committing a requested redraft; persisted
  review decisions can recover their graph projection without another approval.
- Sushanth's frontend is retained and hardened: abort-safe loading, synchronous
  submission locks, read-only recovery after uncertain mutations, exact prompt
  association and server-authoritative workflow status and budgets.
- SSE validates contiguous cursors, immutable identities and framing, cancels
  readers and distinguishes retryable transport failures from protocol failures.
  Tool traces preserve each actual attempt and avoid guessed causal links.
- Support review requires explicit reasons, exact evidence and scope confirmation.
  Snapshot changes clear stale forms. Report decisions bind the exact packet and
  report. Evidence previews handle logical CSV rows, Unicode spans and invalid
  PDF locators; asynchronous opens cannot overwrite a different dossier.
- Added frontend Windows/Linux CI alongside the existing Python matrix.
  Visual styling and model dependencies are unchanged.

## Verification

- Frontend: 78 tests passed; type checking and production build passed.
- API review and existing API integration suites: 10 tests passed in the final rerun.
- Ruff, formatting, 151 boundary schemas and generated OpenAPI checks passed. CI results remain separate from
  local checks; this record does not claim Windows execution locally.
- Browser/API synthetic flow exercised preparation, foundation approval,
  explicit support assertions, live scripted tool/model trace, qualified verified
  report and authenticated approval. A duplicate React key discovered in this
  flow was fixed and covered by a navigation/unmount regression.
- The synthetic report retained 100 kg target, 55 kg supported allocation,
  25 kg pending and 45 kg unsupported gap. Approval did not erase qualifications.
  Scripted calls verify integration behavior, not actual model quality.

## Checkpoint dependencies

Vedantha's V06/V07 submission is now available on remote `V06` at `71edc54`.
It was inspected for scope, but is not merged or approved by this UI review.
It adds export/replay and runtime isolation. Integration must verify those
boundaries against the current API/runtime, not rely on task completion notes.

CP4 remains WAITING: integrate and verify V06/V07, obtain V08 recovery/budget/
checkpoint/export evidence and V09 independent full-oracle/seal validation,
then complete A08 cold-start and G01–G12 acceptance. S07 and H08 are already
included in the backend history. UI delivery alone does not close CP4 or MG1.

No idempotency-key protocol was introduced. Unknown mutation outcomes stay
locked against blind resubmission and can be investigated through persisted
read-only state. The service remains a single-process demonstration API.
