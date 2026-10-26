"""Thin C08 `compute_reconciliation` service (S03).

Deliberately thin: it archives the three calculation blobs but writes no audit event and has
no dispatcher or CLI hook. Persisting the result as an audited operation is A05/V02 work.
"""

import hashlib
import json
from collections.abc import Mapping

from recycleguard.contracts.artifacts import SnapshotRef
from recycleguard.contracts.core import (
    CommandContext,
    ErrorCode,
    EvidenceRef,
    Issue,
    ServiceResult,
)
from recycleguard.contracts.profiles import CalculationProfile
from recycleguard.contracts.results import CalculationRequest, CalculationResult
from recycleguard.domain.reconcile import TOOL_VERSION, EngineRejected, compute
from recycleguard.domain.universe import (
    Universe,
    UniverseError,
    universe_from_membership,
)
from recycleguard.normalization.units import NumericSafetyError
from recycleguard.snapshots import SnapshotStore
from recycleguard.storage import BlobStore, canonical_json_bytes
from recycleguard.storage.blob_store import BlobIntegrityError
from recycleguard.storage.catalog import CatalogError


def _failure(context, status, code: ErrorCode, message, dependencies=None):
    token = hashlib.sha256(canonical_json_bytes([code, message])).hexdigest()[:12]
    return ServiceResult[CalculationResult](
        contract_version="1.1",
        operation_id=context.operation_id,
        attempt_id=context.attempt_id,
        status=status,
        output=None,
        output_blob=None,
        issues=[
            Issue(
                issue_id=f"issue:{code.lower()}_{token}",
                code=code,
                severity="BLOCKING",
                message=message,
                field_path=None,
                evidence_refs=[],
                retryable=False,
            )
        ],
        dependencies=dependencies or [],
        audit_event_ids=[],
    )


def reconcile_universe(
    context: CommandContext,
    request: CalculationRequest,
    universe: Universe,
    profile: CalculationProfile,
    blob_store: BlobStore,
    *,
    allocation_order: Mapping[str, int] | None = None,
) -> ServiceResult[CalculationResult]:
    """Run the engine on an already-built universe and archive its blobs."""
    snapshot_ref = EvidenceRef(
        ref_kind="ARTIFACT", ref_id=universe.snapshot_id, artifact_revision_id=None, locator=None
    )
    if request.case_version_id != universe.snapshot_id:
        return _failure(
            context,
            "REJECTED",
            "STALE_SNAPSHOT",
            "request pins a different case version",
            [snapshot_ref],
        )
    if request.profile_id != profile.profile_id:
        return _failure(
            context,
            "REJECTED",
            "UNSUPPORTED_PROFILE",
            "request profile does not match profile",
            [snapshot_ref],
        )
    expected = request.expected_input_membership_digest
    if expected is not None and expected != universe.digest:
        return _failure(
            context,
            "REJECTED",
            "STALE_SNAPSHOT",
            "expected input membership digest differs from the server-computed universe",
            [snapshot_ref],
        )
    try:
        output = compute(universe, profile, request.bucket_ids, allocation_order=allocation_order)
    except EngineRejected as exc:
        return _failure(context, "REJECTED", exc.code, str(exc), [snapshot_ref])
    except NumericSafetyError as exc:
        return _failure(context, "FAILED", "NUMERIC_PRECISION_EXCEEDED", str(exc), [snapshot_ref])

    def blob(payload: object):
        return blob_store.put(canonical_json_bytes(payload), "application/json")

    membership_blob = blob(
        {
            "snapshot_id": universe.snapshot_id,
            "membership_digest": universe.digest,
            "members": universe.members(),
        }
    )
    dispositions_blob = blob([d.model_dump(mode="json") for d in output.dispositions])
    derivation_blob = blob(output.derivation.model_dump(mode="json"))
    input_digest = hashlib.sha256(
        canonical_json_bytes(
            {
                "membership": universe.digest,
                "profile": profile.digest,
                "snapshot": universe.snapshot_id,
                "buckets": sorted(output.analyzed_bucket_ids),
                "tool": TOOL_VERSION,
            }
        )
    ).hexdigest()
    result = CalculationResult(
        calculation_id=f"calc:{input_digest[:24]}",
        case_version_id=universe.snapshot_id,
        profile_id=profile.profile_id,
        tool_version=TOOL_VERSION,
        input_digest=input_digest,
        analyzed_input_membership_blob=membership_blob,
        analyzed_bucket_ids=output.analyzed_bucket_ids,
        bucket_results=output.bucket_results,
        quantity_dispositions_blob=dispositions_blob,
        derivation_blob=derivation_blob,
        coverage=output.coverage,
        issues=output.issues,
    )
    clean = output.coverage == "COMPLETE_WITHIN_SCOPE" and not any(
        i.severity == "BLOCKING" for i in output.issues
    )
    issues = list(output.issues)
    if not clean and not issues:
        issues.append(
            Issue(
                issue_id="issue:qualified_result",
                code="INCOMPLETE_COVERAGE",
                severity="WARNING",
                message=f"Result coverage is {output.coverage}; see qualification references",
                field_path=None,
                evidence_refs=[],
                retryable=False,
            )
        )
    return ServiceResult[CalculationResult](
        contract_version="1.1",
        operation_id=context.operation_id,
        attempt_id=context.attempt_id,
        status="SUCCESS" if clean else "PARTIAL",
        output=result,
        output_blob=None,
        issues=issues,
        dependencies=[snapshot_ref],
        audit_event_ids=[],
    )


def compute_reconciliation(
    context: CommandContext,
    request: CalculationRequest,
    *,
    snapshots: SnapshotStore,
    snapshot_ref: SnapshotRef,
    profile: CalculationProfile,
    allocation_order: Mapping[str, int] | None = None,
) -> ServiceResult[CalculationResult]:
    """C08 entry point: the only record source is the pinned CASE snapshot."""
    try:
        snapshot = snapshots.get(snapshot_ref)
    except (CatalogError, KeyError, BlobIntegrityError, FileNotFoundError) as exc:
        code: ErrorCode = "STALE_SNAPSHOT" if "STALE_SNAPSHOT" in str(exc) else "MISSING_ARTIFACT"
        return _failure(context, "REJECTED", code, str(exc))
    if snapshot.snapshot_kind != "CASE":
        return _failure(
            context, "REJECTED", "INVALID_SCHEMA", "reconciliation needs a CASE snapshot"
        )
    blob_store = snapshots.kernel.blob_store
    try:
        membership = json.loads(blob_store.get(snapshot.membership_blob))
        universe = universe_from_membership(snapshot.snapshot_id, membership)
    except UniverseError as exc:
        return _failure(context, "REJECTED", exc.code, str(exc))
    except (BlobIntegrityError, FileNotFoundError, ValueError) as exc:
        return _failure(context, "FAILED", "INTEGRITY_FAILED", str(exc))
    pinned = membership.get("profile")
    if pinned is not None and (
        pinned.get("profile_id"),
        pinned.get("profile_version"),
        pinned.get("digest"),
    ) != (profile.profile_id, profile.profile_version, profile.digest):
        return _failure(
            context, "REJECTED", "STALE_REVIEW", "profile differs from the one the snapshot pins"
        )
    return reconcile_universe(
        context, request, universe, profile, blob_store, allocation_order=allocation_order
    )
