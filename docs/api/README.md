# Local investigation API

This is a single-process demonstration API. The separate [React frontend](../../ui/README.md)
consumes its explicit response contracts in [openapi.json](openapi.json).
The API process does not serve frontend assets.

## Start

From the repository root, install the locked application with `uv sync --locked`.
Set a random bearer token with at least 24 characters in `RECYCLEGUARD_API_TOKEN`,
or put it in a private local file and pass `--token-file PATH`.

```sh
uv run recycleguard serve --host 0.0.0.0 --port 8000 --model-config .recycleguard/local-model.json
```

For a separate browser frontend, add its exact origin, for example
`--cors-origin http://localhost:5173`. Repeat this option for additional origins.
Use one server process/worker. The Mac hosts the local model and API; a college
laptop can call the API at the Mac's LAN address. The model itself stays on
`127.0.0.1:8766`. This is private-LAN demo transport, not an Internet deployment.
Bearer and reviewer credentials require HTTPS before use on an untrusted network.

Start the already-installed native model separately when real inference is needed:

```sh
uv run --project tools/local-model --no-sync python tools/local-model/serve.py
```

`--model-config` is server-owned configuration. Clients cannot supply provider
URLs, weight paths, actors, grants, prompts or scripted proposals. Without a model
configuration the API can still ingest/review evidence and inspect existing runs;
it refuses new MODEL_BACKED investigations. Health reports configuration separately
from actual model readiness. The model configuration/weights/runtime are validated
when starting and advancing an investigation. Normal API dependencies do not
include MLX or an OCR model. The native MLX runtime is Apple Silicon only; the API
and HTTP transport tests are portable.

## Request sequence

Send `Authorization: Bearer YOUR_TOKEN` with every data endpoint. Credentials
are never query parameters. `/docs` provides the framework's API explorer; it is
not a project frontend. `/openapi.json` is the live machine-readable contract.

1. `GET /api/v1/dossiers`: list development fixtures and imported dossiers.
   The default catalogue is `tests/fixtures/visible`; no held-out catalogue is served.
2. `POST /api/v1/dossiers/select` with `{"fixture_id":"case_001"}` copies a
   development dossier into the API's private intake directory. Alternatively,
   POST raw ZIP bytes to `/api/v1/dossiers` with `Content-Type: application/zip`.
   Uploads require exactly one `case_manifest.json` and the supported synthetic
   CSV/JSON/JSONL/PDF dossier layout. They are not arbitrary-PDF conversion.
3. `POST /api/v1/dossiers/{dossier_id}/prepare`: extract originals, account for
   coverage and quarantine, normalize and create a DRAFT foundation. It is not
   automatically approved. The returned `candidate_digest` binds the next review.
4. Enroll the local reviewer once using the existing `recycleguard reviewer init`
   CLI or `POST /api/v1/reviewer` with `actor_id` and `password`. Enrollment cannot
   replace existing credentials. `POST /dossiers/{id}/review-foundation` accepts
   `password`, `candidate_digest` and explicit `accepted_qualifications`.
   It creates immutable approved children; it does not invent applicability dates.
5. `GET /dossiers/{id}/evidence` exposes exact records, observations, originals
   and the current snapshot. Original bytes are available only for revisions in
   that dossier via `/dossiers/{id}/artifacts/{artifact_revision_id}`.
   Foundation approval alone never promotes certificate/allocation support.
   If reviewed evidence supports a record, POST `/dossiers/{id}/support-review`
   with `password`, exact `snapshot_digest`, `assertions` and `reason`.
   Each assertion names `target_record_revision_id`, original `evidence_refs`
   and a reason. No blanket source mutation or automatic support is performed.
6. `POST /api/v1/runs` with `{"dossier_id":"ID","mode":"MODEL_BACKED"}`.
   This returns HTTP 202 and `run_id`. A background worker executes actual A07
   services with the local model. Optional `budgets` override server defaults;
   defaults reserve the configured per-call allowance, up to 12 calls and 600s.
   Bounds are admission limits, not measured latency promises.
7. Read `/runs/{id}` for authoritative `state`, frozen `configuration` and API `job` status. Subscribe
   to `/runs/{id}/events` or poll `/runs/{id}/trace?after=N`. Read `/agent` for
   configured prompt templates/schemas before running.
   `GET /api/v1/runs?dossier_id=ID` lists recoverable runs after a lost start response;
   never blindly repeat a mutation after an unknown outcome. Health advertises
   `available_modes`, which is configuration availability rather than a successful model probe.
8. Read `/runs/{id}/report` and `/runs/{id}/audit`. The report remains qualified
   when evidence is incomplete. The audit verifies frozen bytes, pins, index
   publication and ledger integrity; it does not certify legal correctness.
9. At AWAITING_REVIEW, POST `/runs/{id}/packet`, then POST `/runs/{id}/review`
   with `password`, `packet_id`, `expected_dependency_digest`, `decision` and
   `reason`. APPROVE completes, REJECT blocks output, REQUEST_CHANGES redrafts a
   new version for another review, ESCALATE retains human review. Passwords and
   bearer tokens are excluded from the investigation audit trace.

All routes after step 1 use the `/api/v1` prefix. Creating another foundation can
move profile/corpus heads: a stale candidate is rejected rather than silently
approved. To import corrected inputs, register a new dossier and review its new
candidate. Previous immutable records remain available.

Idle cancellation uses the persisted graph without reconstructing the model runner.
Run reads can recover a previously committed review projection; a redraft needing
execution becomes explicitly resumable. Review scheduling rejects a busy redraft
before committing its human decision. HTTP errors expose structured code/message
details without original host paths.

## Trace and streaming

The sequence number is the existing audit stream sequence. SSE `id` equals that
number. Resume with `Last-Event-ID: N` or `?after=N`, and deduplicate by sequence.
Use authenticated `fetch()` streaming rather than native EventSource, which cannot
set an Authorization header. SSE sends `trace`, then a `stopped` event when the
API job stops, and comment heartbeats while active. AWAITING_REVIEW is a pause,
not an automatic approval or a successful quality benchmark.

- `PROMPT_PREPARED`: persisted logical request/schema plus the configured system
  template. This means prepared, not proof that the provider accepted a request.
- `MODEL_RESULT`: exact adapter request/response, where available, under
  `provider_trace`. `request_body_utf8` is the exact transport JSON containing the
  actual rendered `prompt`. Failed calls can have partial traces. Scripted tests
  have no provider wire prompt and never pretend otherwise.
- `TOOL_PROPOSED`: actual model `allowed_operation`, `typed_arguments`, `plan_ref`
  and `concise_reason`. This is a concise recorded justification, not private
  chain-of-thought or a fabricated explanation.
- `TOOL_OR_STAGE_RESULT`: structured output, full result reference, issues and
  service provenance. `PLAN` and `ASSESSMENT` retain plan changes and observations.

No client can invoke arbitrary tools directly. Tool execution remains inside the
bounded graph. Full originals persist even when excluded from model context;
inline tool summaries are bounded, identify untrusted text and disclose truncation.

## Cancellation and recovery

One investigation runs at a time. Concurrent starts return 409/BUSY. POST
`/runs/{id}/cancel` returns 202 immediately and requests cancellation between graph
turns. It does not kill or repeat an in-flight inference. Terminal runs reject
cancellation/resume. After a server restart, API jobs left RUNNING/QUEUED become
INTERRUPTED; POST `/runs/{id}/resume` explicitly invokes audited graph recovery.
Unknown child completion is not automatically retried. If source/configuration
pins changed, start a new run instead of replaying a different implementation.

Expected failures: 401 invalid bearer token; 404 unknown resource; 409 review,
readiness, concurrency or state conflict; 413 upload limit; 415 wrong media type;
422 malformed request/archive. Validation errors omit raw input so passwords are
not reflected. The API job records worker exceptions separately from graph state;
clients must inspect both, and must never treat an HTTP 202 as completion.

## Verification

```sh
uv run pytest tests/integration/test_api.py tests/integration/test_model_investigation.py
uv run scripts/export_schemas.py --check
uv run scripts/export_openapi.py --check
uv run scripts/verify_api.py --data-root .recycleguard/api-check --output tmp/api-check
uv run scripts/verify_api.py --data-root .recycleguard/api-native-check --output tmp/api-native-check --model-config .recycleguard/local-model.json
```

Demo data/output roots must be new. The default demonstration is explicitly
SCRIPTED_TEST; real inference requires the last command and a live pinned local
server. Both demonstrations exercise actual API ingestion, evidence approval,
explicit support review, investigation, report verification, integrity audit and
version-bound report approval using temporary **synthetic fixture** credentials.
They remove their reviewer credentials on successful completion. These actions
are not actual team acknowledgement or legal certification.

Full visible-evidence oracle validation, runtime isolation, export/replay hardening
and sealed quality evaluation still depend on V06–V09/V10. The incoming 21-case
U01 log records compatibility observations; reaching review does not establish
fault precision/recall, general injection immunity or real-model gate acceptance.
