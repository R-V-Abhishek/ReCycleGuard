# Source Data Card — ReCycleGuard Retrieval Corpus (H08)

**Task:** H08 — Audit final corpus/profile and development retrieval regressions  
**Owner:** Sampreeth (H08)  
**Predecessor checkpoints:** CP3 (`252ddcc`)  
**Date:** 2026-10-29  
**Handoff target:** CP4 integration (A08, V09)

---

## 1. Active Corpus Overview

The retrieval engine operates on two primary regulatory sources. No other sources
are active in the lexical index for `producer_snapshot_v1`.

| Alias | Artifact Revision ID | Document Title |
|-------|---------------------|----------------|
| R02 | `artifact_rev:r02_rules_2022_official_pdf` | E-Waste (Management) Rules 2022 |
| R08 | `artifact_rev:cpcb_faq_20240123_pdf` | CPCB FAQ on E-Waste Rules 2022, Jan 2024 |

---

## 2. Source R02 — E-Waste (Management) Rules 2022

| Field | Value |
|-------|-------|
| **Artifact Revision ID** | `artifact_rev:r02_rules_2022_official_pdf` |
| **Source alias** | `R02`, `domain:R02`, `cpcb:R02` |
| **Issuer** | Ministry of Environment, Forest and Climate Change, Government of India |
| **Instrument type** | Statutory Instrument / Gazette Rule |
| **Regime** | `E_WASTE_2022` |
| **Source URL** | https://eprewaste.cpcb.gov.in/assets/PDF/e-waste_rules_2022.pdf |
| **SHA-256 digest** | `d03f8744bc79d67a94b06e1020537e93d15572b0cf1d575cb32b76c89f30a5fb` |
| **Total pages** | 38 |
| **Access policy** | `policy:local_source_review` |
| **Rights decision** | `decision:review_required` |
| **Copyright owner** | Government of India (Crown/India copyright) |
| **Statutory exception** | Section 52(1)(q), Copyright Act 1957 — reproduction for compliance review |
| **Redistribution** | **Not permitted**; local compliance-review use only |
| **Review state** | `DRAFT` |

### 2.1 Active provisions (reviewed pages only)

| Provision ID | Physical Page | Legal Path | Roles | Regime |
|---|---|---|---|---|
| `provision:r02_rule6_sub4` | **24** | Rule 6(4), full physical-page context | PRODUCER | E_WASTE_2022 |
| `provision:r02_rule15_sub1_sub3` | **27** | Rule 15(1)-(3), full physical-page context | PRODUCER, RECYCLER | E_WASTE_2022 |

### 2.2 Unreviewed pages

Pages 1–23, 25–26, 28–38 are captured but **not individually reviewed**.
No conclusions are drawn from unreviewed page ranges. Any retrieval candidate
from these pages carries `review_state=DRAFT` and `authority=UNRESOLVED`.

---

## 3. Source R08 — CPCB FAQ on E-Waste Rules 2022

| Field | Value |
|-------|-------|
| **Artifact Revision ID** | `artifact_rev:cpcb_faq_20240123_pdf` |
| **Source alias** | `R08`, `cpcb:FAQ` |
| **Issuer** | Central Pollution Control Board (CPCB), Government of India |
| **Instrument type** | Official Guidance / FAQ |
| **Regime** | `E_WASTE_2022` |
| **Source URL** | https://eprewaste.cpcb.gov.in/assets/PDF/faqewaste.pdf |
| **SHA-256 digest** | `30f56238fb7db53dd82f69d198be9a92e31d98ea5b21d2724eb7397641a80d16` |
| **Total pages** | 13 |
| **Access policy** | `policy:local_source_review` |
| **Rights decision** | `decision:review_required` |
| **Copyright owner** | Government of India / CPCB (Crown/India copyright) |
| **Statutory exception** | Section 52(1)(q), Copyright Act 1957 — reproduction for compliance review |
| **Redistribution** | **Not permitted**; local compliance-review use only |
| **Review state** | `DRAFT` |

> **Important:** FAQ status is official guidance, not a statute. The FAQ cannot override
> Rule text. Conclusions drawn from R08 must be corroborated against R02 Rule text.

### 3.1 Active provisions (reviewed pages only)

| Provision ID | Physical Page | Legal Path | Roles | Regime |
|---|---|---|---|---|
| `provision:r08_sec_c_recycler_capability` | **9** | Section C, EEE capability, full page context | PRODUCER, RECYCLER | E_WASTE_2022 |

### 3.2 Unreviewed pages

Pages 1–8, 10–13 are captured but not individually reviewed.

---

## 4. Active Calculation Profile

| Field | Value |
|-------|-------|
| **Profile ID** | `profile:producer_snapshot_v1` |
| **Profile version** | `1.0` |
| **Review state** | `DRAFT` |
| **Supported regime** | `EWASTE_EPR_SUPPLIED_TARGETS` |
| **Target basis** | `SUPPLIED_METAL_WISE_OBLIGATIONS` |
| **Allowed metals** | AU, CU, AL, FE |
| **Category scope** | ITEW4, CEEW1 |
| **Priority check** | `EARLIER_COMPATIBLE_AT_ALLOCATION_TIME` |
| **Purchase ceiling** | `DISABLED_REVIEW_REQUIRED` |
| **Source R02 dependency digest** | `d03f8744bc79d67a94b06e1020537e93d15572b0cf1d575cb32b76c89f30a5fb` |
| **Source R08 dependency digest** | `30f56238fb7db53dd82f69d198be9a92e31d98ea5b21d2724eb7397641a80d16` |

### 4.1 Unsupported features (explicit exclusions)

All six features below are explicitly excluded from `producer_snapshot_v1`:

| Feature | Reason |
|---------|--------|
| `GOLD_OFFSETS` | Out-of-scope regime; F14 fault family |
| `REFURBISHING_DEFERRALS` | Out-of-scope regime; F14 fault family |
| `SALES_DERIVED_TARGETS` | Not applicable to supplied-weight basis |
| `TAX_PRICING` | Excluded from active calculation |
| `SOLAR` | Excluded from active calculation |
| `ENVIRONMENTAL_COMPENSATION` | Out-of-scope regime |

---

## 5. Lexical Index Summary

| Field | Value |
|-------|-------|
| **Index type** | SQLite FTS5 BM25 |
| **Tokenizer** | `unicode61` |
| **BM25 k1** | 1.2 |
| **BM25 b** | 0.75 |
| **Indexed columns** | legal_path, title, text, regime, role_scope, affected_roles |
| **Index binding** | Frozen to `corpus_snapshot_id`; `integrity_digest` verified on every request |
| **Semantic embedding** | Not enabled; `dense_configuration_or_null = null` |

---

## 6. Recorded Retrieval Limitations

### L01 — Unreviewed provisions
- **Scope:** R02 pages 1–23, 25–26, 28–38; R08 pages 1–8, 10–13
- **Effect:** Candidates from unreviewed pages have `review_state=DRAFT`; `authority=UNRESOLVED`
- **Mitigation:** Expand reviewed page set in a future H09 corpus update

### L02 — Missing extension order (F12 family)
- **Scope:** Rule 9A enabling provision; FY 2024-25 RETURN_FILING deadline
- **Effect:** `DeadlineRegister` returns `ABSTAIN` (fallback to `baseline_due`) when
  `unverified_notice=True` or `extension_order_refs` is empty
- **Mitigation:** Capture the signed CPCB extension order when it becomes accessible

### L03 — Disabled purchase ceiling (Rule 15)
- **Scope:** `PurchaseCeilingPolicy.state = DISABLED_REVIEW_REQUIRED`
- **Effect:** No purchase ceiling is enforced; calculations proceed without ceiling cap
- **Mitigation:** Requires a separate `ProfileReview` decision with signed authority

### L04 — Redistribution restricted
- **Scope:** All derived corpus chunks from R02 and R08
- **Effect:** Publication bundles must omit original PDF bytes and full page text
- **Mitigation:** Apply rights filter at export; provide attribution only

### L05 — Temporal applicability unresolved
- **Scope:** All three active provisions (assertion `review_state=DRAFT`)
- **Effect:** `temporal_fit=UNRESOLVED` for all grading assessments
- **Mitigation:** Review and approve applicability assertions with explicit intervals

### L06 — Semantic grades unresolved (C10 TEST_DOUBLE)
- **Scope:** `direct_support`, `contradiction` grades for all candidates
- **Effect:** `direct_support=UNRESOLVED` and `contradiction=UNRESOLVED` always
- **Mitigation:** Wire a real C10 gateway; verify compatibility separately per §8.3

### L07 — Unsupported features (gold offset, refurbishing, etc.)
- **Scope:** GOLD_OFFSETS, REFURBISHING_DEFERRALS, SALES_DERIVED_TARGETS, TAX_PRICING, SOLAR, ENVIRONMENTAL_COMPENSATION
- **Effect:** F14 explicit abstention; no calculation output for these regimes
- **Mitigation:** These are explicit design constraints of v1; document for callers

---

## 7. Retrieval Behavior Summary

```
request pins: corpus_snapshot_id + index_id (+ optional digest assertions)
engine: FTS5 BM25 lexical ranking (k1=1.2, b=0.75, tokenizer=unicode61)
grading: 5D (authority, temporal_fit, direct_support, completeness, contradiction)
  - authority: deterministic (source_class + review_state)
  - temporal_fit: UNRESOLVED (assertion intervals not reviewed)
  - direct_support: UNRESOLVED (C10 TEST_DOUBLE)
  - completeness: PASS if COMPLETE_TEXT + top-level provision
  - contradiction: UNRESOLVED (C10 TEST_DOUBLE)
expansion: max_depth=2, max_nodes=20 (hard boundary; no unbounded traversal)
disposition kinds: FILTERED_OUT | NOT_SCORED | OUTSIDE_ENGINE_WINDOW |
                   SCORED | REJECTED_SUPPORT | OMITTED_CONTEXT_BUDGET
```

---

## 8. Fault Coverage (Development Regression Labels)

| Fault | Kind | Test Label | Expected outcome |
|-------|------|------------|-----------------|
| F11 | Wrong period rule | R03 | `temporal_fit` never `PASS`; UNRESOLVED |
| F12 | Unseen notice lead | R04 | No `authority=PASS` for NOTICE_LEAD; `direct_support=UNRESOLVED` |
| F14 | Out-of-scope regime | R02 | No `authority=PASS + direct_support=PASS` for gold offset |

---

## 9. Handoff Checklist for CP4 (A08, V09)

- [x] Corpus digest pinned for R02 and R08 (`corpus_audit.py`)
- [x] Active physical pages documented: R02→{24,27}, R08→{9}
- [x] Rights and access policy IDs recorded for both sources
- [x] Profile digest and purchase ceiling state audited
- [x] Seven limitation kinds documented with `effect_on_retrieval`
- [x] 14 labelled development retrieval regressions (`test_h08_retrieval_regressions.py`)
- [x] Fresh-root reproducibility integration test (`test_h08_reproducibility.py`)
- [x] Source data card present at `docs/data/source_data_card.md`

---

*This card was generated as part of H08 task execution. It is not a legal opinion
and does not represent a complete rights review. Redistribution decisions require
independent legal review before publication.*

