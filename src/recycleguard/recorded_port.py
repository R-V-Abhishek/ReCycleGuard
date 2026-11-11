"""Recorded-response C10 port: serves saved results keyed by the exact request, never infers.

A replay is not a new trial. Each recorded ``(request, result)`` pair answers only an identical
request (same configuration, prompt template and exact request bytes). Any other request raises;
there is no provider, fallback or nearest match. The recorded response and request blobs must
already be present in the store being replayed into.
"""

import json
from collections import defaultdict, deque

from recycleguard.config import Settings
from recycleguard.contracts import BlobRef, CommandContext, ServiceResult
from recycleguard.contracts.audit import OperationIntent, OperationResult
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


def load_recordings(kernel, run_id: str):
    """Read ``(request, result)`` pairs from a finished run's audit records, in call order.

    Each model operation's intent holds its exact request; each attempt's stored result holds the
    provider result. Only attempts whose result was captured as a ``ServiceResult`` are returned.
    A timeout or an unknown outcome has no recorded response, so a replay of it raises instead.
    """
    blobs, connection = kernel.blob_store, kernel.connection
    pairs = []
    intents = connection.execute(
        "SELECT operation_id,intent_json FROM operation_intents WHERE stream_id=? ORDER BY rowid",
        (f"stream:{run_id}",),
    ).fetchall()
    for intent_row in intents:
        intent = OperationIntent.model_validate_json(intent_row["intent_json"])
        if not intent.event_type.startswith("graph.model."):
            continue
        request = ModelCallRequest.model_validate_json(blobs.get(intent.payload))
        attempts = connection.execute(
            "SELECT a.attempt_id,r.result_json FROM operation_attempts a "
            "JOIN attempt_results r ON r.attempt_id=a.attempt_id "
            "WHERE a.operation_id=? ORDER BY a.rowid",
            (intent_row["operation_id"],),
        ).fetchall()
        for attempt in attempts:
            stored = OperationResult.model_validate_json(attempt["result_json"])
            record = json.loads(blobs.get(stored.payload))
            raw = json.loads(blobs.get(BlobRef.model_validate(record["raw_result_blob"])))
            if "status" in raw:
                pairs.append((request, ServiceResult[ModelCallResult].model_validate(raw)))
    return pairs
