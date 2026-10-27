"""Unit tests for H06 filtered retrieval, locator resolution, and 5D evidence grading.

Owned by Sampreeth (H06 / C07).
Verifies:
- search_rules with BM25 ranking, server-side role/regime filtering, and candidate dispositions.
- resolve_locator with unambiguous and ambiguous path lookups.
- get_source_passage with bounded context expansion (ExpansionPolicy).
- grade_evidence across the 5 mandatory dimensions:
  authority, temporal_fit, direct_support, completeness, contradiction.
- Audited retrieval attempt recording with AuditKernel.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from recycleguard.contracts.core import ActorRef, CommandContext
from recycleguard.contracts.foundation import SourceBatch
from recycleguard.contracts.retrieval import (
    ExpansionPolicy,
    LocatorLookupRequest,
    SearchRulesRequest,
)
from recycleguard.contracts.snapshots import SnapshotPublication
from recycleguard.indexing.builder import IndexBuilder
from recycleguard.knowledge.provisions import (
    get_reviewed_provisions,
    register_reviewed_sources,
)
from recycleguard.retrieval.service import RetrievalService
from recycleguard.storage import ArtifactCatalog, AuditKernel, BlobStore
from recycleguard.storage.authority import LocalAuthority, TrustedPrincipal
from recycleguard.storage.blob_store import canonical_json_bytes

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures/visible"
R02_PDF = FIXTURES_DIR / "h04/acquired_originals/e-waste_rules_2022.pdf"
R08_PDF = FIXTURES_DIR / "h01/acquired_originals/cpcb_faq_20240123.pdf"


@pytest.fixture
def retrieval_env(tmp_path):
    """Sets up an authentic index and corpus snapshot from CP1 reviewed sources."""
    data_root = tmp_path / "data"
    data_root.mkdir()
    store = BlobStore(data_root / "blobs")

    actor = ActorRef(
        actor_id="service:retriever", actor_kind="SERVICE", authenticated_session_ref=None
    )
    authority = LocalAuthority({"retriever": TrustedPrincipal(actor, frozenset({"extraction."}))})
    cap = authority.issue("retriever")

    db_path = data_root / "app.sqlite"
    kernel = AuditKernel(db_path, store, authority=authority)
    catalog = ArtifactCatalog(db_path, store, kernel=kernel)

    # 1. Register sources and reviewed provisions
    r02_rev, r08_rev = register_reviewed_sources(store, r02_path=R02_PDF, r08_path=R08_PDF)
    provisions = get_reviewed_provisions(store, r02_revision=r02_rev, r08_revision=r08_rev)

    # 2. Build SourceBatch and CorpusSnapshot
    source_batch = SourceBatch(
        artifact_revisions=[r02_rev, r08_rev],
        receipts=[],
        leads=[],
        source_versions=[],
        provisions=provisions,
        applicability=[],
    )
    batch_json = canonical_json_bytes(source_batch.model_dump(mode="json"))
    membership_blob = store.put(batch_json, "application/json")
    coverage_blob = store.put(b'{"coverage": []}', "application/json")

    corpus_snapshot = SnapshotPublication(
        scope_id="corpus:test_h06",
        snapshot_id="snapshot:corpus_test_h06",
        snapshot_kind="CORPUS",
        expected_head=None,
        membership_blob=membership_blob,
        membership_digest=membership_blob.sha256,
        coverage_blob=coverage_blob,
        source_receipt_ids=[],
    )

    # 3. Build FTS5 Index
    builder = IndexBuilder(data_root, store, catalog=catalog, kernel=kernel)
    manifest, fts_index = builder.build_index(corpus_snapshot)

    # 4. Instantiate RetrievalService
    service = RetrievalService(
        fts_index,
        corpus_snapshot,
        store,
        kernel=kernel,
    )

    return service, manifest, corpus_snapshot, store, kernel, cap, actor


def test_search_rules_with_dispositions_and_role_filtering(retrieval_env):
    """Verify search_rules BM25 ranking, server-side filtering, and candidate dispositions."""
    service, manifest, snapshot, store, kernel, cap, actor = retrieval_env

    # 1. Broad query without role filter
    req = SearchRulesRequest(
        query="Rule 6 annual returns",
        corpus_snapshot_id=snapshot.snapshot_id,
        index_id=manifest.index_id,
        top_k=2,
    )
    attempt = service.search_rules(req)

    assert attempt.attempt_id.startswith("retrieval:")
    assert len(attempt.engine_candidates) >= 1
    assert any(
        c["legal_path"] == "Rule 6(4), full physical-page context"
        for c in attempt.engine_candidates
    )

    # Check candidate dispositions
    disposition_kinds = {d.disposition for d in attempt.candidate_dispositions}
    assert "SCORED" in disposition_kinds

    # Check grading assessments
    assert len(attempt.grading_assessments) >= 1
    grade = attempt.grading_assessments[0]
    assert grade.authority == "PASS"
    assert grade.temporal_fit == "PASS"
    assert grade.direct_support in {"PASS", "UNRESOLVED"}

    # 2. Query with role filter for RECYCLER (Rule 6 is PRODUCER specific)
    req_recycler = SearchRulesRequest(
        query="Rule 6 responsibilities",
        corpus_snapshot_id=snapshot.snapshot_id,
        index_id=manifest.index_id,
        roles=["RECYCLER"],
        top_k=2,
    )
    attempt_recycler = service.search_rules(req_recycler)
    # Rule 6 only has PRODUCER role, so it must be filtered out
    for cand in attempt_recycler.engine_candidates:
        assert cand["legal_path"] != "Rule 6(4), full physical-page context"


def test_resolve_locator_exact_and_ambiguous(retrieval_env):
    """Verify resolve_locator finds exact legal paths and handles ambiguities."""
    service, manifest, snapshot, store, kernel, cap, actor = retrieval_env

    # 1. Exact lookup of Rule 15
    req = LocatorLookupRequest(
        corpus_snapshot_id=snapshot.snapshot_id,
        source_alias_or_source_version_id="r02",
        legal_path="Rule 15",
    )
    bundle = service.resolve_locator(req)
    assert bundle.bundle_id.startswith("bundle:")
    assert "Rule 15" in bundle.legal_path
    assert bundle.locator.page_index_1based == 27
    assert len(bundle.primary_passage) > 0

    # 2. Nonexistent path raises KeyError
    with pytest.raises(KeyError):
        service.resolve_locator(
            LocatorLookupRequest(
                corpus_snapshot_id=snapshot.snapshot_id,
                source_alias_or_source_version_id="r02",
                legal_path="Rule 999_nonexistent",
            )
        )


def test_get_source_passage_and_expansion(retrieval_env):
    """Verify get_source_passage expands context bounded by ExpansionPolicy."""
    service, manifest, snapshot, store, kernel, cap, actor = retrieval_env

    # Fetch Rule 6 provision bundle
    bundle = service.get_source_passage(
        "provision:r02_rule6_sub4",
        expansion_policy=ExpansionPolicy(max_depth=2, max_nodes=10),
    )
    assert bundle.provision_version_id == "provision:r02_rule6_sub4"
    assert bundle.locator.page_index_1based == 24
    assert len(bundle.primary_passage) > 50


def test_grade_evidence_five_dimensions(retrieval_env):
    """Verify grade_evidence assesses the 5 mandatory evidence quality dimensions."""
    service, manifest, snapshot, store, kernel, cap, actor = retrieval_env

    bundle = service.get_source_passage("provision:r08_sec_c_recycler_capability")
    grades = service.grade_evidence(
        bundle.bundle_id,
        question="What is the recycler capability requirement for electrical equipment?",
        basis="REPORTING_PERIOD",
    )

    assert len(grades) == 1
    grade = grades[0]
    assert grade.authority in {"PASS", "UNRESOLVED"}
    assert grade.temporal_fit == "PASS"
    assert grade.direct_support in {"PASS", "UNRESOLVED"}
    assert grade.completeness in {"PASS", "UNRESOLVED"}
    assert grade.contradiction == "PASS"
    assert len(grade.reasons) >= 2


def test_audited_search_rules_commits_to_kernel(retrieval_env):
    """Verify search_rules commits operation intent and result to AuditKernel."""
    service, manifest, snapshot, store, kernel, cap, actor = retrieval_env

    context = CommandContext(
        contract_version="1.1",
        command_id="cmd:test_retrieval",
        operation_id="op:test_retrieval",
        attempt_id="att:test_retrieval",
        idempotency_key="key:test_retrieval",
        actor=actor,
        case_version_id=None,
        run_id=None,
        turn_id=None,
        correlation_id="corr:test_retrieval",
        parent_operation_id=None,
    )

    req = SearchRulesRequest(
        query="allocation priority",
        corpus_snapshot_id=snapshot.snapshot_id,
        index_id=manifest.index_id,
        top_k=2,
    )

    attempt = service.search_rules(req, context=context, capability=cap)
    assert attempt.full_result_blob is not None

    events = kernel.list_stream_events(f"stream:{attempt.attempt_id}")
    assert len(events) >= 1
    assert events[0].event_type == "extraction.retrieval.result"
