import type { TraceEvent } from "../api/types";

export interface TraceState {
  events: TraceEvent[];
  cursor: number;
}

export const emptyTrace: TraceState = { events: [], cursor: 0 };

// Merges by stable event ID and sequence, keeping order. Replayed events are no-ops,
// so a reconnect or a trace refetch can never duplicate a timeline row.
export function applyEvents(state: TraceState, incoming: TraceEvent[]): TraceState {
  const seen = new Set(state.events.map((event) => event.event_id));
  const sequences = new Set(state.events.map((event) => event.sequence));
  const fresh = incoming.filter((event) => {
    if (seen.has(event.event_id) || sequences.has(event.sequence)) return false;
    seen.add(event.event_id);
    sequences.add(event.sequence);
    return true;
  });
  if (!fresh.length) return state;
  const events = [...state.events, ...fresh].sort((a, b) => a.sequence - b.sequence);
  return { events, cursor: Math.max(state.cursor, events[events.length - 1].sequence) };
}

// graph.<kind>.<name>.result, e.g. graph.tool.compute_reconciliation.result
export function eventParts(event: TraceEvent): { family: string; name: string } {
  const parts = event.event_type.split(".");
  return { family: parts[1] ?? event.event_type, name: parts.slice(2, -1).join(".") };
}

export function findPlan(events: TraceEvent[], planId: string | null | undefined) {
  if (!planId) return undefined;
  return events.find((e) => e.kind === "PLAN" && e.data.plan_id === planId);
}

export function findByOperation(events: TraceEvent[], operationId: string | null | undefined) {
  if (!operationId) return undefined;
  return events.find((e) => e.operation_id === operationId && e.kind !== "AUDIT");
}

// The tool result that follows a proposal: the next tool event before any later proposal.
export function resultForProposal(events: TraceEvent[], proposal: TraceEvent) {
  for (const event of events) {
    if (event.sequence <= proposal.sequence) continue;
    if (event.kind === "TOOL_PROPOSED") return undefined;
    if (event.kind === "TOOL_OR_STAGE_RESULT" && eventParts(event).family === "tool") return event;
  }
  return undefined;
}
