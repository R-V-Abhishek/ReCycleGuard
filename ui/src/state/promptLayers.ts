import type {
  Json,
  ModelResultEvent,
  PromptPreparedEvent,
  ProviderTrace,
  TraceEvent,
} from "../api/types";

export type SentPrompt =
  | { state: "NO_TRACE" }
  | { state: "NOT_DISPATCHED"; trace: ProviderTrace }
  | { state: "UNPARSEABLE"; trace: ProviderTrace; raw: string }
  | {
      state: "SENT";
      trace: ProviderTrace;
      raw: string;
      prompt: string | null;
      parameters: Record<string, Json>;
    };

// Only a recorded provider_trace establishes what went over the wire. A sent prompt is never
// rebuilt from the /agent template or the prepared context.
export function sentPrompt(event: ModelResultEvent): SentPrompt {
  const trace = event.provider_trace;
  if (!trace) return { state: "NO_TRACE" };
  const raw = trace.request_body_utf8;
  if (raw === null || raw === undefined) return { state: "NOT_DISPATCHED", trace };
  try {
    const parsed: unknown = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      return { state: "UNPARSEABLE", trace, raw };
    }
    const { prompt, ...parameters } = parsed as Record<string, Json>;
    return { state: "SENT", trace, raw, prompt: typeof prompt === "string" ? prompt : null, parameters };
  } catch {
    return { state: "UNPARSEABLE", trace, raw };
  }
}

// The context prepared for a model call: the latest PROMPT_PREPARED before it in the same turn.
export function preparedFor(
  events: TraceEvent[],
  model: ModelResultEvent,
): PromptPreparedEvent | undefined {
  let found: PromptPreparedEvent | undefined;
  for (const event of events) {
    if (event.sequence >= model.sequence) break;
    if (event.kind === "PROMPT_PREPARED" && event.turn_id === model.turn_id) found = event;
  }
  return found;
}
