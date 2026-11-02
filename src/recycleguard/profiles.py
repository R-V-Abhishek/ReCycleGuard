"""Immutable profile revisions and exact-head review on the shared audit transaction."""

from recycleguard.contracts.artifacts import ProfileRef
from recycleguard.contracts.audit import OperationIntent, OperationResult
from recycleguard.contracts.profiles import (
    CalculationProfile,
    ProfilePublication,
    ProfileReview,
    profile_digest,
)
from recycleguard.storage import ArtifactCatalog, AuditKernel, canonical_json_bytes
from recycleguard.storage.catalog import CatalogError


class ProfileError(CatalogError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class ProfileStore:
    def __init__(self, kernel: AuditKernel, catalog: ArtifactCatalog):
        if catalog.kernel is not kernel or kernel.connection.in_transaction:
            raise ValueError("profile store requires the shared idle audit coordinator")
        self.kernel, self.catalog = kernel, catalog
        kernel.connection.executescript("""
            CREATE TABLE IF NOT EXISTS profile_revisions (
                profile_id TEXT NOT NULL, profile_version TEXT NOT NULL,
                digest TEXT NOT NULL, parent_version TEXT, profile_json TEXT NOT NULL,
                PRIMARY KEY(profile_id, profile_version)
            );
            CREATE TABLE IF NOT EXISTS profile_heads (
                profile_id TEXT PRIMARY KEY, profile_version TEXT NOT NULL,
                FOREIGN KEY(profile_id, profile_version)
                REFERENCES profile_revisions(profile_id, profile_version)
            );
        """)

    def get(self, reference: ProfileRef, *, require_approved=False) -> CalculationProfile:
        row = self.kernel.connection.execute(
            "SELECT profile_json FROM profile_revisions WHERE profile_id=? AND profile_version=?",
            (reference.profile_id, reference.profile_version),
        ).fetchone()
        if row is None:
            raise ProfileError("MISSING_ARTIFACT", "profile revision is missing")
        result = CalculationProfile.model_validate_json(row["profile_json"])
        if result.digest != reference.digest:
            raise ProfileError("STALE_REVIEW", "profile digest does not match pinned revision")
        if require_approved and result.review_state != "APPROVED":
            raise ProfileError("UNAPPROVED_PROFILE", "calculations require an approved revision")
        self._dependencies(result)
        return result

    def head(self, profile_id: str) -> ProfileRef | None:
        row = self.kernel.connection.execute(
            "SELECT r.profile_version,r.digest FROM profile_heads h JOIN profile_revisions r "
            "USING(profile_id,profile_version) WHERE h.profile_id=?",
            (profile_id,),
        ).fetchone()
        return (
            None
            if row is None
            else ProfileRef(
                profile_id=profile_id, profile_version=row["profile_version"], digest=row["digest"]
            )
        )

    def _dependencies(self, definition):
        pinned = {dep.artifact_revision_id for dep in definition.source_dependencies}
        for dependency in definition.source_dependencies:
            try:
                artifact = self.catalog.get_artifact_revision(dependency.artifact_revision_id)
            except KeyError as exc:
                raise ProfileError(
                    "MISSING_ARTIFACT", "profile source revision is missing"
                ) from exc
            if artifact.blob.sha256 != dependency.blob_digest:
                raise ProfileError("HASH_MISMATCH", "profile source digest mismatch")
            self.kernel.blob_store.get(artifact.blob)
        refs = list(definition.applicability_assertion_refs)
        refs.extend(ref for rule in definition.eligibility_rules for ref in rule.source_refs)
        ceiling = definition.purchase_ceiling_policy
        refs.extend(ceiling.source_refs + ceiling.applicability_refs)
        if any(ref.artifact_revision_id not in pinned for ref in refs):
            raise ProfileError(
                "MISSING_ARTIFACT", "policy evidence must bind a pinned source revision"
            )
        if ceiling.state == "APPROVED":
            intent = self.kernel.get_intent(ceiling.review_ref)
            result = self.kernel.get_result(ceiling.review_ref)
            # Only a dedicated review of these exact policy bytes could authorize
            # this slot. A successful unrelated snapshot/profile review cannot.
            expected = canonical_json_bytes(
                ceiling.model_dump(mode="json", exclude={"review_ref", "state"})
            )
            if (
                intent is None
                or result is None
                or result.status != "SUCCESS"
                or intent.context.actor.actor_kind != "HUMAN"
                or intent.event_type != "review.purchase_ceiling"
                or self.kernel.blob_store.get(intent.payload) != expected
            ):
                raise ProfileError(
                    "UNAPPROVED_PROFILE", "purchase ceiling lacks audited human review"
                )

    def _begin(self, context, request, event_type, capability):
        self.kernel.authority.check(capability, context.actor, event_type)
        payload = self.kernel.blob_store.put(
            canonical_json_bytes(request.model_dump(mode="json")), "application/json"
        )
        profile_id = (
            request.profile_id if event_type == "profile.publish" else request.target.profile_id
        )
        intent = OperationIntent(
            context=context,
            idempotency_key=context.idempotency_key,
            event_type=event_type,
            payload=payload,
            stream_id=f"stream:{profile_id}",
        )
        self.kernel.commit_intent(intent, capability=capability)
        result = self.kernel.get_result(context.operation_id)
        if result is not None:
            if result.status != "SUCCESS":
                raise ProfileError(result.issue_codes[0], "profile operation was rejected")
            return intent, CalculationProfile.model_validate_json(
                self.kernel.blob_store.get(result.payload)
            )
        return intent, None

    def _commit(self, intent, request, capability, build):
        try:
            profile, expected = build()
            self._dependencies(profile)
            payload = self.kernel.blob_store.put(
                canonical_json_bytes(profile.model_dump(mode="json")), "application/json"
            )
            result = OperationResult(
                operation_id=intent.context.operation_id,
                attempt_id=intent.context.attempt_id,
                status="SUCCESS",
                payload=payload,
            )

            def mutation():
                if self.head(profile.profile_id) != expected:
                    raise ProfileError("CONCURRENT_MODIFICATION", "profile head changed")
                if self.kernel.connection.execute(
                    "SELECT 1 FROM profile_revisions WHERE profile_id=? AND profile_version=?",
                    (profile.profile_id, profile.profile_version),
                ).fetchone():
                    raise ProfileError("CONCURRENT_MODIFICATION", "profile version already exists")
                self.kernel.connection.execute(
                    "INSERT INTO profile_revisions VALUES (?,?,?,?,?)",
                    (
                        profile.profile_id,
                        profile.profile_version,
                        profile.digest,
                        None if expected is None else expected.profile_version,
                        canonical_json_bytes(profile.model_dump(mode="json")).decode("utf-8"),
                    ),
                )
                self.kernel.connection.execute(
                    "INSERT INTO profile_heads VALUES (?,?) ON CONFLICT(profile_id) "
                    "DO UPDATE SET profile_version=excluded.profile_version",
                    (profile.profile_id, profile.profile_version),
                )

            self.kernel.commit_result(intent, result, capability=capability, mutation=mutation)
            return profile
        except ProfileError as exc:
            payload = self.kernel.blob_store.put(
                canonical_json_bytes({"message": str(exc)}), "application/json"
            )
            self.kernel.commit_result(
                intent,
                OperationResult(
                    operation_id=intent.context.operation_id,
                    attempt_id=intent.context.attempt_id,
                    status="REJECTED",
                    payload=payload,
                    issue_codes=[exc.code],
                ),
                capability=capability,
            )
            raise

    def publish(self, context, request: ProfilePublication, *, capability):
        intent, replay = self._begin(context, request, "profile.publish", capability)
        if replay is not None:
            return replay

        def build():
            if (
                request.expected_head is not None
                and request.expected_head.profile_id != request.profile_id
            ):
                raise ProfileError("INVALID_SCHEMA", "expected head belongs to another profile")
            data = request.definition.model_dump(mode="json") | {
                "profile_id": request.profile_id,
                "profile_version": request.profile_version,
                "review_state": "DRAFT",
                "review_refs": [],
            }
            return CalculationProfile(**data, digest=profile_digest(data)), request.expected_head

        return self._commit(intent, request, capability, build)

    def review(self, context, request: ProfileReview, *, capability):
        intent, replay = self._begin(context, request, "review.profile", capability)
        if replay is not None:
            return replay

        def build():
            target = self.get(request.target)
            if target.review_state != "DRAFT":
                raise ProfileError("STALE_REVIEW", "only draft profiles can be reviewed")
            data = target.model_dump(mode="json", exclude={"digest"}) | {
                "profile_version": request.new_profile_version,
                "review_state": "APPROVED" if request.decision == "APPROVE" else "REJECTED",
                "review_refs": [context.operation_id],
            }
            return CalculationProfile(**data, digest=profile_digest(data)), request.target

        return self._commit(intent, request, capability, build)
