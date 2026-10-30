"""S07 pilot dossiers through C08 and real intake.

The 24 development dossiers are committed fixtures. The 24 held-out dossiers live outside
version control; their C08 check runs only where they have been regenerated, and is skipped
otherwise (their bytes are still verified against the committed seal by the unit tests).
"""

import json
from pathlib import Path

import pytest

from benchmarks.generator.generate import HELDOUT_ROOT
from benchmarks.generator.hidden import reference_balances
from benchmarks.generator.pilot_cases import DEV, HELD_OUT, build_pilot_cases
from recycleguard.application import local_application
from recycleguard.config import Settings
from recycleguard.contracts.domain import RECORD_ADAPTER
from recycleguard.contracts.foundation import FoundationRequest
from recycleguard.domain import reconcile_universe, universe_from_membership, universe_from_records
from recycleguard.foundation import FoundationService
from recycleguard.storage import BlobStore
from tests.support.c08 import CONTEXT, SNAPSHOT, bucket_result, profile, request

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures/visible"
CASES = {f"{c.split}:{c.spec.name}": c for c in build_pilot_cases()}
DEV_KEYS = sorted(k for k, c in CASES.items() if c.split == DEV)
HELD_KEYS = sorted(k for k, c in CASES.items() if c.split == HELD_OUT)
RECORD_FILES = (
    "entities",
    "registrations",
    "obligations",
    "certificates",
    "certificate_events",
    "allocations",
    "commercial_records",
    "account_balances",
    "product_mappings",
    "sales",
)
# Codes raised outside C08 reconciliation: the extractor and the weight-basis check tool.
NOT_C08 = {"INCOMPLETE_COVERAGE", "WEIGHT_BASIS_CONFLICT"}


def _dir(case) -> Path:
    root = FIXTURES if case.split == DEV else HELDOUT_ROOT
    return root / f"case_{case.world.case_tag}"


def records(case):
    d = _dir(case)
    return [
        RECORD_ADAPTER.validate_json(line)
        for name in RECORD_FILES
        if (d / f"records/{name}.jsonl").exists()
        for line in (d / f"records/{name}.jsonl").read_text("utf-8").splitlines()
    ]


def _reconciles(tmp_path, case):
    reference = reference_balances(case.world)
    buckets = tuple(row["bucket_id"] for row in reference["buckets"])
    result = reconcile_universe(
        CONTEXT,
        request(buckets),
        universe_from_records(SNAPSHOT, records(case)),
        profile(deadlines_testable=True),
        BlobStore(tmp_path / "blobs"),
    )
    assert result.status in {"SUCCESS", "PARTIAL"}, result.issues
    for want in reference["buckets"]:
        out = bucket_result(result, want["bucket_id"])
        assert out.required.decimal == want["required"]
        assert out.supported.decimal == want["supported"]
        assert out.signed_gap.decimal == want["signed_gap"]
        assert out.pending.decimal == want["pending"]
        assert out.portal_reported.decimal == want["portal_reported"]
        assert out.delta.decimal == want["delta_portal_minus_supported"]
    raised = {i.code for i in result.issues}
    declared = {code for ch in case.corrupted.changes for code in ch.issue_codes} - NOT_C08
    assert declared <= raised, declared - raised


@pytest.mark.parametrize("key", DEV_KEYS)
def test_c08_reproduces_the_reference_on_development_dossiers(tmp_path, key):
    _reconciles(tmp_path, CASES[key])


@pytest.mark.skipif(
    not HELDOUT_ROOT.is_dir(), reason="held-out dossiers are regenerated locally, not committed"
)
@pytest.mark.parametrize("key", HELD_KEYS)
def test_c08_reproduces_the_reference_on_held_out_dossiers(tmp_path, key):
    case = CASES[key]
    if not _dir(case).is_dir():
        pytest.skip("held-out root present but this dossier was not regenerated")
    _reconciles(tmp_path, case)


@pytest.mark.parametrize("key", DEV_KEYS)
def test_development_dossier_passes_real_intake(tmp_path, key):
    case = CASES[key]
    d = _dir(case)
    foundation_request = FoundationRequest(
        case_root=str(d),
        r02_path=str(FIXTURES / "h04/acquired_originals/e-waste_rules_2022.pdf"),
        r08_path=str(FIXTURES / "h01/acquired_originals/cpcb_faq_20240123.pdf"),
        case_snapshot_id="snapshot:case_initial",
        corpus_snapshot_id="snapshot:corpus_initial",
        profile_version="s07-integration",
    )
    with local_application(Settings(data_root=tmp_path)) as (cases, context, cap):
        built = FoundationService(cases).build(context, foundation_request, capability=cap)
        assert built.status in {"SUCCESS", "PARTIAL"}, built.issues
        assert [i.code for i in built.issues if i.severity == "BLOCKING"] == ["UNAPPROVED_PROFILE"]
        codes = {i.code for i in built.issues}
        assert not codes & {
            "HASH_MISMATCH",
            "MISSING_ARTIFACT",
            "ACCESS_DENIED",
            "UNCONFIRMED_IDENTIFIER",
        }
        lost = [c for c in case.corrupted.changes if c.family == "F15_EXTRACTION_PAGE_LOSS"]
        coverage = [i for i in built.issues if i.code == "INCOMPLETE_COVERAGE"]
        assert len(coverage) == len(lost)
        blobs = cases.kernel.blob_store
        snapshot = built.output.case_snapshot
        membership = json.loads(blobs.get(snapshot.membership_blob))
        assert all(r["intake_status"] == "RECEIVED" for r in membership["receipts"])
        normalized = {r["record_id"] for r in membership["normalization"]["records"]}
        assert {r.record_id for r in records(case)} <= normalized
        universe = universe_from_membership(snapshot.snapshot_id, membership)
        reference = reference_balances(case.world)
        buckets = tuple(row["bucket_id"] for row in reference["buckets"])
        result = reconcile_universe(
            CONTEXT, request(buckets, snapshot=snapshot.snapshot_id), universe, profile(), blobs
        )
        for want in reference["buckets"]:
            assert bucket_result(result, want["bucket_id"]).required.decimal == want["required"]
        assert result.output.coverage == "QUALIFIED"
