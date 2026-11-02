"""C14 frozen-byte export and conservative publication regressions."""

import json

import pytest
from typer.testing import CliRunner

from recycleguard.cli import app
from recycleguard.contracts.bundles import ReplayRequest
from recycleguard.exports.service import ExportService
from recycleguard.storage import canonical_json_bytes
from tests.integration.test_a05_baseline import approved_foundation as approved_foundation
from tests.integration.test_a06_workflow import workflow as workflow
from tests.support.workflow import assess, plan


def export(env, kind="COMPLETE_LOCAL", **kwargs):
    return (
        ExportService(env.cases)
        .export_bundle(env.context, env.spec.run_id, kind, capability=env.capability, **kwargs)
        .output
    )


def request(manifest, mode="ARTIFACT"):
    return ReplayRequest(
        bundle_id=manifest.bundle_id,
        mode=mode,
        dependency_environment_ref="env:offline",
        access_scope_id="scope:local",
    )


def test_complete_local_export_contains_originals_and_nested_dependencies(workflow):
    with workflow([plan(), assess()]) as env:
        env.drive(env.start())
        manifest = export(env)
        service = ExportService(env.cases)
        entries = json.loads(service.blobs.get(manifest.included_objects_blob))
        assert any(entry["object_kind"] == "AUDIT_EVENT" for entry in entries)
        assert any(entry["object_kind"] == "CATALOG_METADATA" for entry in entries)
        snapshot = env.cases.snapshots.catalog.get_snapshot(env.spec.case_snapshot.snapshot_id)
        assert snapshot.membership_blob.sha256 in {entry["sha256"] for entry in entries}
        assert service.verify_bundle(manifest).verdict == "PASS"


def test_publication_withholds_opaque_run_context_and_caller_claimed_clearance(workflow):
    with workflow([plan(), assess()]) as env:
        env.drive(env.start())
        manifest = export(
            env,
            "QUALIFIED_PUBLIC",
            raw_artifacts=[
                {
                    "artifact_revision_id": "artifact:caller_claim",
                    "redistribution_status": "ALLOW",
                    "sha256": "1" * 64,
                    "byte_length": 12,
                }
            ],
        )
        service = ExportService(env.cases)
        assert json.loads(service.blobs.get(manifest.included_objects_blob)) == []
        omissions = json.loads(service.blobs.get(manifest.omission_dispositions_blob))
        assert any(item["object_ref"] == "artifact:caller_claim" for item in omissions)
        assert manifest.completeness == "PARTIAL"
        assert service.verify_bundle(manifest).verdict == "PASS"
        assert (
            service.replay_bundle(env.context, request(manifest), capability=env.capability).status
            == "FAILED"
        )


def test_bundle_integrity_tampered_metadata_and_bytes(workflow):
    with workflow([plan(), assess()]) as env:
        env.drive(env.start())
        manifest = export(env)
        service = ExportService(env.cases)
        assert service.verify_bundle(manifest).verdict == "PASS"
        changed = service.blobs.put(canonical_json_bytes([]), "application/json")
        tampered = manifest.model_copy(update={"included_objects_blob": changed})
        assert service.verify_bundle(tampered).verdict == "FAIL"
        entries = json.loads(service.blobs.get(manifest.included_objects_blob))
        digest = entries[0]["sha256"]
        path = service.blobs.objects / digest[:2] / digest
        path.write_bytes(b"corrupted")
        assert service.verify_bundle(manifest).verdict == "FAIL"


def test_artifact_replay_uses_frozen_package_not_live_events(workflow, monkeypatch, tmp_path):
    with workflow([plan(), assess()]) as env:
        env.drive(env.start())
        manifest = export(env)
        service = ExportService(env.cases)
        monkeypatch.setattr(
            service, "_collect_run_events", lambda _: pytest.fail("live ledger read")
        )
        replay = service.replay_bundle(env.context, request(manifest), capability=env.capability)
        assert replay.status == "SUCCESS"
        assert replay.output.reconstructed_state_refs
        assert replay.output.new_run_id is None
        assert replay.audit_event_ids
        path = service.write_package(manifest, tmp_path / "standalone-package")
        offline, frozen = ExportService.open_package(path)
        assert offline.kernel is None
        assert frozen == manifest
        result = offline.replay_bundle(env.context, request(frozen))
        assert result.status == "SUCCESS"
        assert result.output.reconstructed_state_refs == replay.output.reconstructed_state_refs
        assert offline.blobs.root != service.blobs.root


@pytest.mark.parametrize("mode", ["RECOMPUTE", "MODEL_RERUN"])
def test_unimplemented_replay_modes_fail_explicitly(workflow, mode):
    with workflow([plan(), assess()]) as env:
        env.drive(env.start())
        manifest = export(env)
        replay = ExportService(env.cases).replay_bundle(
            env.context, request(manifest, mode), capability=env.capability
        )
        assert replay.status == "FAILED"
        assert replay.output.reconstructed_state_refs == []
        assert any(issue.code == "UNSUPPORTED_FEATURE" for issue in replay.issues)


def test_missing_run_cannot_be_exported(workflow):
    with workflow([]) as env:
        with pytest.raises(ValueError, match="no auditable events"):
            export(env)


def test_cli_audit_export_verify_and_replay(workflow, monkeypatch):
    with workflow([plan(), assess()]) as env:
        env.drive(env.start())
        monkeypatch.setenv("RECYCLEGUARD_DATA_ROOT", str(env.settings.data_root))
        monkeypatch.setenv("RECYCLEGUARD_MODE", "runtime")
        runner = CliRunner()
        result = runner.invoke(app, ["audit", "export", "--run-id", env.spec.run_id])
        assert result.exit_code == 0, result.output
        bundle_id = json.loads(result.stdout)["output"]["bundle_id"]
        for args in (
            ["audit", "verify", "--bundle-id", bundle_id],
            ["replay", "--bundle-id", bundle_id, "--mode", "ARTIFACT"],
        ):
            response = runner.invoke(app, args)
            assert response.exit_code == 0, response.output


def test_export_has_durable_audit_and_idempotent_manifest(workflow):
    with workflow([plan(), assess()]) as env:
        env.drive(env.start())
        service = ExportService(env.cases)
        first = service.export_bundle(env.context, env.spec.run_id, capability=env.capability)
        second = service.export_bundle(env.context, env.spec.run_id, capability=env.capability)
        assert first.output == second.output
        assert first.audit_event_ids == second.audit_event_ids
        event = env.cases.kernel.get_event(first.audit_event_ids[0])
        assert event.event_type == "export.bundle.result"
        assert env.cases.kernel.blob_store.get(event.payload_blob)
