"""Trusted, version-bound acceptance of a qualified A04 foundation.

The caller authenticates the human and supplies server-owned service grants.
No actor/capability can be reconstructed from the review request JSON.
"""

import json

from recycleguard.contracts.artifacts import ProfileRef, SnapshotRef
from recycleguard.contracts.core import Issue, ServiceResult
from recycleguard.contracts.foundation import FoundationApproval, FoundationResult
from recycleguard.contracts.profiles import ProfileDefinition, ProfilePublication, ProfileReview
from recycleguard.contracts.snapshots import SnapshotReview
from recycleguard.foundation import FoundationService


class FoundationReviewer:
    def __init__(self, cases, *, service_actor, service_capability):
        self.cases = cases
        self.foundation = FoundationService(cases)
        self.kernel = cases.kernel
        self.service_actor = service_actor
        self.service_capability = service_capability

    def approve(self, context, request: FoundationApproval, *, capability):
        self.kernel.authority.check(capability, context.actor, "review.foundation")
        self.kernel.blob_store.get(request.approval_evidence_blob)
        output = self.foundation._stage(
            context,
            "review.foundation",
            request.model_dump(mode="json"),
            FoundationResult,
            lambda: self._approve(context, request, capability),
            capability,
        )
        persisted = self.kernel.get_result(context.operation_id)
        return ServiceResult[FoundationResult](
            contract_version="1.1",
            operation_id=context.operation_id,
            attempt_id=context.attempt_id,
            status="PARTIAL" if output.issues else "SUCCESS",
            output=output,
            output_blob=persisted.payload,
            issues=output.issues,
            dependencies=[],
            audit_event_ids=[
                event.event_id
                for event in self.kernel.list_stream_events(f"stream:{context.correlation_id}")
            ],
        )

    def _approve(self, context, request, capability):
        fs = self.foundation
        candidate = FoundationResult.model_validate_json(fs.blobs.get(request.candidate_blob))
        for snapshot in [candidate.case_snapshot, candidate.corpus_snapshot]:
            fs.cases.snapshots.get(
                SnapshotRef(
                    snapshot_id=snapshot.snapshot_id, membership_digest=snapshot.membership_digest
                )
            )
        profile = self.cases.profiles.get(candidate.profile)
        case = json.loads(fs.blobs.get(candidate.case_snapshot.membership_blob))
        corpus = json.loads(fs.blobs.get(candidate.corpus_snapshot.membership_blob))
        if ProfileRef.model_validate(case["profile"]) != candidate.profile:
            raise ValueError("case membership does not pin the candidate profile")
        service_root = context.model_copy(update={"actor": self.service_actor})
        # If a stage committed before interruption, its exact operation replay and
        # subsequent compare-and-swap checks remain authoritative for manual recovery.
        for scope, expected, stage in [
            (case["manifest"]["case_id"], candidate.case_snapshot.snapshot_id, "snapshot.case"),
            ("corpus:initial", candidate.corpus_snapshot.snapshot_id, "snapshot.corpus"),
        ]:
            if self.kernel.get_result(fs._context(service_root, stage).operation_id) is None:
                head = self.cases.snapshots.head(scope)
                if head is None or head.snapshot_id != expected:
                    raise ValueError("STALE_REVIEW: candidate snapshot head changed")
        publish_context = fs._context(service_root, "profile.reviewed_draft")
        if self.kernel.get_result(publish_context.operation_id) is None:
            if self.cases.profiles.head(candidate.profile.profile_id) != candidate.profile:
                raise ValueError("STALE_REVIEW: candidate profile head changed")
        suffix = context.operation_id.split(":", 1)[1]
        provision_ids = {
            p["provision_version_id"]: p["provision_version_id"] + f"_{suffix}"
            for p in corpus["provisions"]
        }
        source_ids = {
            s["source_version_id"]: s["source_version_id"] + f"_{suffix}"
            for s in corpus["source_versions"]
        }
        assertion_ids = {
            a["assertion_id"]: a["assertion_id"] + f"_{suffix}" for a in corpus["applicability"]
        }
        assertion_by_provision = {
            p["provision_version_id"]: assertion_ids[p["applicability_assertion_id"]]
            for p in corpus["provisions"]
        }
        for source in corpus["source_versions"]:
            source["source_version_id"] = source_ids[source["source_version_id"]]
            source["review_state"] = "APPROVED"
        for provision in corpus["provisions"]:
            provision["provision_version_id"] = provision_ids[provision["provision_version_id"]]
            provision["source_version_id"] = source_ids[provision["source_version_id"]]
            provision["applicability_assertion_id"] = assertion_ids[
                provision["applicability_assertion_id"]
            ]
            provision["review_state"] = "APPROVED"
        for assertion in corpus["applicability"]:
            assertion["assertion_id"] = assertion_ids[assertion["assertion_id"]]
            assertion["provision_version_id"] = provision_ids[assertion["provision_version_id"]]
            assertion["interval"]["review_state"] = "APPROVED"
            # Approval records acceptance of this uncertainty, never invented dates.
            assertion["scope_notes"] += (
                f" Accepted qualification: {request.accepted_qualifications}"
            )
        definition = profile.model_dump(mode="json", include=set(ProfileDefinition.model_fields))
        refs = [ref for rule in definition["eligibility_rules"] for ref in rule["source_refs"]]
        refs += definition["purchase_ceiling_policy"]["source_refs"]
        refs += definition["purchase_ceiling_policy"]["applicability_refs"]
        for ref in refs:
            if ref["ref_id"] in provision_ids:
                ref["ref_id"] = provision_ids[ref["ref_id"]]
        for ref in definition["applicability_assertion_refs"]:
            if ref["ref_id"] in assertion_by_provision:
                ref["ref_kind"] = "RECORD"
                ref["ref_id"] = assertion_by_provision[ref["ref_id"]]
        draft = self.cases.publish_profile(
            publish_context,
            ProfilePublication(
                profile_id=profile.profile_id,
                profile_version=request.reviewed_profile_version,
                expected_head=candidate.profile,
                definition=ProfileDefinition.model_validate(definition),
            ),
            capability=self.service_capability,
        )
        self._require(draft)
        reviewed = self.cases.review_profile(
            fs._context(context, "review.profile"),
            ProfileReview(
                target=ProfileRef(
                    profile_id=draft.output.profile_id,
                    profile_version=draft.output.profile_version,
                    digest=draft.output.digest,
                ),
                new_profile_version=request.approved_profile_version,
                decision="APPROVE",
                reason=request.accepted_qualifications,
            ),
            capability=capability,
        )
        self._require(reviewed)
        approved_profile = ProfileRef(
            profile_id=reviewed.output.profile_id,
            profile_version=reviewed.output.profile_version,
            digest=reviewed.output.digest,
        )
        review = {
            "approval_reference": request.approval_reference,
            "actor": context.actor.model_dump(mode="json"),
            "review_operation_id": context.operation_id,
            "accepted_qualifications": request.accepted_qualifications,
        }
        corpus["review"] = review
        corpus_draft = fs._publish(
            service_root,
            request.reviewed_corpus_snapshot_id,
            "CORPUS",
            "corpus:initial",
            candidate.corpus_snapshot.snapshot_id,
            corpus,
            json.loads(fs.blobs.get(candidate.corpus_snapshot.coverage_blob)),
            [fs.catalog.get_receipt(i) for i in candidate.corpus_snapshot.source_receipt_ids],
            self.service_capability,
        )
        corpus_final = self._review_snapshot(
            context,
            corpus_draft,
            request.approved_corpus_snapshot_id,
            "corpus:initial",
            "review.corpus",
            request,
            capability,
        )
        case["profile"] = approved_profile.model_dump(mode="json")
        case["corpus_snapshot"] = SnapshotRef(
            snapshot_id=corpus_final.snapshot_id, membership_digest=corpus_final.membership_digest
        ).model_dump(mode="json")
        case["review"] = review
        case_draft = fs._publish(
            service_root,
            request.reviewed_case_snapshot_id,
            "CASE",
            case["manifest"]["case_id"],
            candidate.case_snapshot.snapshot_id,
            case,
            json.loads(fs.blobs.get(candidate.case_snapshot.coverage_blob)),
            [fs.catalog.get_receipt(i) for i in candidate.case_snapshot.source_receipt_ids],
            self.service_capability,
        )
        case_final = self._review_snapshot(
            context,
            case_draft,
            request.approved_case_snapshot_id,
            case["manifest"]["case_id"],
            "review.case",
            request,
            capability,
        )
        qualification = Issue(
            issue_id="issue:cp1_qualified_scope",
            code="APPLICABILITY_UNRESOLVED",
            severity="WARNING",
            message=request.accepted_qualifications,
            field_path=None,
            evidence_refs=[],
            retryable=False,
        )
        data = candidate.model_dump(mode="json") | {
            "case_snapshot": case_final.model_dump(mode="json"),
            "corpus_snapshot": corpus_final.model_dump(mode="json"),
            "profile": approved_profile.model_dump(mode="json"),
            "issues": [qualification.model_dump(mode="json")]
            + [
                i.model_dump(mode="json")
                for i in candidate.issues
                if i.code != "UNAPPROVED_PROFILE"
            ],
        }
        return FoundationResult.model_validate(data)

    @staticmethod
    def _require(result):
        if result.status != "SUCCESS":
            raise ValueError(f"foundation review stage failed: {result.issues}")

    def _review_snapshot(self, context, snapshot, new_id, scope, stage, request, capability):
        result = self.cases.review_snapshot(
            self.foundation._context(context, stage),
            SnapshotReview(
                scope_id=scope,
                target_snapshot_id=snapshot.snapshot_id,
                target_membership_digest=snapshot.membership_digest,
                expected_head=snapshot.snapshot_id,
                new_snapshot_id=new_id,
                decision="APPROVE",
                reason=request.accepted_qualifications,
            ),
            capability=capability,
        )
        self._require(result)
        return result.output
