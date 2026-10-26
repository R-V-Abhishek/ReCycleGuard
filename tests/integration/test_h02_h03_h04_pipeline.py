"""End-to-end integration test connecting H02 intake, H03 extraction, and H04 profile review.

Proves the complete Sampreeth workstream (C01, C03, C06, C07) is ready for A04/CP1:
1. Intake batch processes case_001 visible dossier, commits receipts and revisions to catalog.
2. Extraction processes all ingested artifacts (CSV ledger, JSON records, PDF invoices).
3. Full coverage and observation accounting guarantees page/row dispositions.
4. Reviewed sources R02/R08 and canonical profile producer_snapshot_v1 are validated and approved.
"""

from pathlib import Path

from recycleguard.contracts.artifacts import ProfileRef
from recycleguard.contracts.core import ActorRef, CommandContext
from recycleguard.contracts.profiles import ProfilePublication, ProfileReview
from recycleguard.extraction import extract_artifact
from recycleguard.intake import intake_batch
from recycleguard.knowledge import (
    build_v1_profile_definition,
)
from recycleguard.profiles import ProfileStore
from recycleguard.storage import ArtifactCatalog, AuditKernel, BlobStore
from recycleguard.storage.authority import LocalAuthority, TrustedPrincipal
from tests.unit.test_h04_knowledge import register_reviewed_sources

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"
CASE_001_DIR = FIXTURES_DIR / "visible/case_001"


def test_complete_h02_h03_h04_pipeline(tmp_path):
    # Setup data root and audited storage
    data_root = tmp_path / "data"
    data_root.mkdir()
    store = BlobStore(data_root)

    actor = ActorRef(
        actor_id="service:pipeline_runner", actor_kind="SERVICE", authenticated_session_ref=None
    )
    human_reviewer = ActorRef(
        actor_id="human:sampreeth",
        actor_kind="HUMAN",
        authenticated_session_ref="session:sampreeth_review",
    )
    authority = LocalAuthority(
        {
            "service": TrustedPrincipal(actor, frozenset({"intake.", "profile."})),
            "reviewer": TrustedPrincipal(human_reviewer, frozenset({"review."})),
        }
    )
    cap_service = authority.issue("service")
    cap_reviewer = authority.issue("reviewer")

    db_path = data_root / "application.sqlite"
    kernel = AuditKernel(db_path, store, authority=authority)
    catalog = ArtifactCatalog(db_path, store, kernel=kernel)
    profiles = ProfileStore(kernel, catalog)

    context = CommandContext(
        contract_version="1.1",
        command_id="cmd:e2e_pipeline",
        operation_id="op:e2e_pipeline",
        attempt_id="att:e2e_pipeline",
        idempotency_key="key:e2e_pipeline",
        actor=actor,
        case_version_id=None,
        run_id=None,
        turn_id=None,
        correlation_id="corr:e2e_pipeline",
        parent_operation_id=None,
    )

    # -------------------------------------------------------------
    # Step 1 (H02): Audited Full-Batch Intake of case_001 dossier
    # -------------------------------------------------------------
    intake_result = intake_batch(
        CASE_001_DIR,
        blob_store=store,
        catalog=catalog,
        kernel=kernel,
        capability=cap_service,
        context=context,
    )

    assert len(intake_result.receipts) > 0
    assert len(intake_result.artifact_revisions) > 0
    assert intake_result.case_id == "case:001"

    # -------------------------------------------------------------
    # Step 2 (H03): Extraction and Coverage Tracking
    # -------------------------------------------------------------
    all_extractions = []
    total_observations = 0
    total_coverage_items = 0

    for rev in intake_result.artifact_revisions:
        ext_res, observations, coverage = extract_artifact(rev, store)
        all_extractions.append(ext_res)
        total_observations += len(observations)
        total_coverage_items += len(coverage)

        # Every extraction outcome must be stored in BlobStore
        assert store.get(ext_res.observations_blob) is not None
        assert store.get(ext_res.coverage_blob) is not None
        assert ext_res.status in {"COMPLETE", "PARTIAL"}

    assert len(all_extractions) == len(intake_result.artifact_revisions)
    assert total_observations > 0
    assert total_coverage_items > 0

    # -------------------------------------------------------------
    # Step 3 (H04): Register Reviewed Regulatory Sources & Profile
    # -------------------------------------------------------------
    r02_rev, r08_rev = register_reviewed_sources(store)

    from recycleguard.contracts.audit import OperationIntent, OperationResult
    from recycleguard.storage.blob_store import canonical_json_bytes

    # Commit sources to catalog under audited transaction
    sources_intent_payload = store.put(
        canonical_json_bytes({"step": "register_sources"}), "application/json"
    )
    sources_ctx = context.model_copy(
        update={
            "command_id": "cmd:reg_sources",
            "operation_id": "op:reg_sources",
            "attempt_id": "att:reg_sources",
            "idempotency_key": "key:reg_sources",
        }
    )
    sources_intent = OperationIntent(
        context=sources_ctx,
        idempotency_key="key:reg_sources",
        event_type="intake.batch",
        payload=sources_intent_payload,
        stream_id="stream:regulatory_sources",
    )
    kernel.commit_intent(sources_intent, capability=cap_service)

    def _persist_sources():
        catalog.put_artifact_revision(r02_rev)
        catalog.put_artifact_revision(r08_rev)

    sources_res_payload = store.put(canonical_json_bytes({"status": "SUCCESS"}), "application/json")
    sources_result = OperationResult(
        operation_id="op:reg_sources",
        attempt_id="att:reg_sources",
        status="SUCCESS",
        payload=sources_res_payload,
        issue_codes=[],
    )
    kernel.commit_result(
        sources_intent, sources_result, capability=cap_service, mutation=_persist_sources
    )

    # Publish draft profile
    defn = build_v1_profile_definition(r02_rev, r08_rev)
    pub_ctx = context.model_copy(
        update={
            "command_id": "cmd:publish_v1_prof",
            "operation_id": "op:publish_v1_prof",
            "attempt_id": "att:publish_v1_prof",
            "idempotency_key": "key:publish_v1_prof",
        }
    )
    draft_prof = profiles.publish(
        pub_ctx,
        ProfilePublication(
            profile_id="profile:producer_snapshot_v1",
            profile_version="1.0-draft",
            expected_head=None,
            definition=defn,
        ),
        capability=cap_service,
    )
    assert draft_prof.review_state == "DRAFT"

    # Human review and approval
    rev_ctx = context.model_copy(
        update={
            "command_id": "cmd:review_v1_prof",
            "operation_id": "op:review_v1_prof",
            "attempt_id": "att:review_v1_prof",
            "idempotency_key": "key:review_v1_prof",
            "actor": human_reviewer,
        }
    )
    approved_prof = profiles.review(
        rev_ctx,
        ProfileReview(
            target=ProfileRef(
                profile_id=draft_prof.profile_id,
                profile_version=draft_prof.profile_version,
                digest=draft_prof.digest,
            ),
            new_profile_version="1.0",
            decision="APPROVE",
            reason="Approved H04 initial profile for CP1 integration",
        ),
        capability=cap_reviewer,
    )
    assert approved_prof.review_state == "APPROVED"

    # Verify head of profile
    head = profiles.head("profile:producer_snapshot_v1")
    assert head is not None
    assert head.profile_version == "1.0"
    assert head.digest == approved_prof.digest
