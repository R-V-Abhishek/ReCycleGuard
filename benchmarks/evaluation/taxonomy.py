"""PROTOCOL section 7 failure classes, derived only from recorded outcomes. Evaluator-only.

The first matching rule wins, so a trial has exactly one class. A trial that succeeded has none.
"""

INFRASTRUCTURE, PARSER, TOOL, RETRIEVAL = (
    "infrastructure",
    "parser",
    "tool",
    "retrieval/applicability",
)
MODEL_SCHEMA, MODEL_REASONING, VERIFIER = "model-schema", "model-reasoning", "verifier"
BUDGET_STOP, TIMEOUT, ORACLE, NOT_RUN = "budget-stop", "timeout", "oracle", "not-run"
CLASSES = (
    INFRASTRUCTURE,
    PARSER,
    TOOL,
    RETRIEVAL,
    MODEL_SCHEMA,
    MODEL_REASONING,
    VERIFIER,
    BUDGET_STOP,
    TIMEOUT,
    ORACLE,
    NOT_RUN,
)
_TIMEOUT_CODES = {"PROVIDER_TIMEOUT"}
_BUDGET_CODES = {"BUDGET_EXHAUSTED"}
_RETRIEVAL_SCOPES = {"rule_version_applied", "deadline_extension"}


def _codes(calls, kinds):
    return {code for call in calls if call["kind"] in kinds for code in call["issue_codes"]}


def classify_failure(row: dict, ledger_status: str | None, result: dict | None) -> str | None:
    """``row`` is a score row; ``result`` is the sealed trial result, when one exists."""
    if row.get("success"):
        return None
    if row.get("not_scored_reason"):
        return ORACLE
    if ledger_status == "NOT_RUN" or (ledger_status is None and result is None):
        return NOT_RUN
    if result is None:
        return INFRASTRUCTURE
    calls = result.get("calls") or []
    status, stop = result["status"], result.get("stop_reason")
    model_codes = _codes(calls, {"MODEL"})
    every_code = _codes(calls, {"MODEL", "TOOL", "STAGE"})
    if every_code & _TIMEOUT_CODES:
        return TIMEOUT
    if stop == "BUDGET_EXHAUSTED" or every_code & _BUDGET_CODES:
        return BUDGET_STOP
    if status == "BLOCKED_INPUT":
        return PARSER
    if model_codes or status == "BLOCKED_OUTPUT" or result.get("rejected_actions"):
        return MODEL_SCHEMA
    if _codes(calls, {"TOOL"}):
        return TOOL
    if _codes(calls, {"STAGE"}) or status == "FAILED":
        return VERIFIER if _verifier_failed(calls) else TOOL
    verification = ((result.get("report") or {}).get("verification") or {}).get("verdict")
    if verification == "BLOCKED":
        return VERIFIER
    if set(row.get("missing_abstentions") or ()) & _RETRIEVAL_SCOPES:
        return RETRIEVAL
    return MODEL_REASONING


def _verifier_failed(calls):
    return any(
        call["kind"] == "STAGE" and call["issue_codes"] and ".verify" in call["event_type"]
        for call in calls
    )
