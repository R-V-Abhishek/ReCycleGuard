# A08 integration and acceptance record

Date: 1 November 2026. Integration branch: `checkpoint-4`.
**Checkpoint status: WAITING. This record is not an approval.**

## Integrated submissions and repairs

| Member | Work carried into this candidate | Review outcome |
| --- | --- | --- |
| Abhishek | API/UI contract and lifecycle repairs from `12db29f`; A08 integration, CLI package commands, schema publication, recovery regressions and gate evidence tooling | Integration candidate; mandatory acceptance gaps remain |
| Sampreeth | H08 frozen corpus/profile audit and retrieval work already integrated through the backend handoff | Existing evidence preserved |
| Sushanth | S07 grouped 48-case pilot and S_ui frontend already integrated through the backend/UI handoffs | Existing evidence preserved; unrelated uncommitted frontend edits left in the original checkout |
| Vedantha | V06/V07 at `71edc54`, V08/V09 at `8b9c7ad` | Submissions merged with history; completion labels checked against implementation |

The V08 submission introduced a second incompatible export service and contract
family. Integration retains the canonical `contracts/bundles.py` and
`exports/service.py`, removes the unused conflicting implementation, and publishes
its eight boundary schemas. CLI investigation and export commands are both retained.

Export now collects actual nested evidence, catalog/profile metadata and frozen
audit events. Verification reads exact bytes and checks transitive blob coverage
and hash-chain continuity. Export and live replay persist audit operations and
support idempotent recovery. Missing runs cannot produce empty successful bundles.
A new standalone package can be verified and inspected without the live database.
Artifact replay reconstructs artifact references; it does not restore a live DB
or recompute a report/model result. Unimplemented execution modes fail explicitly.

Public export is deliberately **PARTIAL**: opaque source/model derivatives and
caller-provided attribution text are withheld until exact-object clearance exists.
It is not a publication-ready cleared package. A conservative omission record
cannot be used to bypass required local evidence coverage.

Installed wheels now hash actual installed package sources and carry exact build-lock
bytes; checkout execution still pins its working lock. This fixes the discovered
checkout-only source/lock assumptions without silently weakening run pins.

The submitted broad `os.link` error fallback could overwrite a competing blob.
It was removed; regression tests preserve immutable publication and explicit
permission failures. CLI mode typos are rejected before opening the database.

Recovery checks reject checkpoint audit-sequence mismatches and checkpoints ahead
of the ledger. An interrupted turn resumes with its committed reservation,
without provider dispatch or duplicate budget accounting.

V09 now validates canonical decimal strings, dimensions, bucket coverage and
world identity. A list of reviewed IDs cannot promote unreviewed projections.
Reviewed seals require exact digest-bound visible-reference attestations and
already reviewed visible answers. These attestations are evidence records, not
an authentication mechanism or substitutes for independent review.

## Executed evidence

- Fresh `verify_api.py`: completed scripted API investigation, three tool calls,
  six model calls, qualified report, authenticated synthetic approval and
  `VERIFIED_INTEGRITY`.
- Fresh `verify_a07.py`: completed real-service/scripted-model investigation,
  revised retrieval, qualified report and synthetic review.
- Export of that actual A07 run: **368 objects**, durable export event, integrity
  PASS, standalone offline artifact replay SUCCESS with no live DB/model.
- Independent evaluator arithmetic: **48/48 world references valid**; **zero**
  hand-reviewed visible references. Private answer-bearing evidence stays outside
  runtime and public documentation. World arithmetic is not visible-evidence truth.
- Frontend: **78 tests**, type checking and production build passed.
- Canonical boundary schemas: **159** generated and checked.

Additional final test counts and G01–G12 regression evidence are recorded in the
accompanying verification files. Passing helper/regression tests do not waive a
mandatory demonstration. No new real-model quality experiment was run for A08.
Local checks do not imply Windows/Linux CI success.

## Mandatory blockers

1. **V07 / G11:** the submitted path/environment validator is cooperative and not
   wired to an enforced investigator process/filesystem boundary. Parent mounts
   and forbidden descendants now fail validation, but arbitrary host reads are
   not intercepted and violations are not a durable runtime denial audit.
   Required: connect a restricted runtime to actual execution, exclude evaluator,
   hidden labels and seed inputs, attempt forbidden reads/listing, and retain
   durable denied-access evidence. Docker/Colima was inspected but is not running;
   no sandbox was falsely reported as tested.
2. **V09:** the 48-case visible-evidence answers, justified findings/abstentions
   and rubric still lack the independent complete reference review and bound
   dataset/oracle/rubric seal. Arithmetic checks cannot establish this evidence.
3. **A08 / CP4:** collect the final independent acceptance review and team
   acknowledgment against the exact repaired candidate after the mandatory
   demonstrations pass. No synthetic reviewer action counts as team approval.

A08 cannot be marked complete, CP4 cannot be approved, and downstream experiment
freeze/quality claims remain blocked by these gaps. This candidate is a verified
integration handoff, not an unqualified completed prototype.

## Reproduce

Use `uv sync --locked` and new paths for each run:

```sh
uv run scripts/verify_api.py --data-root tmp/cp4-api-data --output tmp/cp4-api-output
uv run scripts/verify_a07.py --data-root tmp/cp4-a07-data --output tmp/cp4-a07-output
uv run pytest --junitxml=tmp/cp4-tests.xml
uv run scripts/verify_cp4.py --junit tmp/cp4-tests.xml --output tmp/cp4-gates.json
uv run scripts/export_schemas.py --check
uv run scripts/export_openapi.py --check
```

The gate summary uses actual JUnit results and explicitly preserves missing
modules, failures and review requirements. It cannot grant checkpoint approval.
For a recorded run, export and inspect a new standalone directory:

```sh
uv run recycleguard audit export --run-id RUN_ID --output tmp/cp4-package
uv run recycleguard audit verify-package tmp/cp4-package
uv run recycleguard replay-package tmp/cp4-package
```

The first command uses the configured source application root. The latter two
only inspect package bytes and do not open that application database. Select
`--kind QUALIFIED_PUBLIC` only when an explicitly partial withheld package is
acceptable. Keep local packages private: they contain original evidence/prompts.
