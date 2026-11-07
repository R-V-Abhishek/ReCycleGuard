"""The Retriever: a bounded loop that decides what to read, grades what came back, and re-queries.

It is the only agent that sees dossier text. Each turn is one model call; the tool it asks for is
run by `execute`, which the workflow runner supplies as an audited external call. Everything the
loop decides for itself is deterministic: which calls are valid, which are repeats, what the model
was shown, and which claims are kept. A claim survives only when its quote occurs verbatim in text
the Retriever was shown, and no quote is kept.
"""

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from pydantic import JsonValue

from recycleguard.agents.models import (
    DroppedClaim,
    RetrievalCoverage,
    RetrieverStep,
    RetrieverTurn,
    VerifiedClaim,
)
from recycleguard.agents.passages import (
    MAX_UNIT_CHARS,
    AgentCallError,
    shown_text,
    text_units,
    verify_claims,
)
from recycleguard.contracts.extraction import Observation

HISTORY_TURNS = 6


@dataclass
class ToolResult:
    """What a tool gave back. `view` is what the next turn sees, never more."""

    view: dict
    refused: str | None = None
    result_ids: list[str] = field(default_factory=list)


@dataclass
class RetrievalOutcome:
    verified: list[VerifiedClaim]
    turns: list[RetrieverTurn]
    coverage: RetrievalCoverage


def fingerprint(tool: str | None, query: str | None, observation_ids: list[str]) -> str:
    text = json.dumps([tool, (query or "").strip().lower(), sorted(observation_ids)])
    return hashlib.sha256(text.encode()).hexdigest()


def refusal_for(step: RetrieverStep, units: Mapping[str, str], called: set[str]) -> str | None:
    """Why a requested call cannot run, or None. A refusal still uses the turn."""
    if step.tool is None:
        return "tool is required when action is CALL"
    if step.tool == "read_passages":
        if not step.observation_ids:
            return "observation_ids is required for read_passages"
        unknown = [ref for ref in step.observation_ids if ref not in units]
        if unknown:
            return "observation_ids must be copied exactly from passage_ids"
    if step.tool == "search_rules" and not (step.query or "").strip():
        return "query is required for search_rules"
    if fingerprint(step.tool, step.query, step.observation_ids) in called:
        return "that call was already made; read other passages or word the query differently"
    return None


def retriever_body(
    turn: int,
    max_turns: int,
    context: Mapping[str, JsonValue],
    passage_ids: list[str],
    history: list[dict],
    last: dict | None,
) -> dict:
    """The only content a Retriever call receives."""
    return {
        "case_context": dict(context),
        "turn": turn,
        "turns_left": max_turns - turn + 1,
        "passage_ids": passage_ids,
        "history": history[-HISTORY_TURNS:],
        "last_result": last,
    }


def run_retriever(
    observations: list[Observation],
    step: Callable[[dict], RetrieverStep],
    execute: Callable[[RetrieverStep], ToolResult],
    max_turns: int,
    context: Mapping[str, JsonValue] | None = None,
) -> RetrievalOutcome:
    """Run at most max_turns turns. An unusable reply ends retrieval with the claims kept so far.

    `step` returns a validated RetrieverStep or raises AgentCallError. `execute` runs one valid,
    new tool call and returns its result; it is never asked for a call this loop has refused.
    """
    units = dict(text_units(observations))
    passage_ids = sorted(units)
    shown: dict[str, str] = {}
    called: set[str] = set()
    history: list[dict] = []
    turns: list[RetrieverTurn] = []
    verified: dict[tuple[str, str], VerifiedClaim] = {}
    dropped: list[DroppedClaim] = []
    last: dict | None = None
    proposed = tool_calls = searches = reformulations = 0
    stopped = None
    for turn in range(1, max_turns + 1):
        try:
            reply = step(retriever_body(turn, max_turns, context or {}, passage_ids, history, last))
        except AgentCallError as exc:
            stopped = exc.reason
            break
        proposed += len(reply.claims)
        good, bad = verify_claims(reply.claims, shown)
        verified.update({(item.kind, item.observation_id): item for item in good})
        dropped.extend(bad)
        calling = reply.action == "CALL"
        refused, result_ids = None, []
        if calling and turn == max_turns:
            refused, stopped = "TURN_CAP", "TURN_CAP"
        elif calling:
            refused = refusal_for(reply, units, called)
            if refused is None:
                called.add(fingerprint(reply.tool, reply.query, reply.observation_ids))
                tool_calls += 1
                if reply.tool == "search_rules":
                    reformulations += searches > 0
                    searches += 1
                result = execute(reply)
                refused, result_ids = result.refused, result.result_ids
                # Text counts as shown only when the tool really returned it.
                if reply.tool == "read_passages" and refused is None:
                    shown.update({ref: shown_text(units, ref) for ref in reply.observation_ids})
                last = {"tool": reply.tool, "refused": refused, "result": result.view}
            else:
                last = {"tool": reply.tool, "refused": refused, "result": None}
            history.append(
                {
                    "turn": turn,
                    "grade_of_previous_result": reply.grade,
                    "tool": reply.tool,
                    "query": reply.query,
                    "observation_ids": reply.observation_ids,
                    "refused": refused,
                }
            )
        turns.append(
            RetrieverTurn(
                turn=turn,
                grade=reply.grade,
                reason=reply.reason,
                action=reply.action,
                tool=reply.tool if calling else None,
                query=reply.query if calling else None,
                observation_ids=reply.observation_ids if calling else [],
                refused=refused,
                result_ids=result_ids,
                claims_proposed=len(reply.claims),
            )
        )
        if not calling or stopped:
            break
    read = sorted(shown)
    coverage = RetrievalCoverage(
        units_total=len(units),
        units_read=len(read),
        units_truncated=sum(len(units[ref]) > MAX_UNIT_CHARS for ref in read),
        turns=len(turns),
        tool_calls=tool_calls,
        searches=searches,
        reformulations=reformulations,
        claims_proposed=proposed,
        claims_verified=len(verified),
        claims_dropped=dropped,
        read_observation_ids=read,
        stopped_because=stopped,
    )
    return RetrievalOutcome(list(verified.values()), turns, coverage)
