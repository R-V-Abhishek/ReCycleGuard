# H Sampreeth Bhat: H01

Source acquisition, extraction and RAG corpus workstream. USN: 1BM23CD020.
Input: PR #3, commit `44b114de0860e6edf906de2c10edd016c9a3e652`.

## Submitted work

- A 29-entry lead manifest with regulatory aliases, official URLs, source classes,
  acquisition state and explicit rights metadata.
- A supplied CPCB FAQ PDF: 13 physical pages, 167,964 bytes, SHA-256
  `30f56238fb7db53dd82f69d198be9a92e31d98ea5b21d2724eb7397641a80d16`.
- SourceLead, SourceVersion, ProvisionVersion and RightsMetadata models; extraction,
  observation and coverage models using common evidence and time types.
- Lead loading/manifest validation, a row-coverage helper, locator/source/provision/
  observation fixtures and 16 additional submitted tests over the A01 suite.
- A local VLM evaluation direction for later C03 extraction, retaining originals
  and quarantining unsupported pages rather than inventing successful extraction.

## How A02 connected and repaired it

S01 observations now pass the same H01 Observation model, including ingestion
clock and temporal precision. The coverage helper now rejects duplicated/missing
row coordinates rather than relying on count alone. UTC ingestion timestamps
are calendar-validated; arbitrary Python objects are excluded from JSON fields.

Unreviewed source/provision fixtures were changed to DRAFT; R02's example is not
represented as acquired complete text. Unknown upload time has an explicit unknown
TemporalValue. The extraction example is PARTIAL because its full blobs are not
materialized. These are schema examples, not a completed audited extraction run.

A02 checked physical FAQ page 9, replaced a paraphrase incorrectly labelled as an
exact extraction, and retained the actual normalized excerpt/digest. Original PDF
bytes remain unchanged. Rights flags and legal/applicability approval are not
inferred from this check. Initial H01 digests remain historical; the CP0 manifest
records the corrected candidate.

## Handoff

H01 is DONE through the lead's reported all-four acknowledgement. H02 remains
BLOCKED by V02; H03 follows its own dependencies. No particular local VLM or 16 GB performance is certified.
