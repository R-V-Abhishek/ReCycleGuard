"""S05 cases through the real CP1 pipeline, and C08 self-consistency on their reviewed records."""

import json
from pathlib import Path

import pytest

from benchmarks.generator.hidden import reference_balances
from benchmarks.generator.s05_cases import build_worlds
from recycleguard.application import local_application
from recycleguard.config import Settings
from recycleguard.contracts.core import BlobRef
from recycleguard.contracts.domain import RECORD_ADAPTER
from recycleguard.contracts.foundation import FoundationRequest
from recycleguard.domain import reconcile_universe, universe_from_membership, universe_from_records
from recycleguard.foundation import FoundationService
from recycleguard.storage import BlobStore
from tests.support.c08 import CONTEXT, SNAPSHOT, bucket_result, profile, request

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures/visible"
WORLDS = {w.case_tag: w for w in build_worlds()}
RECORD_FILES = (
    "entities",
    "registrations",
    "obligations",
    "certificates",
    "certificate_events",
    "allocations",
    "commercial_records",
    "account_balances",
)


def _records(case: Path):
    return [
        RECORD_ADAPTER.validate_json(line)
        for name in RECORD_FILES
        if (case / f"records/{name}.jsonl").exists()
        for line in (case / f"records/{name}.jsonl").read_text("utf-8").splitlines()
    ]


@pytest.mark.parametrize("tag", sorted(WORLDS))
def test_reviewed_records_reproduce_the_world_reference_balances(tmp_path, tag):
    """Self-consistency only: the generator's arithmetic and C08 agree on clean worlds."""
    world = WORLDS[tag]
    reference = reference_balances(world)
    universe = universe_from_records(SNAPSHOT, _records(FIXTURES / f"case_{tag}"))
    buckets = [row["bucket_id"] for row in reference["buckets"]]
    result = reconcile_universe(
        CONTEXT,
        request(tuple(buckets)),
        universe,
        profile(deadlines_testable=True),
        BlobStore(tmp_path / "blobs"),
        allocation_order=reference["allocation_order"],
    )
    assert result.status in {"SUCCESS", "PARTIAL"}, result.issues
    for want in reference["buckets"]:
        out = bucket_result(result, want["bucket_id"])
        assert out.required.decimal == want["required"]
        assert out.supported.decimal == out.ledger_supported.decimal == want["supported"]
        assert out.signed_gap.decimal == want["signed_gap"]
        assert (out.shortfall.decimal, out.surplus.decimal) == (want["shortfall"], want["surplus"])
        assert out.pending.decimal == want["pending"]
        assert out.portal_reported.decimal == want["portal_reported"]
        assert out.delta.decimal == want["delta_portal_minus_supported"]
    pending = any(row["pending"] != "0.0000" for row in reference["buckets"])
    expected = "QUALIFIED" if pending else "COMPLETE_WITHIN_SCOPE"
    assert result.output.coverage == expected, result.issues


@pytest.mark.parametrize("tag", sorted(WORLDS))
def test_case_passes_real_intake_extraction_and_normalization(tmp_path, tag):
    case = FIXTURES / f"case_{tag}"
    foundation_request = FoundationRequest(
        case_root=str(case),
        r02_path=str(FIXTURES / "h04/acquired_originals/e-waste_rules_2022.pdf"),
        r08_path=str(FIXTURES / "h01/acquired_originals/cpcb_faq_20240123.pdf"),
        case_snapshot_id="snapshot:case_initial",
        corpus_snapshot_id="snapshot:corpus_initial",
        profile_version="s05-integration",
    )
    with local_application(Settings(data_root=tmp_path)) as (cases, context, cap):
        built = FoundationService(cases).build(context, foundation_request, capability=cap)
        assert built.status in {"SUCCESS", "PARTIAL"}, built.issues
        blocking = [i.code for i in built.issues if i.severity == "BLOCKING"]
        assert blocking == ["UNAPPROVED_PROFILE"]  # CP1 review gate only
        assert not {i.code for i in built.issues} & {
            "HASH_MISMATCH",
            "MISSING_ARTIFACT",
            "ACCESS_DENIED",
            "UNCONFIRMED_IDENTIFIER",
        }
        # Unmapped observation types (page text, provenance rows) quarantine as warnings.
        assert all(
            i.message.startswith("Normalization unresolved: No approved mapping")
            for i in built.issues
            if i.code == "INVALID_SCHEMA"
        )
        blobs = cases.kernel.blob_store
        snapshot = built.output.case_snapshot
        membership = json.loads(blobs.get(snapshot.membership_blob))

        receipts = membership["receipts"]
        assert receipts and all(r["intake_status"] == "RECEIVED" for r in receipts)
        assert all(r["reason"] is None for r in receipts)  # declared, digest-matched files

        observed = []
        for extraction in membership["extractions"]:
            body = blobs.get(BlobRef.model_validate(extraction["observations_blob"]))
            observed += [json.loads(line)["observation_id"] for line in body.splitlines() if line]
        dispositions = membership["normalization"]["dispositions"]
        assert sorted(d["observation_id"] for d in dispositions) == sorted(observed)
        assert {d["disposition"] for d in dispositions} <= {"ACCEPTED", "QUARANTINED"}

        normalized = {r["record_id"] for r in membership["normalization"]["records"]}
        assert {r.record_id for r in _records(case)} <= normalized

        # Supplied events/allocations are PENDING after normalization; C08 must not promote.
        universe = universe_from_membership(snapshot.snapshot_id, membership)
        reference = reference_balances(WORLDS[tag])
        buckets = tuple(row["bucket_id"] for row in reference["buckets"])
        result = reconcile_universe(
            CONTEXT,
            request(buckets, snapshot=snapshot.snapshot_id),
            universe,
            profile(),
            blobs,
        )
        for want in reference["buckets"]:
            out = bucket_result(result, want["bucket_id"])
            assert out.required.decimal == want["required"]
            assert out.supported.decimal == "0.0000"
        assert result.output.coverage == "QUALIFIED"
