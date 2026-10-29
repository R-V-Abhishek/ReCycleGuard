# C08 deterministic domain tools

Owner: Sushanth S. Pure functions over the pinned snapshot; no clock, no I/O except archiving
result blobs. Decimal strings only, display 4dp ROUND_HALF_EVEN, never a float.

Two rules hold everywhere: the checked universe is always the whole pinned snapshot (request
subjects only select which results come back), and only affirmative evidence demotes. Missing,
unreviewed or undated evidence is `UNKNOWN`, never a silent pass and never an exclusion. Checks
only demote; nothing here promotes support.

| Module | What it decides |
| --- | --- |
| `universe.py` | Active records of the snapshot, supersession, ambiguity |
| `lots.py`, `allocation.py` | Lot capacity and allocation conservation (S03) |
| `priority.py` | Earlier-liability order (F08), from an explicit order or `allocation_time` |
| `chronology.py` | Half-open time spans; an overlap is a tie, so `UNKNOWN` |
| `lifecycle.py` | F09: a credit that expired or was cancelled before use is excluded |
| `identity.py` | F05 identity, registrations, F10 capability (EEE code coverage) |
| `products.py` | F13: weight-basis conflicts are escalated, never averaged; sales per basis |
| `commercial.py` | F07/T09: invoice and payment are one quantity; money is never credit |
| `checks.py` | Allowlisted dispatcher returning `StructuredCheckResult` |
| `reconcile.py`, `service.py` | The reconciliation engine and its `ServiceResult` wrapper |

## Verdict rules

- **Lifecycle:** FAIL when a supported EXPIRED/CANCELLED fact (event or certificate
  `expiry_time`) precedes the transfer or the allocation. No terminal evidence passes (absence is
  not proof, and the trace says so). A fact that is unsupported, undated or cannot be ordered
  against the allocation is `UNKNOWN`.
- **Chronology:** an explicit `allocation_order` input beats `Allocation.allocation_time`. A
  transfer's time is never used as allocation time. Missing, partial or tied order is `UNKNOWN`.
- **Capability:** applies in the engine only when both a Registration and a ProductMapping exist.
  FAIL when none of the producer's EEE codes is covered, `UNKNOWN` when only some are. A purely
  alphabetic registered code (`CEEW`) covers its numbered items (`CEEW1`); other codes match
  exactly.
- **Commercial:** an invoice and the payment that references it count once. A record linked to an
  allocated transfer adds no quantity; one linked to an unallocated transfer, or unlinked, is
  pending in a single compatible bucket. Contradicting parties, metal or quantity are FAIL.
- **Weight basis:** two bases (or weights) in force together are `WEIGHT_BASIS_CONFLICT`.
  Fiscal years run 1 April to 1 April.

`TOOL_VERSION` is part of the calculation digest, so a rule change must bump it.

## Checks

`run_check(context, request, snapshots=..., snapshot_ref=...)` accepts `COMPARE_IDENTITY`,
`LOOKUP_REGISTRATION_EVIDENCE`, `CHECK_CAPABILITY`, `LOOKUP_PRODUCT_MAPPING`,
`COMPARE_WEIGHT_BASIS`, `AGGREGATE_SALES`, `GET_CERTIFICATE_HISTORY`, `CHECK_CREDIT_EVENTS` and
`MATCH_TRANSACTIONS`. Unknown kinds are rejected. The `check_id` is a hash of the membership
digest, tool version, kind and subjects, so the same inputs give the same result and blob.

Not in S04: `read_scope`, `list_evidence`, `inspect_evidence`, `load_obligations`,
`compare_versions`, `compare_return_draft`, audited event prefix, CLI and graph wiring (A07).
