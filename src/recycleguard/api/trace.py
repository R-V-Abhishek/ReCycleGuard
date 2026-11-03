"""Read-only projections of actual audit records, never reconstructed agent reasoning."""

import json

from recycleguard.contracts.core import BlobRef
from recycleguard.contracts.workflow import ConfigurationPin, ContextManifest
from recycleguard.local_model import (
    BUILTIN_PROMPT,
    BUILTIN_PROMPT_VERSION,
    LocalModelConfig,
    PromptText,
    prompt_digest,
)
from recycleguard.workflow.runner import CallRecord


def _run_prompt(pin: ConfigurationPin, configured: LocalModelConfig | None) -> PromptText | None:
    """The template text only when its pin matches the run's; otherwise none is shown."""
    if configured is not None and configured.prompt_pin() == pin:
        return configured.prompt_text()
    if pin.digest == prompt_digest(BUILTIN_PROMPT_VERSION, BUILTIN_PROMPT):
        return BUILTIN_PROMPT
    return None


def trace_events(service, run_id, *, after=0, configured: LocalModelConfig | None = None):
    service.store.load(run_id)  # verifies event hash chain and referenced bytes
    spec = service.store.spec(run_id)
    model_backed = spec.execution_kind == "MODEL_BACKED"
    prompt = _run_prompt(spec.prompt, configured) if model_backed else None
    blobs, kernel = service.blobs, service.kernel
    output = []
    for event in kernel.list_stream_events(f"stream:{run_id}"):
        if event.sequence <= after:
            continue
        item = {
            "sequence": event.sequence,
            "event_id": event.event_id,
            "operation_id": event.operation_id,
            "turn_id": event.turn_id,
            "attempt_id": event.attempt_id,
            "event_type": event.event_type,
            "payload_ref": event.payload_blob.model_dump(mode="json"),
        }
        if event.event_type == "graph.context.result":
            manifest = ContextManifest.model_validate_json(blobs.get(event.payload_blob))
            request = json.loads(blobs.get(manifest.exact_request_blob))
            item.update(
                kind="PROMPT_PREPARED",
                phase=manifest.phase,
                request=request,
                system_template=(
                    None if prompt is None else prompt.system + prompt.phase_rules[manifest.phase]
                ),
                note=(
                    "Prepared context; exact sent wire prompt is retained after adapter completion."
                ),
            )
        elif event.event_type in {
            "graph.plan.result",
            "graph.action.result",
            "graph.assessment.result",
        }:
            item.update(
                kind={
                    "graph.plan.result": "PLAN",
                    "graph.action.result": "TOOL_PROPOSED",
                    "graph.assessment.result": "ASSESSMENT",
                }[event.event_type],
                data=json.loads(blobs.get(event.payload_blob)),
            )
        elif event.event_type.startswith(
            ("graph.model.", "graph.tool.", "graph.stage.")
        ) and event.event_type.endswith(".result"):
            # A logical operation can have multiple attempts. Each event's immutable
            # payload is authoritative for that attempt; terminal lookup can point
            # at a later attempt or be absent while retry is still in progress.
            record = CallRecord.model_validate_json(blobs.get(event.payload_blob))
            raw = json.loads(blobs.get(record.raw_result_blob))
            item.update(
                kind="MODEL_RESULT"
                if event.event_type.startswith("graph.model.")
                else "TOOL_OR_STAGE_RESULT",
                status=record.status,
                issues=[i.model_dump(mode="json") for i in record.issues],
            )
            if record.stage_output is not None:
                item["data"] = record.stage_output.model_dump(mode="json")
                if record.stage_output.output_blob is not None:
                    item["result"] = json.loads(blobs.get(record.stage_output.output_blob))
            if record.model_output is not None:
                item["response"] = record.model_output.model_dump(mode="json")
                item["exact_response"] = blobs.get(record.model_output.exact_response_blob).decode(
                    "utf-8"
                )
            # Exact provider transport retained even on failure, where available.
            if event.event_type.startswith("graph.model.") and raw.get("output_blob") is not None:
                item["provider_trace"] = json.loads(
                    blobs.get(BlobRef.model_validate(raw["output_blob"]))
                )
        else:
            item["kind"] = "AUDIT"
        output.append(item)
    return output
