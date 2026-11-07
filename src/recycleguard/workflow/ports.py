"""Trusted injected workflow services. No runtime test adapter or provider selection."""

from collections.abc import Callable
from dataclasses import dataclass

from pydantic import JsonValue

from recycleguard.agents.models import AgentArchitecture
from recycleguard.contracts.core import BoundaryModel, CommandContext, ServiceResult
from recycleguard.contracts.extraction import Observation
from recycleguard.contracts.workflow import BriefProposal, ReviewerBrief, RunSpec, StageOutcome


@dataclass(frozen=True)
class ToolBinding:
    arguments_model: type[BoundaryModel]
    handler: Callable[[CommandContext, BoundaryModel], ServiceResult[StageOutcome]]
    # Why arguments cannot be dispatched, so the model is asked again instead of a futile retry.
    reject_arguments: Callable[[BoundaryModel], str | None] | None = None


@dataclass(frozen=True)
class WorkflowStages:
    preflight: Callable[[CommandContext, RunSpec], ServiceResult[StageOutcome]]
    draft: Callable[[CommandContext, RunSpec], ServiceResult[StageOutcome]]
    verify: Callable[[CommandContext, RunSpec], ServiceResult[StageOutcome]]


@dataclass(frozen=True)
class AgentFacts:
    """What the deterministic engine computed, in the form the agents may be shown."""

    facts: dict[str, JsonValue]
    calculation_ids: list[str]
    decided_families: list[str]
    # Ids each compute tool accepts, by tool name; a call naming any other id is refused.
    known_ids: dict[str, list[str]]
    context: dict[str, JsonValue]


@dataclass(frozen=True)
class AgentWiring:
    """Trusted inputs of the Retriever and Classifier. Present only for the multi-agent variants."""

    observations: Callable[[], list[Observation]]
    facts: Callable[[CommandContext], AgentFacts]
    families: tuple[str, ...]
    architecture: AgentArchitecture
    max_retriever_turns: int
    max_classifier_calls: int


@dataclass(frozen=True)
class Briefing:
    """After verification, one advisory model brief per finding. A brief never changes the report.

    ``requests`` gives each finding's revision ID and the data the model is shown. ``record`` turns
    the model's draft, or the reason there is none, into the brief that is archived.
    """

    requests: Callable[[RunSpec], list[tuple[str, dict]]]
    record: Callable[[RunSpec, str, BriefProposal | None, str | None, str | None], ReviewerBrief]


class OutcomeUnknownError(RuntimeError):
    """A child operation may have committed; retrying it automatically is unsafe."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
