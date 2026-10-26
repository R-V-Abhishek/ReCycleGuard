"""S03 through the real snapshot store and, where the platform allows, the real CP1 pipeline."""

import json
import os
from pathlib import Path

import pytest

from recycleguard.application import local_application
from recycleguard.config import Settings
from recycleguard.contracts.artifacts import SnapshotRef
from recycleguard.contracts.foundation import FoundationRequest
from recycleguard.contracts.snapshots import SnapshotPublication
from recycleguard.domain import compute_reconciliation, reconcile_universe, universe_from_membership
from recycleguard.foundation import FoundationService
from recycleguard.storage import canonical_json_bytes
from tests.support.c08 import (
    CONTEXT,
    PROFILE,
    bucket_result,
    clean_case,
    profile,
    request,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures/visible"
needs_posix_intake = pytest.mark.skipif(
    not hasattr(os, "O_NOFOLLOW"), reason="CP1 intake uses O_NOFOLLOW (POSIX only)"
)


def publish_case(cases, context, cap, membership, snapshot_id="snapshot:s03"):
    blobs = cases.kernel.blob_store
    member = blobs.put(canonical_json_bytes(membership), "application/json")
    coverage = blobs.put(b'{"coverage":[]}', "application/json")
    result = cases.publish_snapshot(
        context,
        SnapshotPublication(
            scope_id="case:t",
            snapshot_id=snapshot_id,
            snapshot_kind="CASE",
            expected_head=None,
            membership_blob=member,
            membership_digest=member.sha256,
            coverage_blob=coverage,
            source_receipt_ids=[],
        ),
        capability=cap,
    )
    assert result.status == "SUCCESS", result.issues
    return result.output


def test_c08_reads_only_the_pinned_snapshot(tmp_path):
    membership = {"normalization": {"records": [r.model_dump(mode="json") for r in clean_case()]}}
    with local_application(Settings(data_root=tmp_path)) as (cases, context, cap):
        snapshot = publish_case(cases, context, cap, membership, "snapshot:t")
        pinned = SnapshotRef(
            snapshot_id=snapshot.snapshot_id, membership_digest=snapshot.membership_digest
        )
        result = compute_reconciliation(
            context,
            request(snapshot="snapshot:t"),
            snapshots=cases.snapshots,
            snapshot_ref=pinned,
            profile=profile(deadlines_testable=True),
        )
        assert result.status == "SUCCESS", result.issues
        out = bucket_result(result)
        assert (out.required.decimal, out.supported.decimal) == ("100.0000", "55.0000")
        assert out.signed_gap.decimal == "45.0000"
        blobs = cases.kernel.blob_store
        assert json.loads(blobs.get(result.output.analyzed_input_membership_blob))["members"]

        stale = pinned.model_copy(update={"membership_digest": "0" * 64})
        rejected = compute_reconciliation(
            context,
            request(snapshot="snapshot:t"),
            snapshots=cases.snapshots,
            snapshot_ref=stale,
            profile=profile(deadlines_testable=True),
        )
        assert rejected.status == "REJECTED" and rejected.issues[0].code == "STALE_SNAPSHOT"


def test_profile_must_match_the_one_the_snapshot_pins(tmp_path):
    other = profile(deadlines_testable=True)
    membership = {
        "normalization": {"records": [r.model_dump(mode="json") for r in clean_case()]},
        "profile": {"profile_id": PROFILE, "profile_version": "other", "digest": "f" * 64},
    }
    with local_application(Settings(data_root=tmp_path)) as (cases, context, cap):
        snapshot = publish_case(cases, context, cap, membership, "snapshot:t")
        pinned = SnapshotRef(
            snapshot_id=snapshot.snapshot_id, membership_digest=snapshot.membership_digest
        )
        result = compute_reconciliation(
            context,
            request(snapshot="snapshot:t"),
            snapshots=cases.snapshots,
            snapshot_ref=pinned,
            profile=other,
        )
        assert result.status == "REJECTED" and result.issues[0].code == "STALE_REVIEW"


def test_corpus_snapshot_is_rejected(tmp_path):
    with local_application(Settings(data_root=tmp_path)) as (cases, context, cap):
        blobs = cases.kernel.blob_store
        member = blobs.put(b'{"provisions":[]}', "application/json")
        coverage = blobs.put(b'{"coverage":[]}', "application/json")
        published = cases.publish_snapshot(
            context,
            SnapshotPublication(
                scope_id="corpus:t",
                snapshot_id="snapshot:corpus_t",
                snapshot_kind="CORPUS",
                expected_head=None,
                membership_blob=member,
                membership_digest=member.sha256,
                coverage_blob=coverage,
                source_receipt_ids=[],
            ),
            capability=cap,
        ).output
        result = compute_reconciliation(
            context,
            request(snapshot="snapshot:corpus_t"),
            snapshots=cases.snapshots,
            snapshot_ref=SnapshotRef(
                snapshot_id=published.snapshot_id, membership_digest=published.membership_digest
            ),
            profile=profile(),
        )
        assert result.status == "REJECTED" and result.issues[0].code == "INVALID_SCHEMA"


@needs_posix_intake
def test_real_cp1_pipeline_is_honestly_qualified_not_manufactured_support(tmp_path):
    """The accepted CP1 foundation leaves the 55 kg allocation PENDING; C08 must not promote it."""
    foundation_request = FoundationRequest(
        case_root=str(FIXTURES / "case_001"),
        r02_path=str(FIXTURES / "h04/acquired_originals/e-waste_rules_2022.pdf"),
        r08_path=str(FIXTURES / "h01/acquired_originals/cpcb_faq_20240123.pdf"),
        case_snapshot_id="snapshot:case_initial",
        corpus_snapshot_id="snapshot:corpus_initial",
        profile_version="s03-integration",
    )
    with local_application(Settings(data_root=tmp_path)) as (cases, context, cap):
        built = FoundationService(cases).build(context, foundation_request, capability=cap)
        snapshot = built.output.case_snapshot
        membership = json.loads(cases.kernel.blob_store.get(snapshot.membership_blob))
        bucket_id = "bucket:prod_001_cu_2024_2025"
        universe = universe_from_membership(snapshot.snapshot_id, membership)
        calc_request = request((bucket_id,), snapshot=snapshot.snapshot_id)
        result = reconcile_universe(
            CONTEXT, calc_request, universe, profile(), cases.kernel.blob_store
        )
        out = bucket_result(result, bucket_id)
        assert out.required.decimal == "100.0000"
        assert out.supported.decimal == "0.0000", "S03 must never promote a PENDING allocation"
        # 55 kg PENDING allocation + 25 kg unlinked invoice; pending is never subtracted.
        assert out.pending.decimal == "80.0000"
        assert out.signed_gap.decimal == "100.0000"
        derivation = json.loads(cases.kernel.blob_store.get(result.output.derivation_blob))
        row = derivation["buckets"][0]
        assert row["pending_allocation_ids"] == ["alloc:001"]
        assert row["pending_commercial_ids"] == ["comm:inv_001"]
        assert result.status == "PARTIAL" and result.output.coverage == "QUALIFIED"
        items = json.loads(cases.kernel.blob_store.get(result.output.quantity_dispositions_blob))
        assert len(items) == len(membership["normalization"]["records"])

        draft = cases.profiles.get(built.output.profile)
        rejected = compute_reconciliation(
            context,
            calc_request,
            snapshots=cases.snapshots,
            snapshot_ref=SnapshotRef(
                snapshot_id=snapshot.snapshot_id, membership_digest=snapshot.membership_digest
            ),
            profile=draft,
        )
        assert rejected.status == "REJECTED"
        assert rejected.issues[0].code == "UNAPPROVED_PROFILE"
