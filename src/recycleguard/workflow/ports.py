"""Trusted injected workflow services. No runtime test adapter or provider selection."""

from collections.abc import Callable
from dataclasses import dataclass

from recycleguard.contracts.core import BoundaryModel, CommandContext, ServiceResult
from recycleguard.contracts.workflow import RunSpec, StageOutcome


@dataclass(frozen=True)
class ToolBinding:
    arguments_model: type[BoundaryModel]
    handler: Callable[[CommandContext, BoundaryModel], ServiceResult[StageOutcome]]


@dataclass(frozen=True)
class WorkflowStages:
    preflight: Callable[[CommandContext, RunSpec], ServiceResult[StageOutcome]]
    draft: Callable[[CommandContext, RunSpec], ServiceResult[StageOutcome]]
    verify: Callable[[CommandContext, RunSpec], ServiceResult[StageOutcome]]
