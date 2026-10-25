"""Regression cases from the V02 readiness review, using the production API."""

import sqlite3

import pytest

from recycleguard.storage import ArtifactCatalog, AuditKernel, BlobStore
from recycleguard.storage.authority import Capability, LocalAuthority, TrustedPrincipal
from recycleguard.storage.catalog import CatalogError
from tests.unit.test_v02_storage import (
    TestSnapshotCatalogRoundTrip as _SnapshotFixtures,
)
from tests.unit.test_v02_storage import (
    _actor,
    _artifact_revision,
    _context,
    _failed_result,
    _intent,
    _receipt,
    _success_result,
)


def system(tmp_path):
    store = BlobStore(tmp_path)
    authority = LocalAuthority(
        {"service": TrustedPrincipal(_actor(), frozenset({"intake.", "snapshot."}))}
    )
    cap = authority.issue("service")
    kernel = AuditKernel(tmp_path / "db.sqlite", store, authority=authority)
    catalog = ArtifactCatalog(tmp_path / "db.sqlite", store, kernel=kernel)
    return store, authority, cap, kernel, catalog


def test_catalog_domain_mutation_rolls_back_with_audit_failure(tmp_path):
    store, _, cap, kernel, catalog = system(tmp_path)
    ctx = _context("atomic")
    intent = _intent(store, ctx)
    revision = _artifact_revision(store)
    kernel.commit_intent(intent, capability=cap)
    kernel.connection.execute(
        "CREATE TRIGGER fail_event BEFORE INSERT ON audit_events "
        "BEGIN SELECT RAISE(ABORT,'audit unavailable'); END"
    )
    with pytest.raises(sqlite3.IntegrityError):
        kernel.commit_result(
            intent,
            _success_result(ctx, intent.payload),
            capability=cap,
            mutation=lambda: catalog.put_artifact_revision(revision),
        )
    with pytest.raises(KeyError):
        catalog.get_artifact_revision(revision.artifact_revision_id)
    assert kernel.get_result(ctx.operation_id) is None
    assert kernel.list_stream_events(intent.stream_id) == []
    assert kernel.connection.execute("SELECT count(*) FROM attempt_results").fetchone()[0] == 0
    kernel.connection.execute("DROP TRIGGER fail_event")
    calls = []

    def write():
        calls.append(1)
        catalog.put_artifact_revision(revision)

    event = kernel.commit_result(
        intent, _success_result(ctx, intent.payload), capability=cap, mutation=write
    )
    assert (
        kernel.commit_result(
            intent, _success_result(ctx, intent.payload), capability=cap, mutation=write
        )
        == event
    )
    assert calls == [1]
    kernel.close()


def test_unaudited_catalog_write_is_rejected(tmp_path):
    store, _, _, kernel, catalog = system(tmp_path)
    with pytest.raises(CatalogError, match="shared audited transaction"):
        catalog.put_artifact_revision(_artifact_revision(store))
    standalone = ArtifactCatalog(tmp_path / "db.sqlite", store)
    with pytest.raises(CatalogError, match="shared audited transaction"):
        standalone.put_artifact_revision(_artifact_revision(store))
    standalone.close()
    kernel.close()


def test_retry_keeps_request_identity_and_both_attempt_outcomes(tmp_path):
    store, _, cap, kernel, _ = system(tmp_path)
    ctx = _context("retry")
    first = _intent(store, ctx)
    kernel.commit_intent(first, capability=cap)
    failure = kernel.commit_result(first, _failed_result(ctx), capability=cap, terminal=False)
    assert kernel.get_result(ctx.operation_id) is None
    second_ctx = ctx.model_copy(update={"attempt_id": "attempt:second"})
    second = first.model_copy(update={"context": second_ctx})
    kernel.commit_intent(second, capability=cap)
    success = kernel.commit_result(
        second, _success_result(second_ctx, second.payload), capability=cap
    )
    assert len(kernel.list_attempts(ctx.operation_id)) == 2
    assert kernel.get_result(ctx.operation_id).attempt_id == second_ctx.attempt_id
    assert success.previous_event_hash == failure.event_hash
    assert kernel.get_event(failure.event_id).attempt_id == ctx.attempt_id
    with pytest.raises(ValueError, match="terminal"):
        third = first.model_copy(
            update={"context": ctx.model_copy(update={"attempt_id": "attempt:third"})}
        )
        kernel.commit_intent(third, capability=cap)
    kernel.close()


def test_forged_or_unknown_capability_and_revocation_fail_closed(tmp_path):
    store, authority, cap, kernel, _ = system(tmp_path)
    ctx = _context("auth")
    intent = _intent(store, ctx)
    for supplied in (None, Capability()):
        with pytest.raises(ValueError, match="capability"):
            kernel.commit_intent(intent, capability=supplied)
    with pytest.raises(ValueError, match="permitted"):
        kernel.commit_intent(_intent(store, ctx, event_type="unregistered.write"), capability=cap)
    human = _intent(store, _context("human", actor_kind="HUMAN"), event_type="review.approve")
    with pytest.raises(ValueError, match="capability"):
        kernel.commit_intent(human, capability=cap)
    with pytest.raises(ValueError, match="session"):
        TrustedPrincipal(_actor("HUMAN"), frozenset({"review."}))
    authority.revoke(cap)
    with pytest.raises(ValueError, match="capability"):
        kernel.commit_intent(intent, capability=cap)
    kernel.close()


def test_missing_receipt_remains_in_snapshot(tmp_path):
    from tests.unit.test_v02_storage import ArtifactCatalog as AuditedTestCatalog

    store = BlobStore(tmp_path)
    catalog = AuditedTestCatalog(tmp_path / "db.sqlite", store)
    snapshot = _SnapshotFixtures()._make_snapshot(store, catalog)
    missing = _receipt(None, "receipt:missing", status="DECLARED_MISSING")
    catalog.put_receipt(missing)
    snapshot = snapshot.model_copy(update={"source_receipt_ids": [missing.receipt_id]})
    assert catalog.put_snapshot(snapshot).source_receipt_ids == [missing.receipt_id]
    catalog.close()
