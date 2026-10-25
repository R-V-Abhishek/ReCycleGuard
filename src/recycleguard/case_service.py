"""C05 structured boundary over immutable stores; capabilities come from composition."""

import hashlib
import json
import sqlite3
from typing import Literal

from pydantic import ValidationError

from recycleguard.contracts.artifacts import FrozenSnapshot
from recycleguard.contracts.audit import OperationResult
from recycleguard.contracts.core import EvidenceRef, Issue, ServiceResult
from recycleguard.contracts.profiles import CalculationProfile
from recycleguard.profiles import ProfileError, ProfileStore
from recycleguard.snapshots import SnapshotStore
from recycleguard.storage import canonical_json_bytes
from recycleguard.storage.authority import AuthorizationError
from recycleguard.storage.blob_store import BlobIntegrityError
from recycleguard.storage.catalog import CatalogError


class CaseService:
    def __init__(self, snapshots: SnapshotStore, profiles: ProfileStore):
        if snapshots.kernel is not profiles.kernel:
            raise ValueError("C05 stores must share one coordinator")
        self.snapshots, self.profiles, self.kernel = snapshots, profiles, snapshots.kernel

    def _call(self, context, request, capability, event_type, model, action):
        output, code, message = None, None, None
        try:
            self.kernel.authority.check(capability, context.actor, event_type)
        except AuthorizationError as exc:
            return self._envelope(context, model, code="ACCESS_DENIED", message=str(exc))
        try:
            output = action()
        except ProfileError as exc:
            code, message = exc.code, str(exc)
        except (FileNotFoundError, KeyError) as exc:
            code, message = "MISSING_ARTIFACT", str(exc)
        except BlobIntegrityError as exc:
            code, message = "HASH_MISMATCH", str(exc)
        except (CatalogError, ValidationError, ValueError) as exc:
            code = (
                "CONCURRENT_MODIFICATION"
                if "CONCURRENT_MODIFICATION" in str(exc)
                else "INVALID_SCHEMA"
            )
            message = str(exc)
        except (sqlite3.Error, OSError) as exc:
            return self._envelope(
                context, model, code="AUDIT_UNAVAILABLE", message=str(exc), status="OUTCOME_UNKNOWN"
            )
        try:
            intent = self.kernel.get_intent(context.operation_id)
            if intent is None:
                return self._envelope(
                    context,
                    model,
                    code=code or "AUDIT_UNAVAILABLE",
                    message=message or "intent could not be committed",
                    status="REJECTED" if code else "OUTCOME_UNKNOWN",
                )
            request_digest = hashlib.sha256(
                canonical_json_bytes(request.model_dump(mode="json"))
            ).hexdigest()
            bound = (
                intent is not None
                and intent.context == context
                and intent.payload.sha256 == request_digest
                and intent.event_type == event_type
            )
            # A conflicting caller must not receive another operation's archived output.
            if not bound:
                return self._envelope(
                    context,
                    model,
                    code="CONCURRENT_MODIFICATION",
                    message=message or "operation is bound to another request",
                )
            result = self.kernel.get_result(context.operation_id)
            if result is None and code is not None:
                payload = self.kernel.blob_store.put(
                    canonical_json_bytes({"message": message}), "application/json"
                )
                result = OperationResult(
                    operation_id=context.operation_id,
                    attempt_id=context.attempt_id,
                    status="REJECTED",
                    payload=payload,
                    issue_codes=[code],
                )
                self.kernel.commit_result(intent, result, capability=capability)
            events = [
                e.event_id
                for e in self.kernel.list_stream_events(intent.stream_id)
                if e.operation_id == context.operation_id and e.attempt_id == context.attempt_id
            ]
            if result is None:
                return self._envelope(
                    context,
                    model,
                    code="AUDIT_UNAVAILABLE",
                    message="operation has no durable outcome",
                    status="OUTCOME_UNKNOWN",
                )
            if result.status != "SUCCESS":
                archived_message = (
                    json.loads(self.kernel.blob_store.get(result.payload))["message"]
                    if result.payload is not None
                    else "operation rejected"
                )
                return self._envelope(
                    context,
                    model,
                    code=result.issue_codes[0],
                    message=archived_message,
                    status=result.status,
                    blob=result.payload,
                    events=events,
                )
            if output is None:
                return self._envelope(
                    context,
                    model,
                    code="CONCURRENT_MODIFICATION",
                    message=message or "conflicting replay",
                )
            return self._envelope(context, model, output=output, blob=result.payload, events=events)
        except BlobIntegrityError as exc:
            return self._envelope(context, model, code="HASH_MISMATCH", message=str(exc))
        except (sqlite3.Error, OSError) as exc:
            return self._envelope(
                context, model, code="AUDIT_UNAVAILABLE", message=str(exc), status="OUTCOME_UNKNOWN"
            )

    @staticmethod
    def _envelope(
        context, model, *, output=None, code=None, message=None, status=None, blob=None, events=None
    ):
        return ServiceResult[model](
            contract_version="1.1",
            operation_id=context.operation_id,
            attempt_id=context.attempt_id,
            status=status or ("SUCCESS" if code is None else "REJECTED"),
            output=output,
            output_blob=blob,
            issues=[]
            if code is None
            else [
                Issue(
                    issue_id=f"issue:{context.attempt_id.split(':', 1)[1]}",
                    code=code,
                    severity="BLOCKING",
                    message=message,
                    field_path=None,
                    evidence_refs=[],
                    retryable=False,
                )
            ],
            dependencies=[]
            if model is FrozenSnapshot or output is None
            else [
                EvidenceRef(
                    ref_kind="ARTIFACT",
                    ref_id=dep.artifact_revision_id,
                    artifact_revision_id=dep.artifact_revision_id,
                    locator=None,
                )
                for dep in output.source_dependencies
            ],
            audit_event_ids=events or [],
        )

    def publish_snapshot(self, context, request, *, capability):
        return self._call(
            context,
            request,
            capability,
            "snapshot.publish",
            FrozenSnapshot,
            lambda: self.snapshots.publish(context, request, capability=capability),
        )

    def publish_case(self, context, request, *, capability):
        return self._publish_kind(context, request, capability, "CASE")

    def publish_corpus(self, context, request, *, capability):
        return self._publish_kind(context, request, capability, "CORPUS")

    def _publish_kind(self, context, request, capability, kind: Literal["CASE", "CORPUS"]):
        if request.snapshot_kind != kind:
            return self._envelope(
                context,
                FrozenSnapshot,
                code="INVALID_SCHEMA",
                message=f"publication requires {kind} membership",
            )
        return self.publish_snapshot(context, request, capability=capability)

    def reopen_case(self, context, request, *, capability):
        # H03/A04 provide the revised complete manifest; publication pins its exact bytes.
        if request.expected_head is None:
            return self._envelope(
                context,
                FrozenSnapshot,
                code="STALE_SNAPSHOT",
                message="reopening requires the exact parent snapshot",
            )
        return self.publish_case(context, request, capability=capability)

    def review_snapshot(self, context, request, *, capability):
        return self._call(
            context,
            request,
            capability,
            "review.snapshot",
            FrozenSnapshot,
            lambda: self.snapshots.review(context, request, capability=capability),
        )

    def publish_profile(self, context, request, *, capability):
        return self._call(
            context,
            request,
            capability,
            "profile.publish",
            CalculationProfile,
            lambda: self.profiles.publish(context, request, capability=capability),
        )

    def review_profile(self, context, request, *, capability):
        return self._call(
            context,
            request,
            capability,
            "review.profile",
            CalculationProfile,
            lambda: self.profiles.review(context, request, capability=capability),
        )
