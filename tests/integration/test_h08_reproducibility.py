"""H08: Fresh-root reproducibility integration test for corpus/profile audit.

Owned by Sampreeth (H08).

Verifies:
  1. Foundation → review → index → retrieval pipeline from a clean temp root.
  2. Corpus audit manifest is generated against the live index manifest.
  3. Exact locator resolution (page 24, 27, 9) survives a fresh root build.
  4. Rights metadata and access policy IDs are preserved through audit.
  5. AuditKernel records at least one retrieval event after a live search.
  6. Profile audit record matches live approved profile digest and ceiling state.
  7. Source digest verification returns True for actual PDF bytes; False for tampered.
"""

from pathlib import Path

from recycleguard.application import command_context
from recycleguard.contracts.core import ActorRef
from recycleguard.contracts.retrieval import SearchRulesRequest
from recycleguard.indexing.builder import IndexBuilder
from recycleguard.knowledge.corpus_audit import (
    _R02_REV_ID,
    _R08_REV_ID,
    build_corpus_profile_audit_manifest,
    verify_source_digest,
)
from recycleguard.retrieval.service import RetrievalService
from recycleguard.storage import AuditKernel
from recycleguard.storage.authority import LocalAuthority, TrustedPrincipal
from tests.integration.test_a04_foundation import review_environment

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures/visible"
R02_PDF = FIXTURES_DIR / "h04/acquired_originals/e-waste_rules_2022.pdf"
R08_PDF = FIXTURES_DIR / "h01/acquired_originals/cpcb_faq_20240123.pdf"


def test_h08_fresh_root_corpus_audit_reproducibility(tmp_path):
    """H08 end-to-end: fresh root, corpus audit manifest, locators, rights, and profile."""

    # ── 1. Build foundation, review and approve from a single clean root ──────
    # review_environment handles foundation build + qualified human approval.
    cases_rv, prepared, reviewer, approval, rv_ctx, _, review_cap = review_environment(tmp_path)
    assert prepared.status == "PARTIAL", (
        f"H08 repro: foundation must return PARTIAL, got {prepared.status}"
    )
    approved_result = reviewer.approve(rv_ctx, approval, capability=review_cap)
    assert approved_result.status == "PARTIAL"
    approved_corpus = approved_result.output.corpus_snapshot

    # ── 2. Build H05 lexical index ────────────────────────────────────────────
    actor = ActorRef(
        actor_id="service:h08_repro",
        actor_kind="SERVICE",
        authenticated_session_ref=None,
    )
    authority = LocalAuthority({"svc": TrustedPrincipal(actor, frozenset({"extraction."}))})
    kernel = AuditKernel(
        tmp_path / "h08_repro.sqlite",
        cases_rv.kernel.blob_store,
        authority=authority,
    )
    cap_svc = authority.issue("svc")
    ctx_svc = command_context(actor)

    builder = IndexBuilder(
        tmp_path,
        cases_rv.kernel.blob_store,
        kernel=kernel,
    )
    idx_ctx = ctx_svc.model_copy(
        update={
            "command_id": "cmd:h08_index",
            "operation_id": "op:h08_index",
            "attempt_id": "att:h08_index",
            "idempotency_key": "key:h08_index",
        }
    )
    manifest, fts_index = builder.build_index(approved_corpus, context=idx_ctx, capability=cap_svc)

    # ── 3. Build H06 retrieval service ───────────────────────────────────────
    service = RetrievalService(
        fts_index,
        approved_corpus,
        cases_rv.kernel.blob_store,
        manifest=manifest,
        kernel=kernel,
    )

    # ── 4. Verify exact locator resolution ────────────────────────────────────
    # Three active provisions: R02 pages 24, 27 and R08 page 9
    pages_found = sorted(p.locator.page_index_1based for p in service.provisions_map.values())
    assert pages_found == [9, 24, 27], (
        f"H08 repro: expected active pages [9, 24, 27], got {pages_found}"
    )

    # Rule 6(4) must be on page 24
    rule6_pages = [
        p.locator.page_index_1based
        for p in service.provisions_map.values()
        if "Rule 6" in p.legal_path
    ]
    assert 24 in rule6_pages, "H08 repro: Rule 6(4) must resolve to physical page 24"

    # Rule 15 must be on page 27
    rule15_pages = [
        p.locator.page_index_1based
        for p in service.provisions_map.values()
        if "Rule 15" in p.legal_path
    ]
    assert 27 in rule15_pages, "H08 repro: Rule 15(1)-(3) must resolve to physical page 27"

    # ── 5. Perform a live retrieval and verify audit event is recorded ────────
    search_req = SearchRulesRequest(
        query="producer extended responsibility",
        corpus_snapshot_id=service.corpus_snapshot.snapshot_id,
        index_id=manifest.index_id,
        target_reporting_period="2024-2025",
    )
    search_ctx = ctx_svc.model_copy(
        update={
            "command_id": "cmd:h08_search",
            "operation_id": "op:h08_search",
            "attempt_id": "att:h08_search",
            "idempotency_key": "key:h08_search",
        }
    )
    attempt = service.search_rules(search_req, context=search_ctx, capability=cap_svc)

    # All candidates must receive dispositions
    assert len(attempt.candidate_dispositions) == manifest.total_chunks, (
        "H08 repro: all corpus chunks must receive a disposition"
    )

    # AuditKernel must have committed a retrieval event
    events = kernel.list_stream_events(f"stream:{service.corpus_snapshot.snapshot_id}")
    retrieval_events = [e for e in events if e.event_type == "extraction.retrieval.result"]
    assert retrieval_events, (
        "H08 repro: at least one extraction.retrieval.result event must be committed"
    )

    # ── 6. Generate corpus audit manifest ────────────────────────────────────
    approved_profile = cases_rv.profiles.get(approved_result.output.profile, require_approved=True)
    profile_payload = approved_profile.model_dump(mode="json")

    audit_manifest = build_corpus_profile_audit_manifest(
        profile_payload=profile_payload,
        index_manifest_payload=manifest.model_dump(mode="json"),
    )

    # Two sources with correct digests and redistribution restriction
    assert len(audit_manifest.sources) == 2
    for src in audit_manifest.sources:
        assert src.redistribution_allowed is False
        assert src.review_state in ("DRAFT", "APPROVED")

    # Index record tied to the live manifest
    assert audit_manifest.index is not None
    assert audit_manifest.index.index_id == manifest.index_id
    assert audit_manifest.index.total_chunks == manifest.total_chunks

    # Profile record matches live profile
    assert audit_manifest.profile.profile_id == "profile:producer_snapshot_v1"
    assert audit_manifest.profile.purchase_ceiling_state == "DISABLED_REVIEW_REQUIRED"
    assert set(audit_manifest.profile.allowed_metals) == {"AU", "CU", "AL", "FE"}

    # At least 7 limitations
    assert len(audit_manifest.limitations) >= 7

    # ── 7. Verify rights metadata passes through ──────────────────────────────
    r02_src = next(s for s in audit_manifest.sources if s.artifact_revision_id == _R02_REV_ID)
    r08_src = next(s for s in audit_manifest.sources if s.artifact_revision_id == _R08_REV_ID)

    assert r02_src.access_policy_id == "policy:local_source_review"
    assert r02_src.rights_decision_id == "decision:review_required"
    assert r08_src.access_policy_id == "policy:local_source_review"
    assert r08_src.rights_decision_id == "decision:review_required"

    # ── 8. Source digest verification against actual PDF bytes ────────────────
    r02_bytes = R02_PDF.read_bytes()
    r08_bytes = R08_PDF.read_bytes()

    assert verify_source_digest(_R02_REV_ID, r02_bytes) is True, (
        "H08 repro: R02 PDF bytes must match pinned SHA-256 digest"
    )
    assert verify_source_digest(_R08_REV_ID, r08_bytes) is True, (
        "H08 repro: R08 PDF bytes must match pinned SHA-256 digest"
    )

    # Tampered bytes must fail
    assert verify_source_digest(_R02_REV_ID, b"tampered") is False

    # ── Cleanup ───────────────────────────────────────────────────────────────
    fts_index.close()
    kernel.close()
    cases_rv.kernel.close()
