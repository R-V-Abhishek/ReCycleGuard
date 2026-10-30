# Backend integration checkpoint

Branch: `codex/backend-api`. Backend only; no UI implementation.

## Integrated inputs

- U01 `f03103e`: pinned local MLX adapter and prompt-v4 compatibility work.
- S07 `21dd1e1`: grouped 24-development / 24-held-out pilot, split/leakage checks
  and held-out seal. Only development fixtures are offered by the API.
- H08 `489b501`: corpus/profile audit and retrieval regression submission.

S07/H08 histories were merged intact. Integration repairs replace H08's fixed
metadata assumptions with real frozen-byte, exact-pin, index-publication and
ledger verification. Legacy metadata remains explicitly unverified. Model-backed
investigation now invokes the real A07 services and receives bounded, untrusted
original evidence summaries. Model/actor/config paths are server-owned; uploaded
pending records are not automatically promoted to supported credit.

## Per-member construction

| Member | Contribution carried into this backend |
| --- | --- |
| Abhishek | U01/A07 integration, real model/service composition, API, background execution, cancellation/recovery, exact prompt/tool trace, endpoint contracts and UI handoff |
| Sushanth | S07 pilot generation/split invariants and existing S04–S06 domain/dossier work |
| Sampreeth | H08 source/profile/retrieval audit and existing ingestion, extraction and retrieval services |
| Vedantha | Existing V04/V05 audit/report/review foundations; no new V06–V09 submission was available during this integration |

The API implements dossier selection/ZIP ingestion, draft preparation, explicit
foundation/support review, model-backed investigation, SSE/audit trace, original
artifact lookup, verified reports, cancellation/resume and exact authenticated
report decisions. It uses the application ledger as authority; a separate API
catalogue tracks imports and background-job status only.

[API setup/contract](../../api/README.md) ·
[UI plan](../../api/UI_IMPLEMENTATION_PLAN.md) ·
[OpenAPI](../../api/openapi.json)

## Verification and qualifications

Focused verification covers real local HTTP transport, actual A07 tools, strict
config/source pins, ZIP paths/limits, authentication, immutable downloads, support
review, background execution, SSE, H08 auditing, concurrency/cancellation and all
report review outcomes. The reproducible API script uses temporary synthetic
fixture reviewers; they are not real team acknowledgements.

### Passed verifications
- **API and Model Investigation Suites:** `tests/integration/test_api.py` and
  `tests/integration/test_model_investigation.py` (15/15 passed).
- **Contracts and Schemas:** 151 boundary schemas validated (`scripts/export_schemas.py --check`)
  and OpenAPI contract validated (`scripts/export_openapi.py --check`).
- **Scripted API Demonstration:** `scripts/verify_api.py` passed with `VERIFIED_INTEGRITY`.
- **Integrated Predecessors:** S07 (pilot generation, split and leakage checks) and H08 (corpus/profile
  frozen-input audit and retrieval regressions) merged and verified.

### Live-model trial records
- **Earlier trial failure:** The first real API trial on the frozen dossier exposed a genuine
  model mistake: it supplied a finding ID where an observation ID was required for `inspect_evidence`.
  The tool rejected the invocation; source evidence was not changed. The PLAN context and tool schema
  now explicitly distinguish those IDs and expose actual prior stage observations. Historical failed-run
  records are retained locally rather than rewritten as successful trials.
- **Fresh live-model rerun:** The fresh live-model run passed cleanly: two model calls, one real
  tool call (`compute_reconciliation`), zero retries, a qualified report and authenticated fixture review.

### Unfinished checks and downstream gates
- The full regression sweep across the broader repository test suite is marked **unfinished** for this
  progress push.
- CP4 and MG1 are not approved by this API handoff. Export/replay, stronger runtime
  isolation, independent full visible-oracle validation and sealed evaluation still
  require Vedantha's downstream work. The incoming 21-case log demonstrates narrow
  compatibility; it is not a sealed quality benchmark or proof of general injection
  immunity. Scanned PDF OCR still requires a separately configured local parser.
