"""A03 profile persistence uses synthetic policy content, never real legal approval."""

import pytest
from pydantic import ValidationError

from recycleguard.case_service import CaseService
from recycleguard.contracts.artifacts import ProfileRef
from recycleguard.contracts.audit import OperationResult
from recycleguard.contracts.profiles import ProfileDefinition, ProfilePublication, ProfileReview
from recycleguard.profiles import ProfileError, ProfileStore
from recycleguard.snapshots import SnapshotStore
from recycleguard.storage import ArtifactCatalog, AuditKernel, BlobStore
from recycleguard.storage.authority import LocalAuthority, TrustedPrincipal
from tests.unit.test_v02_storage import _actor, _artifact_revision, _context, _intent


def definition(artifact):
    evidence = {
        "ref_kind": "PROVISION",
        "ref_id": "provision:fixture",
        "artifact_revision_id": artifact.artifact_revision_id,
        "locator": None,
    }
    return ProfileDefinition.model_validate(
        {
            "supported_regime": "EWASTE_EPR_SUPPLIED_TARGETS",
            "target_basis": "SUPPLIED_METAL_WISE_OBLIGATIONS",
            "supported_components": ["SUPPORTED_ALLOCATIONS", "HISTORICAL_LIABILITIES"],
            "allowed_metals": ["AU", "CU"],
            "category_scope": ["FIXTURE_ONLY"],
            "applicability_assertion_refs": [evidence],
            "eligibility_rules": [
                {
                    "condition": name,
                    "testability": "UNAVAILABLE",
                    "missing_fact_outcome": "UNRESOLVED",
                    "source_refs": [evidence],
                }
                for name in (
                    "ENTITY",
                    "PERIOD",
                    "METAL",
                    "CATEGORY",
                    "LIFECYCLE",
                    "CAPABILITY",
                    "REGISTRATION",
                    "ACHIEVEMENT_DEADLINE",
                    "CREDIT_EVENT_DEADLINE",
                )
            ],
            "allocation_policy": {
                "priority_check": "EARLIER_COMPATIBLE_AT_ALLOCATION_TIME",
                "missing_history_outcome": "LIABILITY_PRIORITY_UNRESOLVED",
                "prohibited_allocation_outcome": "EARLIER_LIABILITY_UNMET",
                "supported_basis": "SUPPORTED_ALLOCATIONS_ONLY",
                "historical_buckets": "SEPARATE",
            },
            "event_equivalence_policy": {
                "policy_version": "fixture",
                "required_exact_fields": [
                    "CERTIFICATE_LOT",
                    "KIND_STAGE",
                    "TIME_VALUE_PRECISION_TIMEZONE",
                    "QUANTITY_DIMENSION_METAL",
                    "FROM_TO_PARTIES",
                ],
                "corroboration": "EXTERNAL_ID_OR_COMPLETE_KEY_WITH_SOURCE_CONTINUITY",
                "missing_or_conflicting_outcome": "PENDING",
                "coarse_time_collision_outcome": "PENDING",
            },
            "purchase_ceiling_policy": {
                "state": "DISABLED_REVIEW_REQUIRED",
                "source_refs": [],
                "applicability_refs": [],
                "current_liability_basis": None,
                "prior_liability_basis": None,
                "buffer_rate": None,
                "review_ref": None,
            },
            "numeric_policy": {
                "precision": 28,
                "display_places": 4,
                "rounding": "ROUND_HALF_EVEN",
                "trap_inexact": True,
                "trap_overflow": True,
                "rounding_stage": "FINAL_DISPLAY_ONLY",
            },
            "unsupported_features": [
                "GOLD_OFFSETS",
                "REFURBISHING_DEFERRALS",
                "SALES_DERIVED_TARGETS",
                "TAX_PRICING",
                "SOLAR",
                "ENVIRONMENTAL_COMPENSATION",
            ],
            "source_dependencies": [
                {
                    "artifact_revision_id": artifact.artifact_revision_id,
                    "blob_digest": artifact.blob.sha256,
                }
            ],
        }
    )


def reference(profile):
    return ProfileRef(
        profile_id=profile.profile_id,
        profile_version=profile.profile_version,
        digest=profile.digest,
    )


def setup(tmp_path):
    blobs = BlobStore(tmp_path)
    human = _actor().model_copy(
        update={
            "actor_id": "human:reviewer",
            "actor_kind": "HUMAN",
            "authenticated_session_ref": "session:verified_test",
        }
    )
    authority = LocalAuthority(
        {
            "service": TrustedPrincipal(_actor(), frozenset({"intake.", "profile.", "snapshot."})),
            "human": TrustedPrincipal(human, frozenset({"review."})),
        }
    )
    cap, review_cap = authority.issue("service"), authority.issue("human")
    kernel = AuditKernel(tmp_path / "db.sqlite", blobs, authority=authority)
    catalog = ArtifactCatalog(tmp_path / "db.sqlite", blobs, kernel=kernel)
    profiles = ProfileStore(kernel, catalog)
    service = CaseService(SnapshotStore(kernel, catalog), profiles)
    artifact = _artifact_revision(blobs)
    intent = _intent(blobs, _context("fixture_intake"))
    kernel.commit_intent(intent, capability=cap)
    kernel.commit_result(
        intent,
        OperationResult(
            operation_id=intent.context.operation_id,
            attempt_id=intent.context.attempt_id,
            status="SUCCESS",
            payload=intent.payload,
        ),
        capability=cap,
        mutation=lambda: catalog.put_artifact_revision(artifact),
    )
    request = ProfilePublication(
        profile_id="profile:test",
        profile_version="draft",
        expected_head=None,
        definition=definition(artifact),
    )
    return service, request, cap, review_cap, human


@pytest.mark.parametrize("decision,state", [("APPROVE", "APPROVED"), ("REJECT", "REJECTED")])
def test_profile_roundtrip_replay_review_and_reopen(tmp_path, decision, state):
    service, request, cap, review_cap, human = setup(tmp_path)
    context = _context("publish")
    first = service.publish_profile(context, request, capability=cap)
    assert first.status == "SUCCESS" and first.audit_event_ids
    assert service.publish_profile(context, request, capability=cap) == first
    original = service.profiles.get(reference(first.output)).model_dump_json()
    with pytest.raises(ProfileError, match="approved"):
        service.profiles.get(reference(first.output), require_approved=True)
    review = ProfileReview(
        target=reference(first.output),
        new_profile_version="reviewed",
        decision=decision,
        reason="Synthetic fixture review only",
    )
    ctx = _context("review").model_copy(update={"actor": human})
    result = service.review_profile(ctx, review, capability=review_cap)
    assert result.status == "SUCCESS" and result.output.review_state == state
    assert service.review_profile(ctx, review, capability=review_cap) == result
    assert service.profiles.get(reference(first.output)).model_dump_json() == original
    assert result.output.digest != first.output.digest
    assert result.output.review_refs == [ctx.operation_id]
    if decision == "APPROVE":
        assert (
            service.profiles.get(reference(result.output), require_approved=True) == result.output
        )
    service.kernel.close()
    blobs = BlobStore(tmp_path)
    kernel = AuditKernel(tmp_path / "db.sqlite", blobs)
    catalog = ArtifactCatalog(tmp_path / "db.sqlite", blobs, kernel=kernel)
    reopened = ProfileStore(kernel, catalog)
    assert reopened.head("profile:test") == reference(result.output)
    assert reopened.get(reference(first.output)).model_dump_json() == original
    kernel.close()


@pytest.mark.parametrize(
    "change,code",
    [
        ("stale", "CONCURRENT_MODIFICATION"),
        ("digest", "STALE_REVIEW"),
        ("service", "ACCESS_DENIED"),
    ],
)
def test_review_conflicts_and_capability_boundaries(tmp_path, change, code):
    service, request, cap, review_cap, human = setup(tmp_path)
    draft = service.publish_profile(_context("draft"), request, capability=cap).output
    target = reference(draft)
    if change == "stale":
        request2 = request.model_copy(update={"profile_version": "new", "expected_head": target})
        assert (
            service.publish_profile(_context("new"), request2, capability=cap).status == "SUCCESS"
        )
    if change == "digest":
        target = target.model_copy(update={"digest": "0" * 64})
    review = ProfileReview(
        target=target, new_profile_version="reviewed", decision="APPROVE", reason="Fixture"
    )
    context = _context("review").model_copy(update={"actor": human})
    result = service.review_profile(
        context, review, capability=cap if change == "service" else review_cap
    )
    assert result.status == "REJECTED" and result.issues[0].code == code
    assert result.output is None
    if change != "service":
        replay = service.review_profile(context, review, capability=review_cap)
        assert replay.issues[0].code == code and replay.audit_event_ids == result.audit_event_ids
    else:
        assert service.kernel.get_intent(context.operation_id) is None
    service.kernel.close()


@pytest.mark.parametrize(
    "fault,code",
    [("missing", "MISSING_ARTIFACT"), ("hash", "HASH_MISMATCH"), ("unpinned", "MISSING_ARTIFACT")],
)
def test_dependency_failures_are_audited(tmp_path, fault, code):
    service, request, cap, _, _ = setup(tmp_path)
    data = request.model_dump(mode="json")
    if fault == "missing":
        data["definition"]["source_dependencies"][0]["artifact_revision_id"] = (
            "artifact_revision:absent"
        )
    elif fault == "hash":
        data["definition"]["source_dependencies"][0]["blob_digest"] = "0" * 64
    else:
        data["definition"]["applicability_assertion_refs"][0]["artifact_revision_id"] = None
    request = ProfilePublication.model_validate(data)
    result = service.publish_profile(_context("bad"), request, capability=cap)
    assert result.status == "REJECTED" and result.issues[0].code == code
    assert result.audit_event_ids and service.profiles.head(request.profile_id) is None
    service.kernel.close()


def test_audit_failure_cannot_commit_profile(tmp_path):
    service, request, cap, _, _ = setup(tmp_path)
    service.kernel.connection.execute("""CREATE TRIGGER fail_event BEFORE INSERT ON audit_events
        BEGIN SELECT RAISE(ABORT,'test audit unavailable'); END""")
    result = service.publish_profile(_context("fail"), request, capability=cap)
    assert result.status == "OUTCOME_UNKNOWN" and result.issues[0].code == "AUDIT_UNAVAILABLE"
    assert service.profiles.head(request.profile_id) is None
    assert service.kernel.get_result("operation:fail") is None
    service.kernel.close()


def test_pinned_source_bytes_reverified_before_calculation(tmp_path):
    service, request, cap, review_cap, human = setup(tmp_path)
    draft = service.publish_profile(_context("draft"), request, capability=cap).output
    reviewed = service.review_profile(
        _context("review").model_copy(update={"actor": human}),
        ProfileReview(
            target=reference(draft),
            new_profile_version="approved",
            decision="APPROVE",
            reason="Fixture",
        ),
        capability=review_cap,
    ).output
    dependency = reviewed.source_dependencies[0]
    path = service.kernel.blob_store.objects / dependency.blob_digest[:2] / dependency.blob_digest
    path.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="mismatch"):
        service.profiles.get(reference(reviewed), require_approved=True)
    service.kernel.close()


def test_conflicting_operation_cannot_leak_or_replace_archived_output(tmp_path):
    service, request, cap, _, _ = setup(tmp_path)
    context = _context("same")
    first = service.publish_profile(context, request, capability=cap)
    changed = request.model_copy(update={"profile_version": "different"})
    result = service.publish_profile(context, changed, capability=cap)
    assert result.status == "REJECTED" and result.output is None and result.output_blob is None
    assert result.issues[0].code == "CONCURRENT_MODIFICATION"
    assert service.profiles.head(request.profile_id) == reference(first.output)
    service.kernel.close()


@pytest.mark.parametrize(
    "path,value",
    [
        ("target_basis", "SALES"),
        ("allowed_metals", ["PT"]),
        ("eligibility_rules", []),
        ("unsupported_features", []),
    ],
)
def test_invalid_policy_rejected_at_boundary(tmp_path, path, value):
    service, request, _, _, _ = setup(tmp_path)
    data = request.definition.model_dump(mode="json")
    data[path] = value
    with pytest.raises(ValidationError):
        ProfileDefinition.model_validate(data)
    service.kernel.close()


def test_missing_event_key_and_ceiling_approval_cannot_be_silently_enabled(tmp_path):
    service, request, cap, _, _ = setup(tmp_path)
    data = request.definition.model_dump(mode="json")
    data["event_equivalence_policy"]["required_exact_fields"].pop()
    with pytest.raises(ValidationError):
        ProfileDefinition.model_validate(data)
    data = request.model_dump(mode="json")
    evidence = data["definition"]["applicability_assertion_refs"]
    data["definition"]["purchase_ceiling_policy"] = {
        "state": "APPROVED",
        "source_refs": evidence,
        "applicability_refs": evidence,
        "current_liability_basis": "fixture",
        "prior_liability_basis": "fixture",
        "buffer_rate": "0.05",
        "review_ref": "operation:fixture_intake",
    }
    result = service.publish_profile(
        _context("ceiling"), ProfilePublication.model_validate(data), capability=cap
    )
    assert result.issues[0].code == "UNAPPROVED_PROFILE"
    service.kernel.close()
