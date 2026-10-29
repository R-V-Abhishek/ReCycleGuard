"""End-to-end integration test connecting H05 indexing and H06 retrieval services.

Owned by Sampreeth (H05 / H06).
Verifies:
- Building SQLite FTS5 index and IndexManifest directly from CP1 corpus snapshot.
- End-to-end search_rules with BM25 ranking and candidate dispositions.
- resolve_locator with physical page locators and context expansion.
- 5-dimensional evidence grading of regulatory rules.
- Audited pipeline execution under AuditKernel and capability checks.
"""

from __future__ import annotations

from pathlib import Path

from recycleguard.application import local_application
from recycleguard.config import Settings
from recycleguard.contracts.foundation import FoundationRequest
from recycleguard.contracts.retrieval import (
    ExpansionPolicy,
    LocatorLookupRequest,
    SearchRulesRequest,
)
from recycleguard.foundation import FoundationService
from recycleguard.indexing.builder import IndexBuilder
from recycleguard.retrieval.service import RetrievalService

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures/visible"
R02_PDF = FIXTURES_DIR / "h04/acquired_originals/e-waste_rules_2022.pdf"
R08_PDF = FIXTURES_DIR / "h01/acquired_originals/cpcb_faq_20240123.pdf"


def test_h05_h06_complete_indexing_and_retrieval_pipeline(tmp_path):
    """End-to-end pipeline: CP1 foundation -> H05 FTS5 index -> H06 retrieval & 5D grading."""
    settings = Settings(data_root=tmp_path)
    with local_application(settings) as (cases, context, cap):
        # 1. Build Foundation (CP1 outputs: case and corpus snapshots)
        f_req = FoundationRequest(
            case_root=str(FIXTURES_DIR / "case_001"),
            r02_path=str(R02_PDF),
            r08_path=str(R08_PDF),
            case_snapshot_id="snapshot:case_e2e_h05_h06",
            corpus_snapshot_id="snapshot:corpus_e2e_h05_h06",
            profile_version="1.0-draft",
        )
        f_service = FoundationService(cases)
        f_result = f_service.build(context, f_req, capability=cap)
        corpus_snapshot = f_result.output.corpus_snapshot

        # 2. Build H05 SQLite FTS5 Lexical Index
        builder = IndexBuilder(
            tmp_path,
            cases.kernel.blob_store,
            catalog=cases.snapshots.catalog,
            kernel=cases.kernel,
        )
        idx_ctx = context.model_copy(
            update={
                "command_id": "cmd:build_h05_index",
                "operation_id": "op:build_h05_index",
                "attempt_id": "att:build_h05_index",
                "idempotency_key": "key:build_h05_index",
            }
        )
        manifest, fts_index = builder.build_index(
            corpus_snapshot,
            context=idx_ctx,
            capability=cap,
        )

        assert manifest.total_chunks > 0
        assert manifest.corpus_snapshot_id == corpus_snapshot.snapshot_id
        assert len(manifest.integrity_digest) == 64

        # 3. Instantiate H06 Retrieval Service
        retrieval = RetrievalService(
            fts_index,
            corpus_snapshot,
            cases.kernel.blob_store,
            kernel=cases.kernel,
        )

        # 4. Search rules for producer annual filing
        ret_ctx = context.model_copy(
            update={
                "command_id": "cmd:search_rule6",
                "operation_id": "op:search_rule6",
                "attempt_id": "att:search_rule6",
                "idempotency_key": "key:search_rule6",
            }
        )
        search_req = SearchRulesRequest(
            query="Rule 6 annual returns",
            corpus_snapshot_id=corpus_snapshot.snapshot_id,
            index_id=manifest.index_id,
            roles=["PRODUCER"],
            top_k=3,
        )
        attempt = retrieval.search_rules(search_req, context=ret_ctx, capability=cap)

        assert len(attempt.engine_candidates) >= 1
        assert any("Rule 6" in c["legal_path"] for c in attempt.engine_candidates)
        assert len(attempt.grading_assessments) >= 1

        # 5. Resolve exact legal path via resolve_locator
        lookup_req = LocatorLookupRequest(
            corpus_snapshot_id=corpus_snapshot.snapshot_id,
            source_alias_or_source_version_id="r02",
            legal_path="Rule 15",
            expansion_policy=ExpansionPolicy(include_parent=True),
        )
        bundle = retrieval.resolve_locator(lookup_req)

        assert "Rule 15" in bundle.legal_path
        assert bundle.locator.page_index_1based == 27
        assert len(bundle.primary_passage) > 0

        # 6. Grade evidence bundle across 5 dimensions
        grades = retrieval.grade_evidence(
            bundle.bundle_id,
            question="What is the priority of allocation for earlier liabilities?",
            basis="REPORTING_PERIOD",
        )

        assert len(grades) == 1
        grade = grades[0]
        assert grade.authority == "PASS"
        assert grade.temporal_fit == "PASS"
        assert grade.direct_support in {"PASS", "UNRESOLVED"}
        assert grade.completeness in {"PASS", "UNRESOLVED"}
        assert grade.contradiction == "PASS"

        fts_index.close()
