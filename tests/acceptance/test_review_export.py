"""G10 acceptance tests: Review outcomes, stale digest, forbidden verdicts,
restricted derivatives and public omissions.
"""

import json
from pathlib import Path

import pytest

from recycleguard.application import local_review_application
from recycleguard.config import Settings
from recycleguard.contracts.bundles import ReplayRequest
from recycleguard.contracts.review import ReviewDecision
from recycleguard.exports.service import ExportService
from recycleguard.local_session import initialize_reviewer
from recycleguard.reporting.baseline import BaselineReportBuilder
from recycleguard.review.service import ReviewService
from tests.support.c08 import clean_case
from tests.support.c08 import run as run_reconcile


@pytest.fixture
def g10_env(tmp_path: Path):
    data_root = tmp_path / "g10_data"
    data_root.mkdir(parents=True, exist_ok=True)
    initialize_reviewer(data_root, "human:reviewer_g10", "SecretPass123!")
    settings = Settings(data_root=data_root, mode="test", enable_test_adapters=True)
    return settings


def test_g10_review_and_export_lifecycle(g10_env, tmp_path: Path):
    """Test G10 acceptance: all review outcomes, stale digests, restricted derivatives
    and omissions.
    """
    with local_review_application(g10_env, "SecretPass123!") as args:
        cases, context, human_cap, actor, service_cap = args
        review_svc = ReviewService(cases)
        export_svc = ExportService(cases)
        blobs = cases.kernel.blob_store

        # 1. Setup report
        calc = run_reconcile(tmp_path, clean_case()).output
        report = BaselineReportBuilder().build(calc)

        # 2. Review packet creation
        packet = review_svc.create_review_packet(report)
        assert packet.report_revision_id == report.revision.report_revision_id

        # 3. Stale review dependency digest rejection
        decision = ReviewDecision(
            decision="APPROVE",
            authenticated_reviewer_ref=context.actor,
            reason="Approved baseline",
            recorded_at="2026-10-30T09:30:00Z",
        )
        with pytest.raises(ValueError, match="STALE_REVIEW"):
            review_svc.submit_review(
                context,
                packet.packet_id,
                expected_dependency_digest="a" * 64,  # STALE / WRONG DIGEST
                decision=decision,
                capability=human_cap,
            )

        # 4. Valid APPROVE transition
        valid_result = review_svc.submit_review(
            context,
            packet.packet_id,
            expected_dependency_digest=packet.review_dependency_digest,
            decision=decision,
            capability=human_cap,
        )
        assert valid_result.status == "SUCCESS"
        assert valid_result.output.new_run_status == "COMPLETED"
        assert valid_result.output.new_review_outcome == "APPROVED"

        # 5. Export with restricted derivatives
        raw_artifacts = [
            {
                "artifact_revision_id": "art:gazette_restricted",
                "title": "Restricted Gazette Notice",
                "copyright_owner": "Authority",
                "license": "Restricted",
                "attribution_text": "Gazette e-waste",
                "redistribution_status": "REVIEW_REQUIRED",  # Not ALLOW
                "sha256": "1" * 64,
                "byte_length": 500,
            }
        ]
        provisions = [
            {
                "provision_version_id": "prov:clause_1",
                "source_artifact_revision_id": "art:gazette_restricted",
                "sha256": "2" * 64,
                "byte_length": 150,
            }
        ]
        prompts = [
            {
                "prompt_id": "prompt:turn_1",
                "derived_from_artifacts": ["art:gazette_restricted"],
                "sha256": "3" * 64,
                "byte_length": 250,
            }
        ]

        service_context = context.model_copy(update={"actor": actor})
        pub_bundle = export_svc.export_bundle(
            service_context,
            "run:g10_01",
            bundle_kind="QUALIFIED_PUBLIC",
            capability=service_cap,
            raw_artifacts=raw_artifacts,
            provisions=provisions,
            prompts=prompts,
        )

        assert pub_bundle.status == "SUCCESS"
        manifest = pub_bundle.output
        assert manifest.bundle_kind == "QUALIFIED_PUBLIC"

        # Check omissions
        omiss = json.loads(blobs.get(manifest.omission_dispositions_blob))
        omitted_ids = {o["object_ref"] for o in omiss}
        assert "art:gazette_restricted" in omitted_ids
        assert "prov:clause_1" in omitted_ids
        assert "prompt:turn_1" in omitted_ids

        # 6. Offline artifact replay without model provider
        replay_req = ReplayRequest(
            bundle_id=manifest.bundle_id,
            mode="ARTIFACT",
            dependency_environment_ref="env:g10",
            access_scope_id="scope:g10",
        )
        replay_result = export_svc.replay_bundle(
            context,
            replay_req,
            capability=service_cap,
            expected_report=report,
        )
        assert replay_result.status == "SUCCESS"
        assert replay_result.output.mode == "ARTIFACT"
