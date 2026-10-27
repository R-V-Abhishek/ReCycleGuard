"""Audited deterministic baseline, using exact approved inputs from local storage."""

import json
import sqlite3

from recycleguard.contracts.artifacts import FrozenSnapshot, ProfileRef, SnapshotRef
from recycleguard.contracts.audit import OperationIntent, OperationResult
from recycleguard.contracts.baseline import BaselineRequest
from recycleguard.contracts.core import BoundaryModel, Issue, ServiceResult
from recycleguard.contracts.results import CalculationResult
from recycleguard.domain.service import compute_reconciliation
from recycleguard.domain.universe import universe_from_membership
from recycleguard.foundation import FoundationService
from recycleguard.profiles import ProfileError
from recycleguard.reporting.baseline import (
    BaselineReport,
    BaselineReportBuilder,
    ReportVerifier,
    VerificationResult,
)
from recycleguard.storage.authority import AuthorizationError
from recycleguard.storage.blob_store import BlobIntegrityError
from recycleguard.storage.catalog import CatalogError


class BaselineOutput(BoundaryModel):
    calculation: CalculationResult
    report: BaselineReport
    verification: VerificationResult


class VerifiedReport(BoundaryModel):
    report: BaselineReport
    verification: VerificationResult


class BaselineService:
    def __init__(self, cases):
        self.cases = cases
        self.kernel = cases.kernel
        self.blobs = self.kernel.blob_store

    def run(self, context, request: BaselineRequest, *, capability):
        """Durably bind requests/results. A qualified report is never a clean SUCCESS."""
        try:
            for event in ("calculation.baseline", "report.baseline"):
                self.kernel.authority.check(capability, context.actor, event)
        except AuthorizationError as exc:
            return self._failure(context, "ACCESS_DENIED", str(exc))
        intent = None
        try:
            payload = self.blobs.put(request.model_dump_json().encode(), "application/json")
            intent = OperationIntent(
                context=context,
                idempotency_key=context.idempotency_key,
                event_type="calculation.baseline",
                payload=payload,
                stream_id=f"stream:{context.correlation_id}",
            )
            self.kernel.commit_intent(intent, capability=capability)
            previous = self.kernel.get_result(context.operation_id)
            if previous is not None:
                return (
                    ServiceResult[BaselineOutput]
                    .model_validate_json(self.blobs.get(previous.payload))
                    .model_copy(update={"output_blob": previous.payload})
                )
            snapshot = self.cases.snapshots.get(request.snapshot)
            if snapshot.snapshot_kind != "CASE" or snapshot.review_state != "APPROVED":
                raise ValueError("baseline requires an approved CASE snapshot")
            membership = json.loads(self.blobs.get(snapshot.membership_blob))
            self._check_support(snapshot.snapshot_id, membership)
            profile_ref = ProfileRef.model_validate(membership["profile"])
            profile = self.cases.profiles.get(profile_ref, require_approved=True)
            calculated = compute_reconciliation(
                context,
                request.calculation,
                snapshots=self.cases.snapshots,
                snapshot_ref=request.snapshot,
                profile=profile,
            )
            if calculated.output is None:
                envelope = self._failure(
                    context, calculated.issues[0].code, calculated.issues[0].message
                )
            else:
                calculation = calculated.output
                fs = FoundationService(self.cases)
                verified = fs._stage(
                    fs._context(context, "report.baseline"),
                    "report.baseline",
                    calculation.model_dump(mode="json"),
                    VerifiedReport,
                    lambda: self._report(calculation),
                    capability,
                )
                report, verification = verified.report, verified.verification
                issues = list(calculated.issues) + verification.issues
                status = "SUCCESS"
                if verification.verdict == "BLOCKED":
                    status = "REJECTED"
                elif calculated.status != "SUCCESS" or verification.verdict != "PASS":
                    status = "PARTIAL"
                if status != "SUCCESS" and not issues:
                    issues = [self._issue("INCOMPLETE_COVERAGE", "Baseline remains qualified")]
                envelope = ServiceResult[BaselineOutput](
                    contract_version="1.1",
                    operation_id=context.operation_id,
                    attempt_id=context.attempt_id,
                    status=status,
                    output=BaselineOutput(
                        calculation=calculation, report=report, verification=verification
                    ),
                    output_blob=None,
                    issues=issues,
                    dependencies=calculated.dependencies,
                    audit_event_ids=[],
                )
            return self._persist(context, intent, envelope, capability)
        except AuthorizationError as exc:
            return self._failure(context, "ACCESS_DENIED", str(exc))
        except ProfileError as exc:
            return self._persist_failure(context, intent, exc.code, str(exc), capability)
        except (KeyError, FileNotFoundError) as exc:
            return self._persist_failure(context, intent, "MISSING_ARTIFACT", str(exc), capability)
        except BlobIntegrityError as exc:
            return self._persist_failure(context, intent, "HASH_MISMATCH", str(exc), capability)
        except (CatalogError, ValueError) as exc:
            code = "STALE_SNAPSHOT" if "STALE_SNAPSHOT" in str(exc) else "INTEGRITY_FAILED"
            return self._persist_failure(context, intent, code, str(exc), capability)
        except (OSError, sqlite3.Error) as exc:
            return self._failure(context, "AUDIT_UNAVAILABLE", str(exc), "OUTCOME_UNKNOWN")

    @staticmethod
    def _issue(code, message):
        return Issue(
            issue_id="issue:baseline",
            code=code,
            severity="BLOCKING",
            message=message,
            field_path=None,
            evidence_refs=[],
            retryable=False,
        )

    def _failure(self, context, code, message, status="REJECTED"):
        return ServiceResult[BaselineOutput](
            contract_version="1.1",
            operation_id=context.operation_id,
            attempt_id=context.attempt_id,
            status=status,
            output=None,
            output_blob=None,
            issues=[self._issue(code, message)],
            dependencies=[],
            audit_event_ids=[],
        )

    def _persist_failure(self, context, intent, code, message, capability):
        # An idempotency conflict must never overwrite or expose another request's result.
        stored = self.kernel.get_intent(context.operation_id)
        if intent is None or stored != intent:
            return self._failure(context, "CONCURRENT_MODIFICATION", message)
        try:
            return self._persist(context, intent, self._failure(context, code, message), capability)
        except (sqlite3.Error, OSError) as exc:
            return self._failure(context, "AUDIT_UNAVAILABLE", str(exc), "OUTCOME_UNKNOWN")

    def _persist(self, context, intent, envelope, capability):
        event_id = f"event:result_{context.operation_id}"
        event_ids = [e.event_id for e in self.kernel.list_stream_events(intent.stream_id)]
        envelope = envelope.model_copy(update={"audit_event_ids": event_ids + [event_id]})
        blob = self.blobs.put(envelope.model_dump_json().encode(), "application/json")
        refs = []
        if envelope.output is not None:
            calc = envelope.output.calculation
            refs = [
                calc.analyzed_input_membership_blob,
                calc.quantity_dispositions_blob,
                calc.derivation_blob,
            ]
        self.kernel.commit_result(
            intent,
            OperationResult(
                operation_id=context.operation_id,
                attempt_id=context.attempt_id,
                status=envelope.status,
                payload=blob,
                output_refs=refs,
                issue_codes=[i.code for i in envelope.issues],
            ),
            capability=capability,
        )
        return envelope.model_copy(update={"output_blob": blob})

    @staticmethod
    def _report(calculation):
        report = BaselineReportBuilder().build(calculation)
        verification = ReportVerifier().verify(report, authoritative_calculations=[calculation])
        return VerifiedReport(report=report, verification=verification)

    def _check_support(self, snapshot_id, membership):
        """A self-declared SUPPORTED field is not a reviewed support assertion."""
        universe = universe_from_membership(snapshot_id, membership)
        for record in universe.records:
            if record.record_revision_id in universe.superseded:
                continue
            supported = (
                (record.record_type == "Allocation" and record.state == "SUPPORTED")
                or (
                    record.record_type == "CertificateEvent"
                    and record.assertion_state == "SUPPORTED"
                )
                or (record.record_type == "Certificate" and record.validation_state == "VALID")
            )
            if not supported:
                continue
            operation = record.created_by_operation_id
            intent = self.kernel.get_intent(operation)
            result = self.kernel.get_result(operation)
            if (
                intent is None
                or intent.event_type != "review.record_support"
                or intent.context.actor.actor_kind != "HUMAN"
                or result is None
                or result.status != "SUCCESS"
                or result.payload is None
            ):
                raise ValueError("supported record has no committed human support assertion")
            reviewed = FrozenSnapshot.model_validate_json(self.blobs.get(result.payload))
            stored = self.cases.snapshots.get(
                SnapshotRef(
                    snapshot_id=reviewed.snapshot_id, membership_digest=reviewed.membership_digest
                )
            )
            reviewed_membership = json.loads(self.blobs.get(stored.membership_blob))
            if (
                record.model_dump(mode="json")
                not in reviewed_membership["normalization"]["records"]
            ):
                raise ValueError("record differs from the committed support revision")
