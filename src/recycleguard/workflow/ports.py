"""Trusted injected workflow services. No runtime test adapter or provider selection."""

from collections.abc import Callable
from dataclasses import dataclass

from recycleguard.contracts.core import BoundaryModel, CommandContext, ServiceResult
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
