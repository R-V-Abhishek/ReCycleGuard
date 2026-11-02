# H01: Source leads, aliases, and initial source/locator fixtures

Owner: H Sampreeth Bhat — 1BM23CD020.
Workstream: Regulatory acquisition, extraction coverage, and provision locators (C01, C03, C06, C07).
State: **IN_REVIEW**. CP0 remains **WAITING**.
Target PR integration branch: `checkpoint-0`.

## Delivered boundary

1. **Source leads manifest (`configs/sources/source_leads.jsonl`)**:
   - 29 curated regulatory and operational source leads conforming strictly to `SourceLead` model from `CONTRACTS.md` §4.1.
   - Preserves canonical IDs (`source_lead:r01` to `source_lead:r16`, plus benchmark, state OCMMS SOP, and cross-regime leads) and document-local aliases (`domain:Rxx`, `cpcb:Rxx`).
   - Complete priority P0 coverage: R02 base rules, R03–R06 amendments, R07 producer registration SOP, R08 CPCB FAQ, R09 certificate generation framework, R10 generation/transfer guidance, R11 producer return instruction sheet.
   - Priority P1 parent statute (R01 Environment Protection Act 1986), official portal shells (R13, R14).
   - Asset-level rights and licensing: all Gazette rule seeds are initialized to `REVIEW_REQUIRED` under Section 52(1)(q) of the Indian Copyright Act, 1957, with `redistribution_allowed = False`. Non-commercial research fair dealing recorded under Section 52(1)(a)(i) for CPCB manuals.
2. **Acquired authentic original (`tests/fixtures/visible/h01/acquired_originals/cpcb_faq_20240123.pdf`)**:
   - Genuine 13-page CPCB FAQ document published on 23 January 2024.
   - Exact length: `167,964` bytes.
   - Exact SHA-256: `30f56238fb7db53dd82f69d198be9a92e31d98ea5b21d2724eb7397641a80d16`.
   - Contains foundational primary evidence: Section C confirms that metal obligations (Au, Cu, Al, Fe) are generated independently of EEE codes, while recyclers must have verified recycling capability for the producer's obligated EEE codes.
3. **Pydantic contracts**:
   - `src/recycleguard/contracts/sources.py`: `SourceLead`, `SourceVersion`, `ProvisionVersion`, `RightsMetadata`.
   - `src/recycleguard/contracts/extraction.py`: `ExtractionResult`, `CoverageItem`, `Observation`, enforcing terminal dispositions, issue reporting for partial extractions, and the Temporal Triad (`event_time`, `source_capture_time`, `ingestion_time`).
   - `src/recycleguard/contracts/__init__.py`: Clean exports of all contract models.
4. **Intake and extraction helpers**:
   - `src/recycleguard/intake/__init__.py`: `load_source_leads()`, `validate_lead_manifest()`.
   - `src/recycleguard/extraction/__init__.py`: `validate_row_coverage_consistency()`.
5. **Visible fixtures (`tests/fixtures/visible/h01/`)**:
   - `source_version_r02.json` and `source_version_r08.json`.
   - `provision_version_r02_rule6.json`, `provision_version_r02_rule15.json`, `provision_version_r08_section_c.json`.
   - `locator_examples.json`: exercises all 5 Locator kinds (`PDF_PAGE`, `PDF_CELL`, `CSV_ROW`, `JSON_POINTER`, `TEXT_SPAN`).
   - `coverage_summary.json`: terminal dispositions (`PARSED`, `QUARANTINED`, `NOT_APPLICABLE`).
   - `extraction_result_sample.json`: compliant `ExtractionResult`.
   - `observation_sample.json`: observation record with quality metadata and temporal triad.
6. **Automated test suite**:
   - `tests/contracts/test_h01_fixtures.py`: 11 contract tests verifying all fixtures and invariants.
   - `tests/unit/test_sources.py`: 5 unit tests validating the manifest, P0 coverage, and rights seeds.
   - Entire suite: **67 tests passing** (including all existing A01 tests).

## Boundary digests

| File | Bytes | SHA-256 |
| --- | --- | --- |
| `configs/sources/source_leads.jsonl` | 23304 | `3635485da1ddf0978a5c3863c0ffd7f8242459854002fcc1726801361550085c` |
| `tests/fixtures/visible/h01/acquired_originals/cpcb_faq_20240123.pdf` | 167964 | `30f56238fb7db53dd82f69d198be9a92e31d98ea5b21d2724eb7397641a80d16` |
| `tests/fixtures/visible/h01/source_version_r02.json` | 1526 | `0a827de9adcdb63dc666410df667218fab81cdffe431b22af215aca3f113b45d` |
| `tests/fixtures/visible/h01/source_version_r08.json` | 1164 | `5412108c5e7ad895c7dbb80430c338bf01928d0f280616952b7f27918837df6c` |
| `tests/fixtures/visible/h01/provision_version_r02_rule6.json` | 922 | `b239494117ef40fb9d45b41591045df8f8f0868f93173c4215066f0dea2a8079` |
| `tests/fixtures/visible/h01/provision_version_r02_rule15.json` | 962 | `eac0196b1ae19b3d4c89fc2c3fd8428bdd1a1fac6d456d353799abb7d841ffa8` |
| `tests/fixtures/visible/h01/provision_version_r08_section_c.json` | 1007 | `d79e7cb2cd31b75eb4d716c29a2dad05e519b2800fdf0d0f58a9a19966cb3945` |
| `tests/fixtures/visible/h01/locator_examples.json` | 2112 | `a2ce9e37bda57ba97fc06a7e172cdd52e4832654204912b6404fae28bfa67bdf` |
| `tests/fixtures/visible/h01/coverage_summary.json` | 2447 | `b465fb80ad9e69778f2aa4ca892cba8de695988eccd3511fcea5f4bb3218dd73` |
| `tests/fixtures/visible/h01/extraction_result_sample.json` | 849 | `d45e13a91fa2d1b279e7614d79d08556c45acdb82b065632e606edce53641fd1` |
| `tests/fixtures/visible/h01/observation_sample.json` | 1924 | `0b892c229c7646a900e614a998603eb5772923bbc3deac1b808e188a97cce5b1` |
| `src/recycleguard/contracts/sources.py` | 2557 | `d7f47e157b7edbc596ecccfc1a67028b26e02a74f1bc0a297a10cd95b1d12117` |
| `src/recycleguard/contracts/extraction.py` | 2283 | `108169ce2e47e44ba874811a81a91271548059d78ff975b375fa66f4e0bc12ba` |
| `src/recycleguard/intake/__init__.py` | 2121 | `ac74d6eddfb8f1ff9bfa76143254efa34162f8df52188fb25df1c05a7c0abeb3` |
| `src/recycleguard/extraction/__init__.py` | 723 | `35c074393d9a3d759fdfcb5ae81c66fa2461d4658913ae9ed0440419ea7fd581` |
| `tests/contracts/test_h01_fixtures.py` | 5454 | `339d1415dda44d437f05169acbb7ca0e2ec3221470971fcd1b9fc32e0ebe1951` |
| `tests/unit/test_sources.py` | 2168 | `24815b2db7e8c90ed1400258cc66cfa1f464bdb7901b3f241c405c2f873302af` |

## Direction on VLM for PDF Parsing and RAG

As part of the implementation plan, the user highlighted guidance from faculty:
> *"whoever is handling rag as the part of the plan, for pdf parsing, sir suggested to use a VLM"*

**Confirmed assignment & strategy:**
- Sampreeth (H) is the designated owner of C01/C03 extraction and C06/C07 RAG corpus indexing and retrieval (`implementation plan.md` §3).
- **Execution roadmap for H03 & H05:**
  1. For structured extraction of complex regulatory gazettes (such as Schedule I/III conversion tables) and synthetic producer dossier PDFs (invoices, transfer slips, stamps), we will evaluate a lightweight, locally runnable Vision-Language Model (VLM, such as quantized Chandra-OCR or compact vision models compatible with 16 GB RAM).
  2. The VLM extraction adapter will be strictly isolated behind the C03 `extract()` contract, producing typed `ExtractionResult` records with exact `Locator(kind="PDF_CELL")` and `CoverageItem` receipts.
  3. Scanned unparseable stamps will be explicitly quarantined under `disposition="QUARANTINED"` rather than hallucinated.
  4. Original PDF bytes and SHA-256 hashes remain immutable in storage.

## A02 integration checklist

1. Confirm all 67 tests pass:
   ```sh
   uv run pytest
   uv run ruff check .
   uv run ruff format --check .
   ```
2. Review `SourceLead`, `SourceVersion`, `ProvisionVersion`, and `ExtractionResult` models for integration into `schemas/v1`.
3. Confirm `configs/sources/source_leads.jsonl` provides the authoritative source inventory needed by C05 snapshot persistence.
4. Merge `codex/h01-source-leads` into `checkpoint-0`.

## A02 follow-up

The original submission/evidence above is retained as history. The integrated
CP0 candidate, corrected fixture digests, interface changes and pending
acknowledgements are recorded in [checkpoint construction history](../checkpoints/checkpoint-0/README.md).

CP0 acceptance update, 24 October 2026: H01 and A02 are DONE; CP0 is APPROVED.
Abhishek reported that all four members acknowledged candidate c8fb512 and its
integration repairs. The checkpoint ledger records this evidence separately from
the original submission state above.
