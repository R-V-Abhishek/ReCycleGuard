"""Real C07/C08/C12 composition with explicitly scripted C10 proposals."""

import hashlib
import json
import shutil
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import get_args

import pytest

from benchmarks.generator.s06_cases import build_s06_cases
from recycleguard.application import command_context, local_application
from recycleguard.baseline import BaselineOutput
from recycleguard.config import Settings
from recycleguard.contracts.artifacts import SnapshotRef
from recycleguard.contracts.checks import StructuredCheckResult
from recycleguard.contracts.core import ServiceResult
from recycleguard.contracts.results import FaultFamily
from recycleguard.contracts.retrieval import RetrievalAttempt
from recycleguard.extraction import extract_pdf_pages
from recycleguard.indexing.corpus import load_corpus
from recycleguard.investigation import (
    Inspection,
    InvestigationRequest,
    InvestigationService,
    ScriptedExchange,
)
from recycleguard.storage import canonical_json_bytes
from tests.integration.test_a05_baseline import approved_foundation as approved_foundation
from tests.support.workflow import assess, plan


def _exchange(step):
    return ScriptedExchange(phase=step.phase, response=step.output)


def _steps():
    calculation = plan(operation="compute_reconciliation")
    calculation.output["action"]["typed_arguments"] = {"bucket_ids": []}
    return [
        plan("unlikely_missing_phrase_7632"),
        assess(verdict="WEAK", disposition="CONTINUE", revised=True),
        plan("producer", kind="REFORMULATE"),
        assess(verdict="WEAK", disposition="CONTINUE"),
        calculation,
        assess(verdict="UNKNOWN", disposition="ABSTAIN"),
    ]


@dataclass
class Harness:
    cases: object
    context: object
    capability: object
    service: InvestigationService
    spec: object
    runner: object

    def tool(self, name, arguments):
        binding = self.runner.tools[name]
        context = self.service.bound(command_context(self.context.actor), self.spec)
        return context, binding.handler(context, binding.arguments_model.model_validate(arguments))

    def output(self, result):
        assert result.output.output_blob == result.output_blob
        return json.loads(self.service.blobs.get(result.output.output_blob))

    def close(self):
        self.runner.close()


@pytest.fixture
def investigation(tmp_path, approved_foundation):
    root = tmp_path / "data"
    shutil.copytree(approved_foundation, root, ignore=shutil.ignore_patterns("reviewer.json"))
    settings = Settings(data_root=root, mode="test", enable_test_adapters=True)

    @contextmanager
    def create(ablated=(), briefs=(), name=""):
        with local_application(settings) as (cases, context, capability):
            case = cases.snapshots.catalog.get_snapshot("snapshot:case_approved")
            corpus = cases.snapshots.catalog.get_snapshot("snapshot:corpus_approved")
            request = InvestigationRequest(
                run_id="run:a07_real_services" + ("_ablated" if ablated else "") + name,
                case_snapshot=SnapshotRef(
                    snapshot_id=case.snapshot_id, membership_digest=case.membership_digest
                ),
                corpus_snapshot=SnapshotRef(
                    snapshot_id=corpus.snapshot_id, membership_digest=corpus.membership_digest
                ),
                finding_ids=["finding:one"],
                scripted_exchanges=[_exchange(step) for step in _steps()] + list(briefs),
                ablated_families=list(ablated),
            )
            service = InvestigationService(cases, settings, capability=capability)
            spec = service.prepare(context, request)
            harness = Harness(cases, context, capability, service, spec, service.runner(spec))
            try:
                yield harness
            finally:
                harness.close()

    return create


def test_real_search_reformulation_reconciliation_and_verified_report(investigation):
    with investigation() as env:
        state = env.runner.start_run(env.context, env.spec, capability=env.capability)
        for _ in range(15):
            if state.status in {"AWAITING_REVIEW", "FAILED", "BLOCKED_INPUT", "BLOCKED_OUTPUT"}:
                break
            state = env.runner.advance(
                command_context(env.context.actor),
                state.run_id,
                state.version,
                capability=env.capability,
            )
        assert state.status == "AWAITING_REVIEW"
        assert state.abstained_finding_ids == ["finding:one"]
        assert state.resolved_finding_ids == []
        assert state.budget.tool_calls == 3
        assert state.budget.finding_reformulations == {"finding:one": 1}
        assert len(state.assessment_refs) == 3
        assert state.budget.model_calls == 6
        assert state.budget.observed_tokens is None
        report = env.service.latest_report(state.run_id)
        assert report.verification.verdict in {"PASS", "QUALIFIED"}
        assert report.report.revision.run_id == state.run_id
        assert report.report.calculations
        assert all(
            c.case_version_id == env.spec.case_snapshot.snapshot_id
            for c in report.report.calculations
        )
        events = env.cases.kernel.list_stream_events(f"stream:{state.run_id}")
        assert sum(e.event_type == "extraction.retrieval.result" for e in events) == 2
        assert any(e.event_type == "graph.tool.tool.result" for e in events)
        turns = env.service.store.list_turns(state.run_id)
        assert len({ref for turn in turns for ref in turn.retrieval_attempt_ids}) == 2
        calculated_ids = {ref for turn in turns for ref in turn.calculation_ids}
        assert {c.calculation_id for c in report.report.calculations} <= calculated_ids


def _drive(env):
    state = env.runner.start_run(env.context, env.spec, capability=env.capability)
    for _ in range(15):
        if state.status in {"AWAITING_REVIEW", "FAILED", "BLOCKED_INPUT", "BLOCKED_OUTPUT"}:
            break
        state = env.runner.advance(
            command_context(env.context.actor),
            state.run_id,
            state.version,
            capability=env.capability,
        )
    return state


def _limitations(report):
    return [c.template_or_text for c in report.report.claims if c.kind == "LIMITATION"]


def test_ablation_switches_off_deterministic_findings_and_says_so(investigation):
    every = list(get_args(FaultFamily))
    with investigation() as env:
        state = _drive(env)
        stored = json.loads(env.service.blobs.get(env.spec.runtime_configuration))
        # A default run's stored configuration is byte-for-byte what it was before ablation.
        assert "ablated_families" not in stored
        default = env.service.latest_report(state.run_id)
        assert not any("switched off" in text for text in _limitations(default))
    with investigation(ablated=every) as env:
        state = _drive(env)
        assert state.status == "AWAITING_REVIEW"
        assert env.service.configuration(env.spec).ablated_families == every
        report = env.service.latest_report(state.run_id)
        # The scripted control proposes nothing, so with every source off nothing is reported,
        # and a settled reconciliation is not passed off as a clean case.
        assert report.findings == []
        assert report.verification.verdict in {"PASS", "QUALIFIED"}
        assert f"Deterministic checks for {len(every)} fault families" in " ".join(
            _limitations(report)
        )


def test_ablation_is_refused_outside_evaluation_and_test_modes(tmp_path, approved_foundation):
    root = tmp_path / "data"
    shutil.copytree(approved_foundation, root, ignore=shutil.ignore_patterns("reviewer.json"))
    with local_application(Settings(data_root=root)) as (cases, context, capability):
        case = cases.snapshots.catalog.get_snapshot("snapshot:case_approved")
        corpus = cases.snapshots.catalog.get_snapshot("snapshot:corpus_approved")
        request = InvestigationRequest(
            run_id="run:a07_ablation_refused",
            case_snapshot=SnapshotRef(
                snapshot_id=case.snapshot_id, membership_digest=case.membership_digest
            ),
            corpus_snapshot=SnapshotRef(
                snapshot_id=corpus.snapshot_id, membership_digest=corpus.membership_digest
            ),
            finding_ids=["finding:one"],
            scripted_exchanges=[_exchange(step) for step in _steps()],
            ablated_families=["F09_EXPIRED_CANCELLED"],
        )
        service = InvestigationService(cases, Settings(data_root=root), capability=capability)
        with pytest.raises(ValueError, match="evaluation setting"):
            service.prepare(context, request)


def _brief_reply(finding, text=None):
    cited = [*finding.fact_refs, *finding.next_action.evidence_refs, *finding.provision_refs]
    refs = [ref.ref_id for ref in cited]
    return ScriptedExchange(
        phase="BRIEF",
        response={
            "what_to_check": text or "Check that the cited record supports this finding.",
            "explanation": "The finding rests on the cited evidence.",
            "evidence_request": "Please send the source document behind the cited record.",
            "evidence_ref_ids": refs[:1],
        },
    )


def _outcome(report):
    """What a brief must never change: the findings, their numbers and the verification."""
    return (
        [
            (f.issue_type, f.bucket_ids, f.advisory_status, f.priority, f.fact_refs)
            for f in report.findings
        ],
        [c.bucket_results for c in report.report.calculations],
        report.verification.verdict,
    )


def test_briefing_runs_after_verification_and_changes_no_finding(investigation):
    with investigation() as env:
        plain = env.service.latest_report(_drive(env).run_id)
    assert plain.findings, "the approved foundation must yield findings to brief"
    good = [_brief_reply(f) for f in plain.findings]
    with investigation(briefs=good, name="_briefed") as env:
        state = _drive(env)
        assert state.status == "AWAITING_REVIEW" and state.review_outcome == "PENDING"
        assert state.budget.model_calls == 6 + len(plain.findings)
        report = env.service.latest_report(state.run_id)
        assert _outcome(report) == _outcome(plain)
        briefs = env.service.briefs(state.run_id)
        revision = report.report.revision.report_revision_id
        assert briefs.report_revision_id == revision
        assert [b.finding_revision_id for b in briefs.model_briefs] == [
            f.finding_revision_id for f in report.findings
        ]
        assert {(b.source, b.status, b.report_revision_id) for b in briefs.model_briefs} == {
            ("MODEL", "ACCEPTED", revision)
        }
        assert all(b.model_operation_ref for b in briefs.model_briefs)
        assert len(briefs.template_briefs) == len(report.findings)
        events = env.cases.kernel.list_stream_events(f"stream:{state.run_id}")
        assert sum(e.event_type == "graph.brief.result" for e in events) == len(report.findings)


def test_a_brief_the_gate_rejects_is_recorded_and_review_still_opens(investigation):
    with investigation() as env:
        plain = env.service.latest_report(_drive(env).run_id)
    bad = [_brief_reply(f, "The shortfall is 45 KG.") for f in plain.findings]
    with investigation(briefs=bad, name="_bad_briefs") as env:
        state = _drive(env)
        assert state.status == "AWAITING_REVIEW" and state.review_outcome == "PENDING"
        report = env.service.latest_report(state.run_id)
        assert _outcome(report) == _outcome(plain)
        briefs = env.service.briefs(state.run_id)
        assert {(b.status, b.reason) for b in briefs.model_briefs} == {
            ("REJECTED", "DIGITS_IN_TEXT")
        }
        assert all(b.what_to_check is None for b in briefs.model_briefs)
        assert all(b.status == "ACCEPTED" for b in briefs.template_briefs)


def test_read_tools_return_original_provenance_and_real_calculations(investigation):
    with investigation() as env:
        _, inspected = env.tool("inspect_evidence", {})
        inspection = Inspection.model_validate(env.output(inspected))
        assert inspection.observations
        assert inspected.output.evidence_refs
        assert {r.ref_id for r in inspected.output.evidence_refs} == {
            o.observation_id for o in inspection.observations
        }
        for observation in inspection.observations:
            assert observation.artifact_revision_id
            assert observation.locator
        for name in ("compute_reconciliation", "compare_return"):
            context, result = env.tool(name, {"bucket_ids": []})
            baseline = BaselineOutput.model_validate(env.output(result))
            assert baseline.calculation.case_version_id == env.spec.case_snapshot.snapshot_id
            assert baseline.calculation.bucket_results
            assert baseline.calculation.derivation_blob
            child = env.service.foundation._context(context, "baseline")
            committed = env.cases.kernel.get_result(child.operation_id)
            persisted = ServiceResult[BaselineOutput].model_validate_json(
                env.service.blobs.get(committed.payload)
            )
            assert persisted.output.calculation == baseline.calculation
        certificate = next(
            record
            for record in env.service._membership(env.spec)["normalization"]["records"]
            if record["record_type"] == "Certificate"
        )
        context, traced = env.tool(
            "trace_certificate", {"certificate_ids": [certificate["certificate_id"]]}
        )
        traced_output = env.output(traced)
        assert traced_output["results"]
        assert all(row["evidence"] for row in traced_output["results"])
        child = env.service.foundation._context(context, "certificate")
        committed = env.cases.kernel.get_result(child.operation_id)
        persisted = StructuredCheckResult.model_validate_json(
            env.service.blobs.get(committed.payload)
        )
        assert persisted.model_dump(mode="json") == traced_output


def test_search_retains_frozen_pins_grades_and_audit(investigation):
    with investigation() as env:
        context, result = env.tool("search_rules", {"query": "producer"})
        attempt = RetrievalAttempt.model_validate(env.output(result))
        assert attempt.request.corpus_snapshot_id == env.spec.corpus_snapshot.snapshot_id
        manifest = env.service.configuration(env.spec).index_manifest
        assert attempt.request.expected_index_digest == manifest.integrity_digest
        assert (
            attempt.request.expected_corpus_membership_digest
            == env.spec.corpus_snapshot.membership_digest
        )
        assert attempt.grading_assessments
        assert all(g.temporal_fit == "UNRESOLVED" for g in attempt.grading_assessments)
        events = env.cases.kernel.list_stream_events(f"stream:{env.spec.run_id}")
        assert any(
            e.event_type == "extraction.retrieval.result"
            and e.operation_id == env.service.foundation._context(context, "retrieval").operation_id
            for e in events
        )


def test_observations_outside_frozen_case_are_rejected(investigation):
    with investigation() as env:
        with pytest.raises(ValueError, match="not in frozen case"):
            env.tool("inspect_evidence", {"observation_ids": ["observation:unavailable"]})


def test_changed_index_pin_and_mutated_cache_are_rejected(investigation):
    with investigation() as env:
        changed = env.spec.model_copy(
            update={"index": env.spec.index.model_copy(update={"digest": "0" * 64})}
        )
        with pytest.raises(ValueError, match="index manifest pin"):
            env.service.runner(changed)
        path = env.runner.index.db_path
        env.runner.index.close()
        with path.open("ab") as stream:
            stream.write(b"unapproved mutation")
        with pytest.raises(ValueError, match="frozen index bytes"):
            env.service.runner(env.spec)


def test_missing_index_cache_rebuilds_exact_immutable_bytes(investigation):
    with investigation() as env:
        path = env.runner.index.db_path
        manifest = env.service.configuration(env.spec).index_manifest
        env.close()
        path.unlink()
        env.runner = env.service.runner(env.spec)
        assert hashlib.sha256(path.read_bytes()).hexdigest() == manifest.integrity_digest
        assert path.read_bytes() == env.service.blobs.get(manifest.index_blob)
        _, result = env.tool("search_rules", {"query": "producer"})
        assert RetrievalAttempt.model_validate(env.output(result)).engine_candidates


def test_exact_locator_inspection_retains_provision_identity(investigation):
    with investigation() as env:
        corpus = env.cases.snapshots.get(env.spec.corpus_snapshot)
        provision = load_corpus(corpus, env.service.blobs).batch.provisions[0]
        _, result = env.tool(
            "lookup_locator",
            {
                "source_alias_or_source_version_id": provision.source_version_id,
                "legal_path": provision.legal_path,
            },
        )
        payload = env.output(result)
        assert provision.provision_version_id in json.dumps(payload)
        assert result.output.disposition == "QUALIFIED"


def test_changed_script_model_pin_cannot_load_frozen_runtime(investigation):
    with investigation() as env:
        changed = env.spec.model_copy(
            update={"model": env.spec.model.model_copy(update={"digest": "0" * 64})}
        )
        with pytest.raises(
            ValueError, match="runtime configuration does not match frozen run pins"
        ):
            env.service.runner(changed)


@pytest.mark.parametrize(
    ("case_key", "issue_type", "reason", "scope", "withheld"),
    [
        (
            "period",
            "F11_WRONG_PERIOD_RULE",
            "TEMPORAL_UNCERTAINTY",
            "cited rule / reporting period",
            "rule_version_applied",
        ),
        (
            "notice",
            "F12_UNSEEN_NOTICE_LEAD",
            "MISSING_AUTHORITY",
            "claimed deadline extension",
            "deadline_extension",
        ),
        (
            "gold",
            "F14_OUT_OF_SCOPE_REGIME",
            "UNSUPPORTED_FEATURE",
            "refurbishment offset only",
            "gold_offset_credits",
        ),
    ],
)
def test_actual_s06_pdf_claims_become_scoped_findings_without_quantity_mutation(
    investigation, monkeypatch, case_key, issue_type, reason, scope, withheld
):
    # Test selection metadata stays here; runtime sees only opaque original evidence
    # and normalized producer records, never recipes or expected benchmark effects.
    case = next(c for c in build_s06_cases() if c.world.template_key == case_key)
    root = Path(__file__).resolve().parents[1] / "fixtures/visible" / f"case_{case.world.case_tag}"
    records = [
        json.loads(line)
        for name in (
            "entities",
            "registrations",
            "obligations",
            "certificates",
            "certificate_events",
            "allocations",
            "commercial_records",
            "account_balances",
            "product_mappings",
            "sales",
        )
        if (path := root / "records" / f"{name}.jsonl").exists()
        for line in path.read_text("utf-8").splitlines()
        if line.strip()
    ]
    membership = {"normalization": {"records": records}}
    observations = []
    for path in sorted((root / "documents").glob("*.pdf")):
        pages, _, _, issues = extract_pdf_pages(
            path.read_bytes(), f"artifact:{path.stem}", f"extraction:{path.stem}"
        )
        assert not issues
        observations.extend(pages)
    original = canonical_json_bytes(membership)
    with investigation() as env:
        monkeypatch.setattr(env.service, "_membership", lambda spec: membership)
        monkeypatch.setattr(env.service, "_observations", lambda spec: observations)
        findings = env.service._findings(env.spec)
        selected = [f for f in findings if f.issue_type == issue_type]
        assert selected, [(f.issue_type, f.priority_basis) for f in findings]
        # The scorer counts a second finding of one family as a duplicate.
        assert len(selected) == 1
        assert len({f.issue_type for f in findings}) == len(findings)
        for finding in selected:
            assert finding.advisory_status == "REQUIRES_EXPERT_REVIEW"
            assert finding.abstention_reason == reason
            assert finding.withheld_claim_scopes == [withheld]
            assert finding.scope_limits == [scope]
            assert finding.fact_refs
            assert all(
                ref.ref_id in {o.observation_id for o in observations}
                and ref.artifact_revision_id
                and ref.locator
                for ref in finding.fact_refs
            )
            assert finding.calculation_refs == []
            assert finding.delta_value_ref is None
        assert canonical_json_bytes(membership) == original
        if case_key == "gold":
            ordinary_gold = [
                r for r in records if r["record_type"] == "ObligationBucket" and r["metal"] == "AU"
            ]
            assert ordinary_gold
            assert all(f.bucket_ids == [] for f in selected)


def test_unknown_child_baseline_outcome_stops_preflight_without_retry(investigation, monkeypatch):
    from recycleguard.baseline import BaselineService
    from recycleguard.contracts.core import Issue
    from recycleguard.workflow.runner import CallRecord

    calls = []

    def unknown_child(service, context, request, *, capability):
        calls.append(context.operation_id)
        return ServiceResult[BaselineOutput](
            contract_version="1.1",
            operation_id=context.operation_id,
            attempt_id=context.attempt_id,
            status="OUTCOME_UNKNOWN",
            output=None,
            output_blob=None,
            issues=[
                Issue(
                    issue_id="issue:baseline_audit_unknown",
                    code="AUDIT_UNAVAILABLE",
                    severity="BLOCKING",
                    message="Child commit acknowledgement unavailable",
                    field_path=None,
                    evidence_refs=[],
                    retryable=False,
                )
            ],
            dependencies=[],
            audit_event_ids=[],
        )

    with investigation() as env:
        monkeypatch.setattr(BaselineService, "run", unknown_child)
        state = env.runner.start_run(env.context, env.spec, capability=env.capability)
        for _ in range(3):
            if state.status == "BLOCKED_OUTPUT":
                break
            state = env.runner.advance(
                command_context(env.context.actor),
                state.run_id,
                state.version,
                capability=env.capability,
            )
        assert state.status == "BLOCKED_OUTPUT"
        assert state.stop_reason == "PROVIDER_FAILURE"
        assert len(calls) == 1
        assert state.budget.retries == 0
        assert state.budget.model_calls == state.budget.tool_calls == 0
        events = env.cases.kernel.list_stream_events(f"stream:{state.run_id}")
        results = [event for event in events if event.event_type == "graph.stage.preflight.result"]
        assert len(results) == 1
        record = env.service.store.read(results[0].operation_id, CallRecord)
        assert record.status == "OUTCOME_UNKNOWN"
        assert [issue.code for issue in record.issues] == ["AUDIT_UNAVAILABLE"]
        with pytest.raises(ValueError):
            env.runner.advance(
                command_context(env.context.actor),
                state.run_id,
                state.version,
                capability=env.capability,
            )
        assert len(calls) == 1
