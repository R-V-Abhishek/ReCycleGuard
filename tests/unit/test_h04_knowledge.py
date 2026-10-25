"""Unit and regression tests for H04 regulatory review and v1 profile content.

Verifies:
- Authentic R02 and R08 sources and provisions are registered.
- Canonical CalculationProfile for producer_snapshot_v1 matches CONTRACTS §4.2.
- Exact profile digest is reproducible and matches profile definition.
- Profile dependencies enforce that all pinned sources exist in ArtifactCatalog and BlobStore.
- ProfileStore validates approved status and unapproved profile rejection.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from recycleguard.contracts.artifacts import ProfileRef
from recycleguard.contracts.core import ActorRef, CommandContext
from recycleguard.contracts.profiles import (
    CalculationProfile,
    ProfileDefinition,
    ProfilePublication,
    ProfileReview,
    profile_digest,
)
from recycleguard.knowledge import (
    R02_ARTIFACT_REV_ID,
    R08_ARTIFACT_REV_ID,
    build_v1_calculation_profile,
    build_v1_profile_definition,
    get_reviewed_provisions,
    register_reviewed_sources,
)
from recycleguard.profiles import ProfileError, ProfileStore
from recycleguard.storage import ArtifactCatalog, AuditKernel, BlobStore
from recycleguard.storage.authority import LocalAuthority, TrustedPrincipal


def test_reviewed_sources_and_provisions_registration(tmp_path):
    store = BlobStore(tmp_path / "blobs")
    r02_rev, r08_rev = register_reviewed_sources(store)

    assert r02_rev.artifact_revision_id == R02_ARTIFACT_REV_ID
    assert r08_rev.artifact_revision_id == R08_ARTIFACT_REV_ID

    # Ensure blob bytes exist and can be retrieved
    r02_bytes = store.get(r02_rev.blob)
    r08_bytes = store.get(r08_rev.blob)
    assert len(r02_bytes) > 0
    assert len(r08_bytes) > 0

    provisions = get_reviewed_provisions(store)
    assert len(provisions) == 3

    pv_map = {pv.provision_version_id: pv for pv in provisions}
    assert "provision:r02_rule6_sub4" in pv_map
    assert "provision:r02_rule15_sub1_sub3" in pv_map
    assert "provision:r08_sec_c_recycler_capability" in pv_map

    # Check that legal paths and locators match specifications
    p6 = pv_map["provision:r02_rule6_sub4"]
    assert p6.role_scope == "SPECIFIC"
    assert p6.affected_roles == ["PRODUCER"]
    assert p6.locator.page_index_1based == 8

    p15 = pv_map["provision:r02_rule15_sub1_sub3"]
    assert p15.role_scope == "GENERAL"
    assert set(p15.affected_roles) == {"PRODUCER", "RECYCLER"}
    assert p15.locator.page_index_1based == 14

    p_faq = pv_map["provision:r08_sec_c_recycler_capability"]
    assert p_faq.locator.page_index_1based == 9


def test_v1_profile_definition_and_exact_digest(tmp_path):
    store = BlobStore(tmp_path / "blobs")
    r02_rev, r08_rev = register_reviewed_sources(store)

    defn = build_v1_profile_definition(r02_rev, r08_rev)
    assert isinstance(defn, ProfileDefinition)
    assert defn.supported_regime == "EWASTE_EPR_SUPPLIED_TARGETS"
    assert defn.target_basis == "SUPPLIED_METAL_WISE_OBLIGATIONS"
    assert defn.allowed_metals == ["AU", "CU", "AL", "FE"]
    assert defn.category_scope == ["ITEW4", "CEEW1"]
    assert len(defn.eligibility_rules) == 9
    assert len(defn.unsupported_features) == 6
    assert len(defn.source_dependencies) == 2

    # Build calculation profile
    profile = build_v1_calculation_profile(r02_rev, r08_rev, review_state="APPROVED")
    assert isinstance(profile, CalculationProfile)
    assert profile.profile_id == "profile:producer_snapshot_v1"
    assert profile.profile_version == "1.0"
    assert profile.review_state == "APPROVED"
    assert len(profile.review_refs) == 1

    # Verify digest calculation matches model digest
    expected_digest = profile_digest(profile.model_dump(mode="json", exclude={"digest"}))
    assert profile.digest == expected_digest


def test_profile_store_integration_and_dependency_verification(tmp_path):
    store = BlobStore(tmp_path / "blobs")
    r02_rev, r08_rev = register_reviewed_sources(store)

    actor = ActorRef(actor_id="service:profile_admin", actor_kind="SERVICE", authenticated_session_ref=None)
    authority = LocalAuthority({"admin": TrustedPrincipal(actor, frozenset({"profile.", "intake."}))})
    cap = authority.issue("admin")
    db_path = tmp_path / "app.sqlite"
    kernel = AuditKernel(db_path, store, authority=authority)
    catalog = ArtifactCatalog(db_path, store, kernel=kernel)
    profiles = ProfileStore(kernel, catalog)

    context = CommandContext(
        contract_version="1.1",
        command_id="cmd:prof_test",
        operation_id="op:prof_test",
        attempt_id="att:prof_test",
        idempotency_key="key:prof_test",
        actor=actor,
        case_version_id=None,
        run_id=None,
        turn_id=None,
        correlation_id="corr:prof_test",
        parent_operation_id=None,
    )

    defn = build_v1_profile_definition(r02_rev, r08_rev)
    publication = ProfilePublication(
        profile_id="profile:producer_snapshot_v1",
        profile_version="1.0-draft",
        expected_head=None,
        definition=defn,
    )

    # 1. Register artifacts into catalog within an audited transaction
    from recycleguard.contracts.audit import OperationIntent, OperationResult
    from recycleguard.storage.blob_store import canonical_json_bytes

    intent_payload = store.put(canonical_json_bytes({"init": True}), "application/json")
    intent = OperationIntent(
        context=context,
        idempotency_key=context.idempotency_key,
        event_type="intake.batch",
        payload=intent_payload,
        stream_id="stream:init_sources",
        recorded_at="2026-10-25T00:00:00Z",
    )
    kernel.commit_intent(intent, capability=cap)

    def _persist_sources():
        catalog.put_artifact_revision(r02_rev)
        catalog.put_artifact_revision(r08_rev)

    res_payload = store.put(canonical_json_bytes({"status": "sources_registered"}), "application/json")
    res = OperationResult(
        operation_id=context.operation_id,
        attempt_id=context.attempt_id,
        status="SUCCESS",
        payload=res_payload,
        issue_codes=[],
    )
    kernel.commit_result(intent, res, capability=cap, mutation=_persist_sources)

    # 2. Publish draft profile
    context_pub = context.model_copy(
        update={
            "command_id": "cmd:prof_pub",
            "operation_id": "op:prof_pub",
            "attempt_id": "att:prof_pub",
            "idempotency_key": "key:prof_pub",
        }
    )
    draft_profile = profiles.publish(context_pub, publication, capability=cap)
    assert draft_profile.review_state == "DRAFT"

    # Getting draft with require_approved=True must raise ProfileError
    pref = ProfileRef(
        profile_id=draft_profile.profile_id,
        profile_version=draft_profile.profile_version,
        digest=draft_profile.digest,
    )
    with pytest.raises(ProfileError) as exc_info:
        profiles.get(pref, require_approved=True)
    assert exc_info.value.code == "UNAPPROVED_PROFILE"

    # 3. Authenticate human reviewer and approve profile
    human_actor = ActorRef(
        actor_id="human:sampreeth",
        actor_kind="HUMAN",
        authenticated_session_ref="session:sampreeth_review",
    )
    authority_review = LocalAuthority({"reviewer": TrustedPrincipal(human_actor, frozenset({"profile."}))})
    cap_review = authority_review.issue("reviewer")

    context_review = context.model_copy(
        update={
            "command_id": "cmd:prof_rev",
            "operation_id": "op:prof_rev",
            "attempt_id": "att:prof_rev",
            "idempotency_key": "key:prof_rev",
            "actor": human_actor,
        }
    )
    review_req = ProfileReview(
        target=pref,
        new_profile_version="1.0",
        decision="APPROVE",
        reason="Initial regulatory source and profile review pursuant to H04 for CP1 baseline",
    )
    approved_profile = profiles.review(context_review, review_req, capability=cap_review)
    assert approved_profile.review_state == "APPROVED"
    assert approved_profile.profile_version == "1.0"

    # 4. Successfully fetch approved profile with require_approved=True
    approved_ref = ProfileRef(
        profile_id=approved_profile.profile_id,
        profile_version=approved_profile.profile_version,
        digest=approved_profile.digest,
    )
    fetched = profiles.get(approved_ref, require_approved=True)
    assert fetched.digest == approved_profile.digest
    assert fetched.review_state == "APPROVED"
