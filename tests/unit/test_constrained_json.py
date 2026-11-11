"""The optional constrained decoder's matcher. Standard library only; no MLX is needed."""

import importlib.util
import json
from pathlib import Path

import pytest

from recycleguard.contracts.workflow import AssessmentProposal, PlanProposal

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "constrained_json", ROOT / "tools/local-model/constrained_json.py"
)
constrained = importlib.util.module_from_spec(spec)
spec.loader.exec_module(constrained)

PLAN = {
    "plan": {
        "objective": "Check the reconciliation.",
        "hypotheses": ["A gap may exist."],
        "proposed_checks": ["compute_reconciliation"],
        "expected_evidence": ["Calculation"],
        "stopping_criteria": ["The check ran"],
    },
    "action": {
        "action_kind": "CHECK",
        "allowed_operation": "compute_reconciliation",
        "typed_arguments": {"bucket_ids": [], "nested": {"a": [1, 2.5, None, True, "x"]}},
        "finding_id": "finding:one",
        "concise_reason": 'Quote " and unicode é.',
        "evidence_refs": [],
    },
    "stop_reason": None,
}
ASSESS = {
    "verdict": "UNKNOWN",
    "weak_result_or_mistake": None,
    "next_check_or_stop": "stop",
    "disposition": "ABSTAIN",
    "revised_plan": None,
    "finding_proposal": {
        "issue_type": "F07_PAID_NO_TRANSFER",
        "advisory_status": "PENDING_VERIFICATION",
        "basis": "A sentence.",
        "evidence_ref_ids": ["calc:one"],
        "abstention_reason": "MISSING_EVIDENCE",
        "withheld_claim_scopes": ["pending_untransferred_credits"],
        "next_action_kind": "INVESTIGATE",
        "next_action_text": "A sentence.",
    },
}
CASES = [(PlanProposal, PLAN), (AssessmentProposal, ASSESS)]


@pytest.mark.parametrize(("model", "reply"), CASES)
@pytest.mark.parametrize("separators", [(",", ":"), (", ", ": ")])
def test_every_prefix_of_a_valid_reply_stays_viable(model, reply, separators):
    matcher = constrained.SchemaMatcher(model.model_json_schema())
    text = json.dumps(reply, separators=separators)
    model.model_validate_json(text)
    for end in range(len(text) + 1):
        assert matcher.viable(text[:end]), text[:end][-40:]
    assert matcher.complete(text)
    assert not matcher.complete(text[:-1])


@pytest.mark.parametrize(
    "text",
    [
        "prefix",
        "```json",
        '{"unknown_key"',
        '{"plan":null',
        '{"plan":{"objective":1',
        '{"stop_reason":"MANUAL_CLOSURE"',
        '{"action":null,"action":null',
        '{"action":{"action_kind":"OTHER"',
        '{"stop_reason":null}',  # required keys missing
    ],
)
def test_text_that_cannot_become_a_plan_is_refused(text):
    matcher = constrained.SchemaMatcher(PlanProposal.model_json_schema())
    assert not matcher.viable(text)


def test_enum_is_enforced_inside_a_nested_optional_object():
    matcher = constrained.SchemaMatcher(AssessmentProposal.model_json_schema())
    assert matcher.viable('{"finding_proposal":{"issue_type":"F07')
    assert not matcher.viable('{"finding_proposal":{"issue_type":"F99')


def test_choose_token_takes_the_likeliest_viable_token_and_stops_only_when_whole():
    matcher = constrained.SchemaMatcher(
        {
            "type": "object",
            "properties": {"a": {"type": "boolean"}},
            "required": ["a"],
            "additionalProperties": False,
        }
    )
    pieces = {1: "nonsense", 2: '{"a":', 3: "true", 4: "}", 9: ""}
    stop = {9}
    choose = constrained.choose_token
    assert choose(matcher, "", [9, 1, 2], pieces.__getitem__, stop) == 2
    assert choose(matcher, '{"a":', [1, 3], pieces.__getitem__, stop) == 3
    assert choose(matcher, '{"a":true}', [1, 3, 9], pieces.__getitem__, stop) == 9
    assert choose(matcher, "", [1], pieces.__getitem__, stop) is None


def test_partial_multibyte_token_is_not_taken():
    matcher = constrained.SchemaMatcher({"type": "string"})
    pieces = {1: '"�', 2: '"ok'}
    assert constrained.choose_token(matcher, "", [1, 2], pieces.__getitem__, {9}) == 2


def test_serve_script_keeps_constrained_mode_off_by_default():
    source = (ROOT / "tools/local-model/serve.py").read_text("utf-8")
    assert 'sys.argv[1:] == ["--constrained"]' in source
    assert "[CONSTRAINED_FLAG] if constrained else []" in source
