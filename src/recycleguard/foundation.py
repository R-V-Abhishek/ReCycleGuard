"""A04 audited intake -> extraction -> normalization -> frozen case/corpus/profile drafts."""

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from recycleguard.contracts.artifacts import AssetReceipt, ProfileRef
from recycleguard.contracts.audit import OperationIntent, OperationResult
from recycleguard.contracts.core import Issue, ServiceResult, TemporalValue
from recycleguard.contracts.domain import ReviewedInterval
from recycleguard.contracts.foundation import (
    ApplicabilityProposal,
    ExtractedBatch,
    FoundationRequest,
    FoundationResult,
    SourceBatch,
)
from recycleguard.contracts.profiles import ProfilePublication
from recycleguard.contracts.snapshots import SnapshotPublication
from recycleguard.contracts.sources import RightsMetadata, SourceLead, SourceVersion
from recycleguard.extraction import extract_artifact
from recycleguard.intake import intake_batch
from recycleguard.knowledge import (
    build_v1_profile_definition,
    get_reviewed_provisions,
    register_reviewed_sources,
)
from recycleguard.normalization.models import NormalizationBatch
from recycleguard.normalization.service import NormalizationService
from recycleguard.storage import canonical_json_bytes
from recycleguard.storage.authority import AuthorizationError
from recycleguard.storage.blob_store import BlobIntegrityError


class FoundationService:
    def __init__(self, cases):
        self.cases, self.kernel, self.catalog = cases, cases.kernel, cases.snapshots.catalog
        self.blobs = self.kernel.blob_store

    def _context(self, root, stage):
        key = root.operation_id.split(":", 1)[1] + "_" + stage.replace(".", "_")
        return root.model_copy(
            update={
                "command_id": f"command:{key}",
                "operation_id": f"operation:{key}",
                "attempt_id": f"attempt:{key}",
                "idempotency_key": key,
                "parent_operation_id": root.operation_id,
            }
        )

    def _stage(self, context, event_type, request, model, compute, capability, mutation=None):
        self.kernel.authority.check(capability, context.actor, event_type)
        payload = self.blobs.put(canonical_json_bytes(request), "application/json")
        intent = OperationIntent(
            context=context,
            idempotency_key=context.idempotency_key,
            event_type=event_type,
            payload=payload,
            stream_id=f"stream:{context.correlation_id}",
        )
        self.kernel.commit_intent(intent, capability=capability)
        previous = self.kernel.get_result(context.operation_id)
        if previous is not None:
            return model.model_validate_json(self.blobs.get(previous.payload))
        output = compute()
        blob = self.blobs.put(
            canonical_json_bytes(output.model_dump(mode="json")), "application/json"
        )
        self.kernel.commit_result(
            intent,
            OperationResult(
                operation_id=context.operation_id,
                attempt_id=context.attempt_id,
                status="SUCCESS",
                payload=blob,
            ),
            capability=capability,
            mutation=None if mutation is None else lambda: mutation(output),
        )
        return output

    def build(self, context, request: FoundationRequest, *, capability):
        try:
            return self._build_result(context, request, capability=capability)
        except AuthorizationError as exc:
            code, status = "ACCESS_DENIED", "REJECTED"
            message = str(exc)
        except BlobIntegrityError as exc:
            code, status = "HASH_MISMATCH", "REJECTED"
            message = str(exc)
        except FileNotFoundError as exc:
            code, status = "MISSING_ARTIFACT", "REJECTED"
            message = str(exc)
        except (sqlite3.Error, OSError) as exc:
            code, status = "AUDIT_UNAVAILABLE", "OUTCOME_UNKNOWN"
            message = str(exc)
        except ValueError as exc:
            code, status = "INVALID_SCHEMA", "REJECTED"
            message = str(exc)
        return ServiceResult[FoundationResult](
            contract_version="1.1",
            operation_id=context.operation_id,
            attempt_id=context.attempt_id,
            status=status,
            output=None,
            output_blob=None,
            dependencies=[],
            audit_event_ids=[],
            issues=[
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
        )

    def _build_result(self, context, request: FoundationRequest, *, capability):
        # Validate the full capability set before any request/archive/evidence writes.
        for event in [
            "snapshot.foundation",
            "intake.batch",
            "extraction.batch",
            "normalization.batch",
            "profile.publish",
        ]:
            self.kernel.authority.check(capability, context.actor, event)
        data = request.model_dump(mode="json")
        output = self._stage(
            context,
            "snapshot.foundation",
            data,
            FoundationResult,
            lambda: self._build(context, request, capability),
            capability,
        )
        persisted = self.kernel.get_result(context.operation_id)
        events = self.kernel.list_stream_events(f"stream:{context.correlation_id}")
        return ServiceResult[FoundationResult](
            contract_version="1.1",
            operation_id=context.operation_id,
            attempt_id=context.attempt_id,
            status="PARTIAL" if output.issues else "SUCCESS",
            output=output,
            output_blob=persisted.payload,
            issues=output.issues,
            dependencies=[],
            audit_event_ids=[event.event_id for event in events],
        )

    def _sources(self, request):
        revisions = list(
            register_reviewed_sources(
                self.blobs, r02_path=Path(request.r02_path), r08_path=Path(request.r08_path)
            )
        )
        for index, revision in enumerate(revisions):
            try:
                existing = self.catalog.get_artifact_revision(revision.artifact_revision_id)
            except KeyError:
                continue
            if existing.blob != revision.blob:
                raise ValueError(
                    "source identity already pins different bytes; use a new source revision"
                )
            revisions[index] = existing
        provisions = get_reviewed_provisions(
            self.blobs, r02_revision=revisions[0], r08_revision=revisions[1]
        )
        receipts, leads, versions, proposals = [], [], [], []
        unknown = TemporalValue(
            raw=None,
            value=None,
            precision="UNKNOWN",
            timezone=None,
            interpretation_status="UNKNOWN",
        )
        for name, revision in zip(["r02", "r08"], revisions, strict=True):
            receipts.append(
                AssetReceipt(
                    receipt_id=f"receipt:{revision.artifact_revision_id.split(':')[1]}",
                    batch_id="batch:regulatory_originals",
                    declared_asset_id=None,
                    supplied_path_or_url=revision.source_url,
                    intake_status="RECEIVED",
                    artifact_revision_id=revision.artifact_revision_id,
                    reason="Original PDF; rights and applicability review required",
                    received_at=datetime.now(UTC).isoformat(),
                )
            )
            leads.append(
                SourceLead(
                    source_lead_id=f"source_lead:{name}",
                    aliases=[name.upper()],
                    official_url=revision.source_url,
                    discovery_evidence_refs=[],
                    source_class="GAZETTE_RULE" if name == "r02" else "FAQ",
                    regime="E_WASTE_2022",
                    state="REVIEW_REQUIRED",
                    acquired_artifact_revision_id=revision.artifact_revision_id,
                    rights_and_license=RightsMetadata(
                        copyright_owner="Government of India / CPCB",
                        statutory_exception_sec52=None,
                        asset_rights_seed="REVIEW_REQUIRED",
                        redistribution_allowed=False,
                        attribution_text=revision.source_url,
                    ),
                )
            )
            versions.append(
                SourceVersion(
                    source_version_id=f"source_ver:{name}_original",
                    source_lead_id=f"source_lead:{name}",
                    artifact_revision_id=revision.artifact_revision_id,
                    title="E-Waste Rules 2022" if name == "r02" else "CPCB FAQ, 23 January 2024",
                    issuer="MoEFCC" if name == "r02" else "CPCB",
                    notification_number="G.S.R. 801(E)" if name == "r02" else None,
                    notification_date=unknown,
                    publication_date=unknown,
                    commencement=unknown,
                    commencement_basis_refs=[],
                    website_upload_date=unknown,
                    completeness="COMPLETE_TEXT",
                    review_state="DRAFT",
                )
            )
        for index, receipt in enumerate(receipts):
            try:
                existing = self.catalog.get_receipt(receipt.receipt_id)
            except KeyError:
                continue
            if existing.artifact_revision_id != receipt.artifact_revision_id:
                raise ValueError("source receipt points to another revision")
            receipts[index] = existing
        for provision in provisions:
            proposals.append(
                ApplicabilityProposal(
                    assertion_id=provision.applicability_assertion_id,
                    provision_version_id=provision.provision_version_id,
                    interval=ReviewedInterval(
                        start=None,
                        end=None,
                        end_open_ended=False,
                        review_state="DRAFT",
                        applicability_scope="UNKNOWN",
                        evidence_refs=[],
                    ),
                    affected_roles=provision.affected_roles,
                    category_scope=[],
                    scope_notes=(
                        "Base-source proposal; period-specific amendments, deadlines "
                        "and exceptions require human review."
                    ),
                )
            )
        return SourceBatch(
            artifact_revisions=revisions,
            receipts=receipts,
            leads=leads,
            source_versions=versions,
            provisions=provisions,
            applicability=proposals,
        )

    def _build(self, root, request, capability):
        intake = intake_batch(
            request.case_root,
            blob_store=self.blobs,
            catalog=self.catalog,
            kernel=self.kernel,
            capability=capability,
            context=self._context(root, "intake.case"),
        )
        if intake.manifest is None:
            raise ValueError(
                "A04 requires a valid complete case manifest; receipts remain archived"
            )

        def persist_sources(output):
            for revision in output.artifact_revisions:
                self.catalog.put_artifact_revision(revision)
            for receipt in output.receipts:
                self.catalog.put_receipt(receipt)

        sources = self._stage(
            self._context(root, "intake.sources"),
            "intake.sources",
            {"r02_path": request.r02_path, "r08_path": request.r08_path},
            SourceBatch,
            lambda: self._sources(request),
            capability,
            persist_sources,
        )

        def extract():
            results, observations, coverage = [], [], []
            for revision in intake.artifact_revisions + sources.artifact_revisions:
                result, obs, cov = extract_artifact(revision, self.blobs)
                results.append(result)
                observations.extend(obs)
                coverage.extend(cov)
            return ExtractedBatch(results=results, observations=observations, coverage=coverage)

        extracted = self._stage(
            self._context(root, "extraction.all"),
            "extraction.batch",
            {
                "revision_ids": [
                    r.artifact_revision_id
                    for r in intake.artifact_revisions + sources.artifact_revisions
                ]
            },
            ExtractedBatch,
            extract,
            capability,
        )
        case_revisions = {r.artifact_revision_id for r in intake.artifact_revisions}
        normalization_context = self._context(root, "normalization.case")
        normalized = self._stage(
            normalization_context,
            "normalization.batch",
            {"extraction_ids": [r.extraction_id for r in extracted.results]},
            NormalizationBatch,
            lambda: NormalizationService(normalization_context.operation_id).normalize(
                intake.case_id,
                [
                    obs
                    for obs in extracted.observations
                    if obs.artifact_revision_id in case_revisions
                ],
                batch_id=f"batch:{normalization_context.operation_id.split(':')[1]}",
            ),
            capability,
        )
        profile = self.cases.publish_profile(
            self._context(root, "profile.draft"),
            ProfilePublication(
                profile_id=intake.manifest.calculation_profile_id,
                profile_version=request.profile_version,
                expected_head=request.expected_profile_head,
                definition=build_v1_profile_definition(*sources.artifact_revisions),
            ),
            capability=capability,
        )
        if profile.status != "SUCCESS":
            raise ValueError(f"profile publication failed: {profile.issues}")
        reference = ProfileRef(
            profile_id=profile.output.profile_id,
            profile_version=profile.output.profile_version,
            digest=profile.output.digest,
        )
        case = self._publish(
            root,
            request.case_snapshot_id,
            "CASE",
            intake.case_id,
            request.expected_case_head,
            {
                "manifest": intake.manifest.model_dump(mode="json"),
                "receipts": [r.model_dump(mode="json") for r in intake.receipts],
                "originals": [r.model_dump(mode="json") for r in intake.artifact_revisions],
                "extractions": [
                    r.model_dump(mode="json")
                    for r in extracted.results
                    if r.artifact_revision_id in case_revisions
                ],
                "normalization": normalized.model_dump(mode="json"),
                "profile": reference.model_dump(mode="json"),
            },
            {
                "coverage": [
                    c.model_dump(mode="json")
                    for c in extracted.coverage
                    if c.artifact_revision_id in case_revisions
                ],
                "intake_issues": [i.model_dump(mode="json") for i in intake.issues],
            },
            intake.receipts,
            capability,
        )
        corpus = self._publish(
            root,
            request.corpus_snapshot_id,
            "CORPUS",
            "corpus:initial",
            request.expected_corpus_head,
            sources.model_dump(mode="json"),
            {
                "coverage": [
                    c.model_dump(mode="json")
                    for c in extracted.coverage
                    if c.artifact_revision_id not in case_revisions
                ]
            },
            sources.receipts,
            capability,
        )
        issue = Issue(
            issue_id="issue:foundation_review_required",
            code="UNAPPROVED_PROFILE",
            severity="BLOCKING",
            message=(
                "Corrected source/applicability and profile drafts require "
                "version-bound human review; CP1 not approved."
            ),
            field_path=None,
            evidence_refs=[],
            retryable=False,
        )
        return FoundationResult(
            case_snapshot=case,
            corpus_snapshot=corpus,
            profile=reference,
            inventory_count=len(intake.receipts),
            extraction_count=len(extracted.results),
            observation_count=len(extracted.observations),
            record_count=len(normalized.records),
            normalization_quarantine_count=sum(
                d.disposition == "QUARANTINED" for d in normalized.dispositions
            ),
            issues=[issue]
            + intake.issues
            + normalized.issues
            + [i for result in extracted.results for i in result.issues],
        )

    def _publish(
        self, root, snapshot_id, kind, scope, expected, membership, coverage, receipts, capability
    ):
        member_blob = self.blobs.put(canonical_json_bytes(membership), "application/json")
        coverage_blob = self.blobs.put(canonical_json_bytes(coverage), "application/json")
        result = self.cases.publish_snapshot(
            self._context(root, f"snapshot.{kind.lower()}"),
            SnapshotPublication(
                scope_id=scope,
                snapshot_id=snapshot_id,
                snapshot_kind=kind,
                expected_head=expected,
                membership_blob=member_blob,
                membership_digest=member_blob.sha256,
                coverage_blob=coverage_blob,
                source_receipt_ids=[r.receipt_id for r in receipts],
            ),
            capability=capability,
        )
        if result.status != "SUCCESS":
            raise ValueError(f"snapshot publication failed: {result.issues}")
        return result.output
