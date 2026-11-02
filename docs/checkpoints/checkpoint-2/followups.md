# CP2 boundary tracking

These are release checks and owned follow-ups, not a scheduled background monitor.

| Reported item | CP2 treatment | Owner / remaining acceptance |
| --- | --- | --- |
| Missing calculation audit authority | Repaired: service-only `calculation.` prefix, audited dispatcher, report child event, PARTIAL retention and replay. Audit failure returns OUTCOME_UNKNOWN. | A/V; preserve regression tests through graph integration. |
| Missing CLI/dispatcher | Repaired by A05: exact approved snapshot/profile resolution, baseline run and audit inspection. | A; A06 can build on this boundary after CP2 approval. |
| Missing allocation chronology | Remains explicit: UNKNOWN when allocation order is unavailable; NOT_EVALUATED where history is not supplied. Explicit experimental order affects the input digest. No timestamp is invented from a transfer or account capture. | A/H with S04/H07: add evidence-bound chronology, tie/missing-order tests and authoritative temporal applicability. |
| Contract gaps | Repaired: QuantityDisposition and derivation/report/request schemas exported; OVER_ALLOCATION and UNSUPPORTED_FEATURE codes added. | A; schema freshness is enforced in CI. |
| No route from PENDING to SUPPORTED | Repaired for CP2's structured synthetic originals: authenticated review creates new support revisions and a new approved case. Baseline checks the persisted support assertion. Imported source flags alone cannot promote support. | A/V; additional real-document capability mappings remain outside this narrow handler. |
| Minimal commercial handling | Deliberately bounded: unlinked invoice/payment quantity remains pending; ambiguous commercial assignments remain unassigned. No monetary amount becomes metal credit. | S04: complete commercial links, lifecycle, expiry/cancellation and F08/F09 checks. |
| Windows compatibility | Full functional suite and fresh-root demonstration added to Windows/Linux CI. Native Windows credential ACL checks replace the unsafe permission-check bypass. | A/V; all four OS/Python jobs passed; keep this matrix required for subsequent changes. |

CP2 is approved. Next readiness: A06, S04, V05 and V07 become READY. H05 and S05 remain independently
READY. V04 still depends on S05; A07 still requires A06, H06, S04 and V05. None of
those tasks is marked DONE by this checkpoint.
