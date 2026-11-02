# H01 visible contract fixtures

Owner: H Sampreeth Bhat (1BM23CD020).
Workstream: Regulatory acquisition, extraction coverage, and provision locators (C01, C03, C06, C07).

These fixtures provide authentic inspected primary sources, typed locator coordinates across all five supported locator modes, extraction and coverage item dispositions, and granular provision version models conforming to `CONTRACTS.md` §§3.3 & 4.1.

## Fixture inventory

- `acquired_originals/cpcb_faq_20240123.pdf`:
  Authentic 13-page PDF acquired from CPCB WM-III Division.
  - Length: `167,964` bytes.
  - SHA-256: `30f56238fb7db53dd82f69d198be9a92e31d98ea5b21d2724eb7397641a80d16`.
  - Rights seed: `REVIEW_REQUIRED` (Section 52(1)(a)(i) Indian Copyright Act, 1957; non-commercial research fair dealing; no bulk redistribution allowed).
- `source_version_r02.json`:
  Acquired source version metadata for the base E-Waste (Management) Rules, 2022 (G.S.R. 801(E)).
- `source_version_r08.json`:
  Acquired source version metadata for CPCB FAQ (23 January 2024).
- `provision_version_r02_rule6.json`:
  Provision version for Rule 6(4) specifying quarterly and annual return filing baseline timelines.
- `provision_version_r02_rule15.json`:
  Provision version for Rule 15(1) & (3) specifying EPR certificate mechanism and mandatory priority against earlier liabilities.
- `provision_version_r08_section_c.json`:
  Provision version for Section C answering metal obligation independence from EEE items while enforcing recycler capability matching.
- `locator_examples.json`:
  Five typed locator examples verifying:
  1. `PDF_PAGE`: Physical 1-based page index.
  2. `PDF_CELL`: Table-id, row, and column coordinates within a physical page.
  3. `CSV_ROW`: 1-based data-row index excluding header and column name.
  4. `JSON_POINTER`: RFC 6901 compliant pointer.
  5. `TEXT_SPAN`: Non-empty half-open [start, end) character offsets.
- `coverage_summary.json`:
  Coverage items demonstrating terminal dispositions (`PARSED`, `QUARANTINED`, `NOT_APPLICABLE`).
- `extraction_result_sample.json`:
  `ExtractionResult` matching strict boundary model with configuration digest and blob references.
- `observation_sample.json`:
  `Observation` record demonstrating extraction provenance and the Temporal Triad (`event_time`, `source_capture_time`, `ingestion_time`).

## Verification

Run automated tests:
```sh
uv run pytest tests/contracts/test_h01_fixtures.py tests/unit/test_sources.py
```
