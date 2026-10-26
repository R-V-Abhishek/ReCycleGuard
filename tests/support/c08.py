"""Test-only builders for C08 universes. Never imported by runtime code."""

from types import SimpleNamespace

from recycleguard.contracts.core import CommandContext, Quantity, TemporalValue
from recycleguard.contracts.domain import (
    AccountBalanceObservation,
    Allocation,
    Certificate,
    CertificateEvent,
    CommercialRecord,
    NonnegativeMass,
    ObligationBucket,
    SignedAdjustment,
)
from recycleguard.contracts.profiles import CalculationProfile, profile_digest
from recycleguard.contracts.results import CalculationRequest
from recycleguard.domain import reconcile_universe, universe_from_records
from recycleguard.knowledge.profile_v1 import build_v1_profile_definition
from recycleguard.storage import BlobStore

CASE = "case:t"
SNAPSHOT = "snapshot:t"
PRODUCER = "entity:prod"
RECYCLER = "entity:rec"
PROFILE = "profile:producer_snapshot_v1"
CONTEXT = CommandContext(
    contract_version="1.1",
    command_id="command:t",
    operation_id="operation:t",
    attempt_id="attempt:t",
    idempotency_key="t",
    actor={"actor_id": "service:t", "actor_kind": "SERVICE", "authenticated_session_ref": None},
    case_version_id=None,
    run_id=None,
    turn_id=None,
    correlation_id="correlation:t",
    parent_operation_id=None,
)


def qty(value: str, metal: str = "CU", unit: str = "KG") -> NonnegativeMass:
    return NonnegativeMass(decimal=value, unit=unit, dimension="METAL_MASS", metal=metal)


def signed_qty(value: str, metal: str = "CU") -> Quantity:
    return Quantity(decimal=value, unit="KG", dimension="METAL_MASS", metal=metal)


def instant(value: str) -> TemporalValue:
    return TemporalValue(
        raw=value,
        value=value,
        precision="INSTANT",
        timezone="UTC",
        interpretation_status="REVIEWED",
    )


def _common(key: str, state: str = "VALID", revision: str | None = None, supersedes=None) -> dict:
    return {
        "case_id": CASE,
        "record_id": key,
        "record_revision_id": revision or "rev:" + key.replace(":", "_"),
        "observation_refs": [f"obs:{key.split(':', 1)[1]}"],
        "derived_from_record_refs": [],
        "validation_state": state,
        "created_by_operation_id": "op:t",
        "supersedes_revision_id": supersedes,
    }


def bucket(
    key="bucket:a", year="2024-2025", target="100.0000", metal="CU", adjustments=(), unit="KG", **kw
):
    return ObligationBucket(
        **_common(key, **{k: v for k, v in kw.items() if k in {"state", "revision"}}),
        record_type="ObligationBucket",
        bucket_id=key,
        producer_entity_id=kw.get("producer", PRODUCER),
        liability_year=year,
        component="STANDARD",
        metal=metal,
        target=qty(target, metal, unit),
        basis="SUPPLIED_ACCOUNT",
        basis_refs=[],
        profile_id=kw.get("profile", PROFILE),
        adjustments=[
            SignedAdjustment(
                adjustment_id=f"adj:{i}", quantity=a, basis_refs=[], review_ref="review:t"
            )
            for i, a in enumerate(adjustments)
        ],
    )


def certificate(key="cert:1", face="55.0000", metal="CU", state="VALID"):
    return Certificate(
        **_common(key, state),
        record_type="Certificate",
        certificate_id=key,
        external_certificate_ref=f"ext/{key}",
        issuer_entity_id=RECYCLER,
        metal=metal,
        face_quantity=qty(face, metal),
        identity_evidence=[],
    )


def event(
    key="evt:1",
    cert="cert:1",
    lot="lot:1",
    quantity="55.0000",
    state="SUPPORTED",
    to=PRODUCER,
    stage="COMPLETED",
    kind="TRANSFERRED",
    when="2024-09-15T11:30:00Z",
    validation="VALID",
):
    return CertificateEvent(
        **_common(key, validation),
        record_type="CertificateEvent",
        event_id=key,
        certificate_id=cert,
        credit_lot_id=lot,
        event_kind=kind,
        event_time=instant(when),
        quantity=qty(quantity),
        assertion_state=state,
        supporting_observations=[f"obs:{key.split(':', 1)[1]}"],
        from_entity_id=RECYCLER,
        to_entity_id=to,
        transfer_stage=stage,
    )


def allocation(
    key="alloc:1",
    bucket_id="bucket:a",
    lot="lot:1",
    evt="evt:1",
    quantity="55.0000",
    state="SUPPORTED",
    revision=None,
    supersedes_revision=None,
    supersedes_allocation=None,
    profile=PROFILE,
    metal="CU",
    validation="VALID",
):
    return Allocation(
        **_common(key, validation, revision, supersedes_revision),
        record_type="Allocation",
        allocation_id=key,
        credit_lot_id=lot,
        event_id=evt,
        bucket_id=bucket_id,
        quantity=qty(quantity, metal),
        basis_refs=[],
        state=state,
        profile_id=profile,
        supersedes_allocation_id=supersedes_allocation,
    )


def balance(
    key="bal:1",
    bucket_id="bucket:a",
    reported="55.0000",
    capture="2024-10-15T09:00:00Z",
    cutoff="2024-09-30T23:59:59Z",
):
    return AccountBalanceObservation(
        **_common(key),
        record_type="AccountBalanceObservation",
        balance_observation_id=key,
        producer_entity_id=PRODUCER,
        bucket_id=bucket_id,
        reported_supported=qty(reported),
        source_capture_time=instant(capture),
        business_cutoff=instant(cutoff),
        basis_refs=[],
    )


def commercial(key="comm:1", quantity="25.0000", kind="INVOICE", linked=()):
    return CommercialRecord(
        **_common(key),
        record_type="CommercialRecord",
        commercial_id=key,
        record_kind=kind,
        issuer_entity_id=RECYCLER,
        recipient_entity_id=PRODUCER,
        external_ref=f"ext/{key}",
        event_time=instant("2024-10-10T14:15:00Z"),
        linked_credit_refs=list(linked),
        money=Quantity(decimal="12500.0000", unit="INR", dimension="MONEY", metal=None),
        credit_quantity=qty(quantity),
    )


def clean_case():
    """One bucket (100), one supported 55 kg transfer fully allocated, matching portal view."""
    return [bucket(), certificate(), event(), allocation(), balance()]


def profile(*, state="APPROVED", deadlines_testable=False) -> CalculationProfile:
    stub = lambda name: SimpleNamespace(  # noqa: E731
        artifact_revision_id=f"art:{name}", blob=SimpleNamespace(sha256="a" * 64)
    )
    payload = build_v1_profile_definition(stub("r02"), stub("r08")).model_dump(mode="json")
    if deadlines_testable:
        for rule in payload["eligibility_rules"]:
            rule["testability"] = "TESTABLE"
    payload.update(
        profile_id=PROFILE,
        profile_version="t",
        review_state=state,
        review_refs=[] if state == "DRAFT" else ["review:t"],
    )
    payload["digest"] = profile_digest(payload)
    return CalculationProfile.model_validate(payload)


def request(buckets=("bucket:a",), digest=None, snapshot=SNAPSHOT) -> CalculationRequest:
    return CalculationRequest(
        case_version_id=snapshot,
        profile_id=PROFILE,
        bucket_ids=list(buckets),
        expected_input_membership_digest=digest,
    )


def run(tmp_path, records, buckets=("bucket:a",), *, order=None, digest=None, prof=None):
    universe = universe_from_records(SNAPSHOT, records)
    return reconcile_universe(
        CONTEXT,
        request(buckets, digest),
        universe,
        prof or profile(deadlines_testable=True),
        BlobStore(tmp_path / "blobs"),
        allocation_order=order,
    )


def bucket_result(result, bucket_id="bucket:a"):
    return next(b for b in result.output.bucket_results if b.bucket_id == bucket_id)
