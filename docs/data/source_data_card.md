# Source data card: frozen retrieval corpus

Owner: Sampreeth, H08. Integrity verification repairs: Abhishek integration.

This card describes the checked fixture sources and the audit boundary. It does not
certify a live deployment, legal interpretation, redistribution permission, model
quality or full-page legal review. A runtime audit result must bind its exact
corpus, profile and index pins; the source constants alone cannot establish that.

## Known fixture originals

| Alias | Original artifact revision | SHA-256 | Physical pages |
| --- | --- | --- | --- |
| R02 | `artifact_rev:r02_rules_2022_official_pdf` | `d03f8744bc79d67a94b06e1020537e93d15572b0cf1d575cb32b76c89f30a5fb` | 38 |
| R08 | `artifact_rev:cpcb_faq_20240123_pdf` | `30f56238fb7db53dd82f69d198be9a92e31d98ea5b21d2724eb7397641a80d16` | 13 |

The fixture corpus retains R02 physical pages 24 and 27 for Rule 6(4) and Rule
15(1)-(3), and R08 page 9 for recycler capability guidance. Originals remain
retained independently of the selected provision text. The Gazette and FAQ are
distinct source classes; retrieval does not make guidance equivalent to statute.

Exact runtime source titles, URLs, rights metadata, review states, provision IDs
and locators come from the frozen corpus membership. Do not copy a fixed DRAFT or
APPROVED label from this card into an audit result.

## Two different outputs

`build_corpus_profile_audit_manifest(...)` remains a compatibility metadata helper.
Its status is **UNVERIFIED_METADATA**, with no verified checks or audit streams.
Source review state and redistribution authorization are unknown in this output.
Its expected source constants and supplied profile/index summaries do not prove
that files exist, that their bytes match, or that a review was committed.

`audit_frozen_corpus_profile(...)` returns **VERIFIED_INTEGRITY** only after checking:

- Exact expected corpus, profile and index pins and their persisted catalog revisions.
- Immutable corpus membership and coverage bytes, original source revisions and
  original file bytes, provision text blobs and valid physical page locators.
- Canonical profile digest, exact source dependencies and source-bound policy evidence.
- Index membership digest and exact immutable SQLite bytes against the local index.
- Hash links, event sequence, payload/input/output blobs and indexed heads for all
  streams in the supplied application audit ledger, including child-service streams.

Missing or changed pins, files, blobs, dependencies or audit hashes fail clearly;
the audit does not silently repair evidence or downgrade a failed check to a
metadata success. Use the application ledger that published the inputs and built
the index. A separate empty audit database cannot demonstrate their provenance.

The result records `verified_checks`, `verified_audit_streams` and caller-supplied
`runtime_metadata`. Runtime metadata is labelled evidence about configuration,
not a measurement or proof that a model executed successfully. No model provider,
scripted adapter or TEST_DOUBLE mode is assumed by the audit.

## Remaining qualifications

Integrity verification and review are separate. Actual source/provision review
states and temporal assertion intervals are retained. Unapproved or insufficiently
dated applicability remains qualified; checking hashes does not resolve it.

The calculation profile declares allowed metals, target basis, unsupported
features and purchase-ceiling state. A disabled ceiling remains disabled. An
ordinary supplied AU target remains available even when a refurbishment offset
is unsupported; the audit does not reduce that target or calculate compensation.

Rights fields reproduce the recorded source metadata and policy/decision IDs.
They do not provide a fresh legal conclusion about copyright or statutory
exceptions. REVIEW_REQUIRED/DENY or restricted redistribution remains explicit;
matching hashes grants no additional publication permission.

The audit performs no semantic inference, legal sufficiency evaluation, retrieval
query, latency benchmark or held-out model assessment. Runtime evaluation remains
a separately measured task. Development retrieval regressions are not a completed
48-dossier held-out evaluation.

## Verification

```sh
uv run pytest -q tests/integration/test_h08_frozen_audit.py
uv run pytest -q tests/integration/test_h08_reproducibility.py tests/unit/test_h08_retrieval_regressions.py
```

The real-input tests clone approved foundation evidence without reviewer
credentials, build an actual index and verify exact pins and recorded states.
Negative cases change expected pins, index bytes, original/provision blobs,
profile content and audit hashes. Legacy helper tests require an explicitly
unverified result instead of fabricated source review/rights assertions.
