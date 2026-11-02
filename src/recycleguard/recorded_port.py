"""Recorded-response C10 port: serves saved results keyed by the exact request, never infers.

A replay is not a new trial. Each recorded ``(request, result)`` pair answers only an identical
request (same configuration, prompt template and exact request bytes). Any other request raises;
there is no provider, fallback or nearest match. The recorded response and request blobs must
already be present in the store being replayed into.
"""

from collections import defaultdict, deque

from recycleguard.config import Settings
from recycleguard.contracts import CommandContext, ServiceResult
from recycleguard.model_port import ModelCallRequest, ModelCallResult


def _key(request: ModelCallRequest) -> tuple[str, str, str]:
    return (
        request.model_configuration_id,
        request.prompt_template_digest,
        request.exact_request_blob.sha256,
    )


class RecordedReplayModelPort:
    def __init__(
        self,
        settings: Settings,
        recordings: list[tuple[ModelCallRequest, ServiceResult[ModelCallResult]]],
    ):
        if settings.mode != "test" or not settings.enable_test_adapters:
            raise ValueError("recorded replay requires explicitly enabled test mode")
        self.queues = defaultdict(deque)
        for request, result in recordings:
            self.queues[_key(request)].append(result)
        self.served = 0

    def remaining(self) -> int:
        return sum(len(queue) for queue in self.queues.values())

    def invoke(
        self, context: CommandContext, request: ModelCallRequest
    ) -> ServiceResult[ModelCallResult]:
        queue = self.queues.get(_key(request))
        if not queue:
            raise RuntimeError("no recorded response for this exact request; no fallback exists")
        recorded = queue.popleft()
        self.served += 1
        output = recorded.output
        if output is not None:
            call_id = f"model_call:{context.attempt_id.split(':', 1)[1]}"
            output = output.model_copy(update={"model_call_id": call_id})
        return recorded.model_copy(
            update={
                "operation_id": context.operation_id,
                "attempt_id": context.attempt_id,
                "output": output,
                "audit_event_ids": [],
            }
        )
