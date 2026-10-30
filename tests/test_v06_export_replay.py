"""Task V06: Local/public export, integrity verification and offline replay tests.

Verifies:
- Complete local export and verified bundles.
- Rights-through-derivatives recursive inspection and public omissions.
- Object-level hash integrity and audit hash-chain continuity.
- No-provider offline artifact replay and deterministic recomputation.
"""

import hashlib
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from recycleguard.application import local_application
from recycleguard.cli import app
from recycleguard.config import Settings
from recycleguard.contracts.audit import AuditEvent
from recycleguard.contracts.bundles import (
    ReplayRequest,
)
from recycleguard.exports.service import ExportService
from recycleguard.storage import canonical_json_bytes
from tests.support.c08 import clean_case
from tests.support.c08 import run as run_reconcile


@pytest.fixture
def mock_run(tmp_path: Path):
    """Create a temporary environment with recorded audit events and report."""
    settings = Settings(data_root=tmp_path / "data", mode="test", enable_test_adapters=True)
    settings.data_root.mkdir(parents=True, exist_ok=True)
    with local_application(settings) as (service, context, capability):
        kernel = service.kernel
        blobs = kernel.blob_store
        run_id = "run:test_001"
        stream_id = f"stream:{run_id}"

        # Store test calculation
        calc = run_reconcile(tmp_path, clean_case()).output
        calc_blob = blobs.put(
            canonical_json_bytes(calc.model_dump(mode="json")), "application/json"
        )

        # Create two sequential audit events
        event1 = AuditEvent(
            event_id="event:001",
            stream_id=stream_id,
            sequence=1,
            event_type="calculation.baseline.result",
            recorded_at="2026-10-30T09:00:00Z",
            actor=context.actor,
            command_id=context.command_id,
            operation_id="op:001",
            attempt_id="att:001",
            case_version_id="case:test_v1",
            run_id=run_id,
            turn_id=None,
            input_refs=[],
            output_refs=[calc_blob],
            dependency_refs=[],
            payload_blob=calc_blob,
            previous_event_hash=None,
            event_hash="0" * 64,
        )
        h1 = hashlib.sha256(
            canonical_json_bytes(event1.model_dump(mode="json", exclude={"event_hash"}))
        ).hexdigest()
        event1 = event1.model_copy(update={"event_hash": h1})

        event2 = AuditEvent(
            event_id="event:002",
            stream_id=stream_id,
            sequence=2,
            event_type="report.baseline.result",
            recorded_at="2026-10-30T09:00:05Z",
            actor=context.actor,
            command_id=context.command_id,
            operation_id="op:002",
            attempt_id="att:002",
            case_version_id="case:test_v1",
            run_id=run_id,
            turn_id=None,
            input_refs=[calc_blob],
            output_refs=[],
            dependency_refs=[],
            payload_blob=calc_blob,
            previous_event_hash=h1,
            event_hash="0" * 64,
        )
        h2 = hashlib.sha256(
            canonical_json_bytes(event2.model_dump(mode="json", exclude={"event_hash"}))
        ).hexdigest()
        event2 = event2.model_copy(update={"event_hash": h2})

        with kernel.connection:
            kernel.connection.execute(
                "INSERT INTO audit_events VALUES (?,?,?,?,?)",
                (
                    event1.event_id,
                    event1.stream_id,
                    event1.sequence,
                    event1.event_hash,
                    event1.model_dump_json(),
                ),
            )
            kernel.connection.execute(
                "INSERT INTO audit_events VALUES (?,?,?,?,?)",
                (
                    event2.event_id,
                    event2.stream_id,
                    event2.sequence,
                    event2.event_hash,
                    event2.model_dump_json(),
                ),
            )

        return settings, run_id, calc, [event1, event2], calc_blob


def test_complete_local_export(mock_run):
    """Verify complete local export captures all objects without omissions."""
    settings, run_id, calc, events, calc_blob = mock_run

    with local_application(settings) as (cases, context, capability):
        export_svc = ExportService(cases)

        result = export_svc.export_bundle(
            context,
            run_id,
            bundle_kind="COMPLETE_LOCAL",
            capability=capability,
        )

        assert result.status == "SUCCESS"
        manifest = result.output
        assert manifest is not None
        assert manifest.bundle_kind == "COMPLETE_LOCAL"
        assert manifest.completeness == "COMPLETE_LOCAL"
        assert len(manifest.selected_run_refs) == 1
        assert manifest.selected_run_refs[0] == run_id

        # Verify no omissions in local export
        omiss_data = json.loads(cases.kernel.blob_store.get(manifest.omission_dispositions_blob))
        assert omiss_data == []

        # Verify integrity of complete bundle passes
        integrity = export_svc.verify_bundle(manifest)
        assert integrity.verdict == "PASS"
        assert len(integrity.issues) == 0


def test_qualified_public_export_rights_through_derivatives(mock_run):
    """Verify recursive rights-through-derivatives inspection protects public export."""
    settings, run_id, calc, events, calc_blob = mock_run

    with local_application(settings) as (cases, context, capability):
        export_svc = ExportService(cases)
        blobs = cases.kernel.blob_store

        # 1. Setup raw artifacts: one unrestricted, one restricted
        pub_raw = b"%PDF-1.4 Public official guidance..."
        rest_raw = b"%PDF-1.4 Confidential internal company audit..."

        pub_blob = blobs.put(pub_raw, "application/pdf")
        rest_blob = blobs.put(rest_raw, "application/pdf")

        raw_artifacts = [
            {
                "artifact_revision_id": "art:public_guidance_v1",
                "title": "Public Guidance",
                "copyright_owner": "Government",
                "license": "Public",
                "attribution_text": "Gov e-waste notice",
                "redistribution_status": "ALLOW",
                "sha256": pub_blob.sha256,
                "byte_length": pub_blob.byte_length,
            },
            {
                "artifact_revision_id": "art:private_company_doc_v1",
                "title": "Confidential Audit",
                "copyright_owner": "Restricted Entity",
                "license": "Proprietary",
                "attribution_text": "Proprietary doc",
                "redistribution_status": "DENY",  # RESTRICTED
                "sha256": rest_blob.sha256,
                "byte_length": rest_blob.byte_length,
            },
        ]

        # 2. Derivative provisions (clauses)
        pub_prov_bytes = b'{"clause": "Rule 1"}'
        rest_prov_bytes = b'{"clause": "Restricted confidential excerpt"}'
        pub_prov_blob = blobs.put(pub_prov_bytes, "application/json")
        rest_prov_blob = blobs.put(rest_prov_bytes, "application/json")

        provisions = [
            {
                "provision_version_id": "prov:pub_rule1",
                "source_artifact_revision_id": "art:public_guidance_v1",
                "sha256": pub_prov_blob.sha256,
                "byte_length": pub_prov_blob.byte_length,
            },
            {
                "provision_version_id": "prov:rest_clause_secret",
                # DERIVED FROM RESTRICTED
                "source_artifact_revision_id": "art:private_company_doc_v1",
                "sha256": rest_prov_blob.sha256,
                "byte_length": rest_prov_blob.byte_length,
            },
        ]

        # 3. Model prompts containing excerpts from the sources
        pub_prompt_bytes = b'{"prompt": "Analyze Rule 1"}'
        rest_prompt_bytes = b'{"prompt": "Analyze Confidential internal excerpt"}'
        pub_prompt_blob = blobs.put(pub_prompt_bytes, "application/json")
        rest_prompt_blob = blobs.put(rest_prompt_bytes, "application/json")

        prompts = [
            {
                "prompt_id": "prompt:pub_01",
                "derived_from_artifacts": ["art:public_guidance_v1"],
                "sha256": pub_prompt_blob.sha256,
                "byte_length": pub_prompt_blob.byte_length,
            },
            {
                "prompt_id": "prompt:rest_02",
                "derived_from_artifacts": ["art:private_company_doc_v1"],  # DERIVED FROM RESTRICTED
                "sha256": rest_prompt_blob.sha256,
                "byte_length": rest_prompt_blob.byte_length,
            },
        ]

        # Export QUALIFIED_PUBLIC bundle
        result = export_svc.export_bundle(
            context,
            run_id,
            bundle_kind="QUALIFIED_PUBLIC",
            capability=capability,
            raw_artifacts=raw_artifacts,
            provisions=provisions,
            prompts=prompts,
        )

        assert result.status == "SUCCESS"
        manifest = result.output
        assert manifest.bundle_kind == "QUALIFIED_PUBLIC"

        # Verify included objects
        inc_entries = json.loads(blobs.get(manifest.included_objects_blob))
        included_refs = {e["object_ref"] for e in inc_entries}

        # Public items MUST be included
        assert "art:public_guidance_v1" in included_refs
        assert "prov:pub_rule1" in included_refs
        assert "prompt:pub_01" in included_refs

        # Restricted items MUST NOT leak into included objects!
        assert "art:private_company_doc_v1" not in included_refs
        assert "prov:rest_clause_secret" not in included_refs
        assert "prompt:rest_02" not in included_refs

        # Verify omission dispositions
        omiss_entries = json.loads(blobs.get(manifest.omission_dispositions_blob))
        omitted_refs = {o["object_ref"]: o for o in omiss_entries}

        assert "art:private_company_doc_v1" in omitted_refs
        assert (
            omitted_refs["art:private_company_doc_v1"]["restriction_reason"] == "RIGHTS_RESTRICTED"
        )

        assert "prov:rest_clause_secret" in omitted_refs
        assert omitted_refs["prov:rest_clause_secret"]["restriction_reason"] == "RIGHTS_RESTRICTED"

        assert "prompt:rest_02" in omitted_refs
        assert (
            omitted_refs["prompt:rest_02"]["restriction_reason"] == "PROMPT_DERIVATIVE_RESTRICTED"
        )

        # Verify attribution was populated
        attrib_entries = json.loads(blobs.get(manifest.attribution_blob))
        assert len(attrib_entries) == 2


def test_bundle_integrity_tampering(mock_run):
    """Verify that tampering with an included object causes integrity verification to fail."""
    settings, run_id, calc, events, calc_blob = mock_run

    with local_application(settings) as (cases, context, capability):
        export_svc = ExportService(cases)

        result = export_svc.export_bundle(
            context,
            run_id,
            bundle_kind="COMPLETE_LOCAL",
            capability=capability,
        )
        manifest = result.output

        # Integrity initially PASS
        assert export_svc.verify_bundle(manifest).verdict == "PASS"

        # Simulate tampering by mutating the included objects blob to reference non-existent object
        tampered_entries = [
            {
                "object_ref": "obj:tampered",
                "object_kind": "TEST",
                "sha256": "f" * 64,
                "byte_length": 100,
                "media_type": "application/json",
            }
        ]
        tampered_blob = cases.kernel.blob_store.put(
            canonical_json_bytes(tampered_entries), "application/json"
        )
        tampered_manifest = manifest.model_copy(update={"included_objects_blob": tampered_blob})

        # Verification must now FAIL with HASH_MISMATCH
        tampered_integrity = export_svc.verify_bundle(tampered_manifest)
        assert tampered_integrity.verdict == "FAIL"
        assert any(i.code == "HASH_MISMATCH" for i in tampered_integrity.issues)


def test_no_provider_offline_replay(mock_run):
    """Verify offline artifact replay operates without external provider/network calls."""
    settings, run_id, calc, events, calc_blob = mock_run

    with local_application(settings) as (cases, context, capability):
        export_svc = ExportService(cases)

        result = export_svc.export_bundle(
            context,
            run_id,
            bundle_kind="COMPLETE_LOCAL",
            capability=capability,
        )
        manifest = result.output

        # Replay in ARTIFACT mode
        replay_req = ReplayRequest(
            bundle_id=manifest.bundle_id,
            mode="ARTIFACT",
            dependency_environment_ref="env:offline_v1",
            access_scope_id="scope:local",
        )

        replay_res = export_svc.replay_bundle(
            context,
            replay_req,
            capability=capability,
            expected_calculation=calc,
        )

        assert replay_res.status == "SUCCESS"
        replay_out = replay_res.output
        assert replay_out.mode == "ARTIFACT"
        assert replay_out.source_bundle_id == manifest.bundle_id
        assert calc.calculation_id in replay_out.comparison_refs
        assert replay_out.new_run_id is None
        assert len(replay_out.issues) == 0


def test_cli_audit_export_and_verify(mock_run, monkeypatch):
    """Test CLI commands for audit export, audit verify, and replay."""
    settings, run_id, calc, events, calc_blob = mock_run
    runner = CliRunner()

    monkeypatch.setenv("RECYCLEGUARD_DATA_ROOT", str(settings.data_root))
    monkeypatch.setenv("RECYCLEGUARD_MODE", "runtime")

    # 1. uv run recycleguard audit export --run-id <run-id> --kind COMPLETE_LOCAL
    export_result = runner.invoke(
        app, ["audit", "export", "--run-id", run_id, "--kind", "COMPLETE_LOCAL"]
    )
    assert export_result.exit_code == 0
    export_data = json.loads(export_result.stdout)
    assert export_data["status"] == "SUCCESS"
    bundle_id = export_data["output"]["bundle_id"]

    # 2. uv run recycleguard audit verify --bundle-id <bundle-id>
    verify_result = runner.invoke(app, ["audit", "verify", "--bundle-id", bundle_id])
    assert verify_result.exit_code == 0
    verify_data = json.loads(verify_result.stdout)
    assert verify_data["verdict"] == "PASS"

    # 3. uv run recycleguard replay --bundle-id <bundle-id> --mode ARTIFACT
    replay_result = runner.invoke(app, ["replay", "--bundle-id", bundle_id, "--mode", "ARTIFACT"])
    assert replay_result.exit_code == 0
    replay_data = json.loads(replay_result.stdout)
    assert replay_data["status"] == "SUCCESS"
    assert replay_data["output"]["mode"] == "ARTIFACT"
