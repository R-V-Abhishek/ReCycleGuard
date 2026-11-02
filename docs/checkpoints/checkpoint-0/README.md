# CP0: shared interfaces and fixture integration

Date: 24 October 2026. Lead: R V Abhishek. Integration branch: `checkpoint-0`.

**Technical status: verified. Formal status: A02 DONE; CP0 APPROVED.**
On 24 October 2026, Abhishek explicitly confirmed in the current Codex conversation
that all four members acknowledged candidate `c8fb512` and its A02 repairs. This is
a lead-reported team acknowledgement, not a claim of direct GitHub review records.
The [approval ledger](approvals.json) binds that evidence to the exact candidate
and boundary-manifest digest.

## What CP0 establishes

A single installable Python application now has common context/result, evidence,
source/extraction, starter-domain, audit, snapshot-reference and calculation/finding
interchange models. The four streams can validate a shared starter pack without
live services or a model provider. CP0 establishes the interfaces for subsequent
implementation; it is not an end-to-end operational application.

## Contributions and exact inputs

| Member | Task/input | Main responsibility at this checkpoint |
| --- | --- | --- |
| R V Abhishek | A01: `927f492`; workflow: `1213ede`; A02 integration candidate | Package/uv lock, CLI/config, core contracts, C10 test seam; merge coordination, schema publication, cross-stream tests and this construction log |
| H Sampreeth Bhat | H01: [PR #3](https://github.com/R-V-Abhishek/ReCycleGuard/pull/3), `44b114de0860e6edf906de2c10edd016c9a3e652` | 29 source leads, supplied FAQ original, source/provision/observation/coverage models and fixtures |
| Sushanth S | S01: [PR #4](https://github.com/R-V-Abhishek/ReCycleGuard/pull/4), `15c7dd6c389e8021e5aa79d7be1ac696485b55bd` | Starter synthetic dossier, invoice/PDF builders, visible records, expected arithmetic and seven submitted tests |
| Vedantha Vinay Vernekar | V01: [PR #2](https://github.com/R-V-Abhishek/ReCycleGuard/pull/2), `3dc77fd9abd9281fef357655877b6682c5aeaac2` | Content-addressed blob prototype and SQLite intent/result/hash-chain boundary |

Detailed entries: [Abhishek](abhishek.md), [Sampreeth](sampreeth.md),
[Sushanth](sushanth.md), [Vedantha](vedantha.md).

## How the integration was constructed

1. Start from the verified A01/workflow candidate `1213ede` on `checkpoint-0`.
2. Merge V01 as `9225a52`. Resolve add/add conflicts in package/init/CLI/config/
   model-port files by retaining A01's working scaffold. Preserve the storage
   prototype as the starting implementation for its owner.
3. Merge H01 as `29b866a`, retaining its source and extraction handoff.
4. Merge S01 as `eefb7f4`. Resolve the duplicate `tests/__init__.py` marker without
   replacing A01's test configuration.
5. Run the combined suite. Discover an undeclared PDF test dependency and a
   benchmark import failure. Add `pdfplumber` only to the development group and
   make the repository root available only through pytest configuration.
   Generator commands run as modules; remove its ad hoc `sys.path` modification.
6. Reconcile actual payloads across all streams, then regenerate schemas and the
   pre-freeze starter dossier. Submitted revisions remain in Git; no accepted
   snapshot or historical run is rewritten.
7. Add integration and negative tests, build/install checks, a digest-bound
   candidate and an explicit approval ledger. No PR is merged into `main` here.

## Component connections verified

| Producer | Consumer | Contract/evidence checked |
| --- | --- | --- |
| A01 dispatcher context | V01 intent/result prototype | One `CommandContext`; operation and attempt binding; actor/case/run fields retained |
| H01 extraction model | S01 synthetic observations | Required ingestion time, source-time precision, typed locators and JSON payloads |
| S01 visible dossier | Domain-model consumer | Eight supported record families, strict quantities, dimensions, provenance references and manifest declarations |
| S01 original files | V01 blob store | Exact length/digest and byte-identical readback for all 16 manifest assets |
| Normalized records | Observations and original files | Every source observation resolves to an actual visible JSON pointer or data-row locator |
| V01 result commit | Shared `AuditEvent` | Result/event atomicity, chain hashes, terminal replay, restart and rejection of forged intents |
| Calculation example | Generic result/finding consumer | Qualified result, separate pending amount, explicit abstention and numeric field references |
| Published models | JSON schema consumers | 50 generated schemas checked for drift |

## Repairs performed during A02

- **Shared blob/context types:** remove the duplicate storage `BlobRef` dataclass.
  `storage.BlobRef` is the shared Pydantic type. `AuditContext` is an import alias
  for `CommandContext`; callers must use its complete constructor, not the old
  prototype's flattened actor arguments. Operation envelopes and `AuditEvent`
  are published models; `OperationResult` now requires an attempt ID.
- **Intent and replay binding:** compare the complete stored intent, including
  context and input refs, before committing a result. Reused keys cannot bind a
  changed request. Exact repeated terminal results return the same event;
  changed results are rejected. This is a single-attempt prototype, not C11 retry
  recovery. The prototype SQLite layout changed; use a fresh CP0 database. No
  migration of a previously accepted database is claimed.
- **Write-once placement:** use exclusive hard-link placement rather than a rename
  that could replace a concurrently created object. Verify stored bytes on read
  and duplicate put. Power-loss/fsync durability is not established by these tests.
- **Observation provenance:** supply the missing portal JSON; materialize source
  rows, observation records, artifact refs and synthetic receipt examples. Correct
  CSV row indexing to exclude the header. Add a fixed synthetic ingestion clock,
  and preserve date-only precision instead of carrying an instant under `DATE`.
- **F02 identity evidence:** both originals carry `TXN-2024-001`, which is also
  retained in the event. Sharing a certificate alone does not establish event
  equivalence. Distinct status/expiry/cancellation events keep distinct IDs.
  These are contract/fixture checks, not the future C04 equivalence algorithm.
- **Coverage:** require unique contiguous data-row locators for a single artifact;
  merely counting terminal dispositions could incorrectly accept duplicated rows.
- **Honest source status:** retain unreviewed source/provision examples as DRAFT;
  the unacquired R02 version example is PARTIAL_TEXT. Replace an unknown upload
  date's null object with an explicit unknown `TemporalValue`. The partial H01
  extraction example does not claim a complete run or materialized full blobs.
- **FAQ evidence:** verify physical page 9 of the supplied original. Replace the
  purported exact quote/paraphrase with its actual normalized wording; retain the
  checked excerpt and digest. This is a local fixture check, not legal approval.
- **No automatic activation:** the generated case manifest is DRAFT, includes
  cut-offs/adapter versions/evidence expectations and cannot approve a profile.
- **Independent reference seam:** A02 adds a hand-calculated Fraction reference
  outside runtime code. It agrees on 100 required, 55 supported, 45 gap, 25 pending.
  It is not attributed to Vedantha as author. His acknowledgement of the integrated
  reference is included in the lead's recorded all-four confirmation.

## Deliberate limits

The 55 kg allocation and 25 kg paid/pending record remain separate. Account totals
are comparison evidence, never a second credit source. The calculation interchange
example is QUALIFIED for incomplete historical eligibility; it makes no legal
compliance verdict. There is no production C08 calculation, source acquisition,
profile/snapshot publication, trusted review handler or model gateway in CP0.

`CreditLot` has a developer-only derived-output fixture; it is not privileged
truth inserted into the visible dossier. Expected examples are outside runtime
code. Wheel exclusion is checked, but full evaluator filesystem/process isolation
remains V07. A test adapter is not evidence of a model-backed agent.

PDF tooling is a development dependency for tests. Local Chandra-OCR/PaddleOCR
candidates remain unselected and unmeasured; no inference stack, model weights or
claim of fitting 16 GB machines is introduced. Source rights flags remain
review-required; public availability is not a permission grant.

Full profile policies, unsupported record families and richer provider/adapter
payload schemas require a coordinated later publication. CP0 does not quietly
promise every future service schema or production persistence behavior.

## Verification and approval

See [verification record](verification.md) for exact commands/results and
[boundary manifest](boundary-manifest.json) for candidate hashes. The approval
ledger binds acknowledgements to this pack rather than an earlier PR head. The lead's all-four confirmation was recorded on
24 October 2026; A01, H01, S01, V01 and A02 are DONE.

CP0 is approved; the execution register now makes S02, S05 and V02 READY.
A03 and H02 remain BLOCKED by V02, and other dependencies remain unchanged.
Choose one primary task per owner. No CP1 task was implemented as part of A02.
Create `checkpoint-1` from this accepted CP0 candidate when beginning the next
checkpoint; merge to `main` only after CP1 approval. No CP0-to-main merge occurred.
