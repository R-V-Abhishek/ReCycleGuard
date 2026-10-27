# CP2 member contributions and integration

## Sushanth (S): S03

Submitted the deterministic C08 engine on `S_branch`, commit `47c4482`: exact
arithmetic; server-built candidate universe; derived certificate lots; allocation
and shared-lot conservation; earlier-liability checks; required/supported/gap/pending
quantities; account comparisons; per-record dispositions and archived derivations.
Added domain tests and the CP1 snapshot integration test.

Integration repairs by Abhishek's review: precise OVER_ALLOCATION error, published
disposition/derivation schemas, full-record payload hashing, preservation of UNKNOWN
when an earlier required amount is unusable, qualification of invalid allocation
exclusions, and inclusion of explicit order input in the calculation digest.

S04's broader lifecycle and commercial matching were not supplied or accepted as
part of S03. S05's six-case renderer/evaluation pack remains separate.

## Vedantha (V): V03

Submitted the eight-section baseline builder, typed claims, numeric insertion,
Markdown rendering and verifier in `ee2f64a`. The original submission had an
empty-findings runtime failure and had not been verified with pytest.

Integration repairs by Abhishek's review: fixed empty findings and per-finding
next actions; required authoritative calculation inputs; rejected edited embedded
calculations, numeric templates, rendered Markdown, revision metadata, duplicates,
and unavailable exact citation references. Added adversarial verifier tests and
exported the actual report schemas. Report and calculation outputs now participate
in the existing audit kernel through A05.

V05's complete report-review transitions, repair feedback and export policy remain
separate. The new record-support handler does not claim V05 completion.

## Abhishek (A): A05 and checkpoint integration

Integrated the submitted source commits into `checkpoint-2`, preserving CP1 and
`S_branch`. Added calculation event authority, a pinned baseline dispatcher,
calculation/report audit commits, persisted PARTIAL outcomes and exact replay.
Wired `baseline run`, `baseline audit`, `baseline support-review` and
`foundation review` into the local CLI.

Added authenticated, immutable support revisions for exact structured synthetic
originals. Certificate, event and allocation facts are reviewed separately. Payment,
account-total, spoofed-actor, wrong-locator and stale-record evidence cannot promote
an allocation. The baseline rejects SUPPORTED records without a committed human
support assertion. Original observations and record revisions remain retained.

Added fresh-root offline reproduction, integration/failure tests, schema exports,
checkpoint evidence and the next-task register. Expanded CI to Windows and Linux,
each on Python 3.11 and 3.12, with a complete synthetic baseline demonstration.

## Sampreeth (H): inherited CP1 boundary

CP2 consumes the accepted H02/H03/H04 intake/extraction/source foundation: original
receipts, extraction and coverage blobs, source provisions and explicitly qualified
applicability. No new H05/H06/H07 completion is claimed here.

Allocation chronology and authoritative temporal/deadline resolution remain shared
follow-up work with Abhishek and Sushanth. CP2 preserves the uncertainty instead of
inferring chronology from year-end totals.
