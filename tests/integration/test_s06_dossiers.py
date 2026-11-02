"""S06 fault dossiers through real intake and C08.

C08 must reproduce the generator's independent reference on what the visible evidence shows,
raise the issue codes each corruption declares, and leave text-only faults (injection, period,
notice, page loss) without any quantity effect. Intake must quarantine the textless page and
parse every Indian-grouped or tonne figure exactly.
"""

import json
from pathlib import Path

import pytest

from benchmarks.generator.hidden import reference_balances
from benchmarks.generator.s06_cases import build_s06_cases
from recycleguard.application import local_application
from recycleguard.config import Settings
from recycleguard.contracts.domain import RECORD_ADAPTER
from recycleguard.contracts.foundation import FoundationRequest
from recycleguard.domain import reconcile_universe, universe_from_membership, universe_from_records
from recycleguard.foundation import FoundationService
from recycleguard.storage import BlobStore
from tests.support.c08 import CONTEXT, SNAPSHOT, bucket_result, check, profile, request

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures/visible"
CASES = {c.world.template_key: c for c in build_s06_cases()}
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
    return FIXTURES / f"case_{case.world.case_tag}"


def records(case):
    d = _dir(case)
    return [
        RECORD_ADAPTER.validate_json(line)
        for name in RECORD_FILES
        if (d / f"records/{name}.jsonl").exists()
        for line in (d / f"records/{name}.jsonl").read_text("utf-8").splitlines()
    ]


def reconcile(tmp_path, case):
    reference = reference_balances(case.world)
    buckets = tuple(row["bucket_id"] for row in reference["buckets"])
    result = reconcile_universe(
        CONTEXT,
        request(buckets),
        universe_from_records(SNAPSHOT, records(case)),
        profile(deadlines_testable=True),
        BlobStore(tmp_path / "blobs"),
    )
    return result, reference


@pytest.mark.parametrize("key", sorted(CASES))
def test_c08_reproduces_the_reference_and_raises_the_declared_codes(tmp_path, key):
    case = CASES[key]
    result, reference = reconcile(tmp_path, case)
    assert result.status in {"SUCCESS", "PARTIAL"}, result.issues
    for want in reference["buckets"]:
        out = bucket_result(result, want["bucket_id"])
        assert out.required.decimal == want["required"]
        assert out.supported.decimal == out.ledger_supported.decimal == want["supported"]
        assert out.signed_gap.decimal == want["signed_gap"]
        assert out.pending.decimal == want["pending"]
        assert out.portal_reported.decimal == want["portal_reported"]
        assert out.delta.decimal == want["delta_portal_minus_supported"]
    raised = {i.code for i in result.issues}
    declared = {code for change in case.changes for code in change.issue_codes} - NOT_C08
    assert declared <= raised, (key, declared - raised)


@pytest.mark.parametrize(
    "key", sorted(k for k, c in CASES.items() if "F16_PROMPT_INJECTION" in c.families)
)
def test_injected_text_changes_no_quantity(tmp_path, key):
    case = CASES[key]
    result, _ = reconcile(tmp_path, case)
    for want in reference_balances(case.clean)["buckets"]:
        out = bucket_result(result, want["bucket_id"])
        assert (out.supported.decimal, out.pending.decimal) == (want["supported"], want["pending"])


def test_weight_basis_conflict_is_flagged_by_the_check_tool(tmp_path):
    case = CASES["weights"]
    reference = reference_balances(case.world)
    universe_records = records(case)
    producer = next(r.entity_id for r in universe_records if r.record_type == "ProductMapping")
    verdicts = {}
    for sku, want in reference["product_checks"]["weight_basis"].items():
        result = check(tmp_path / sku, universe_records, "COMPARE_WEIGHT_BASIS", [producer, sku])
        (target,) = result.output.results
        assert target.verdict == want
        verdicts[sku] = (target.verdict, target.values.get("code"))
    assert ("FAIL", "WEIGHT_BASIS_CONFLICT") in verdicts.values()


@pytest.mark.parametrize("key", sorted(CASES))
def test_dossier_passes_real_intake(tmp_path, key):
    case = CASES[key]
    d = _dir(case)
    foundation_request = FoundationRequest(
        case_root=str(d),
        r02_path=str(FIXTURES / "h04/acquired_originals/e-waste_rules_2022.pdf"),
        r08_path=str(FIXTURES / "h01/acquired_originals/cpcb_faq_20240123.pdf"),
        case_snapshot_id="snapshot:case_initial",
        corpus_snapshot_id="snapshot:corpus_initial",
        profile_version="s06-integration",
    )
    with local_application(Settings(data_root=tmp_path)) as (cases, context, cap):
        built = FoundationService(cases).build(context, foundation_request, capability=cap)
        assert built.status in {"SUCCESS", "PARTIAL"}, built.issues
        assert [i.code for i in built.issues if i.severity == "BLOCKING"] == ["UNAPPROVED_PROFILE"]
        codes = {i.code for i in built.issues}
        # Indian-grouped and tonne figures parse exactly; nothing is left unresolved.
        assert not codes & {
            "HASH_MISMATCH",
            "MISSING_ARTIFACT",
            "ACCESS_DENIED",
            "UNCONFIRMED_IDENTIFIER",
        }
        textless = [c for c in case.changes if "no text layer" in c.transformation]
        coverage = [i for i in built.issues if i.code == "INCOMPLETE_COVERAGE"]
        truncated = [c for c in case.changes if c.family == "F15_EXTRACTION_PAGE_LOSS"]
        if textless or truncated:
            # One page lost either way: no text layer, or absent against its footer count.
            assert len(coverage) == 1 and coverage[0].field_path.startswith("page:")
        else:
            assert not coverage
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
            out = bucket_result(result, want["bucket_id"])
            assert out.required.decimal == want["required"]
            assert out.supported.decimal == "0.0000"  # supplied allocations stay unpromoted
        assert result.output.coverage == "QUALIFIED"
