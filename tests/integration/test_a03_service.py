"""Structured C05 snapshot boundary, including rejection replay and reopen lineage."""

import pytest
from pydantic import ValidationError

from recycleguard.contracts.snapshots import CaseReopen, SnapshotReview
from tests.integration.test_a03_profiles import setup
from tests.integration.test_a03_snapshots import publication
from tests.unit.test_v02_storage import _context


def test_case_reopen_retains_reason_and_exact_parent(tmp_path):
    service, _, cap, _, _ = setup(tmp_path)
    request = publication(service.kernel.blob_store)
    first = service.publish_case(_context("first"), request, capability=cap)
    assert first.status == "SUCCESS" and first.audit_event_ids
    data = request.model_dump(mode="json") | {
        "snapshot_id": "snapshot:reopened",
        "expected_head": first.output.snapshot_id,
        "reason": "Fixture evidence added; coverage still qualified",
    }
    reopen = CaseReopen.model_validate(data)
    ctx = _context("reopen")
    second = service.reopen_case(ctx, reopen, capability=cap)
    assert second.status == "SUCCESS"
    assert second.output.parent_snapshot_id == first.output.snapshot_id
    intent = service.kernel.get_intent(ctx.operation_id)
    assert b"Fixture evidence added" in service.kernel.blob_store.get(intent.payload)
    assert service.snapshots.catalog.get_snapshot(first.output.snapshot_id) == first.output
    with pytest.raises(ValidationError):
        CaseReopen.model_validate(data | {"reason": ""})
    service.kernel.close()


@pytest.mark.parametrize(
    "fault,code", [("digest", "STALE_REVIEW"), ("missing", "MISSING_ARTIFACT")]
)
def test_snapshot_rejection_replays_same_envelope(tmp_path, fault, code):
    service, _, cap, review_cap, human = setup(tmp_path)
    request = publication(service.kernel.blob_store)
    first = service.publish_case(_context("first"), request, capability=cap).output
    target = first.snapshot_id if fault == "digest" else "snapshot:missing"
    review = SnapshotReview(
        scope_id=request.scope_id,
        target_snapshot_id=target,
        target_membership_digest="0" * 64,
        expected_head=target,
        new_snapshot_id="snapshot:reviewed",
        decision="APPROVE",
        reason="Fixture",
    )
    context = _context("review").model_copy(update={"actor": human})
    first_result = service.review_snapshot(context, review, capability=review_cap)
    assert first_result.issues[0].code == code and first_result.audit_event_ids
    assert service.review_snapshot(context, review, capability=review_cap) == first_result
    assert service.snapshots.head(request.scope_id) == first
    service.kernel.close()


def test_missing_snapshot_blob_is_explicit_and_does_not_commit(tmp_path):
    service, _, cap, _, _ = setup(tmp_path)
    request = publication(service.kernel.blob_store)
    digest = request.membership_blob.sha256
    (service.kernel.blob_store.objects / digest[:2] / digest).unlink()
    result = service.publish_case(_context("missing"), request, capability=cap)
    assert result.status == "REJECTED" and result.issues[0].code == "MISSING_ARTIFACT"
    assert service.snapshots.head(request.scope_id) is None
    assert service.kernel.get_result("operation:missing").status == "REJECTED"
    service.kernel.close()


def test_wrong_snapshot_kind_cannot_publish_case(tmp_path):
    service, _, cap, _, _ = setup(tmp_path)
    request = publication(service.kernel.blob_store).model_copy(update={"snapshot_kind": "CORPUS"})
    result = service.publish_case(_context("wrong"), request, capability=cap)
    assert result.issues[0].code == "INVALID_SCHEMA"
    assert service.snapshots.head(request.scope_id) is None
    assert service.publish_corpus(_context("corpus"), request, capability=cap).status == "SUCCESS"
    service.kernel.close()


def test_snapshot_lookup_pins_membership_and_reverifies_blobs(tmp_path):
    from recycleguard.contracts.artifacts import SnapshotRef
    from recycleguard.storage.catalog import CatalogError

    service, _, cap, _, _ = setup(tmp_path)
    request = publication(service.kernel.blob_store)
    first = service.publish_case(_context("first"), request, capability=cap).output
    ref = SnapshotRef(snapshot_id=first.snapshot_id, membership_digest=first.membership_digest)
    assert service.snapshots.get(ref) == first
    with pytest.raises(CatalogError, match="STALE_SNAPSHOT"):
        service.snapshots.get(ref.model_copy(update={"membership_digest": "0" * 64}))
    digest = first.coverage_blob.sha256
    (service.kernel.blob_store.objects / digest[:2] / digest).write_bytes(b"corrupt coverage")
    with pytest.raises(ValueError, match="mismatch"):
        service.snapshots.get(ref)
    service.kernel.close()
