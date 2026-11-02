"""Scripted C10 port with no provider access, recovery, retries or invented usage."""

from collections import deque

from recycleguard.config import Settings
from recycleguard.contracts import CommandContext, ServiceResult
from recycleguard.model_port import ModelCallRequest, ModelCallResult


class ScriptedModelPort:
    def __init__(self, settings: Settings, results: list[ServiceResult[ModelCallResult]]):
        if settings.mode != "test" or not settings.enable_test_adapters:
            raise ValueError("scripted model requires explicitly enabled test mode")
        self.results = deque(results)
        self.calls: list[tuple[CommandContext, ModelCallRequest]] = []

    def invoke(
        self, context: CommandContext, request: ModelCallRequest
    ) -> ServiceResult[ModelCallResult]:
        if not self.results:
            raise RuntimeError("script exhausted; no fallback model exists")
        result = self.results[0]
        if (result.operation_id, result.attempt_id) != (context.operation_id, context.attempt_id):
            raise ValueError("scripted result does not belong to this operation/attempt")
        self.calls.append((context, request))
        return self.results.popleft()
