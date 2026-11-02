"""S04 dossiers through C08: lifecycle, commercial, capability, product and priority effects.

The expected quantities and verdicts come from the generator's own arithmetic
(``hidden.allocation_outcomes``), which does not call C08; this checks the two agree on the
reviewed records, with no explicit allocation order supplied.
"""

import json
from pathlib import Path

import pytest

from benchmarks.generator.hidden import reference_balances
from benchmarks.generator.s04_cases import build_s04_worlds
from benchmarks.generator.s05_cases import build_worlds
from recycleguard.application import local_application
from recycleguard.config import Settings
from recycleguard.contracts.domain import RECORD_ADAPTER
from recycleguard.contracts.foundation import FoundationRequest
from recycleguard.domain import reconcile_universe, universe_from_membership, universe_from_records
from recycleguard.foundation import FoundationService
from recycleguard.storage import BlobStore
from tests.support.c08 import CONTEXT, SNAPSHOT, bucket_result, check, profile, request

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures/visible"
S04 = {w.template_key: w for w in build_s04_worlds()}
S05 = build_worlds()
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
# Template -> (allocation rule that excludes, issue code, coverage after the run).
EXCLUSIONS = {
    "expired_credit": ("lifecycle", "CREDIT_EXPIRED"),
    "cancelled_credit": ("lifecycle", "CREDIT_CANCELLED"),
    "capability_mismatch": ("capability", "CAPABILITY_MISMATCH"),
}


def records(world):
    case = FIXTURES / f"case_{world.case_tag}"
    return [
        RECORD_ADAPTER.validate_json(line)
        for name in RECORD_FILES
        if (case / f"records/{name}.jsonl").exists()
        for line in (case / f"records/{name}.jsonl").read_text("utf-8").splitlines()
    ]


def reconcile(tmp_path, world):
    universe = universe_from_records(SNAPSHOT, records(world))
    reference = reference_balances(world)
    buckets = tuple(row["bucket_id"] for row in reference["buckets"])
    result = reconcile_universe(
        CONTEXT,
        request(buckets),
        universe,
        profile(deadlines_testable=True),
        BlobStore(tmp_path / "blobs"),
    )
    return result, reference


@pytest.mark.parametrize("template", sorted(S04))
def test_c08_reproduces_the_independent_reference(tmp_path, template):
    world = S04[template]
    result, reference = reconcile(tmp_path, world)
    assert result.status in {"SUCCESS", "PARTIAL"}, result.issues
    for want in reference["buckets"]:
        out = bucket_result(result, want["bucket_id"])
        assert out.required.decimal == want["required"]
        assert out.supported.decimal == want["supported"]
        assert out.ledger_supported.decimal == want["supported"]
        assert out.signed_gap.decimal == want["signed_gap"]
        assert out.pending.decimal == want["pending"]
        assert out.portal_reported.decimal == want["portal_reported"]
        assert out.delta.decimal == want["delta_portal_minus_supported"]


@pytest.mark.parametrize("template", sorted(EXCLUSIONS))
def test_excluded_allocations_carry_their_reason_and_qualify_the_result(tmp_path, template):
    rule, code = EXCLUSIONS[template]
    world = S04[template]
    result, reference = reconcile(tmp_path, world)
    expected = {k for k, row in reference["allocation_checks"].items() if row[rule] == "FAIL"}
    assert len(expected) == 1  # each dossier plants exactly one such allocation
    assert code in {i.code for i in result.issues}
    assert all(
        row["code"] == code for k, row in reference["allocation_checks"].items() if k in expected
    )
    assert result.output.coverage == "QUALIFIED"
    shortfall = [
        row for row in reference["buckets"] if row["delta_portal_minus_supported"] != "0.0000"
    ]
    assert shortfall  # the portal still reports the credit C08 refuses to support


def test_payments_are_not_a_second_quantity(tmp_path):
    world = S04["linked_invoice_payment"]
    result, reference = reconcile(tmp_path, world)
    (row,) = reference["buckets"]
    initiated = next(t for t in world.transfers if t.stage == "INITIATED")
    assert row["pending"] == initiated.quantity_kg  # once, not once per invoice and payment
    assert bucket_result(result, row["bucket_id"]).pending.decimal == initiated.quantity_kg
    assert len(world.payments) == 2
    matched = check(tmp_path, records(world), "MATCH_TRANSACTIONS", []).output.results
    assert {t.verdict for t in matched} == {"PASS"}
    assert len(matched) == len(world.invoices) + len(world.payments)


def test_weight_basis_conflict_is_flagged_and_never_averaged(tmp_path):
    world = S04["weight_basis_conflict"]
    reference = reference_balances(world)
    universe_records = records(world)
    producer = next(r.entity_id for r in universe_records if r.record_type == "ProductMapping")
    for sku, want in reference["product_checks"]["weight_basis"].items():
        result = check(tmp_path / sku, universe_records, "COMPARE_WEIGHT_BASIS", [producer, sku])
        (target,) = result.output.results
        assert target.verdict == want
        if want == "FAIL":
            assert target.values["code"] == "WEIGHT_BASIS_CONFLICT"
    sales = check(
        tmp_path / "sales", universe_records, "AGGREGATE_SALES", [producer], period="2024-2025"
    )
    assert sales.output.results[0].verdict == reference["product_checks"]["sales"]


def test_allocation_dates_establish_the_earlier_liability_without_an_order(tmp_path):
    world = S04["earlier_liability_dated"]
    result, reference = reconcile(tmp_path, world)
    states = {row["priority"] for row in reference["allocation_checks"].values()}
    assert states == {"NOT_EVALUATED", "PASS"}
    blob = BlobStore(tmp_path / "blobs").get(result.output.derivation_blob)
    checks = json.loads(blob)["priority_checks"]
    assert {c["state"] for c in checks} <= {"PASS", "NOT_EVALUATED"}
    assert "LIABILITY_PRIORITY_UNRESOLVED" not in {i.code for i in result.issues}


def test_without_allocation_dates_the_same_shape_is_unresolved(tmp_path):
    shared = next(w for w in S05 if w.template_key == "historical_shared_lot")
    universe = universe_from_records(SNAPSHOT, records(shared))
    buckets = tuple(b.bucket_id for b in shared.buckets)
    result = reconcile_universe(
        CONTEXT, request(buckets), universe, profile(), BlobStore(tmp_path / "blobs")
    )
    blob = BlobStore(tmp_path / "blobs").get(result.output.derivation_blob)
    assert "UNKNOWN" in {c["state"] for c in json.loads(blob)["priority_checks"]}
    assert result.output.coverage == "QUALIFIED"


@pytest.mark.parametrize("template", sorted(S04))
def test_dossier_passes_real_intake_and_c08_does_not_promote(tmp_path, template):
    """Product, sales, payment and lifecycle files go through the same CP1 pipeline."""
    world = S04[template]
    case = FIXTURES / f"case_{world.case_tag}"
    foundation_request = FoundationRequest(
        case_root=str(case),
        r02_path=str(FIXTURES / "h04/acquired_originals/e-waste_rules_2022.pdf"),
        r08_path=str(FIXTURES / "h01/acquired_originals/cpcb_faq_20240123.pdf"),
        case_snapshot_id="snapshot:case_initial",
        corpus_snapshot_id="snapshot:corpus_initial",
        profile_version="s04-integration",
    )
    with local_application(Settings(data_root=tmp_path)) as (cases, context, cap):
        built = FoundationService(cases).build(context, foundation_request, capability=cap)
        assert built.status in {"SUCCESS", "PARTIAL"}, built.issues
        assert [i.code for i in built.issues if i.severity == "BLOCKING"] == ["UNAPPROVED_PROFILE"]
        assert not {i.code for i in built.issues} & {
            "HASH_MISMATCH",
            "MISSING_ARTIFACT",
            "ACCESS_DENIED",
            "UNCONFIRMED_IDENTIFIER",
        }
        blobs = cases.kernel.blob_store
        snapshot = built.output.case_snapshot
        membership = json.loads(blobs.get(snapshot.membership_blob))
        assert all(r["intake_status"] == "RECEIVED" for r in membership["receipts"])
        normalized = {r["record_id"] for r in membership["normalization"]["records"]}
        assert {r.record_id for r in records(world)} <= normalized
        universe = universe_from_membership(snapshot.snapshot_id, membership)
        reference = reference_balances(world)
        buckets = tuple(row["bucket_id"] for row in reference["buckets"])
        result = reconcile_universe(
            CONTEXT, request(buckets, snapshot=snapshot.snapshot_id), universe, profile(), blobs
        )
        for want in reference["buckets"]:
            out = bucket_result(result, want["bucket_id"])
            assert out.required.decimal == want["required"]
            assert out.supported.decimal == "0.0000"  # supplied allocations stay unpromoted
        assert result.output.coverage == "QUALIFIED"


def test_clean_s05_dossiers_are_unchanged_by_the_s04_tools(tmp_path):
    for world in S05:
        reference = reference_balances(world)
        assert all(
            row["lifecycle"] in {"PASS"} and row["capability"] == "NOT_EVALUATED"
            for row in reference["allocation_checks"].values()
        )
        universe = universe_from_records(SNAPSHOT, records(world))
        buckets = tuple(row["bucket_id"] for row in reference["buckets"])
        result = reconcile_universe(
            CONTEXT,
            request(buckets),
            universe,
            profile(deadlines_testable=True),
            BlobStore(tmp_path / world.case_tag),
            allocation_order=reference["allocation_order"],
        )
        for want in reference["buckets"]:
            assert bucket_result(result, want["bucket_id"]).supported.decimal == want["supported"]
