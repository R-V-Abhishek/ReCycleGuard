"""C08 allowlisted structured checks (S04): identity/capability, product/sales, trace, commercial.

Every check runs over the complete pinned-snapshot universe; request subjects only select which
results are returned. Verdicts are PASS, FAIL or UNKNOWN with supporting record references.
"""

import hashlib
import json
import re
from collections.abc import Callable

from recycleguard.contracts.artifacts import SnapshotRef
from recycleguard.contracts.checks import CheckRequest, CheckTarget, StructuredCheckResult
from recycleguard.contracts.core import (
    CommandContext,
    ErrorCode,
    EvidenceRef,
    Issue,
    ServiceResult,
)
from recycleguard.contracts.domain import CertificateEvent, ObligationBucket, Registration
from recycleguard.contracts.profiles import CalculationProfile
from recycleguard.domain.chronology import Span, span
from recycleguard.domain.commercial import match_commercial
from recycleguard.domain.identity import capability_finding, identity_finding, registration_finding
from recycleguard.domain.lifecycle import credit_event_findings, history_finding
from recycleguard.domain.products import (
    fiscal_year_span,
    mapping_finding,
    sales_finding,
    weight_basis_finding,
)
from recycleguard.domain.reconcile import TOOL_VERSION
from recycleguard.domain.refs import Finding, make_issue
from recycleguard.domain.universe import Universe, UniverseError, universe_from_membership
from recycleguard.snapshots import SnapshotStore
from recycleguard.storage import BlobStore, canonical_json_bytes
from recycleguard.storage.blob_store import BlobIntegrityError
from recycleguard.storage.catalog import CatalogError

_ID = re.compile(r"^[a-z][a-z0-9_]*:[^\s]+$")


class CheckRejected(ValueError):
    def __init__(self, code: ErrorCode, message: str):
        super().__init__(message)
        self.code = code


def _arity(request: CheckRequest, count: int, label: str) -> list[str]:
    if len(request.subjects) != count:
        raise CheckRejected("INVALID_SCHEMA", f"{request.check_kind} needs subjects: {label}")
    return request.subjects


def _reference_span(universe: Universe, request: CheckRequest) -> Span | None:
    if request.reference_event_id is None:
        return None
    for event in universe.active(CertificateEvent):
        if event.event_id == request.reference_event_id:
            return span(event.event_time)
    raise CheckRejected("MISSING_ARTIFACT", "reference_event_id is not in the pinned snapshot")


def _identity(universe, request, buckets):
    left, right = _arity(request, 2, "[left entity, right entity]")
    return [identity_finding(universe, left, right, _reference_span(universe, request))]


def _registration(universe, request, buckets):
    (entity,) = _arity(request, 1, "[entity]")
    when = _reference_span(universe, request)
    found = [
        registration_finding(r, when)
        for r in sorted(universe.active(Registration), key=lambda r: r.record_id)
        if r.entity_id == entity
    ]
    return found or [Finding((entity,), "UNKNOWN", "MISSING_ARTIFACT", "No registration evidence")]


def _capability(universe, request, buckets):
    recycler, producer = _arity(request, 2, "[recycler entity, producer entity]")
    return [capability_finding(universe, recycler, producer, _reference_span(universe, request))]


def _mapping(universe, request, buckets):
    entity, sku = _arity(request, 2, "[entity, sku]")
    when = fiscal_year_span(request.period) if request.period else None
    return [mapping_finding(universe, entity, sku, when)]


def _weight(universe, request, buckets):
    entity, sku = _arity(request, 2, "[entity, sku]")
    return [weight_basis_finding(universe, entity, sku)]


def _sales(universe, request, buckets):
    (entity,) = _arity(request, 1, "[entity]")
    if not request.period:
        raise CheckRejected("INVALID_SCHEMA", "AGGREGATE_SALES needs a fiscal-year period")
    return [sales_finding(universe, entity, request.period)]


def _history(universe, request, buckets):
    if not request.subjects:
        raise CheckRejected("INVALID_SCHEMA", "GET_CERTIFICATE_HISTORY needs at least one subject")
    return [history_finding(universe, subject) for subject in request.subjects]


def _credit_events(universe, request, buckets):
    if not request.subjects:
        raise CheckRejected("INVALID_SCHEMA", "CHECK_CREDIT_EVENTS needs at least one subject")
    return [f for subject in request.subjects for f in credit_event_findings(universe, subject)]


def _transactions(universe, request, buckets):
    outcomes = match_commercial(universe, buckets)
    wanted = set(request.subjects) or set(outcomes)
    missing = sorted(wanted - set(outcomes))
    found = [outcomes[key].finding() for key in sorted(wanted & set(outcomes))]
    found += [
        Finding((key,), "UNKNOWN", "MISSING_ARTIFACT", "Not a commercial record") for key in missing
    ]
    return found


_KINDS: dict[str, Callable] = {
    "COMPARE_IDENTITY": _identity,
    "LOOKUP_REGISTRATION_EVIDENCE": _registration,
    "CHECK_CAPABILITY": _capability,
    "LOOKUP_PRODUCT_MAPPING": _mapping,
    "COMPARE_WEIGHT_BASIS": _weight,
    "AGGREGATE_SALES": _sales,
    "GET_CERTIFICATE_HISTORY": _history,
    "CHECK_CREDIT_EVENTS": _credit_events,
    "MATCH_TRANSACTIONS": _transactions,
}


def _evidence(ref: str) -> EvidenceRef:
    return EvidenceRef(ref_kind="RECORD", ref_id=ref, artifact_revision_id=None, locator=None)


def _target(finding: Finding) -> CheckTarget:
    ids = [t for t in finding.targets if _ID.match(t)]
    values = dict(finding.values)
    plain = [t for t in finding.targets if not _ID.match(t)]
    if plain:
        values["subject"] = "|".join(plain)
    if finding.code is not None:
        values["code"] = finding.code
    if not ids:
        ids = [finding.refs[0]] if finding.refs else ["subject:unresolved"]
    return CheckTarget(
        target_refs=ids,
        verdict=finding.state if finding.state != "NOT_EVALUATED" else "UNKNOWN",
        reasons=[finding.reason] if finding.state != "PASS" or finding.reason else [],
        evidence=[_evidence(r) for r in finding.refs if _ID.match(r)],
        values=values,
    )


def _failure(context, status, code: ErrorCode, message: str):
    return ServiceResult[StructuredCheckResult](
        contract_version="1.1",
        operation_id=context.operation_id,
        attempt_id=context.attempt_id,
        status=status,
        output=None,
        output_blob=None,
        issues=[make_issue(code, "BLOCKING", message)],
        dependencies=[],
        audit_event_ids=[],
    )


def run_check_on_universe(
    context: CommandContext,
    request: CheckRequest,
    universe: Universe,
    blob_store: BlobStore,
    profile: CalculationProfile | None = None,
) -> ServiceResult[StructuredCheckResult]:
    if request.case_version_id != universe.snapshot_id:
        return _failure(
            context, "REJECTED", "STALE_SNAPSHOT", "request pins a different case version"
        )
    expected = request.expected_input_membership_digest
    if expected is not None and expected != universe.digest:
        return _failure(
            context, "REJECTED", "STALE_SNAPSHOT", "expected membership digest differs from server"
        )
    if profile is not None and request.profile_id not in {None, profile.profile_id}:
        return _failure(context, "REJECTED", "UNSUPPORTED_PROFILE", "request profile differs")
    buckets = {
        b.bucket_id: b
        for b in universe.active(ObligationBucket)
        if profile is None
        or (b.profile_id == profile.profile_id and b.metal in profile.allowed_metals)
    }
    try:
        findings = _KINDS[request.check_kind](universe, request, buckets)
    except CheckRejected as exc:
        return _failure(context, "REJECTED", exc.code, str(exc))
    targets = [_target(f) for f in findings]
    membership_blob = blob_store.put(
        canonical_json_bytes(
            {
                "snapshot_id": universe.snapshot_id,
                "membership_digest": universe.digest,
                "members": universe.members(),
            }
        ),
        "application/json",
    )
    token = hashlib.sha256(
        canonical_json_bytes(
            [universe.digest, TOOL_VERSION, request.model_dump(mode="json", exclude_none=True)]
        )
    ).hexdigest()
    issues: list[Issue] = []
    for finding in findings:
        if finding.state == "PASS":
            continue
        issues.append(
            make_issue(
                finding.code or "INCOMPLETE_COVERAGE",
                "WARNING",
                f"{request.check_kind} {'/'.join(finding.targets)}: "
                f"{finding.state}: {finding.reason}",
                [_evidence(r) for r in finding.refs if _ID.match(r)],
            )
        )
    result = StructuredCheckResult(
        check_id=f"check:{token[:24]}",
        check_kind=request.check_kind,
        input_membership_blob=membership_blob,
        results=targets,
        tool_version=TOOL_VERSION,
        issues=issues,
    )
    unresolved = any(t.verdict == "UNKNOWN" for t in targets)
    return ServiceResult[StructuredCheckResult](
        contract_version="1.1",
        operation_id=context.operation_id,
        attempt_id=context.attempt_id,
        status="PARTIAL" if unresolved else "SUCCESS",
        output=result,
        output_blob=None,
        issues=issues if unresolved else [i for i in issues if i.severity != "BLOCKING"],
        dependencies=[
            EvidenceRef(
                ref_kind="ARTIFACT",
                ref_id=universe.snapshot_id,
                artifact_revision_id=None,
                locator=None,
            )
        ],
        audit_event_ids=[],
    )


def run_check(
    context: CommandContext,
    request: CheckRequest,
    *,
    snapshots: SnapshotStore,
    snapshot_ref: SnapshotRef,
    profile: CalculationProfile | None = None,
) -> ServiceResult[StructuredCheckResult]:
    """C08 entry point: the only record source is the pinned CASE snapshot."""
    try:
        snapshot = snapshots.get(snapshot_ref)
    except (CatalogError, KeyError, BlobIntegrityError, FileNotFoundError) as exc:
        return _failure(context, "REJECTED", "MISSING_ARTIFACT", str(exc))
    if snapshot.snapshot_kind != "CASE":
        return _failure(context, "REJECTED", "INVALID_SCHEMA", "checks need a CASE snapshot")
    blob_store = snapshots.kernel.blob_store
    try:
        membership = json.loads(blob_store.get(snapshot.membership_blob))
        universe = universe_from_membership(snapshot.snapshot_id, membership)
    except UniverseError as exc:
        return _failure(context, "REJECTED", exc.code, str(exc))
    except (BlobIntegrityError, FileNotFoundError, ValueError) as exc:
        return _failure(context, "FAILED", "INTEGRITY_FAILED", str(exc))
    return run_check_on_universe(context, request, universe, blob_store, profile)
