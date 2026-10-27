"""CP2 original evidence -> trusted support review -> audited baseline integration."""

import json
import shutil

import pytest
from typer.testing import CliRunner

from recycleguard.application import command_context, local_application, local_review_application
from recycleguard.baseline import BaselineOutput, BaselineService
from recycleguard.cli import app
from recycleguard.config import Settings
from recycleguard.contracts.artifacts import SnapshotRef
from recycleguard.contracts.baseline import (
    BaselineRequest,
    RecordSupportAssertion,
    RecordSupportReview,
)
from recycleguard.contracts.core import EvidenceRef
from recycleguard.contracts.extraction import ExtractionResult, Observation
from recycleguard.contracts.results import CalculationRequest
from recycleguard.contracts.snapshots import SnapshotPublication, SnapshotReview
from recycleguard.storage import canonical_json_bytes
from recycleguard.storage.authority import AuthorizationError, Capability
from recycleguard.support_review import SupportReviewer
from tests.integration.test_a04_foundation import review_environment

PASSWORD = "temporary-test-password"


@pytest.fixture(scope="module")
def approved_foundation(tmp_path_factory):
    root = tmp_path_factory.mktemp("a05-foundation")
    cases, _, reviewer, approval, context, _, cap = review_environment(root)
    approved = reviewer.approve(context, approval, capability=cap)
    assert approved.output.case_snapshot.review_state == "APPROVED"
    cases.kernel.close()
    return root


@pytest.fixture
def data_root(tmp_path, approved_foundation):
    root = tmp_path / "data"
    shutil.copytree(approved_foundation, root)
    return root


def snapshot(cases, identifier="snapshot:case_approved"):
    return cases.snapshots.catalog.get_snapshot(identifier)


def snapshot_ref(value):
    return SnapshotRef(snapshot_id=value.snapshot_id, membership_digest=value.membership_digest)


def membership(cases, value):
    return json.loads(cases.kernel.blob_store.get(value.membership_blob))


def baseline_request(cases, value):
    body = membership(cases, value)
    return BaselineRequest(
        snapshot=snapshot_ref(value),
        calculation=CalculationRequest(
            case_version_id=value.snapshot_id,
            profile_id=body["profile"]["profile_id"],
            bucket_ids=[],
            expected_input_membership_digest=None,
        ),
    )


def observations(cases, body):
    result = {}
    for raw in body["extractions"]:
        extraction = ExtractionResult.model_validate_json(canonical_json_bytes(raw))
        for line in cases.kernel.blob_store.get(extraction.observations_blob).splitlines():
            obs = Observation.model_validate_json(line)
            result[obs.observation_id] = obs
    return result


def evidence_ref(obs):
    return EvidenceRef(
        ref_kind="OBSERVATION",
        ref_id=obs.observation_id,
        artifact_revision_id=obs.artifact_revision_id,
        locator=obs.locator,
    )


def support_request(cases, value):
    body = membership(cases, value)
    obs = observations(cases, body)
    assertions = []
    for record in body["normalization"]["records"]:
        if record["record_type"] not in {"Certificate", "CertificateEvent", "Allocation"}:
            continue
        original = next(
            obs[key]
            for key in record["observation_refs"]
            if obs[key].parsed_fields.get("record_type") == record["record_type"]
        )
        assertions.append(
            RecordSupportAssertion(
                target_record_revision_id=record["record_revision_id"],
                evidence_refs=[evidence_ref(original)],
                reason="Synthetic test review of the exact original structured record.",
            )
        )
    return RecordSupportReview(
        target=snapshot_ref(value),
        reviewed_snapshot_id="snapshot:support_reviewed",
        approved_snapshot_id="snapshot:support_approved",
        assertions=assertions,
        reason="Synthetic fixture review only; temporal and legal qualifications remain.",
    )


def test_support_review_enables_exact_baseline_and_preserves_original_drafts(data_root):
    settings = Settings(data_root=data_root)
    with local_application(settings) as (cases, context, cap):
        old = snapshot(cases)
        old_bytes = cases.kernel.blob_store.get(old.membership_blob)
        draft = snapshot(cases, "snapshot:case_initial")
        draft_bytes = cases.kernel.blob_store.get(draft.membership_blob)
        result = BaselineService(cases).run(context, baseline_request(cases, old), capability=cap)
        assert result.status == "PARTIAL"
        bucket = result.output.calculation.bucket_results[0]
        assert (bucket.supported.decimal, bucket.signed_gap.decimal) == ("0.0000", "100.0000")

    with local_review_application(settings, PASSWORD) as args:
        cases, context, human_cap, actor, service_cap = args
        old = snapshot(cases)
        request = support_request(cases, old)
        reviewer = SupportReviewer(cases, service_actor=actor, service_capability=service_cap)
        approved = reviewer.approve(context, request, capability=human_cap)
        assert reviewer.approve(context, request, capability=human_cap) == approved
        assert approved.review_state == "APPROVED"
        assert cases.kernel.blob_store.get(old.membership_blob) == old_bytes
        assert cases.kernel.blob_store.get(draft.membership_blob) == draft_bytes
        assert snapshot(cases, draft.snapshot_id).review_state == "DRAFT"

    with local_application(settings) as (cases, context, cap):
        request = baseline_request(cases, approved)
        service = BaselineService(cases)
        result = service.run(context, request, capability=cap)
        assert result.status == "PARTIAL"
        bucket = result.output.calculation.bucket_results[0]
        assert (bucket.required.decimal, bucket.supported.decimal) == ("100.0000", "55.0000")
        assert (bucket.signed_gap.decimal, bucket.pending.decimal) == ("45.0000", "25.0000")
        assert result.output.verification.verdict != "BLOCKED"
        assert (
            BaselineOutput.model_validate_json(cases.kernel.blob_store.get(result.output_blob))
            == result.output
        )
        assert result.audit_event_ids
        assert service.run(context, request, capability=cap) == result
        assert len(cases.kernel.list_attempts(context.operation_id)) == 1
        event_types = {
            e.event_type
            for e in cases.kernel.list_stream_events(f"stream:{context.correlation_id}")
        }
        assert any(e.startswith("calculation.baseline") for e in event_types)
        assert any(e.startswith("report.baseline") for e in event_types)


@pytest.mark.parametrize(
    "bad_evidence", ["CommercialRecord", "AccountBalanceObservation", "locator"]
)
def test_support_review_rejects_evidence_that_does_not_establish_allocation(
    data_root, bad_evidence
):
    with local_review_application(Settings(data_root=data_root), PASSWORD) as args:
        cases, context, human_cap, actor, service_cap = args
        old = snapshot(cases)
        request = support_request(cases, old)
        body = membership(cases, old)
        allocation = next(
            r for r in body["normalization"]["records"] if r["record_type"] == "Allocation"
        )
        assertion = next(
            a
            for a in request.assertions
            if a.target_record_revision_id == allocation["record_revision_id"]
        )
        if bad_evidence == "locator":
            ref = assertion.evidence_refs[0]
            bad = ref.model_copy(
                update={
                    "locator": ref.locator.model_copy(update={"json_pointer": "/not_the_record"})
                }
            )
        else:
            obs = next(
                o
                for o in observations(cases, body).values()
                if o.parsed_fields.get("record_type") == bad_evidence
            )
            bad = evidence_ref(obs)
        request = request.model_copy(
            update={"assertions": [assertion.model_copy(update={"evidence_refs": [bad]})]}
        )
        reviewer = SupportReviewer(cases, service_actor=actor, service_capability=service_cap)
        with pytest.raises(ValueError, match="different fact|capability mapping|locator/revision"):
            reviewer.approve(context, request, capability=human_cap)
        assert cases.snapshots.head("case:001") == old


def test_support_review_rejects_spoof_and_stale_target(data_root):
    with local_review_application(Settings(data_root=data_root), PASSWORD) as args:
        cases, context, human_cap, actor, service_cap = args
        old = snapshot(cases)
        request = support_request(cases, old)
        reviewer = SupportReviewer(cases, service_actor=actor, service_capability=service_cap)
        with pytest.raises(AuthorizationError):
            reviewer.approve(context, request, capability=service_cap)
        with pytest.raises(AuthorizationError):
            reviewer.approve(context, request, capability=Capability())
        reviewer.approve(context, request, capability=human_cap)
        with pytest.raises(ValueError, match="STALE_REVIEW"):
            reviewer.approve(command_context(context.actor), request, capability=human_cap)


def test_audit_commit_failure_cannot_return_success(data_root):
    with local_application(Settings(data_root=data_root)) as (cases, context, cap):
        request = baseline_request(cases, snapshot(cases))
        cases.kernel.connection.execute("""CREATE TRIGGER fail_calculation
          BEFORE INSERT ON audit_events
          WHEN NEW.event_json LIKE '%calculation.baseline.result%'
          BEGIN SELECT RAISE(ABORT,'simulated calculation audit failure'); END""")
        result = BaselineService(cases).run(context, request, capability=cap)
        assert result.status == "OUTCOME_UNKNOWN"
        assert result.output is None and result.issues[0].code == "AUDIT_UNAVAILABLE"
        assert cases.kernel.get_result(context.operation_id) is None


@pytest.mark.parametrize("record_type", ["Allocation", "CertificateEvent", "Certificate"])
def test_snapshot_approval_cannot_substitute_for_reviewed_record_support(data_root, record_type):
    settings = Settings(data_root=data_root)
    with local_review_application(settings, PASSWORD) as args:
        cases, context, human_cap, actor, service_cap = args
        old = snapshot(cases)
        body = membership(cases, old)
        record = next(
            r for r in body["normalization"]["records"] if r["record_type"] == record_type
        )
        if record_type == "Allocation":
            record["state"] = "SUPPORTED"
        elif record_type == "CertificateEvent":
            record["assertion_state"] = "SUPPORTED"
        else:
            record["validation_state"] = "VALID"
        blob = cases.kernel.blob_store.put(canonical_json_bytes(body), "application/json")
        published = cases.publish_case(
            command_context(actor),
            SnapshotPublication(
                scope_id="case:001",
                snapshot_id="snapshot:self_declared",
                snapshot_kind="CASE",
                expected_head=old.snapshot_id,
                membership_blob=blob,
                membership_digest=blob.sha256,
                coverage_blob=old.coverage_blob,
                source_receipt_ids=old.source_receipt_ids,
            ),
            capability=service_cap,
        )
        assert published.status == "SUCCESS"
        approved = cases.review_snapshot(
            context,
            SnapshotReview(
                scope_id="case:001",
                target_snapshot_id=published.output.snapshot_id,
                target_membership_digest=published.output.membership_digest,
                expected_head=published.output.snapshot_id,
                new_snapshot_id="snapshot:self_declared_approved",
                decision="APPROVE",
                reason="Synthetic test: general snapshot approval supplies no support assertion.",
            ),
            capability=human_cap,
        )
        assert approved.status == "SUCCESS"
    with local_application(settings) as (cases, context, cap):
        result = BaselineService(cases).run(
            context, baseline_request(cases, approved.output), capability=cap
        )
        assert result.status == "REJECTED" and result.output is None
        assert "human support assertion" in result.issues[0].message


def test_cli_partial_exit_and_archived_audit_inspection(data_root, tmp_path, monkeypatch):
    with local_application(Settings(data_root=data_root)) as (cases, _, _):
        request = baseline_request(cases, snapshot(cases))
    path = tmp_path / "baseline.json"
    path.write_text(request.model_dump_json())
    monkeypatch.setenv("RECYCLEGUARD_DATA_ROOT", str(data_root))
    runner = CliRunner()
    executed = runner.invoke(app, ["baseline", "run", str(path)])
    assert executed.exit_code == 2, executed.output
    output = json.loads(executed.output)
    assert output["status"] == "PARTIAL" and output["audit_event_ids"]
    inspected = runner.invoke(app, ["baseline", "audit", output["operation_id"]])
    assert inspected.exit_code == 0, inspected.output
    audit = json.loads(inspected.output)
    assert audit["audit_valid"] is True
    assert audit["result"]["status"] == "PARTIAL"
    assert {event["event_id"] for event in audit["events"]} == set(output["audit_event_ids"])


def test_cli_audit_rejects_tampered_hash_chain(data_root, monkeypatch):
    settings = Settings(data_root=data_root)
    with local_application(settings) as (cases, context, cap):
        result = BaselineService(cases).run(
            context, baseline_request(cases, snapshot(cases)), capability=cap
        )
        assert result.status == "PARTIAL"
        event = cases.kernel.list_stream_events(f"stream:{context.correlation_id}")[0]
        tampered = event.model_copy(update={"event_hash": "0" * 64})
        cases.kernel.connection.execute(
            "UPDATE audit_events SET event_hash=?, event_json=? WHERE event_id=?",
            (tampered.event_hash, tampered.model_dump_json(), event.event_id),
        )
        cases.kernel.connection.commit()
    monkeypatch.setenv("RECYCLEGUARD_DATA_ROOT", str(data_root))
    inspected = CliRunner().invoke(app, ["baseline", "audit", result.operation_id])
    assert inspected.exit_code == 1
    assert "audit hash chain failed verification" in inspected.output
    assert '"audit_valid": true' not in inspected.output


def test_calculation_input_digest_binds_explicit_allocation_order(tmp_path):
    from tests.support.c08 import clean_case, run

    first = run(tmp_path / "first", clean_case(), order={"alloc:1": 1})
    second = run(tmp_path / "second", clean_case(), order={"alloc:1": 2})
    assert first.output.bucket_results == second.output.bucket_results
    assert first.output.input_digest != second.output.input_digest
    assert first.output.calculation_id != second.output.calculation_id
