"""Retriever then Classifier, as a pure function of observations, facts and the agents' ports."""

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass

from pydantic import JsonValue

from recycleguard.agents.classifier import (
    ClassifierToolResult,
    allowed_refs,
    lookup_proposals,
    require_claim_support,
    run_classifier,
)
from recycleguard.agents.models import (
    AgentArchitecture,
    ClassifierStep,
    ClassifierTurn,
    RetrievalCoverage,
    RetrieverStep,
    RetrieverTurn,
    VerifiedClaim,
)
from recycleguard.agents.retriever import ToolResult, run_retriever
from recycleguard.contracts.core import EvidenceRef
from recycleguard.contracts.extraction import Observation
from recycleguard.contracts.workflow import FindingProposal


@dataclass
class AgentOutcome:
    """What the agents produced. Proposals still go through the finding gate."""

    proposals: list[FindingProposal]
    unsupported: list[FindingProposal]
    refs: dict[str, EvidenceRef]
    verified: list[VerifiedClaim]
    coverage: RetrievalCoverage | None
    retriever_turns: list[RetrieverTurn]
    classifier_turns: list[ClassifierTurn]
    classifier_calls: int
    classifier_stopped_because: str | None


def run_agents(
    observations: list[Observation],
    *,
    architecture: AgentArchitecture,
    facts: Mapping[str, JsonValue],
    calculation_ids: Iterable[str],
    decided_families: Iterable[str],
    families: Iterable[str],
    known_ids: Mapping[str, Iterable[str]],
    retrieve: Callable[[dict], RetrieverStep],
    retrieve_tool: Callable[[RetrieverStep], ToolResult],
    classify: Callable[[dict], ClassifierStep],
    classify_tool: Callable[[ClassifierStep], ClassifierToolResult],
    max_retriever_turns: int,
    max_classifier_calls: int,
    context: Mapping[str, JsonValue] | None = None,
) -> AgentOutcome:
    """Retrieval (unless ablated), then classification (unless replaced by the lookup).

    A failed retrieval keeps the claims verified so far. A failed classification yields no
    proposals. The deterministic findings are unaffected either way.
    """
    verified: list[VerifiedClaim] = []
    coverage, retriever_turns = None, []
    if architecture != "CLASSIFIER_ONLY":
        retrieved = run_retriever(
            observations, retrieve, retrieve_tool, max_retriever_turns, context
        )
        verified, coverage, retriever_turns = (
            retrieved.verified,
            retrieved.coverage,
            retrieved.turns,
        )
    calculation_ids = list(calculation_ids)
    decided = list(decided_families)
    if architecture == "RETRIEVER_LOOKUP":
        proposals, unsupported = lookup_proposals(verified, decided), []
        classifier_turns, calls, stopped = [], 0, None
    else:
        classified = run_classifier(
            facts=facts,
            calculation_ids=calculation_ids,
            verified=verified,
            decided_families=decided,
            families=families,
            known_ids=known_ids,
            step=classify,
            execute=classify_tool,
            max_calls=max_classifier_calls,
        )
        calculation_ids = classified.calculation_ids
        proposals, unsupported = require_claim_support(classified.proposals, verified)
        classifier_turns = classified.turns
        calls, stopped = classified.calls, classified.stopped_because
    refs = allowed_refs(observations, verified, calculation_ids)
    return AgentOutcome(
        proposals,
        unsupported,
        refs,
        verified,
        coverage,
        retriever_turns,
        classifier_turns,
        calls,
        stopped,
    )
