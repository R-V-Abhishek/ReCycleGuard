"""Real H02/H03/S02/A03 integration. Reviewer decisions in tests are fixtures only."""

import json
from pathlib import Path

import pytest

from recycleguard.application import local_application
from recycleguard.config import Settings
from recycleguard.contracts.artifacts import SnapshotRef
from recycleguard.contracts.foundation import FoundationRequest
from recycleguard.foundation import FoundationService
from recycleguard.normalization.models import NormalizationBatch
from recycleguard.profiles import ProfileError

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures/visible"


def request():
    return FoundationRequest(
        case_root=str(FIXTURES / "case_001"),
        r02_path=str(FIXTURES / "h04/acquired_originals/e-waste_rules_2022.pdf"),
        r08_path=str(FIXTURES / "h01/acquired_originals/cpcb_faq_20240123.pdf"),
        case_snapshot_id="snapshot:case_initial",
        corpus_snapshot_id="snapshot:corpus_initial",
        profile_version="cp1-integration-test",
    )


def test_a04_real_pipeline_accounting_pinning_and_replay(tmp_path):
    settings = Settings(data_root=tmp_path)
    with local_application(settings) as (cases, context, cap):
        service = FoundationService(cases)
        result = service.build(context, request(), capability=cap)
        assert result.status == "PARTIAL"
        output = result.output
        assert output.case_snapshot.review_state == "DRAFT"
        assert output.corpus_snapshot.review_state == "DRAFT"
        assert output.inventory_count == 17  # 16 declared assets plus the manifest original.
        assert output.extraction_count == 19  # Every case original plus two regulatory PDFs.
        membership = json.loads(service.blobs.get(output.case_snapshot.membership_blob))
        normalized = NormalizationBatch.model_validate_json(json.dumps(membership["normalization"]))
        originals = membership["originals"]
        assert len(originals) == 17
        assert len(normalized.records) >= 8
        types = {record.record_type for record in normalized.records}
        assert {"Registration", "Certificate", "Allocation", "ObligationBucket"} <= types
        assert all(record.observation_refs for record in normalized.records)
        assert all(record.validation_state == "REVIEW_REQUIRED" for record in normalized.records)
        allocation = next(r for r in normalized.records if r.record_type == "Allocation")
        assert allocation.state == "PENDING" and allocation.quantity.decimal == "55.0000"
        target = next(r for r in normalized.records if r.record_type == "ObligationBucket")
        assert target.target.decimal == "100.0000"
        assert all("record_type" in r for r in membership["normalization"]["records"])
        assert len(normalized.dispositions) == len(
            {d.observation_id for d in normalized.dispositions}
        )
        case_coverage = json.loads(service.blobs.get(output.case_snapshot.coverage_blob))[
            "coverage"
        ]
        extracted_ids = {child for item in case_coverage for child in item["child_observation_ids"]}
        assert {d.observation_id for d in normalized.dispositions} == extracted_ids
        corpus = json.loads(service.blobs.get(output.corpus_snapshot.membership_blob))
        assert [p["locator"]["page_index_1based"] for p in corpus["provisions"]] == [24, 27, 9]
        assert all(p["review_state"] == "DRAFT" for p in corpus["provisions"])
        assert all(
            a["interval"]["applicability_scope"] == "UNKNOWN" for a in corpus["applicability"]
        )
        coverage = json.loads(service.blobs.get(output.corpus_snapshot.coverage_blob))["coverage"]
        assert len(coverage) == 51
        assert all(item["disposition"] == "PARSED" for item in coverage)
        for revision in corpus["artifact_revisions"]:
            from recycleguard.contracts.artifacts import ArtifactRevision

            stored = ArtifactRevision.model_validate_json(json.dumps(revision))
            assert service.blobs.get(stored.blob).startswith(b"%PDF-")
        with pytest.raises(ProfileError, match="approved"):
            cases.profiles.get(output.profile, require_approved=True)
        assert service.build(context, request(), capability=cap) == result
        assert len(cases.kernel.list_attempts(context.operation_id)) == 1
        pinned = SnapshotRef(
            snapshot_id=output.case_snapshot.snapshot_id,
            membership_digest=output.case_snapshot.membership_digest,
        )
    with local_application(settings) as (cases, _, _):
        assert cases.snapshots.get(pinned) == output.case_snapshot
        assert cases.profiles.get(output.profile).review_state == "DRAFT"


def test_failure_before_normalization_commit_can_resume_without_duplicate_intake(tmp_path):
    with local_application(Settings(data_root=tmp_path)) as (cases, context, cap):
        cases.kernel.connection.execute("""CREATE TRIGGER fail_norm BEFORE INSERT ON audit_events
          WHEN NEW.event_json LIKE '%normalization.batch.result%'
          BEGIN SELECT RAISE(ABORT,'simulated crash window'); END""")
        service = FoundationService(cases)
        failed = service.build(context, request(), capability=cap)
        assert failed.status == "OUTCOME_UNKNOWN"
        assert failed.issues[0].code == "AUDIT_UNAVAILABLE"
        assert cases.snapshots.head("case:001") is None
        assert cases.kernel.get_result(context.operation_id) is None
        receipts = cases.kernel.connection.execute(
            "SELECT count(*) FROM intake_receipts"
        ).fetchone()[0]
        cases.kernel.connection.execute("DROP TRIGGER fail_norm")
        result = service.build(context, request(), capability=cap)
        assert result.output.case_snapshot.review_state == "DRAFT"
        assert (
            cases.kernel.connection.execute("SELECT count(*) FROM intake_receipts").fetchone()[0]
            == receipts
        )


def test_service_capabilities_checked_before_evidence_writes(tmp_path):
    from recycleguard.storage.authority import Capability

    with local_application(Settings(data_root=tmp_path)) as (cases, context, _):
        result = FoundationService(cases).build(context, request(), capability=Capability())
        assert result.status == "REJECTED" and result.issues[0].code == "ACCESS_DENIED"
        assert list(cases.kernel.blob_store.objects.glob("*/*")) == []


def review_environment(tmp_path):
    from recycleguard.case_service import CaseService
    from recycleguard.contracts.core import ActorRef
    from recycleguard.contracts.foundation import FoundationApproval
    from recycleguard.foundation_review import FoundationReviewer
    from recycleguard.local_session import authenticate_reviewer, initialize_reviewer
    from recycleguard.profiles import ProfileStore
    from recycleguard.snapshots import SnapshotStore
    from recycleguard.storage import ArtifactCatalog, AuditKernel, BlobStore
    from recycleguard.storage.authority import LocalAuthority, TrustedPrincipal

    settings = Settings(data_root=tmp_path)
    with local_application(settings) as (cases, context, cap):
        prepared = FoundationService(cases).build(context, request(), capability=cap)
    initialize_reviewer(tmp_path, "human:review_test", "temporary-test-password")
    human = authenticate_reviewer(tmp_path, "temporary-test-password")
    actor = ActorRef(
        actor_id="service:local_c05", actor_kind="SERVICE", authenticated_session_ref=None
    )
    authority = LocalAuthority(
        {
            "service": TrustedPrincipal(actor, frozenset({"profile.", "snapshot."})),
            "reviewer": TrustedPrincipal(human, frozenset({"review."})),
        }
    )
    cap, review_cap = authority.issue("service"), authority.issue("reviewer")
    blobs = BlobStore(tmp_path)
    kernel = AuditKernel(tmp_path / "application.sqlite", blobs, authority=authority)
    catalog = ArtifactCatalog(tmp_path / "application.sqlite", blobs, kernel=kernel)
    cases = CaseService(SnapshotStore(kernel, catalog), ProfileStore(kernel, catalog))
    reviewer = FoundationReviewer(cases, service_actor=actor, service_capability=cap)
    approval = FoundationApproval(
        candidate_blob=prepared.output_blob,
        approval_evidence_blob=blobs.put(
            b"Synthetic review evidence for this test only", "text/plain"
        ),
        approval_reference="approval:test_fixture",
        accepted_qualifications=(
            "Test fixture review only; applicability remains unknown and deadlines unavailable."
        ),
        reviewed_profile_version="reviewed-test",
        approved_profile_version="approved-test",
        reviewed_case_snapshot_id="snapshot:case_reviewed",
        approved_case_snapshot_id="snapshot:case_approved",
        reviewed_corpus_snapshot_id="snapshot:corpus_reviewed",
        approved_corpus_snapshot_id="snapshot:corpus_approved",
    )
    from recycleguard.application import command_context

    return cases, prepared, reviewer, approval, command_context(human), cap, review_cap


def test_qualified_human_approval_pins_approved_profile_and_preserves_drafts(tmp_path):
    cases, prepared, reviewer, approval, context, _, cap = review_environment(tmp_path)
    result = reviewer.approve(context, approval, capability=cap)
    assert (
        result.status == "PARTIAL"
    )  # Qualified acceptance is not a claim that all evidence is resolved.
    output = result.output
    assert output.case_snapshot.review_state == "APPROVED"
    assert output.corpus_snapshot.review_state == "APPROVED"
    assert cases.profiles.get(output.profile, require_approved=True).review_state == "APPROVED"
    membership = json.loads(cases.kernel.blob_store.get(output.case_snapshot.membership_blob))
    assert membership["profile"] == output.profile.model_dump(mode="json")
    assert membership["corpus_snapshot"]["snapshot_id"] == output.corpus_snapshot.snapshot_id
    corpus = json.loads(cases.kernel.blob_store.get(output.corpus_snapshot.membership_blob))
    assert all(p["review_state"] == "APPROVED" for p in corpus["provisions"])
    assert all(
        a["interval"]["review_state"] == "APPROVED"
        and a["interval"]["applicability_scope"] == "UNKNOWN"
        for a in corpus["applicability"]
    )
    old = json.loads(cases.kernel.blob_store.get(prepared.output.case_snapshot.membership_blob))
    assert old["profile"] == prepared.output.profile.model_dump(mode="json")
    assert (
        cases.snapshots.catalog.get_snapshot(prepared.output.case_snapshot.snapshot_id).review_state
        == "DRAFT"
    )
    assert reviewer.approve(context, approval, capability=cap) == result
    assert all(issue.code != "UNAPPROVED_PROFILE" for issue in result.issues)
    cases.kernel.close()


def test_foundation_review_rejects_spoof_and_stale_candidate_before_new_approval(tmp_path):
    from recycleguard.application import command_context
    from recycleguard.contracts.snapshots import SnapshotPublication
    from recycleguard.storage.authority import AuthorizationError

    cases, prepared, reviewer, approval, context, service_cap, review_cap = review_environment(
        tmp_path
    )
    with pytest.raises(AuthorizationError):
        reviewer.approve(context, approval, capability=service_cap)
    old = prepared.output.case_snapshot
    actor = reviewer.service_actor
    changed = cases.publish_case(
        command_context(actor),
        SnapshotPublication(
            scope_id="case:001",
            snapshot_id="snapshot:newer",
            snapshot_kind="CASE",
            expected_head=old.snapshot_id,
            membership_blob=old.membership_blob,
            membership_digest=old.membership_digest,
            coverage_blob=old.coverage_blob,
            source_receipt_ids=old.source_receipt_ids,
        ),
        capability=service_cap,
    )
    assert changed.status == "SUCCESS"
    with pytest.raises(ValueError, match="STALE_REVIEW"):
        reviewer.approve(context, approval, capability=review_cap)
    assert cases.profiles.head(prepared.output.profile.profile_id) == prepared.output.profile
    cases.kernel.close()
