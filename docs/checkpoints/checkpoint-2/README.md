# CP2: deterministic baseline vertical slice

Status: **APPROVED on 27 October 2026**, by explicit lead acceptance after the
Windows/Linux CI matrix passed. Integration branch:
`checkpoint-2`. The approved CP1 tag remains unchanged.

The lead requested finalization and approval on 27 October 2026, then explicitly
required Windows support. The integration and cross-platform checks passed on technical candidate
`a55138d`. Lock tag: `checkpoint-2-approved-2026-10-27`. This is acceptance of a **qualified synthetic baseline**,
not a legal verdict, a real-model run or four-person acknowledgement.

[Passing four-job CI matrix](https://github.com/R-V-Abhishek/ReCycleGuard/actions/runs/40538495376).

## Construction order

1. Start from CP1 lock `7797672`.
2. Integrate Sushanth's S03 calculation engine, `47c4482`, from `S_branch`.
3. Review platform changes `b207462` and Vedantha's V03 reporting submission
   `ee2f64a`. All source commits remain preserved in the integration history.
4. Repair report construction and verification before accepting V03.
5. Add Abhishek's A05 audited baseline dispatcher, CLI, authenticated support
   revisions, contract/schema repairs and fresh-root verification.
6. Verify exact arithmetic, complete input accounting, rejection/failure paths,
   audit references and the operating-system matrix before locking this candidate.

See [member contributions](contributions.md), [verification](verification.md),
[approval ledger](approvals.json) and [remaining boundaries](followups.md).

## Reproduction

From the repository root, with uv and Python 3.11 or 3.12:

```sh
uv sync --locked
uv run pytest
uv run scripts/export_schemas.py --check
uv run scripts/verify_cp2.py --data-root .recycleguard/cp2-reproduction --output tmp/cp2-reproduction
```

The two reproduction paths must be new and separate. Use different path names
for another run. All source PDFs and dossier originals are local, pinned fixtures;
the verification run needs no network, model, OCR installation or hidden oracle.
Dependency installation can require network access. The commands work in PowerShell
and POSIX shells. Trusted Windows review additionally uses Windows PowerShell for
native credential ACL enforcement.

The demonstration creates a temporary authenticated **synthetic fixture reviewer**
to exercise support review. It removes that generated credential afterward. These
fixture reviews are test inputs, never evidence of actual team acknowledgement.

For existing approved local inputs:

```sh
uv run recycleguard baseline run path/to/request.json
uv run recycleguard baseline audit operation:ID_FROM_RESULT
```

`BaselineRequest` pins both the snapshot ID/digest and calculation request. The
profile is resolved from frozen server-side membership, not accepted from request
JSON. `baseline run` returns exit 0 for SUCCESS, 2 for PARTIAL, and 1 for rejection
or failure. A qualified working paper is retained and audited with exit 2.
`baseline audit` verifies hash continuity and referenced blob integrity.

`foundation review` and `baseline support-review` require an enrolled reviewer
password. Request JSON cannot supply an actor or capability. Their request schemas
are checked in under `schemas/v1/`.

## Demonstrated result

Before evidence support review: 100 kg required, 0 supported, 100 gap and 80 pending.
After exact certificate/event/allocation support revisions: **100 required, 55
supported, 45 gap and 25 pending**. An invoice and an account comparison never add
supported quantity. Both runs remain PARTIAL and their report verification remains
QUALIFIED because applicability, deadline and historical-evidence limits persist.

The fixture retains 17 original files and 19 extraction outputs. All 34 case
observations have normalization dispositions. After support review, all 13 record
revisions receive exactly one calculation disposition: 10 active revisions and
3 superseded historical revisions. Original drafts remain unchanged.

The checked-in [summary](evidence/summary.json), [working paper](evidence/working-paper.md),
[baseline envelope](evidence/baseline-envelope.json), [dispositions](evidence/quantity-dispositions.json)
and [audit](evidence/audit.json) record one actual offline run. The runtime blob
store is not committed; reproduce it using the command above.
