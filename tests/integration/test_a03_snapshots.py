"""First A03 persistence slice: immutable snapshots and version-bound trusted review."""

import sqlite3

import pytest

from recycleguard.contracts.core import ActorRef
from recycleguard.contracts.snapshots import SnapshotPublication, SnapshotReview
from recycleguard.snapshots import SnapshotStore
from recycleguard.storage import ArtifactCatalog, AuditKernel, BlobStore
from recycleguard.storage.authority import LocalAuthority, TrustedPrincipal
from recycleguard.storage.catalog import CatalogError
from tests.unit.test_v02_storage import _context


def setup(tmp_path):
    blobs = BlobStore(tmp_path)
    service = _context().actor
    human = ActorRef(
        actor_id="human:reviewer",
        actor_kind="HUMAN",
        authenticated_session_ref="session:verified_fixture",
    )
    authority = LocalAuthority(
        {
            "service": TrustedPrincipal(service, frozenset({"snapshot.", "intake."})),
            "reviewer": TrustedPrincipal(human, frozenset({"review."})),
        }
    )
    cap, review_cap = authority.issue("service"), authority.issue("reviewer")
    kernel = AuditKernel(tmp_path / "db.sqlite", blobs, authority=authority)
    catalog = ArtifactCatalog(tmp_path / "db.sqlite", blobs, kernel=kernel)
    return blobs, kernel, catalog, SnapshotStore(kernel, catalog), cap, review_cap, human


def publication(blobs, name="draft", expected=None):
    membership = blobs.put(b'{"items":[],"missing_evidence":true}', "application/json")
    coverage = blobs.put(b'{"state":"QUALIFIED"}', "application/json")
    return SnapshotPublication(
        scope_id="case:001",
        snapshot_id=f"snapshot:{name}",
        snapshot_kind="CASE",
        expected_head=expected,
        membership_blob=membership,
        membership_digest=membership.sha256,
        coverage_blob=coverage,
        source_receipt_ids=[],
    )


@pytest.mark.parametrize("decision,state", [("APPROVE", "APPROVED"), ("REJECT", "REJECTED")])
def test_publish_replay_and_review_keep_original_immutable(tmp_path, decision, state):
    blobs, kernel, catalog, store, cap, review_cap, human = setup(tmp_path)
    ctx = _context("publish")
    draft = store.publish(ctx, publication(blobs), capability=cap)
    original_json = catalog.get_snapshot(draft.snapshot_id).model_dump_json()
    assert store.publish(ctx, publication(blobs), capability=cap) == draft
    review = SnapshotReview(
        scope_id="case:001",
        target_snapshot_id=draft.snapshot_id,
        expected_head=draft.snapshot_id,
        target_membership_digest=draft.membership_digest,
        new_snapshot_id="snapshot:approved",
        decision=decision,
        reason="Fixture boundary reviewed",
    )
    reviewer_context = _context("review").model_copy(update={"actor": human})
    child = store.review(reviewer_context, review, capability=review_cap)
    assert child.review_state == state
    assert child.parent_snapshot_id == draft.snapshot_id
    assert child.membership_blob == draft.membership_blob
    assert catalog.get_snapshot(draft.snapshot_id).model_dump_json() == original_json
    assert store.head("case:001") == child
    assert store.review(reviewer_context, review, capability=review_cap) == child
    kernel.close()


def test_stale_publication_and_stale_review_cannot_move_head(tmp_path):
    blobs, kernel, _, store, cap, review_cap, human = setup(tmp_path)
    first = store.publish(_context("first"), publication(blobs), capability=cap)
    second = store.publish(
        _context("second"), publication(blobs, "second", first.snapshot_id), capability=cap
    )
    with pytest.raises(CatalogError, match="CONCURRENT_MODIFICATION"):
        store.publish(
            _context("stale"), publication(blobs, "stale", first.snapshot_id), capability=cap
        )
    stale_review = SnapshotReview(
        scope_id="case:001",
        target_snapshot_id=first.snapshot_id,
        expected_head=first.snapshot_id,
        target_membership_digest=first.membership_digest,
        new_snapshot_id="snapshot:stale_review",
        decision="APPROVE",
        reason="Stale packet",
    )
    with pytest.raises(CatalogError, match="CONCURRENT_MODIFICATION"):
        store.review(
            _context("stale_review").model_copy(update={"actor": human}),
            stale_review,
            capability=review_cap,
        )
    assert store.head("case:001") == second
    assert kernel.get_result("operation:stale_review").status == "REJECTED"
    kernel.close()


def test_wrong_membership_and_spoofed_human_are_rejected(tmp_path):
    blobs, kernel, _, store, cap, review_cap, human = setup(tmp_path)
    draft = store.publish(_context("draft"), publication(blobs), capability=cap)
    review = SnapshotReview(
        scope_id="case:001",
        target_snapshot_id=draft.snapshot_id,
        expected_head=draft.snapshot_id,
        target_membership_digest="a" * 64,
        new_snapshot_id="snapshot:bad",
        decision="REJECT",
        reason="Wrong digest",
    )
    with pytest.raises(CatalogError, match="STALE_REVIEW"):
        store.review(
            _context("bad_digest").model_copy(update={"actor": human}),
            review,
            capability=review_cap,
        )
    with pytest.raises(ValueError, match="capability"):
        store.review(_context("spoof").model_copy(update={"actor": human}), review, capability=cap)
    assert store.head("case:001") == draft
    kernel.close()


def test_snapshot_and_head_roll_back_on_audit_failure(tmp_path):
    blobs, kernel, catalog, store, cap, _, _ = setup(tmp_path)
    kernel.connection.execute(
        "CREATE TRIGGER fail_event BEFORE INSERT ON audit_events "
        "BEGIN SELECT RAISE(ABORT,'audit failed'); END"
    )
    with pytest.raises(sqlite3.IntegrityError):
        store.publish(_context("failure"), publication(blobs), capability=cap)
    assert store.head("case:001") is None
    with pytest.raises(KeyError):
        catalog.get_snapshot("snapshot:draft")
    assert kernel.get_result("operation:failure") is None
    kernel.close()


def test_snapshot_head_survives_reopen(tmp_path):
    blobs, kernel, _, store, cap, _, _ = setup(tmp_path)
    draft = store.publish(_context("persist"), publication(blobs), capability=cap)
    kernel.close()
    _, kernel, _, store, _, _, _ = setup(tmp_path)
    assert store.head("case:001") == draft
    kernel.close()


def test_snapshot_retains_declared_missing_receipts(tmp_path):
    from tests.unit.test_v02_storage import _intent, _receipt, _success_result

    blobs, kernel, catalog, store, cap, _, _ = setup(tmp_path)
    context = _context("missing_receipt")
    intent = _intent(blobs, context, event_type="intake.receipt")
    receipt = _receipt(None, "receipt:declared_missing", status="DECLARED_MISSING")
    kernel.commit_intent(intent, capability=cap)
    kernel.commit_result(
        intent,
        _success_result(context, intent.payload),
        capability=cap,
        mutation=lambda: catalog.put_receipt(receipt),
    )
    request = publication(blobs).model_copy(update={"source_receipt_ids": [receipt.receipt_id]})
    snapshot = store.publish(_context("missing_snapshot"), request, capability=cap)
    assert snapshot.source_receipt_ids == [receipt.receipt_id]
    assert snapshot.review_state == "DRAFT"
    kernel.close()
