"""Human-reviewed, immutable support revisions for structured synthetic baseline evidence.

This narrow CP2 handler verifies exact original-record observations. It cannot turn a
payment, account total or transfer into an allocation. Other document formats need
reviewed capability mappings before they can establish support.
"""

import json

from recycleguard.contracts.artifacts import FrozenSnapshot
from recycleguard.contracts.audit import OperationIntent, OperationResult
from recycleguard.contracts.baseline import RecordSupportReview
from recycleguard.contracts.domain import RECORD_ADAPTER
from recycleguard.contracts.extraction import ExtractionResult, Observation
from recycleguard.contracts.snapshots import SnapshotReview
from recycleguard.foundation import FoundationService
from recycleguard.storage import canonical_json_bytes


class SupportReviewer:
    def __init__(self, cases, *, service_actor, service_capability):
        self.cases = cases
        self.foundation = FoundationService(cases)
        self.kernel = cases.kernel
        self.service_actor = service_actor
        self.service_capability = service_capability

    def approve(self, context, request: RecordSupportReview, *, capability):
        self.kernel.authority.check(capability, context.actor, "review.record_support")
        blobs = self.kernel.blob_store
        intent = OperationIntent(
            context=context,
            idempotency_key=context.idempotency_key,
            event_type="review.record_support",
            stream_id=f"stream:{context.correlation_id}",
            payload=blobs.put(request.model_dump_json().encode(), "application/json"),
        )
        self.kernel.commit_intent(intent, capability=capability)
        previous = self.kernel.get_result(context.operation_id)
        if previous is not None:
            if previous.status != "SUCCESS":
                raise ValueError(json.loads(blobs.get(previous.payload))["message"])
            return FrozenSnapshot.model_validate_json(blobs.get(previous.payload))
        try:
            output = self._approve(context, request, capability)
        except (ValueError, KeyError) as exc:
            self.kernel.commit_result(
                intent,
                OperationResult(
                    operation_id=context.operation_id,
                    attempt_id=context.attempt_id,
                    status="REJECTED",
                    issue_codes=["INVALID_SCHEMA"],
                    payload=blobs.put(
                        canonical_json_bytes({"message": str(exc)}), "application/json"
                    ),
                ),
                capability=capability,
            )
            raise
        self.kernel.commit_result(
            intent,
            OperationResult(
                operation_id=context.operation_id,
                attempt_id=context.attempt_id,
                status="SUCCESS",
                payload=blobs.put(output.model_dump_json().encode(), "application/json"),
            ),
            capability=capability,
        )
        return output

    def _approve(self, context, request, capability):
        snapshot = self.cases.snapshots.get(request.target)
        if snapshot.snapshot_kind != "CASE" or snapshot.review_state != "APPROVED":
            raise ValueError("support review requires an approved CASE snapshot")
        fs = self.foundation
        case = json.loads(fs.blobs.get(snapshot.membership_blob))
        scope = case["manifest"]["case_id"]
        root = context.model_copy(update={"actor": self.service_actor})
        publish_context = fs._context(root, "snapshot.case")
        if self.kernel.get_result(publish_context.operation_id) is None:
            if self.cases.snapshots.head(scope) != snapshot:
                raise ValueError("STALE_REVIEW: case head changed")
        originals = {r["artifact_revision_id"]: r for r in case["originals"]}
        observations = {}
        for raw in case["extractions"]:
            extraction = ExtractionResult.model_validate_json(canonical_json_bytes(raw))
            for line in fs.blobs.get(extraction.observations_blob).splitlines():
                if not line.strip():
                    continue
                obs = Observation.model_validate_json(line)
                observations[obs.observation_id] = obs
        records = case["normalization"]["records"]
        targets = {r["record_revision_id"]: r for r in records}
        superseded = {r["supersedes_revision_id"] for r in records}
        if len({a.target_record_revision_id for a in request.assertions}) != len(
            request.assertions
        ):
            raise ValueError("duplicate support assertion")
        additions = []
        suffix = context.operation_id.split(":", 1)[1]
        for index, assertion in enumerate(request.assertions):
            if assertion.target_record_revision_id in superseded:
                raise ValueError("STALE_REVIEW: target record is superseded")
            record = targets[assertion.target_record_revision_id]
            if record["record_type"] not in {"Allocation", "CertificateEvent", "Certificate"}:
                raise ValueError("unsupported record support type")
            for ref in assertion.evidence_refs:
                if ref.ref_kind != "OBSERVATION" or ref.ref_id not in observations:
                    raise ValueError("support requires an exact extracted observation")
                obs = observations[ref.ref_id]
                original = originals[obs.artifact_revision_id]
                fs.blobs.get(
                    self.cases.snapshots.catalog.get_artifact_revision(
                        obs.artifact_revision_id
                    ).blob
                )
                if (
                    ref.artifact_revision_id != obs.artifact_revision_id
                    or ref.locator != obs.locator
                ):
                    raise ValueError("support evidence locator/revision mismatch")
                # CP2 proves structured synthetic evidence only. An invoice or a
                # summary balance cannot claim this capability by supplying JSON.
                fields = obs.parsed_fields
                if not original["synthetic"] or original["doc_type"] != "OTHER":
                    raise ValueError("source requires a reviewed document capability mapping")
                if fields.get("record_type") != record["record_type"]:
                    raise ValueError("evidence establishes a different fact or record type")
                original_record = RECORD_ADAPTER.validate_json(canonical_json_bytes(fields))
                common = {
                    "observation_refs",
                    "derived_from_record_refs",
                    "supporting_observations",
                    "validation_state",
                    "created_by_operation_id",
                    "record_revision_id",
                    "supersedes_revision_id",
                    "assertion_state",
                    "state",
                }
                supplied = original_record.model_dump(mode="json", exclude=common)
                # Normalization may enrich optional fields with null/defaults.
                expected = RECORD_ADAPTER.validate_json(canonical_json_bytes(record)).model_dump(
                    mode="json", exclude=common
                )
                if supplied != expected or obs.observation_id not in record["observation_refs"]:
                    raise ValueError("source payload does not establish the exact target record")
                if record["record_type"] == "Allocation" and fields.get("state") != "SUPPORTED":
                    raise ValueError("source does not assert a supported allocation")
                if record["record_type"] == "CertificateEvent" and (
                    fields.get("assertion_state") != "SUPPORTED"
                    or fields.get("transfer_stage") != "COMPLETED"
                ):
                    raise ValueError("source does not establish a completed supported event")
            data = record | {
                "record_revision_id": f"rev:support_{suffix}_{index}",
                "supersedes_revision_id": record["record_revision_id"],
                "created_by_operation_id": context.operation_id,
                "validation_state": "VALID",
            }
            if record["record_type"] == "Allocation":
                data["state"] = "SUPPORTED"
                data["basis_refs"] = [
                    ref.model_dump(mode="json") for ref in assertion.evidence_refs
                ]
            elif record["record_type"] == "CertificateEvent":
                data["assertion_state"] = "SUPPORTED"
            additions.append(
                RECORD_ADAPTER.validate_json(canonical_json_bytes(data)).model_dump(mode="json")
            )
        records.extend(additions)
        case.setdefault("support_assertions", []).append(
            {
                "request": request.model_dump(mode="json"),
                "actor": context.actor.model_dump(mode="json"),
                "operation_id": context.operation_id,
                "scope": "Reviewed structured synthetic evidence; eligibility remains separate",
            }
        )
        draft = fs._publish(
            root,
            request.reviewed_snapshot_id,
            "CASE",
            scope,
            snapshot.snapshot_id,
            case,
            json.loads(fs.blobs.get(snapshot.coverage_blob)),
            [fs.catalog.get_receipt(i) for i in snapshot.source_receipt_ids],
            self.service_capability,
        )
        result = self.cases.review_snapshot(
            fs._context(context, "review.case_support"),
            SnapshotReview(
                scope_id=scope,
                target_snapshot_id=draft.snapshot_id,
                target_membership_digest=draft.membership_digest,
                expected_head=draft.snapshot_id,
                new_snapshot_id=request.approved_snapshot_id,
                decision="APPROVE",
                reason=request.reason,
            ),
            capability=capability,
        )
        if result.status != "SUCCESS":
            raise ValueError(f"support snapshot review failed: {result.issues}")
        return result.output
