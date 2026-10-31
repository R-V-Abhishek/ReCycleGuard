import { ApiError } from "../api/client";
import { validateTraceEvent } from "../api/sse";
import type { TraceEvent } from "../api/types";

export interface TraceState { events: TraceEvent[]; cursor: number; }
export const emptyTrace: TraceState = { events: [], cursor: 0 };

function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value !== null && typeof value === "object") {
    const object = value as Record<string, unknown>;
    return `{${Object.keys(object).sort().map(key => `${JSON.stringify(key)}:${canonical(object[key])}`).join(",")}}`;
  }
  return JSON.stringify(value) ?? "undefined";
}

// Replays are idempotent; conflicting records at the same immutable identity are errors.
// The resume cursor covers only a contiguous prefix, never an unseen sequence gap.
export function applyEvents(state: TraceState, incoming: TraceEvent[]): TraceState {
  const byId = new Map(state.events.map(event => [event.event_id, event]));
  const bySequence = new Map(state.events.map(event => [event.sequence, event]));
  const fresh: TraceEvent[] = [];
  for (const event of incoming) {
    validateTraceEvent(event);
    const oldId = byId.get(event.event_id), oldSequence = bySequence.get(event.sequence);
    if (oldId || oldSequence) {
      const old = oldId ?? oldSequence;
      if (oldId !== oldSequence || canonical(old) !== canonical(event)) {
        throw new ApiError("PROTOCOL", null, null, "Conflicting immutable trace identities; the timeline was not changed.");
      }
      continue;
    }
    byId.set(event.event_id, event); bySequence.set(event.sequence, event); fresh.push(event);
  }
  if (!fresh.length) return state;
  const events = [...state.events, ...fresh].sort((a, b) => a.sequence - b.sequence);
  let cursor = state.cursor;
  while (bySequence.has(cursor + 1)) cursor++;
  return { events, cursor };
}

export function eventParts(event: TraceEvent): { family: string; name: string } {
  const parts = event.event_type.split(".");
  return { family: parts[1] ?? event.event_type, name: parts.slice(2, -1).join(".") };
}

export function findPlan(events: TraceEvent[], planId: string | null | undefined) {
  if (!planId) return undefined;
  const matches = events.filter(e => e.kind === "PLAN" && e.data.plan_id === planId);
  return matches.length === 1 ? matches[0] : undefined;
}

export function findByOperation(events: TraceEvent[], operationId: string | null | undefined, attemptId?: string | null) {
  if (!operationId) return undefined;
  const matches = events.filter(e => e.operation_id === operationId && e.kind !== "AUDIT" &&
    (attemptId === undefined || e.attempt_id === attemptId));
  return matches.length === 1 ? matches[0] : undefined;
}

// Assessment references establish the consumed logical operation. A retry with several
// observed attempts stays unlinked unless an exact attempt can be identified by the caller.
export function resultForProposal(events: TraceEvent[], proposal: TraceEvent) {
  if (proposal.kind !== "TOOL_PROPOSED" || !proposal.turn_id || !proposal.data?.allowed_operation ||
      typeof proposal.data.plan_ref !== "string" || !proposal.data.plan_ref) return undefined;
  const sameTurn = events.filter(e => e.turn_id === proposal.turn_id && e.sequence > proposal.sequence);
  const references = new Set(sameTurn.filter(e => e.kind === "ASSESSMENT" &&
    e.data.plan_ref === proposal.data.plan_ref).map(e => e.kind === "ASSESSMENT" ? e.data.operation_ref : ""));
  if (references.size > 1) return undefined;
  const candidates = sameTurn.filter(e => e.kind === "TOOL_OR_STAGE_RESULT" &&
    eventParts(e).family === "tool" &&
    e.operation_id !== null && (references.size ? references.has(e.operation_id) : true));
  const proposals = events.filter(e => e.kind === "TOOL_PROPOSED" && e.turn_id === proposal.turn_id);
  // Before assessment, C09 permits one action per turn. Once any assessment exists,
  // its explicit plan/operation reference must establish the relationship.
  if (!references.size && (proposals.length !== 1 || sameTurn.some(e => e.kind === "ASSESSMENT"))) return undefined;
  return candidates.length === 1 ? candidates[0] : undefined;
}
