"""C13 Authenticated human review service and transition manager.

Implements SYSTEM_DESIGN §7.2 run state machine review transitions,
spoof rejection, stale packet protection, and filing acknowledgments.
"""

import hashlib
from datetime import UTC, datetime

from recycleguard.contracts.artifacts import SnapshotRef
from recycleguard.contracts.audit import OperationIntent, OperationResult
from recycleguard.contracts.core import (
    CommandContext,
    EvidenceRef,
    Issue,
    ServiceResult,
)
from recycleguard.contracts.review import (
    AcknowledgmentRecord,
    AcknowledgmentValidationState,
    ReviewDecision,
    ReviewPacket,
    ReviewRecord,
    ReviewTransitionResult,
)
from recycleguard.reporting.baseline import BaselineReport, ReportRevision
from recycleguard.storage import canonical_json_bytes
from recycleguard.storage.authority import AuthorizationError, Capability


class ReviewService:
    def __init__(self, cases=None, *, kernel=None, blob_store=None):
        self.cases = cases
        self.kernel = kernel or (cases.kernel if cases is not None else None)
        self.blobs = blob_store or (self.kernel.blob_store if self.kernel is not None else None)
        self._packets: dict[str, ReviewPacket] = {}
        self._decided_packets: set[str] = set()

    def create_review_packet(
        self,
        report: BaselineReport | ReportRevision,
        *,
        input_snapshots: list[SnapshotRef] | None = None,
        proposed_action_refs: list[str] | None = None,
        unresolved_issue_refs: list[str] | None = None,
    ) -> ReviewPacket:
        """Create a version-bound review packet for an authenticated reviewer."""
        if isinstance(report, BaselineReport):
            revision_id = report.revision.report_revision_id
            dep_digest = report.revision.review_dependency_digest
            if proposed_action_refs is None:
                proposed_action_refs = []
                for s in report.sections:
                    if s.section_id == "NEXT_ACTIONS":
                        proposed_action_refs.extend(s.claim_ids)
        else:
            revision_id = report.report_revision_id
            dep_digest = report.review_dependency_digest
            if proposed_action_refs is None:
                proposed_action_refs = []

        now_iso = datetime.now(UTC).isoformat()
        packet_id_seed = f"{revision_id}:{dep_digest}:{now_iso}"
        packet_hash = hashlib.sha256(packet_id_seed.encode("utf-8")).hexdigest()[:24]
        packet_id = f"packet:{packet_hash}"

        packet = ReviewPacket(
            packet_id=packet_id,
            report_revision_id=revision_id,
            review_dependency_digest=dep_digest,
            input_snapshot_refs=input_snapshots or [],
            proposed_action_refs=proposed_action_refs,
            unresolved_issue_refs=unresolved_issue_refs or [],
            permitted_decisions=["APPROVE", "REJECT", "REQUEST_CHANGES", "ESCALATE"],
            created_at=now_iso,
        )

        self._packets[packet.packet_id] = packet
        if self.blobs is not None:
            self.blobs.put(canonical_json_bytes(packet.model_dump(mode="json")), "application/json")
        return packet

    def get_packet(self, packet_id: str) -> ReviewPacket | None:
        return self._packets.get(packet_id)

    def submit_review(
        self,
        context: CommandContext,
        packet_id: str,
        expected_dependency_digest: str,
        decision: ReviewDecision,
        *,
        capability: Capability,
        current_run_status: str = "AWAITING_REVIEW",
    ) -> ServiceResult[ReviewTransitionResult]:
        """Submit an authenticated review decision and compute run state transition."""
        # 1. Authority check: only authenticated human sessions can review reports
        if self.kernel is not None:
            self.kernel.authority.check(capability, context.actor, "review.report")

        # 2. Strict spoof rejection: reviewer ref must match authenticated context actor
        if context.actor.actor_kind != "HUMAN":
            raise AuthorizationError("review requires a HUMAN actor")
        if context.actor.authenticated_session_ref is None:
            raise AuthorizationError("human principal requires a trusted authenticated session")
        if decision.authenticated_reviewer_ref.actor_id != context.actor.actor_id:
            raise AuthorizationError("spoofed reviewer identity rejected: actor ID mismatch")

        # 3. Packet existence and stale packet checks
        packet = self._packets.get(packet_id)
        if packet is None:
            return self._make_failure(
                context, "MISSING_ARTIFACT", f"Review packet '{packet_id}' not found"
            )

        if packet_id in self._decided_packets:
            raise ValueError(
                "STALE_REVIEW: packet has already been decided; "
                "corrections require a new authorized review packet"
            )

        if packet.review_dependency_digest != expected_dependency_digest:
            raise ValueError(
                f"STALE_REVIEW: dependency digest mismatch "
                f"(expected {expected_dependency_digest}, got {packet.review_dependency_digest})"
            )

        # 4. Terminal run check: terminal runs cannot resume silently
        if current_run_status in {"COMPLETED", "BLOCKED_OUTPUT", "FAILED", "CANCELLED"}:
            raise ValueError(
                f"terminal runs do not resume silently: corrections create a new authorized "
                f"RunSpec with parent_run_id (status: {current_run_status})"
            )
        if current_run_status != "AWAITING_REVIEW":
            raise ValueError(
                f"review decision requires run status AWAITING_REVIEW, got {current_run_status}"
            )

        # 5. Project review state transition per SYSTEM_DESIGN §7.2 / CONTRACTS §6.1
        if decision.decision == "APPROVE":
            new_run_status = "COMPLETED"
            new_review_outcome = "APPROVED"
            stop_reason = "RESOLVED_WITHIN_SCOPE"
        elif decision.decision == "REJECT":
            new_run_status = "BLOCKED_OUTPUT"
            new_review_outcome = "REJECTED"
            stop_reason = "REVIEW_REJECTED"
        elif decision.decision == "REQUEST_CHANGES":
            new_run_status = "BLOCKED_OUTPUT"
            new_review_outcome = "CHANGES_REQUESTED"
            stop_reason = "CHANGES_REQUESTED"
        elif decision.decision == "ESCALATE":
            new_run_status = "AWAITING_REVIEW"
            new_review_outcome = "ESCALATED"
            stop_reason = "EXPERT_REVIEW_REQUIRED"
        else:
            raise ValueError(f"unsupported review decision: {decision.decision}")

        # 6. Build immutable ReviewRecord
        review_seed = (
            f"{packet_id}:{decision.recorded_at}:{decision.decision}:{context.actor.actor_id}"
        )
        review_hash = hashlib.sha256(review_seed.encode("utf-8")).hexdigest()[:24]
        review_record = ReviewRecord(
            review_id=f"review:{review_hash}",
            packet_id=packet_id,
            review_dependency_digest=packet.review_dependency_digest,
            decision=decision.decision,
            authenticated_reviewer_ref=decision.authenticated_reviewer_ref,
            reason=decision.reason,
            recorded_at=decision.recorded_at,
        )

        transition = ReviewTransitionResult(
            new_run_status=new_run_status,
            new_review_outcome=new_review_outcome,
            stop_reason=stop_reason,
            review_record=review_record,
            issues=[],
        )

        # 7. Persist audit intent & result
        event_ids = []
        output_blob = None
        if self.kernel is not None and self.blobs is not None:
            record_bytes = canonical_json_bytes(review_record.model_dump(mode="json"))
            intent_payload = self.blobs.put(record_bytes, "application/json")
            intent = OperationIntent(
                context=context,
                idempotency_key=context.idempotency_key,
                event_type="review.report",
                payload=intent_payload,
                stream_id=f"stream:{context.correlation_id}",
            )
            self.kernel.commit_intent(intent, capability=capability)

            out_bytes = canonical_json_bytes(transition.model_dump(mode="json"))
            output_blob = self.blobs.put(out_bytes, "application/json")

            event_id = f"event:review_{context.operation_id}"
            stream_events = self.kernel.list_stream_events(intent.stream_id)
            event_ids = [e.event_id for e in stream_events] + [event_id]

            self.kernel.commit_result(
                intent,
                OperationResult(
                    operation_id=context.operation_id,
                    attempt_id=context.attempt_id,
                    status="SUCCESS",
                    payload=output_blob,
                    output_refs=[output_blob],
                    issue_codes=[],
                ),
                capability=capability,
            )

        # Mark packet decided so subsequent submissions fail with STALE_REVIEW
        self._decided_packets.add(packet_id)

        return ServiceResult[ReviewTransitionResult](
            contract_version="1.1",
            operation_id=context.operation_id,
            attempt_id=context.attempt_id,
            status="SUCCESS",
            output=transition,
            output_blob=output_blob,
            issues=[],
            dependencies=[
                EvidenceRef(
                    ref_kind="RECORD",
                    ref_id=packet.report_revision_id,
                    artifact_revision_id=None,
                    locator=None,
                )
            ],
            audit_event_ids=event_ids,
        )

    def close_without_decision(
        self,
        context: CommandContext,
        packet_id: str,
        *,
        capability: Capability,
        reason: str = "Authorized manual closure",
        current_run_status: str = "AWAITING_REVIEW",
    ) -> ServiceResult[ReviewTransitionResult]:
        """Authorized manual closure completing with CLOSED_WITHOUT_DECISION, never APPROVED."""
        if self.kernel is not None:
            self.kernel.authority.check(capability, context.actor, "review.report")

        if context.actor.actor_kind != "HUMAN" or context.actor.authenticated_session_ref is None:
            raise AuthorizationError("manual closure requires an authenticated HUMAN session")

        packet = self._packets.get(packet_id)
        if packet is None:
            return self._make_failure(
                context, "MISSING_ARTIFACT", f"Review packet '{packet_id}' not found"
            )

        if packet_id in self._decided_packets:
            raise ValueError("STALE_REVIEW: packet has already been decided")

        if current_run_status in {"COMPLETED", "BLOCKED_OUTPUT", "FAILED", "CANCELLED"}:
            raise ValueError(f"terminal run cannot be manually closed: status {current_run_status}")

        now_iso = datetime.now(UTC).isoformat()
        review_seed = f"{packet_id}:{now_iso}:MANUAL_CLOSURE:{context.actor.actor_id}"
        _ = hashlib.sha256(review_seed.encode("utf-8")).hexdigest()[:24]

        # Explicit authorized manual closure may complete with CLOSED_WITHOUT_DECISION
        # and MANUAL_CLOSURE, never APPROVED.
        transition = ReviewTransitionResult(
            new_run_status="COMPLETED",
            new_review_outcome="CLOSED_WITHOUT_DECISION",
            stop_reason="MANUAL_CLOSURE",
            review_record=None,
            issues=[],
        )

        event_ids = []
        output_blob = None
        if self.kernel is not None and self.blobs is not None:
            out_bytes = canonical_json_bytes(transition.model_dump(mode="json"))
            output_blob = self.blobs.put(out_bytes, "application/json")
            intent = OperationIntent(
                context=context,
                idempotency_key=context.idempotency_key,
                event_type="review.report",
                payload=output_blob,
                stream_id=f"stream:{context.correlation_id}",
            )
            self.kernel.commit_intent(intent, capability=capability)
            event_id = f"event:closure_{context.operation_id}"
            event_ids = [e.event_id for e in self.kernel.list_stream_events(intent.stream_id)] + [
                event_id
            ]
            self.kernel.commit_result(
                intent,
                OperationResult(
                    operation_id=context.operation_id,
                    attempt_id=context.attempt_id,
                    status="SUCCESS",
                    payload=output_blob,
                    output_refs=[output_blob],
                    issue_codes=[],
                ),
                capability=capability,
            )

        self._decided_packets.add(packet_id)

        return ServiceResult[ReviewTransitionResult](
            contract_version="1.1",
            operation_id=context.operation_id,
            attempt_id=context.attempt_id,
            status="SUCCESS",
            output=transition,
            output_blob=output_blob,
            issues=[],
            dependencies=[
                EvidenceRef(
                    ref_kind="RECORD",
                    ref_id=packet.report_revision_id,
                    artifact_revision_id=None,
                    locator=None,
                )
            ],
            audit_event_ids=event_ids,
        )

    def attach_acknowledgment(
        self,
        context: CommandContext,
        artifact_revision_id: str,
        linked_case_version_id: str,
        claimed_external_reference: str,
        validation_state: AcknowledgmentValidationState,
        *,
        capability: Capability,
        linked_report_revision_id: str | None = None,
        review_ref: str | None = None,
    ) -> ServiceResult[AcknowledgmentRecord]:
        """Attach an external filing acknowledgment with provenance without
        inferring official success.
        """
        if self.kernel is not None:
            self.kernel.authority.check(capability, context.actor, "review.report")

        ack_seed = f"{artifact_revision_id}:{linked_case_version_id}:{claimed_external_reference}"
        ack_hash = hashlib.sha256(ack_seed.encode("utf-8")).hexdigest()[:24]

        record = AcknowledgmentRecord(
            acknowledgment_id=f"ack:{ack_hash}",
            artifact_revision_id=artifact_revision_id,
            linked_case_version_id=linked_case_version_id,
            linked_report_revision_id=linked_report_revision_id,
            claimed_external_reference=claimed_external_reference,
            validation_state=validation_state,
            review_ref=review_ref,
        )

        event_ids = []
        output_blob = None
        if self.kernel is not None and self.blobs is not None:
            record_bytes = canonical_json_bytes(record.model_dump(mode="json"))
            output_blob = self.blobs.put(record_bytes, "application/json")
            intent = OperationIntent(
                context=context,
                idempotency_key=context.idempotency_key,
                event_type="review.acknowledgment",
                payload=output_blob,
                stream_id=f"stream:{context.correlation_id}",
            )
            self.kernel.commit_intent(intent, capability=capability)
            event_id = f"event:ack_{context.operation_id}"
            event_ids = [e.event_id for e in self.kernel.list_stream_events(intent.stream_id)] + [
                event_id
            ]
            self.kernel.commit_result(
                intent,
                OperationResult(
                    operation_id=context.operation_id,
                    attempt_id=context.attempt_id,
                    status="SUCCESS",
                    payload=output_blob,
                    output_refs=[output_blob],
                    issue_codes=[],
                ),
                capability=capability,
            )

        return ServiceResult[AcknowledgmentRecord](
            contract_version="1.1",
            operation_id=context.operation_id,
            attempt_id=context.attempt_id,
            status="SUCCESS",
            output=record,
            output_blob=output_blob,
            issues=[],
            dependencies=[
                EvidenceRef(
                    ref_kind="ARTIFACT",
                    ref_id=artifact_revision_id,
                    artifact_revision_id=artifact_revision_id,
                    locator=None,
                )
            ],
            audit_event_ids=event_ids,
        )

    @staticmethod
    def _make_failure(context, code: str, message: str) -> ServiceResult[ReviewTransitionResult]:
        issue = Issue(
            issue_id=f"issue:{code.lower()}",
            code=code,
            severity="BLOCKING",
            message=message,
            field_path=None,
            evidence_refs=[],
            retryable=False,
        )
        return ServiceResult[ReviewTransitionResult](
            contract_version="1.1",
            operation_id=context.operation_id,
            attempt_id=context.attempt_id,
            status="REJECTED",
            output=None,
            output_blob=None,
            issues=[issue],
            dependencies=[],
            audit_event_ids=[],
        )
