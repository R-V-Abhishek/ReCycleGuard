"""Trusted injected workflow services. No runtime test adapter or provider selection."""

from collections.abc import Callable
from dataclasses import dataclass

from pydantic import JsonValue

from recycleguard.contracts.core import BoundaryModel, CommandContext, ServiceResult
from recycleguard.contracts.extraction import Observation
from recycleguard.contracts.workflow import RunSpec, StageOutcome


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
    """What the deterministic engine computed, in the form the Analyst may be shown."""

    facts: dict[str, JsonValue]
    calculation_ids: list[str]
    decided_families: list[str]
    reader_context: dict[str, JsonValue]


@dataclass(frozen=True)
class AgentWiring:
    """Trusted inputs of the Reader and Analyst. Present only for the multi-agent variants."""

    observations: Callable[[], list[Observation]]
    facts: Callable[[CommandContext], AgentFacts]
    families: tuple[str, ...]
    max_reader_chunks: int
    use_reader: bool


class OutcomeUnknownError(RuntimeError):
    """A child operation may have committed; retrying it automatically is unsafe."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
