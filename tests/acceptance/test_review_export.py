"""G10: exact authenticated report review, frozen export and offline inspection."""

import pytest

from recycleguard.application import local_application
from recycleguard.contracts.bundles import ReplayRequest
from recycleguard.exports.service import ExportService
from tests.integration.test_a05_baseline import approved_foundation as approved_foundation
from tests.integration.test_a07_reviews import prepared as prepared
from tests.integration.test_a07_reviews import submit


def test_g10_authenticated_review_then_frozen_export(prepared):
    settings, spec, packet = prepared
    result = submit(settings, spec, packet, "APPROVE")
    assert result.status == "SUCCESS"
    assert result.output.new_run_status == "COMPLETED"
    with pytest.raises(ValueError, match="already|STALE|decided"):
        submit(settings, spec, packet, "APPROVE")
    with local_application(settings) as (cases, context, capability):
        service = ExportService(cases)
        manifest = service.export_bundle(context, spec.run_id, capability=capability).output
        assert service.verify_bundle(manifest).verdict == "PASS"
        replay = service.replay_bundle(
            context,
            ReplayRequest(
                bundle_id=manifest.bundle_id,
                mode="ARTIFACT",
                dependency_environment_ref="env:g10_offline",
                access_scope_id="scope:g10",
            ),
            capability=capability,
        )
        assert replay.status == "SUCCESS"
        assert packet.report_revision_id
        assert replay.output.reconstructed_state_refs
