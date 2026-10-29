"""Approved CP2 originals, index pins, exact locators, and honest evidence grades."""

import pytest

from recycleguard.application import command_context
from recycleguard.contracts.core import ActorRef
from recycleguard.contracts.retrieval import LocatorLookupRequest, SearchRulesRequest
from recycleguard.indexing.builder import IndexBuilder
from recycleguard.retrieval.service import RetrievalService
from recycleguard.storage import AuditKernel
from recycleguard.storage.authority import AuthorizationError, LocalAuthority, TrustedPrincipal
from tests.integration.test_a04_foundation import review_environment


@pytest.fixture
def retrieval_env(tmp_path):
    cases, _, reviewer, approval, ctx, _, review_cap = review_environment(tmp_path)
    approved = reviewer.approve(ctx, approval, capability=review_cap).output
    blobs = cases.kernel.blob_store
    actor = ActorRef(
        actor_id="service:retrieval", actor_kind="SERVICE", authenticated_session_ref=None
    )
    authority = LocalAuthority({"retrieval": TrustedPrincipal(actor, frozenset({"extraction."}))})
    kernel = AuditKernel(tmp_path / "application.sqlite", blobs, authority=authority)
    cap = authority.issue("retrieval")
    builder = IndexBuilder(tmp_path, blobs, kernel=kernel)
    context = command_context(actor)
    manifest, index = builder.build_index(approved.corpus_snapshot, context=context, capability=cap)
    service = RetrievalService(
        index, approved.corpus_snapshot, blobs, manifest=manifest, kernel=kernel
    )
    yield service, manifest, builder, context, cap
    index.close()
    kernel.close()
    cases.kernel.close()


def test_real_approved_corpus_retrieval_preserves_uncertainty_and_all_dispositions(retrieval_env):
    service, manifest, _, build_context, cap = retrieval_env
    request = SearchRulesRequest(
        query="producer",
        corpus_snapshot_id=service.corpus_snapshot.snapshot_id,
        index_id=manifest.index_id,
        target_reporting_period="2024-2025",
    )
    with pytest.raises(AuthorizationError):
        service.search_rules(request)
    ctx = command_context(build_context.actor)
    attempt = service.search_rules(request, context=ctx, capability=cap)
    assert attempt.engine_candidates
    assert len(attempt.candidate_dispositions) == manifest.total_chunks
    assert any(g.authority == "PASS" for g in attempt.grading_assessments)
    assert all(g.temporal_fit == "UNRESOLVED" for g in attempt.grading_assessments)
    assert all(
        g.direct_support == "UNRESOLVED" and g.contradiction == "UNRESOLVED"
        for g in attempt.grading_assessments
    )
    assert all(g.evidence_refs for g in attempt.grading_assessments)
    assert service.search_rules(request, context=ctx, capability=cap) == attempt
    events = service.kernel.list_stream_events(f"stream:{service.corpus_snapshot.snapshot_id}")
    assert [e.event_type for e in events].count("extraction.retrieval.result") == 1
    with pytest.raises(ValueError, match="pins"):
        service.search_rules(
            request.model_copy(update={"index_id": "index:wrong"}),
            context=command_context(ctx.actor),
            capability=cap,
        )


def test_exact_locator_rejects_wrong_source_and_does_not_guess(retrieval_env):
    service, _, _, _, _ = retrieval_env
    provision = next(
        p for p in service.provisions_map.values() if p.locator.page_index_1based == 27
    )
    request = LocatorLookupRequest(
        corpus_snapshot_id=service.corpus_snapshot.snapshot_id,
        source_alias_or_source_version_id=provision.source_version_id,
        legal_path=provision.legal_path,
    )
    bundle = service.resolve_locator(request)
    assert bundle.locator == provision.locator
    assert bundle.primary_passage == service.blob_store.get(provision.text_blob).decode()
    assert "APPLICABILITY_UNRESOLVED" in bundle.applicability_qualifiers
    with pytest.raises(KeyError):
        service.resolve_locator(
            request.model_copy(update={"source_alias_or_source_version_id": "r99"})
        )
    with pytest.raises(KeyError):
        service.resolve_locator(request.model_copy(update={"legal_path": "Rule 1"}))


def test_immutable_index_recovers_missing_cache_and_rejects_tamper(retrieval_env):
    service, manifest, builder, ctx, cap = retrieval_env
    path = service.index.db_path
    service.index.close()
    path.unlink()
    same, index = builder.build_index(service.corpus_snapshot, context=ctx, capability=cap)
    assert same == manifest and index.search("producer")
    index.close()
    path.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="differ"):
        builder.build_index(service.corpus_snapshot, context=ctx, capability=cap)
