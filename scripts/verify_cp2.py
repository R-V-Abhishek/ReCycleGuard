"""Fresh-root, offline CP2 demonstration using synthetic visible evidence only.

Run with uv run scripts/verify_cp2.py --data-root NEW_ROOT --output NEW_OUTPUT.
Temporary authenticated fixture reviews are not actual team or legal approvals.
"""

import json
import secrets
from decimal import Decimal
from pathlib import Path
from typing import Annotated

import typer
from typer.testing import CliRunner

from recycleguard.application import local_application, local_review_application
from recycleguard.cli import app
from recycleguard.config import Settings
from recycleguard.contracts.artifacts import FrozenSnapshot, SnapshotRef
from recycleguard.contracts.baseline import (
    BaselineRequest,
    RecordSupportAssertion,
    RecordSupportReview,
)
from recycleguard.contracts.core import BlobRef, EvidenceRef
from recycleguard.contracts.extraction import ExtractionResult, Observation
from recycleguard.contracts.foundation import FoundationApproval, FoundationRequest
from recycleguard.contracts.results import CalculationRequest
from recycleguard.domain import universe_from_membership
from recycleguard.foundation import FoundationService
from recycleguard.foundation_review import FoundationReviewer
from recycleguard.local_session import initialize_reviewer
from recycleguard.storage import canonical_json_bytes
from recycleguard.support_review import SupportReviewer

DISCLAIMER = (
    "SYNTHETIC FIXTURE REVIEW ONLY. Temporary authenticated reviewer actions below "
    "exercise the review boundary; they are not actual team acknowledgement, "
    "checkpoint approval, legal certification or confirmation of temporal applicability."
)


def save(path: Path, value):
    path.write_bytes(canonical_json_bytes(value) + b"\n")


def require(condition: bool, message: str):
    if not condition:
        raise RuntimeError(message)


def snapshot_ref(snapshot: FrozenSnapshot) -> SnapshotRef:
    return SnapshotRef(
        snapshot_id=snapshot.snapshot_id, membership_digest=snapshot.membership_digest
    )


def request_for(cases, snapshot: FrozenSnapshot) -> BaselineRequest:
    membership = json.loads(cases.kernel.blob_store.get(snapshot.membership_blob))
    return BaselineRequest(
        snapshot=snapshot_ref(snapshot),
        calculation=CalculationRequest(
            case_version_id=snapshot.snapshot_id,
            profile_id=membership["profile"]["profile_id"],
            bucket_ids=[],
            expected_input_membership_digest=None,
        ),
    )


def support_request(cases, snapshot: FrozenSnapshot) -> RecordSupportReview:
    blobs = cases.kernel.blob_store
    membership = json.loads(blobs.get(snapshot.membership_blob))
    observations = {}
    for raw in membership["extractions"]:
        extraction = ExtractionResult.model_validate_json(canonical_json_bytes(raw))
        for raw_observation in blobs.get(extraction.observations_blob).splitlines():
            observation = Observation.model_validate_json(raw_observation)
            observations[observation.observation_id] = observation
    assertions = []
    for record in membership["normalization"]["records"]:
        if record["record_type"] not in {"Certificate", "CertificateEvent", "Allocation"}:
            continue
        observation = next(
            observations[key]
            for key in record["observation_refs"]
            if observations[key].parsed_fields.get("record_type") == record["record_type"]
        )
        assertions.append(
            RecordSupportAssertion(
                target_record_revision_id=record["record_revision_id"],
                evidence_refs=[
                    EvidenceRef(
                        ref_kind="OBSERVATION",
                        ref_id=observation.observation_id,
                        artifact_revision_id=observation.artifact_revision_id,
                        locator=observation.locator,
                    )
                ],
                reason=DISCLAIMER,
            )
        )
    return RecordSupportReview(
        target=snapshot_ref(snapshot),
        reviewed_snapshot_id="snapshot:cp2_demo_support_reviewed",
        approved_snapshot_id="snapshot:cp2_demo_support_approved",
        assertions=assertions,
        reason=DISCLAIMER,
    )


def run(
    data_root: Annotated[Path, typer.Option(help="Fresh local evidence root; must not exist.")],
    output: Annotated[Path, typer.Option(help="Fresh verification output directory.")],
):
    data_root, output = data_root.resolve(), output.resolve()
    if data_root.exists() or output.exists():
        raise typer.BadParameter("--data-root and --output must both be new paths")
    if data_root == output or data_root in output.parents or output in data_root.parents:
        raise typer.BadParameter("data and output roots must be separate directories")
    fixtures = Path(__file__).resolve().parents[1] / "tests/fixtures/visible"
    build_request = FoundationRequest(
        case_root=str(fixtures / "case_001"),
        r02_path=str(fixtures / "h04/acquired_originals/e-waste_rules_2022.pdf"),
        r08_path=str(fixtures / "h01/acquired_originals/cpcb_faq_20240123.pdf"),
        case_snapshot_id="snapshot:cp2_demo_case_initial",
        corpus_snapshot_id="snapshot:cp2_demo_corpus_initial",
        profile_version="cp2-demo-draft",
    )
    settings = Settings(data_root=data_root)
    output.mkdir(parents=True)
    transcript = [DISCLAIMER, "", "All regulatory originals are read from pinned local fixtures."]
    save(output / "foundation-request.json", build_request.model_dump(mode="json"))
    with local_application(settings) as (cases, context, capability):
        prepared = FoundationService(cases).build(context, build_request, capability=capability)
        require(
            prepared.status == "PARTIAL" and prepared.output is not None,
            f"foundation build did not produce qualified drafts: {prepared.status}",
        )
        save(output / "foundation-envelope.json", prepared.model_dump(mode="json"))
        draft = prepared.output.case_snapshot
        draft_bytes = cases.kernel.blob_store.get(draft.membership_blob)
        membership = json.loads(draft_bytes)
        coverage = json.loads(cases.kernel.blob_store.get(draft.coverage_blob))["coverage"]
        disposition_ids = {
            item["observation_id"] for item in membership["normalization"]["dispositions"]
        }
        extracted_ids = {child for item in coverage for child in item["child_observation_ids"]}
        require(disposition_ids == extracted_ids, "original evidence accounting is incomplete")
        require(
            len(membership["originals"]) == prepared.output.inventory_count,
            "original inventory count differs from frozen membership",
        )

    password = secrets.token_urlsafe(32)
    initialize_reviewer(data_root, "human:synthetic_cp2_fixture_reviewer", password)
    try:
        with local_review_application(settings, password) as args:
            cases, context, human_cap, actor, service_cap = args
            approval = FoundationApproval(
                candidate_blob=prepared.output_blob,
                approval_evidence_blob=cases.kernel.blob_store.put(
                    DISCLAIMER.encode(), "text/plain"
                ),
                approval_reference="approval:synthetic_cp2_fixture_only",
                accepted_qualifications=(
                    f"{DISCLAIMER} Applicability remains UNKNOWN; deadlines remain unavailable."
                ),
                reviewed_profile_version="cp2-demo-reviewed",
                approved_profile_version="cp2-demo-approved",
                reviewed_case_snapshot_id="snapshot:cp2_demo_case_reviewed",
                approved_case_snapshot_id="snapshot:cp2_demo_case_approved",
                reviewed_corpus_snapshot_id="snapshot:cp2_demo_corpus_reviewed",
                approved_corpus_snapshot_id="snapshot:cp2_demo_corpus_approved",
            )
            accepted = FoundationReviewer(
                cases, service_actor=actor, service_capability=service_cap
            ).approve(context, approval, capability=human_cap)
            require(
                accepted.status == "PARTIAL" and accepted.output is not None,
                "synthetic foundation review lost its qualifications",
            )
            original_snapshot = accepted.output.case_snapshot
            before_request = request_for(cases, original_snapshot)
        save(output / "before-request.json", before_request.model_dump(mode="json"))
        runner = CliRunner()
        environment = {"RECYCLEGUARD_DATA_ROOT": str(data_root)}

        def invoke(arguments: list[str], expected_exit: int):
            executed = runner.invoke(app, arguments, env=environment)
            transcript.extend(
                [
                    f"$ recycleguard {' '.join(arguments)}",
                    f"exit={executed.exit_code}",
                    executed.output.strip(),
                    "",
                ]
            )
            require(
                executed.exit_code == expected_exit,
                f"CLI failed for {arguments}: {executed.output} {executed.exception}",
            )
            return json.loads(executed.output)

        before = invoke(["baseline", "run", str(output / "before-request.json")], 2)
        save(output / "before-envelope.json", before)
        before_bucket = before["output"]["calculation"]["bucket_results"][0]
        require(
            Decimal(before_bucket["supported"]["decimal"]) == 0
            and Decimal(before_bucket["signed_gap"]["decimal"]) == 100,
            "unreviewed allocations were counted as supported",
        )

        with local_review_application(settings, password) as args:
            cases, context, human_cap, actor, service_cap = args
            support = support_request(cases, original_snapshot)
            save(output / "support-review-request.json", support.model_dump(mode="json"))
            supported_snapshot = SupportReviewer(
                cases, service_actor=actor, service_capability=service_cap
            ).approve(context, support, capability=human_cap)
            request = request_for(cases, supported_snapshot)
            require(
                cases.kernel.blob_store.get(draft.membership_blob) == draft_bytes,
                "review changed original draft membership",
            )
        save(output / "request.json", request.model_dump(mode="json"))
        after = invoke(["baseline", "run", str(output / "request.json")], 2)
        save(output / "after-envelope.json", after)
        bucket = after["output"]["calculation"]["bucket_results"][0]
        expected = {"required": 100, "supported": 55, "signed_gap": 45, "pending": 25}
        require(
            all(Decimal(bucket[field]["decimal"]) == value for field, value in expected.items()),
            "supported baseline quantities differ from 100/55/45 with pending 25",
        )
        require(
            after["status"] == "PARTIAL"
            and after["output"]["verification"]["verdict"] == "QUALIFIED",
            "qualified fixture was incorrectly presented as complete or rejected",
        )
        audit = invoke(["baseline", "audit", after["operation_id"]], 0)
        save(output / "audit.json", audit)
        require(
            {event["event_id"] for event in audit["events"]} == set(after["audit_event_ids"]),
            "audit event references do not cover the archived run",
        )
        require(audit["result"]["status"] == "PARTIAL", "archived result lost qualifications")
        with local_application(settings) as (cases, _, _):
            blobs = cases.kernel.blob_store
            approved_body = json.loads(blobs.get(supported_snapshot.membership_blob))
            universe = universe_from_membership(supported_snapshot.snapshot_id, approved_body)
            calculated_members = json.loads(
                blobs.get(
                    BlobRef.model_validate(
                        after["output"]["calculation"]["analyzed_input_membership_blob"]
                    )
                )
            )
            require(
                calculated_members["members"] == universe.members(),
                "calculation omitted frozen record revisions",
            )
            initial_record_count = len(membership["normalization"]["records"])
            require(
                len(universe.records) == initial_record_count + len(support.assertions),
                "support review did not preserve every original record revision",
            )
            require(
                len(universe.superseded) == len(support.assertions),
                "support revisions did not supersede the exact original revisions",
            )
            require(
                len(universe.records) - len(universe.superseded) == initial_record_count,
                "review introduced duplicate active records",
            )
            save(output / "calculation-membership.json", calculated_members)
            dispositions = json.loads(
                blobs.get(
                    BlobRef.model_validate(
                        after["output"]["calculation"]["quantity_dispositions_blob"]
                    )
                )
            )
            require(
                len(dispositions) == len(universe.records)
                and {item["record_revision_id"] for item in dispositions}
                == {record.record_revision_id for record in universe.records},
                "calculation must account for every frozen record revision exactly once",
            )
            require(
                all(
                    item["state"] == "EXCLUDED"
                    for item in dispositions
                    if item["record_revision_id"] in universe.superseded
                ),
                "superseded source records were incorrectly included in calculation",
            )
            save(output / "quantity-dispositions.json", dispositions)
        (output / "working-paper.md").write_text(
            after["output"]["report"]["rendered_markdown"], encoding="utf-8"
        )
        save(
            output / "summary.json",
            {
                "disclaimer": DISCLAIMER,
                "status": "VERIFIED_QUALIFIED_SYNTHETIC_DEMONSTRATION",
                "network_required": False,
                "original_inventory_count": prepared.output.inventory_count,
                "extraction_count": prepared.output.extraction_count,
                "case_observation_disposition_count": len(disposition_ids),
                "complete_case_observation_accounting": disposition_ids == extracted_ids,
                "before_supported": before_bucket["supported"],
                "before_gap": before_bucket["signed_gap"],
                "after_quantities": {field: bucket[field] for field in expected},
                "verification": after["output"]["verification"]["verdict"],
                "audit_event_count": len(audit["events"]),
                "initial_normalized_record_count": initial_record_count,
                "calculation_record_revision_count": len(universe.records),
                "historical_superseded_revision_count": len(universe.superseded),
                "active_record_count": len(universe.records) - len(universe.superseded),
                "complete_calculation_membership": True,
                "qualification": "Temporal applicability and deadlines remain unresolved.",
            },
        )
    finally:
        # Generated credential is strictly for this synthetic demonstration.
        (data_root / "reviewer.json").unlink()
        (output / "transcript.txt").write_text("\n".join(transcript), encoding="utf-8")
    typer.echo(f"Verified qualified synthetic CP2 demonstration: {output / 'summary.json'}")


if __name__ == "__main__":
    typer.run(run)
