"""Authenticated, durable review decisions bound to exact verified report/input bytes."""

import hashlib
import json
from datetime import UTC, datetime

from recycleguard.contracts.audit import OperationIntent, OperationResult
from recycleguard.contracts.core import BlobRef, EvidenceRef, ServiceResult
from recycleguard.contracts.review import (
    AcknowledgmentRecord,
    ReviewPacket,
    ReviewRecord,
    ReviewTransitionResult,
)
from recycleguard.reporting import BaselineReport, ReportVerifier
from recycleguard.storage import canonical_json_bytes
from recycleguard.storage.authority import AuthorizationError

_SCHEMA = """
CREATE TABLE IF NOT EXISTS report_review_packets (
 packet_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, packet_blob TEXT NOT NULL,
 sources_blob TEXT NOT NULL, closed_operation_id TEXT,
 superseded_by_packet_id TEXT
);
CREATE TABLE IF NOT EXISTS report_review_decisions (
 packet_id TEXT PRIMARY KEY REFERENCES report_review_packets(packet_id),
 operation_id TEXT UNIQUE NOT NULL, transition_blob TEXT NOT NULL
);
"""
_TRANSITIONS = {
    "APPROVE": ("COMPLETED", "APPROVED", "RESOLVED_WITHIN_SCOPE"),
    "REJECT": ("BLOCKED_OUTPUT", "REJECTED", "REVIEW_REJECTED"),
    "REQUEST_CHANGES": ("DRAFTING", "CHANGES_REQUESTED", "CHANGES_REQUESTED"),
    "ESCALATE": ("AWAITING_REVIEW", "ESCALATED", "EXPERT_REVIEW_REQUIRED"),
}


def _now():
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class ReviewService:
    def __init__(self, cases, *, run_state, current_report):
        self.cases, self.kernel = cases, cases.kernel
        self.blobs = self.kernel.blob_store
        self.connection = self.kernel.connection
        self.run_state, self.current_report = run_state, current_report
        self.connection.executescript(_SCHEMA)

    def _authorize(self, context, capability, event, *, human=False):
        self.kernel.authority.check(capability, context.actor, event)
        kind = "HUMAN" if human else "SERVICE"
        if context.actor.actor_kind != kind or (
            human and context.actor.authenticated_session_ref is None
        ):
            raise AuthorizationError(f"{event} requires an authenticated {kind} principal")

    def _intent(self, context, event, body, capability):
        intent = OperationIntent(
            context=context,
            idempotency_key=context.idempotency_key,
            event_type=event,
            stream_id=f"stream:{context.run_id or context.correlation_id}",
            payload=self.blobs.put(canonical_json_bytes(body), "application/json"),
        )
        self.kernel.commit_intent(intent, capability=capability)
        return intent

    def _packet_row(self, packet_id):
        row = self.connection.execute(
            "SELECT * FROM report_review_packets WHERE packet_id=?", (packet_id,)
        ).fetchone()
        if row is None:
            raise ValueError("MISSING_ARTIFACT: review packet does not exist")
        return row

    def get_packet(self, packet_id):
        row = self._packet_row(packet_id)
        packet = ReviewPacket.model_validate_json(
            self.blobs.get(BlobRef.model_validate_json(row["packet_blob"]))
        )
        if packet.packet_id != packet_id or packet.run_id != row["run_id"]:
            raise ValueError("review packet catalog binding is invalid")
        self._audited_payload(
            packet.creation_operation_id,
            BlobRef.model_validate_json(row["packet_blob"]),
            "report.review_packet",
        )
        self.blobs.get(BlobRef.model_validate_json(row["sources_blob"]))
        return packet

    def _audited_payload(self, operation_id, blob, event_type):
        intent = self.kernel.get_intent(operation_id)
        result = self.kernel.get_result(operation_id)
        event = self.kernel.get_event(f"event:result_{operation_id}")
        if (
            intent is None
            or result is None
            or event is None
            or intent.event_type != event_type
            or result.status != "SUCCESS"
            or result.payload != blob
            or event.payload_blob != blob
            or event.event_type != f"{event_type}.result"
            or event.actor != intent.context.actor
            or event.attempt_id != result.attempt_id
            or event.event_hash
            != hashlib.sha256(
                canonical_json_bytes(event.model_dump(mode="json", exclude={"event_hash"}))
            ).hexdigest()
        ):
            raise ValueError("review artifact is not bound to its committed audit result")
        self.blobs.get(intent.payload)

    def get_report(self, packet_id):
        return BaselineReport.model_validate_json(
            self.blobs.get(self.get_packet(packet_id).report_blob)
        )

    def get_decision(self, packet_id):
        row = self.connection.execute(
            "SELECT operation_id,transition_blob FROM report_review_decisions WHERE packet_id=?",
            (packet_id,),
        ).fetchone()
        if row is None:
            return None
        blob = BlobRef.model_validate_json(row["transition_blob"])
        self._audited_payload(row["operation_id"], blob, "review.report")
        packet = self.get_packet(packet_id)
        transition = ReviewTransitionResult.model_validate_json(self.blobs.get(blob))
        record = transition.review_record
        if record is not None and (
            record.packet_id != packet_id
            or record.run_id != packet.run_id
            or record.report_revision_id != packet.report_revision_id
            or record.input_snapshot_refs != packet.input_snapshot_refs
            or record.review_dependency_digest != packet.review_dependency_digest
        ):
            raise ValueError("review decision does not bind its immutable packet")
        return transition

    def _bindings(self, report, snapshots):
        if not report.revision.run_id:
            raise ValueError("review report must pin a run ID")
        calculations = report.calculations
        if len(calculations) != 1:
            raise ValueError("review report requires exactly one authoritative calculation")
        actual = [self.cases.snapshots.get(ref) for ref in snapshots]
        if any(snapshot.review_state != "APPROVED" for snapshot in actual):
            raise ValueError("review inputs must be approved snapshots")
        case = next(
            (
                snapshot
                for snapshot in actual
                if snapshot.snapshot_kind == "CASE"
                and snapshot.snapshot_id == calculations[0].case_version_id
            ),
            None,
        )
        if case is None:
            raise ValueError("review inputs do not contain the calculation's exact CASE snapshot")
        membership = json.loads(self.blobs.get(case.membership_blob))
        if membership["corpus_snapshot"] not in [ref.model_dump(mode="json") for ref in snapshots]:
            raise ValueError("review inputs omit the corpus pinned by the case")
        if len(snapshots) != len({ref.snapshot_id for ref in snapshots}):
            raise ValueError("duplicate review snapshot refs")

    def create_review_packet(
        self,
        context,
        report,
        *,
        input_snapshots,
        authoritative_calculations,
        available_evidence_refs=(),
        findings=(),
        proposed_action_refs=None,
        unresolved_issue_refs=None,
        capability,
    ):
        self._authorize(context, capability, "report.review_packet")
        self._bindings(report, input_snapshots)
        run_id = report.revision.run_id
        if (
            context.run_id != run_id
            or context.case_version_id != report.calculations[0].case_version_id
        ):
            raise ValueError("review packet context must pin exact report run/case")
        state = self.run_state(run_id)
        if state.status not in {"VERIFYING", "AWAITING_REVIEW"}:
            raise ValueError("packet creation requires a verified report awaiting review")
        if self.current_report(run_id) != report:
            raise ValueError("STALE_REVIEW: report is not the current server report")
        refs, findings = tuple(available_evidence_refs), tuple(findings)
        checked = ReportVerifier().verify(
            report,
            authoritative_calculations=authoritative_calculations,
            available_evidence_refs=refs,
            findings=findings,
        )
        if checked.verdict == "BLOCKED":
            raise ValueError("blocked report cannot be presented for approval")
        report_blob = self.blobs.put(report.model_dump_json().encode(), "application/json")
        sources = {
            "calculations": [item.model_dump(mode="json") for item in authoritative_calculations],
            "findings": [item.model_dump(mode="json") for item in findings],
            "evidence_refs": [item.model_dump(mode="json") for item in refs],
        }
        source_blob = self.blobs.put(canonical_json_bytes(sources), "application/json")
        body = {
            "creation_operation_id": context.operation_id,
            "report_blob": report_blob.model_dump(mode="json"),
            "source_blob": source_blob.model_dump(mode="json"),
            "input_snapshots": [ref.model_dump(mode="json") for ref in input_snapshots],
            "proposed_action_refs": proposed_action_refs or [],
            "unresolved_issue_refs": unresolved_issue_refs or [],
        }
        intent = self._intent(context, "report.review_packet", body, capability)
        previous = self.kernel.get_result(context.operation_id)
        if previous is not None:
            return ReviewPacket.model_validate_json(self.blobs.get(previous.payload))
        identifier = hashlib.sha256(canonical_json_bytes(body)).hexdigest()[:24]
        packet = ReviewPacket(
            packet_id=f"packet:{identifier}",
            creation_operation_id=context.operation_id,
            run_id=run_id,
            report_blob=report_blob,
            report_revision_id=report.revision.report_revision_id,
            review_dependency_digest=report.revision.review_dependency_digest,
            input_snapshot_refs=input_snapshots,
            proposed_action_refs=proposed_action_refs or [],
            unresolved_issue_refs=unresolved_issue_refs or [],
            permitted_decisions=list(_TRANSITIONS),
            created_at=_now(),
        )
        packet_blob = self.blobs.put(packet.model_dump_json().encode(), "application/json")

        def publish():
            existing = self.connection.execute(
                "SELECT packet_blob FROM report_review_packets WHERE packet_id=?",
                (packet.packet_id,),
            ).fetchone()
            if existing is not None:
                raise ValueError("review packet already exists; use its original operation")
            self.connection.execute(
                "UPDATE report_review_packets SET superseded_by_packet_id=? WHERE run_id=? "
                "AND closed_operation_id IS NULL AND superseded_by_packet_id IS NULL",
                (packet.packet_id, run_id),
            )
            self.connection.execute(
                "INSERT INTO report_review_packets VALUES (?,?,?,?,NULL,NULL)",
                (
                    packet.packet_id,
                    run_id,
                    packet_blob.model_dump_json(),
                    source_blob.model_dump_json(),
                ),
            )

        self.kernel.commit_result(
            intent,
            OperationResult(
                operation_id=context.operation_id,
                attempt_id=context.attempt_id,
                status="SUCCESS",
                payload=packet_blob,
                output_refs=[report_blob, source_blob],
            ),
            capability=capability,
            mutation=publish,
        )
        return packet

    def _live(self, context, packet_id, expected_dependency_digest):
        row, packet = self._packet_row(packet_id), self.get_packet(packet_id)
        if row["closed_operation_id"] or row["superseded_by_packet_id"]:
            raise ValueError("STALE_REVIEW: packet has already been decided or superseded")
        if expected_dependency_digest != packet.review_dependency_digest:
            raise ValueError("STALE_REVIEW: dependency digest mismatch")
        if context.run_id != packet.run_id:
            raise ValueError("review context must pin the packet run")
        report = self.get_report(packet_id)
        if context.case_version_id != report.calculations[0].case_version_id:
            raise ValueError("review context must pin the packet case")
        state = self.run_state(packet.run_id)
        if state.status != "AWAITING_REVIEW":
            raise ValueError("STALE_REVIEW: server run is not awaiting review")
        if self.current_report(packet.run_id) != report:
            raise ValueError("STALE_REVIEW: current report/input versions changed")
        self._bindings(report, packet.input_snapshot_refs)
        return packet

    def submit_review(
        self, context, packet_id, expected_dependency_digest, decision, *, capability
    ):
        self._authorize(context, capability, "review.report", human=True)
        if decision.authenticated_reviewer_ref != context.actor:
            raise AuthorizationError("spoofed reviewer identity or session rejected")
        if not decision.reason.strip():
            raise ValueError("review decision requires a nonblank reason")
        body = {
            "packet_id": packet_id,
            "expected_dependency_digest": expected_dependency_digest,
            "decision": decision.model_dump(mode="json"),
        }
        intent = self._intent(context, "review.report", body, capability)
        previous = self.kernel.get_result(context.operation_id)
        if previous is not None:
            return self._envelope(context, previous.payload)
        packet = self._live(context, packet_id, expected_dependency_digest)
        if decision.decision not in packet.permitted_decisions:
            raise ValueError("decision is not permitted for this packet")
        status, outcome, stop = _TRANSITIONS[decision.decision]
        review = ReviewRecord(
            review_id=f"review:{hashlib.sha256(context.operation_id.encode()).hexdigest()[:24]}",
            run_id=packet.run_id,
            report_revision_id=packet.report_revision_id,
            input_snapshot_refs=packet.input_snapshot_refs,
            packet_id=packet_id,
            review_dependency_digest=packet.review_dependency_digest,
            decision=decision.decision,
            authenticated_reviewer_ref=context.actor,
            reason=decision.reason,
            recorded_at=_now(),
        )
        transition = ReviewTransitionResult(
            new_run_status=status,
            new_review_outcome=outcome,
            stop_reason=stop,
            review_record=review,
            issues=[],
        )
        return self._commit(context, intent, packet, transition, capability)

    def _commit(self, context, intent, packet, transition, capability):
        blob = self.blobs.put(transition.model_dump_json().encode(), "application/json")

        def decide():
            self._live(context, packet.packet_id, packet.review_dependency_digest)
            changed = self.connection.execute(
                "UPDATE report_review_packets SET closed_operation_id=? WHERE packet_id=? "
                "AND closed_operation_id IS NULL AND superseded_by_packet_id IS NULL",
                (context.operation_id, packet.packet_id),
            )
            if changed.rowcount != 1:
                raise ValueError("STALE_REVIEW: packet changed concurrently")
            self.connection.execute(
                "INSERT INTO report_review_decisions VALUES (?,?,?)",
                (packet.packet_id, context.operation_id, blob.model_dump_json()),
            )

        self.kernel.commit_result(
            intent,
            OperationResult(
                operation_id=context.operation_id,
                attempt_id=context.attempt_id,
                status="SUCCESS",
                payload=blob,
                output_refs=[packet.report_blob],
            ),
            capability=capability,
            mutation=decide,
        )
        return self._envelope(context, blob)

    def _envelope(self, context, blob):
        transition = ReviewTransitionResult.model_validate_json(self.blobs.get(blob))
        record = transition.review_record
        return ServiceResult[ReviewTransitionResult](
            contract_version="1.1",
            operation_id=context.operation_id,
            attempt_id=context.attempt_id,
            status="SUCCESS",
            output=transition,
            output_blob=blob,
            issues=[],
            dependencies=[]
            if record is None
            else [
                EvidenceRef(
                    ref_kind="RECORD",
                    ref_id=record.report_revision_id,
                    artifact_revision_id=None,
                    locator=None,
                )
            ],
            audit_event_ids=[f"event:result_{context.operation_id}"],
        )

    def close_without_decision(
        self,
        context,
        packet_id,
        *,
        expected_dependency_digest,
        capability,
        reason="Authorized manual closure",
    ):
        self._authorize(context, capability, "review.report", human=True)
        if not reason.strip():
            raise ValueError("manual closure requires a reason")
        intent = self._intent(
            context,
            "review.report",
            {
                "packet_id": packet_id,
                "expected_dependency_digest": expected_dependency_digest,
                "reason": reason,
                "decision": "CLOSED_WITHOUT_DECISION",
            },
            capability,
        )
        previous = self.kernel.get_result(context.operation_id)
        if previous is not None:
            return self._envelope(context, previous.payload)
        packet = self._live(context, packet_id, expected_dependency_digest)
        transition = ReviewTransitionResult(
            new_run_status="COMPLETED",
            new_review_outcome="CLOSED_WITHOUT_DECISION",
            stop_reason="MANUAL_CLOSURE",
            review_record=None,
            issues=[],
        )
        return self._commit(context, intent, packet, transition, capability)

    def attach_acknowledgment(
        self,
        context,
        artifact_revision_id,
        linked_case_version_id,
        claimed_external_reference,
        validation_state,
        *,
        capability,
        linked_report_revision_id=None,
        review_ref=None,
    ):
        self._authorize(context, capability, "review.acknowledgment", human=True)
        self.cases.snapshots.catalog.get_artifact_revision(artifact_revision_id)
        self.cases.snapshots.catalog.get_snapshot(linked_case_version_id)
        if validation_state != "PENDING_VERIFICATION":
            raise ValueError("external filing validity cannot be asserted by an attachment request")
        record = AcknowledgmentRecord(
            acknowledgment_id=f"ack:{hashlib.sha256(context.operation_id.encode()).hexdigest()[:24]}",
            artifact_revision_id=artifact_revision_id,
            linked_case_version_id=linked_case_version_id,
            linked_report_revision_id=linked_report_revision_id,
            claimed_external_reference=claimed_external_reference,
            validation_state="PENDING_VERIFICATION",
            review_ref=review_ref,
        )
        intent = self._intent(
            context, "review.acknowledgment", record.model_dump(mode="json"), capability
        )
        blob = self.blobs.put(record.model_dump_json().encode(), "application/json")
        self.kernel.commit_result(
            intent,
            OperationResult(
                operation_id=context.operation_id,
                attempt_id=context.attempt_id,
                status="SUCCESS",
                payload=blob,
            ),
            capability=capability,
        )
        return ServiceResult[AcknowledgmentRecord](
            contract_version="1.1",
            operation_id=context.operation_id,
            attempt_id=context.attempt_id,
            status="SUCCESS",
            output=record,
            output_blob=blob,
            issues=[],
            dependencies=[],
            audit_event_ids=[f"event:result_{context.operation_id}"],
        )
