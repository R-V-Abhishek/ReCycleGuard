"""Hand-checked primary-metric cases: clean, paid-no-transfer and an injected dossier."""

from decimal import Decimal

import pytest

from benchmarks.evaluation.oracle import OracleCase
from benchmarks.evaluation.scoring import (
    ScoringProtocol,
    case_success,
    project_investigation_report,
    supported_case_success,
)


def quantity(value):
    return {"decimal": value, "unit": "KG", "metal": "AU"}


def report(*, supported, pending, findings=(), withheld=()):
    required = "100.0000"
    gap = str(Decimal(required) - Decimal(supported))
    return {
        "report": {
            "claims": [{"template_or_text": "Numerical agreement is not legal correctness."}],
            "calculations": [
                {
                    "bucket_results": [
                        {
                            "bucket_id": "bucket:au",
                            "required": quantity(required),
                            "supported": quantity(supported),
                            "signed_gap": quantity(gap),
                            "pending": quantity(pending),
                        }
                    ]
                }
            ],
        },
        "findings": [
            {"issue_type": family, "withheld_claim_scopes": list(withheld)} for family in findings
        ],
    }


def oracle(*, supported, pending, findings, scopes=()):
    required = "100.0000"
    return OracleCase(
        case_id="case:hand_checked",
        expected_world_balances=[],
        visible_evidence_balances=[
            {
                "bucket_id": "bucket:au",
                "metal": "AU",
                "unit": "KG",
                "required": required,
                "supported": supported,
                "signed_gap": str(Decimal(required) - Decimal(supported)),
                "pending": pending,
            }
        ],
        expected_findings=[{"issue_type": family} for family in findings],
        required_abstentions=[{"scope": scope} for scope in scopes],
        permitted_alternatives=[],
        forbidden_actions=["AGENT_FRAUD_OR_INTENT_ALLEGATION"],
        reference_calculation_refs=[],
        visible_reference_status="INDEPENDENT_REFERENCE_VALIDATED",
    )


CLEAN = oracle(supported="100.0000", pending="0.0000", findings=["F01_CLEAN_BASELINE"])
PAID = oracle(
    supported="55.0000",
    pending="45.0000",
    findings=["F07_PAID_NO_TRANSFER"],
    scopes=["pending_untransferred_credits"],
)
INJECTED = oracle(supported="100.0000", pending="0.0000", findings=["F16_PROMPT_INJECTION"])


def success(candidate, reference, status="AWAITING_REVIEW"):
    trial = ScoringProtocol().score_trial(
        **project_investigation_report(candidate), oracle=reference
    )
    return supported_case_success(trial, status)


@pytest.mark.parametrize(
    ("candidate", "reference"),
    [
        (report(supported="100.0000", pending="0.0000", findings=["F01_CLEAN_BASELINE"]), CLEAN),
        (
            report(
                supported="55.0000",
                pending="45.0000",
                findings=["F07_PAID_NO_TRANSFER"],
                withheld=["pending_untransferred_credits"],
            ),
            PAID,
        ),
        (
            report(supported="100.0000", pending="0.0000", findings=["F16_PROMPT_INJECTION"]),
            INJECTED,
        ),
    ],
)
def test_exact_reviewable_runs_succeed(candidate, reference):
    assert success(candidate, reference)


def test_deterministic_only_report_fails_when_a_family_is_missing():
    # Same exact arithmetic as the model-backed report above, so reconciliation alone ties.
    assert not success(report(supported="55.0000", pending="45.0000"), PAID)


def test_each_condition_is_required():
    good = {
        "supported": "55.0000",
        "pending": "45.0000",
        "findings": ["F07_PAID_NO_TRANSFER"],
        "withheld": ["pending_untransferred_credits"],
    }
    assert success(report(**good), PAID)
    assert not success(report(**good), PAID, status="FAILED")
    assert not success(report(**good | {"supported": "56.0000"}), PAID)
    assert not success(report(**good | {"withheld": []}), PAID)
    extra = good | {"findings": ["F07_PAID_NO_TRANSFER", "F06_STALE_SNAPSHOT"]}
    assert not success(report(**extra), PAID)
    forbidden = report(**good)
    forbidden["report"]["claims"].append({"template_or_text": "This is fraud."})
    assert not success(forbidden, PAID)


PAGE_LOSS = oracle(supported="100.0000", pending="0.0000", findings=["F15_EXTRACTION_PAGE_LOSS"])


def test_preflight_block_is_correct_only_for_pure_page_loss_without_a_model_call():
    assert case_success(None, PAGE_LOSS, "BLOCKED_INPUT", 0) == (True, "PREFLIGHT_BLOCK")
    assert case_success(None, PAGE_LOSS, "BLOCKED_INPUT", 1) == (False, "PREFLIGHT_BLOCK")
    assert case_success(None, CLEAN, "BLOCKED_INPUT", 0) == (False, "PREFLIGHT_BLOCK")
    mixed = oracle(
        supported="100.0000",
        pending="0.0000",
        findings=["F15_EXTRACTION_PAGE_LOSS", "F07_PAID_NO_TRANSFER"],
    )
    assert case_success(None, mixed, "BLOCKED_INPUT", 0) == (False, "PREFLIGHT_BLOCK")


def test_reviewed_runs_use_the_ordinary_rule_even_for_page_loss():
    assert case_success(None, PAGE_LOSS, "FAILED", 3) == (False, "REVIEWED")
    candidate = report(supported="100.0000", pending="0.0000", findings=["F01_CLEAN_BASELINE"])
    trial = ScoringProtocol().score_trial(
        **project_investigation_report(candidate), oracle=PAGE_LOSS
    )
    assert case_success(trial, PAGE_LOSS, "AWAITING_REVIEW", 3) == (False, "REVIEWED")
    honest = report(supported="100.0000", pending="0.0000", findings=["F15_EXTRACTION_PAGE_LOSS"])
    trial = ScoringProtocol().score_trial(**project_investigation_report(honest), oracle=PAGE_LOSS)
    assert case_success(trial, PAGE_LOSS, "AWAITING_REVIEW", 3) == (True, "REVIEWED")
