"""Independent V09 validation and sealing for evaluator-only oracle records."""

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from decimal import Decimal, InvalidOperation, localcontext
from pathlib import Path
from typing import Literal

from pydantic import Field

from benchmarks.evaluation.oracle import OracleCase
from recycleguard.contracts.core import ID, BoundaryModel, Digest, Nonempty, Timestamp


class OracleValidation(BoundaryModel):
    case_id: ID
    valid: bool
    numeric_errors: list[Nonempty] = Field(default_factory=list)
    rubric_errors: list[Nonempty] = Field(default_factory=list)


class OracleSeal(BoundaryModel):
    dataset_version: Nonempty
    rubric_version: Nonempty
    oracle_digests: dict[ID, Digest]
    aggregate_digest: Digest
    reviewed_case_ids: list[ID]
    visible_reference_status: Literal["HAND_REVIEWED", "UNVERIFIED_WORLD_PROJECTION"]


class VisibleReferenceReview(BoundaryModel):
    """Trusted evaluator review evidence bound to exact supplied visible answers.

    This is an attestation record, not an authentication mechanism. The caller
    must retain its referenced originals/calculations outside investigator roots.
    """

    reviewer_ref: ID
    oracle_digest: Digest
    visible_input_digest: Digest
    evidence_refs: list[Nonempty] = Field(min_length=1)
    reference_calculation_refs: list[Nonempty] = Field(min_length=1)
    recorded_at: Timestamp


class HeldOutAccessRecord(BoundaryModel):
    access_id: ID
    dataset_version: Nonempty
    run_id: ID
    case_ids: list[ID] = Field(min_length=1)
    visible_input_digests: dict[ID, Digest]
    oracle_digests: dict[ID, Digest]
    purpose: Nonempty
    recorded_at: Timestamp
    run_closed: bool
    oracle_loaded_after_close: bool


def _decimal(value, field: str, errors: list[str]) -> Decimal | None:
    if type(value) is not str or not re.fullmatch(r"-?(0|[1-9][0-9]{0,17})(\.[0-9]{1,8})?", value):
        errors.append(f"{field}: expected canonical decimal string")
        return None
    try:
        result = Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        errors.append(f"{field}: invalid decimal")
        return None
    if not result.is_finite():
        errors.append(f"{field}: non-finite decimal")
        return None
    return result


def _check_balance(balance: Mapping, errors: list[str], prefix: str) -> None:
    required = _decimal(balance.get("required"), f"{prefix}.required", errors)
    supported = _decimal(balance.get("supported"), f"{prefix}.supported", errors)
    signed_gap = _decimal(balance.get("signed_gap"), f"{prefix}.signed_gap", errors)
    shortfall = _decimal(balance.get("shortfall"), f"{prefix}.shortfall", errors)
    surplus = _decimal(balance.get("surplus"), f"{prefix}.surplus", errors)
    pending = _decimal(balance.get("pending"), f"{prefix}.pending", errors)
    portal = _decimal(balance.get("portal_reported"), f"{prefix}.portal_reported", errors)
    delta = _decimal(balance.get("delta"), f"{prefix}.delta", errors)
    values = (required, supported, signed_gap, shortfall, surplus, pending, portal, delta)
    if any(value is None for value in values):
        return
    if signed_gap != required - supported:
        errors.append(f"{prefix}: signed_gap mismatch")
    if shortfall != max(signed_gap, Decimal(0)):
        errors.append(f"{prefix}: shortfall mismatch")
    if surplus != max(-signed_gap, Decimal(0)):
        errors.append(f"{prefix}: surplus mismatch")
    if delta != portal - supported:
        errors.append(f"{prefix}: portal delta mismatch")
    for field, value in (
        ("required", required),
        ("supported", supported),
        ("shortfall", shortfall),
        ("surplus", surplus),
        ("pending", pending),
        ("portal_reported", portal),
    ):
        if value < 0:
            errors.append(f"{prefix}: negative {field}")


def validate_oracle(oracle: OracleCase) -> OracleValidation:
    numeric_errors: list[str] = []
    rubric_errors: list[str] = []
    groups = (
        ("world", oracle.expected_world_balances),
        ("projection", oracle.world_projection_balances),
        ("visible", oracle.visible_evidence_balances),
    )
    if not oracle.expected_world_balances:
        rubric_errors.append("world: missing balances")
    for group, balances in groups:
        for index, balance in enumerate(balances):
            with localcontext() as context:
                context.prec = 60
                _check_balance(balance, numeric_errors, f"{group}[{index}]")
            identifier = balance.get("bucket_id")
            if type(identifier) is not str or not re.fullmatch(r"bucket:[^\s]+", identifier):
                rubric_errors.append(f"{group}[{index}]: invalid bucket_id")
            if balance.get("metal") not in {"AU", "CU", "AL", "FE"}:
                rubric_errors.append(f"{group}[{index}]: invalid metal")
            year = balance.get("liability_year")
            if type(year) is not str or not re.fullmatch(r"[0-9]{4}-[0-9]{4}", year):
                rubric_errors.append(f"{group}[{index}]: invalid liability year")
            elif int(year[5:]) != int(year[:4]) + 1:
                rubric_errors.append(f"{group}[{index}]: invalid liability year interval")
            if balance.get("unit") != "KG":
                rubric_errors.append(f"{group}[{index}]: invalid unit")
        ids = [balance.get("bucket_id") for balance in balances]
        if len(ids) != len(set(ids)):
            rubric_errors.append(f"{group}: duplicate bucket_id")
    world = {balance.get("bucket_id"): balance for balance in oracle.expected_world_balances}
    for group, balances in groups[1:]:
        if balances and {balance.get("bucket_id") for balance in balances} != set(world):
            rubric_errors.append(f"{group}: incomplete or unexpected bucket coverage")
        for balance in balances:
            expected = world.get(balance.get("bucket_id"))
            if expected and any(
                balance.get(field) != expected.get(field)
                for field in ("metal", "liability_year", "unit")
            ):
                rubric_errors.append(f"{group}: bucket dimension mismatch")
    if not oracle.review_rubric_version:
        rubric_errors.append("missing review rubric version")
    if not oracle.reference_calculation_refs:
        rubric_errors.append("missing independent calculation reference")
    if oracle.visible_reference_status == "HAND_REVIEWED" and not oracle.visible_evidence_balances:
        rubric_errors.append("hand-reviewed oracle has no visible balances")
    return OracleValidation(
        case_id=oracle.case_id,
        valid=not numeric_errors and not rubric_errors,
        numeric_errors=numeric_errors,
        rubric_errors=rubric_errors,
    )


def validate_oracle_against_world(world, oracle: OracleCase) -> OracleValidation:
    result = validate_oracle(oracle)
    if world.case_id != oracle.case_id:
        return result.model_copy(
            update={
                "valid": False,
                "rubric_errors": [*result.rubric_errors, "world: case identity mismatch"],
            }
        )
    numeric_errors = list(result.numeric_errors)
    expected = []
    transfers = {item.key: item for item in world.transfers}
    for bucket in sorted(world.buckets, key=lambda item: item.bucket_id):
        required = Decimal(bucket.target_kg)
        supported = sum(
            (Decimal(item.quantity_kg) for item in world.allocations if item.bucket == bucket.key),
            Decimal(0),
        )
        pending = sum(
            (
                Decimal(item.quantity_kg)
                for item in world.invoices
                if item.bucket == bucket.key and transfers[item.transfer].stage != "COMPLETED"
            ),
            Decimal(0),
        )
        portal = next(
            Decimal(item.reported_kg) for item in world.balances if item.bucket == bucket.key
        )
        expected.append(
            {
                "bucket_id": bucket.bucket_id,
                "required": required,
                "supported": supported,
                "signed_gap": required - supported,
                "shortfall": max(required - supported, Decimal(0)),
                "surplus": max(supported - required, Decimal(0)),
                "pending": pending,
                "portal_reported": portal,
                "delta": portal - supported,
            }
        )
    actual = {item["bucket_id"]: item for item in oracle.expected_world_balances}
    if set(actual) != {item["bucket_id"] for item in expected}:
        numeric_errors.append("world: bucket set mismatch")
    for item in expected:
        got = actual.get(item["bucket_id"])
        if got is None:
            continue
        bucket = next(bucket for bucket in world.buckets if bucket.bucket_id == item["bucket_id"])
        if got.get("metal") != bucket.metal or got.get("liability_year") != bucket.liability_year:
            numeric_errors.append(f"world.{item['bucket_id']}: dimension mismatch")
        for field, value in item.items():
            if field == "bucket_id":
                continue
            if (
                _decimal(got.get(field), f"world.{item['bucket_id']}.{field}", numeric_errors)
                != value
            ):
                numeric_errors.append(f"world.{item['bucket_id']}: {field} mismatch")
    return result.model_copy(
        update={
            "valid": not numeric_errors and not result.rubric_errors,
            "numeric_errors": numeric_errors,
        }
    )


def oracle_digest(oracle: OracleCase) -> str:
    """Digest the same canonical evaluator artifact written by the oracle builder."""
    return hashlib.sha256(
        (
            json.dumps(oracle.model_dump(mode="json"), indent=2, sort_keys=True, ensure_ascii=True)
            + "\n"
        ).encode()
    ).hexdigest()


def seal_oracles(
    records: Mapping[str, OracleCase],
    *,
    dataset_version: str,
    reviewed_case_ids: Iterable[str] = (),
    review_records: Mapping[str, VisibleReferenceReview] | None = None,
) -> OracleSeal:
    if not records:
        raise ValueError("cannot seal an empty oracle set")
    reviewed = sorted(set(reviewed_case_ids))
    expected = set(records)
    if any(case_id != record.case_id for case_id, record in records.items()):
        raise ValueError("oracle mapping key does not match case identity")
    if len({record.review_rubric_version for record in records.values()}) != 1:
        raise ValueError("oracle seal requires one rubric version")
    reviews = review_records or {}
    if set(reviews) != set(reviewed):
        raise ValueError("reviewed cases require exact independent review records")
    for case_id in reviewed:
        if case_id not in records:
            raise ValueError("reviewed case is absent from oracle records")
        record = records[case_id]
        review = reviews[case_id]
        if record.visible_reference_status != "HAND_REVIEWED":
            raise ValueError("unverified world projection cannot be promoted by a seal")
        if review.oracle_digest != oracle_digest(record):
            raise ValueError("independent review does not bind this oracle digest")
        if set(review.reference_calculation_refs) != set(record.reference_calculation_refs):
            raise ValueError("independent review calculation references do not match")
    if set(reviewed) - expected:
        raise ValueError("reviewed case is absent from oracle records")
    validations = [validate_oracle(record) for record in records.values()]
    invalid = [item for item in validations if not item.valid]
    if invalid:
        raise ValueError("oracle validation failed: " + ", ".join(item.case_id for item in invalid))
    digests = {case_id: oracle_digest(records[case_id]) for case_id in sorted(records)}
    aggregate = hashlib.sha256(
        "\n".join(f"{case_id}\t{digests[case_id]}" for case_id in sorted(digests)).encode()
    ).hexdigest()
    return OracleSeal(
        dataset_version=dataset_version,
        rubric_version=next(iter(records.values())).review_rubric_version,
        oracle_digests=digests,
        aggregate_digest=aggregate,
        reviewed_case_ids=reviewed,
        visible_reference_status=(
            "HAND_REVIEWED" if set(reviewed) == expected else "UNVERIFIED_WORLD_PROJECTION"
        ),
    )


def record_heldout_access(path: Path, record: HeldOutAccessRecord, seal: OracleSeal) -> None:
    # These flags record evaluator assertions, not proof of process isolation.
    if len(record.case_ids) != len(set(record.case_ids)):
        raise ValueError("held-out access contains duplicate cases")
    if set(record.visible_input_digests) != set(record.case_ids):
        raise ValueError("held-out access requires exact visible input digest coverage")
    if not record.run_closed or not record.oracle_loaded_after_close:
        raise ValueError("held-out oracle access requires a closed run")
    if record.dataset_version != seal.dataset_version:
        raise ValueError("held-out access dataset does not match the seal")
    if set(record.case_ids) - set(seal.oracle_digests):
        raise ValueError("held-out access contains an unsealed case")
    if record.oracle_digests != {
        case_id: seal.oracle_digests[case_id] for case_id in record.case_ids
    }:
        raise ValueError("held-out access oracle digests do not match the seal")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(record.model_dump_json() + "\n")


def load_oracle_records(root: Path, case_ids: Iterable[str]) -> dict[str, OracleCase]:
    records = {}
    for case_id in case_ids:
        path = root / f"{case_id.split(':', 1)[-1]}.json"
        records[case_id] = OracleCase.model_validate_json(path.read_bytes())
    return records
