import { ApiClient, ApiError, ROUTES } from "./client";
import type { Job, TraceEvent } from "./types";

export interface SseFrame {
  event: string;
  id: string | null;
  data: string;
}

const protocol = (message: string) => new ApiError("PROTOCOL", null, null, message);

// Line-oriented parsing supports LF, CRLF and CR, including a CRLF split between reads.
// Only blank-line-terminated frames are dispatched; an interrupted frame is replayed.
export class SseParser {
  private readonly decoder = new TextDecoder("utf-8", { fatal: true });
  private line = "";
  private skipLf = false;
  private event = "message";
  private id: string | null = null;
  private data: string[] = [];
  private size = 0;

  feed(chunk: Uint8Array): SseFrame[] {
    let decoded: string;
    try { decoded = this.decoder.decode(chunk, { stream: true }); }
    catch { throw protocol("The event stream contains invalid UTF-8."); }
    const frames: SseFrame[] = [];
    for (const character of decoded) {
      if (this.skipLf) {
        this.skipLf = false;
        if (character === "\n") continue;
      }
      if (++this.size > 4 * 1024 * 1024) throw protocol("An event stream frame is too large to display.");
      if (character !== "\r" && character !== "\n") { this.line += character; continue; }
      this.skipLf = character === "\r";
      if (this.line === "") {
        if (this.data.length) frames.push({ event: this.event, id: this.id, data: this.data.join("\n") });
        this.event = "message"; this.id = null; this.data = []; this.size = 0;
      } else if (!this.line.startsWith(":")) {
        const colon = this.line.indexOf(":");
        const field = colon === -1 ? this.line : this.line.slice(0, colon);
        let value = colon === -1 ? "" : this.line.slice(colon + 1);
        if (value.startsWith(" ")) value = value.slice(1);
        if (field === "event") this.event = value || "message";
        else if (field === "id" && !value.includes("\0")) this.id = value;
        else if (field === "data") this.data.push(value);
      }
      this.line = "";
    }
    return frames;
  }
}

export type StreamConnection = "connecting" | "live" | "reconnecting" | "stopped" | "failed";

export interface StreamHandlers {
  onTrace(event: TraceEvent): void;
  onStopped(job: Job): void;
  onConnection(state: StreamConnection, detail?: string): void;
}

function record(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function strings(value: unknown): value is string[] {
  return Array.isArray(value) && value.every(item => typeof item === "string");
}
function nullableString(value: unknown): boolean { return value === null || typeof value === "string"; }
function stage(value: unknown): boolean {
  return record(value) && ["PASS", "QUALIFIED", "BLOCKED"].includes(String(value.disposition)) &&
    typeof value.concise_decision === "string" && Array.isArray(value.evidence_refs) &&
    strings(value.service_operation_ids) && strings(value.retrieval_attempt_ids) &&
    strings(value.calculation_ids) && strings(value.finding_revision_ids);
}

export function validateTraceEvent(value: unknown): asserts value is TraceEvent {
  if (!record(value) || !Number.isSafeInteger(value.sequence) || Number(value.sequence) < 1 ||
      typeof value.event_id !== "string" || !value.event_id ||
      typeof value.event_type !== "string" || !value.event_type ||
      !["AUDIT", "PLAN", "TOOL_PROPOSED", "ASSESSMENT", "PROMPT_PREPARED", "MODEL_RESULT", "TOOL_OR_STAGE_RESULT"].includes(String(value.kind))) {
    throw protocol("The event stream returned an invalid trace identity or sequence.");
  }
  for (const key of ["operation_id", "attempt_id", "turn_id"]) {
    if (value[key] !== null && typeof value[key] !== "string") throw protocol(`Trace ${key} is invalid.`);
  }
  if (!record(value.payload_ref) || !/^[0-9a-f]{64}$/.test(String(value.payload_ref.sha256)) ||
      !Number.isSafeInteger(value.payload_ref.byte_length) || Number(value.payload_ref.byte_length) < 0 ||
      typeof value.payload_ref.media_type !== "string") throw protocol("Trace payload reference is invalid.");
  if (["PLAN", "TOOL_PROPOSED", "ASSESSMENT"].includes(String(value.kind)) && !record(value.data)) {
    throw protocol("The event stream returned a missing structured trace payload.");
  }
  if (value.kind === "PROMPT_PREPARED" &&
      (!["PLAN", "ASSESS"].includes(String(value.phase)) ||
       (value.system_template !== null && typeof value.system_template !== "string") ||
       typeof value.note !== "string" || !("request" in value))) throw protocol("Prepared context is invalid.");
  if (value.kind === "PLAN") {
    const data = value.data as Record<string, unknown>;
    if (typeof data.plan_id !== "string" || typeof data.finding_id !== "string" ||
        !Number.isSafeInteger(data.revision) || Number(data.revision) < 1 ||
        !nullableString(data.previous_plan_ref) || !nullableString(data.triggering_operation_ref) ||
        typeof data.objective !== "string" || !strings(data.hypotheses) ||
        !strings(data.proposed_checks) || !strings(data.expected_evidence) || !strings(data.stopping_criteria)) {
      throw protocol("The stream returned an invalid plan record.");
    }
  }
  if (value.kind === "TOOL_PROPOSED") {
    const data = value.data as Record<string, unknown>;
    if (!["CHECK", "REFORMULATE"].includes(String(data.action_kind)) ||
        typeof data.plan_ref !== "string" || typeof data.allowed_operation !== "string" ||
        typeof data.finding_id !== "string" || typeof data.concise_reason !== "string" ||
        !record(data.typed_arguments) || !Array.isArray(data.evidence_refs)) {
      throw protocol("The stream returned an invalid tool proposal.");
    }
  }
  if (value.kind === "ASSESSMENT") {
    const data = value.data as Record<string, unknown>;
    if (typeof data.assessment_id !== "string" || typeof data.operation_ref !== "string" ||
        typeof data.plan_ref !== "string" || !Array.isArray(data.observation_refs) ||
        !["SUPPORTS", "REFUTES", "WEAK", "NO_PROGRESS", "UNKNOWN"].includes(String(data.verdict)) ||
        !["CONTINUE", "RESOLVE", "ABSTAIN"].includes(String(data.disposition)) ||
        typeof data.next_check_or_stop !== "string" || !nullableString(data.weak_result_or_mistake) ||
        !nullableString(data.revised_plan_ref)) throw protocol("The stream returned an invalid assessment.");
  }
  if (["MODEL_RESULT", "TOOL_OR_STAGE_RESULT"].includes(String(value.kind))) {
    if (typeof value.status !== "string" || !Array.isArray(value.issues) ||
        !value.issues.every(issue => record(issue) && typeof issue.code === "string" &&
          typeof issue.message === "string" && ["INFO", "WARNING", "BLOCKING"].includes(String(issue.severity)))) {
      throw protocol("Trace outcome is invalid.");
    }
    if (value.data !== undefined && !stage(value.data)) throw protocol("Trace stage outcome is invalid.");
  }
}

function parse(data: string): unknown {
  try { return JSON.parse(data); }
  catch { throw protocol("The event stream returned invalid JSON; the cursor was not advanced."); }
}

function stoppedJob(value: unknown, runId: string): Job {
  if (!record(value) || !["STOPPED", "FAILED", "INTERRUPTED"].includes(String(value.status)) ||
      (value.run_id !== undefined && value.run_id !== runId)) throw protocol("The stream returned an invalid stopped job.");
  return value as unknown as Job;
}

const sleep = (ms: number, signal: AbortSignal) => new Promise<void>((resolve) => {
  if (signal.aborted) return resolve();
  const finish = () => { clearTimeout(timer); signal.removeEventListener("abort", finish); resolve(); };
  const timer = setTimeout(finish, ms);
  signal.addEventListener("abort", finish, { once: true });
});

// Subscription retries only reads. Mutations are never dispatched here. An event is
// acknowledged only after its handler returns, so a disconnect replays uncommitted work.
export async function followRun(
  client: ApiClient, runId: string, after: number, handlers: StreamHandlers,
  signal: AbortSignal, retryDelayMs = 2000,
): Promise<void> {
  if (!Number.isSafeInteger(after) || after < 0) throw protocol("The trace cursor must be a nonnegative integer.");
  let cursor = after;
  let firstConnection = true;
  while (!signal.aborted) {
    handlers.onConnection(firstConnection ? "connecting" : "reconnecting");
    firstConnection = false;
    try {
      const response = await client.send(ROUTES.events, {
        params: { run_id: runId }, query: `?after=${cursor}`,
        headers: { "Last-Event-ID": String(cursor), Accept: "text/event-stream" }, signal,
      });
      if (signal.aborted) { await response.body?.cancel(); return; }
      const contentType = response.headers.get("Content-Type");
      if (contentType && !contentType.toLowerCase().startsWith("text/event-stream")) {
        await response.body?.cancel();
        throw protocol("Expected an event stream, received a different content type.");
      }
      if (!response.body) throw new ApiError("NETWORK", null, null, "No stream body");
      handlers.onConnection("live");
      const parser = new SseParser();
      const reader = response.body.getReader();
      const cancel = () => { void reader.cancel().catch(() => {}); };
      signal.addEventListener("abort", cancel, { once: true });
      try {
        for (;;) {
          const { done, value } = await reader.read();
          if (signal.aborted) return;
          if (done) break;
          for (const frame of parser.feed(value)) {
            if (signal.aborted) return;
            if (frame.event === "trace") {
              const event = parse(frame.data);
              validateTraceEvent(event);
              if (frame.id === null || !/^\d+$/.test(frame.id) ||
                  !Number.isSafeInteger(Number(frame.id)) || Number(frame.id) !== event.sequence) {
                throw protocol("Trace SSE id does not match its recorded sequence; cursor unchanged.");
              }
              if (event.sequence > cursor + 1) throw new Error("Trace sequence gap; replaying from the last applied event.");
              handlers.onTrace(event); // Replays remain idempotent in the trace store.
              cursor = Math.max(cursor, event.sequence);
            } else if (frame.event === "stopped") {
              const job = stoppedJob(parse(frame.data), runId);
              handlers.onStopped(job);
              handlers.onConnection(job.status === "STOPPED" ? "stopped" : "failed",
                job.status === "STOPPED" ? undefined : job.detail ?? `Investigation worker ${job.status.toLowerCase()}.`);
              return;
            }
          }
        }
      } finally {
        signal.removeEventListener("abort", cancel);
        // Cancellation errors cannot replace the actual stream/handler error being reported.
        try { await reader.cancel(); } catch { /* the stream may already be errored */ }
        reader.releaseLock();
      }
    } catch (cause) {
      if (signal.aborted) return;
      if (cause instanceof ApiError && (cause.kind === "PROTOCOL" ||
          (cause.kind === "HTTP" && cause.status !== 429 && (cause.status ?? 0) < 500))) {
        handlers.onConnection("failed", cause.message); return;
      }
      handlers.onConnection("reconnecting", cause instanceof Error ? cause.message : "Stream disconnected.");
    }
    if (!signal.aborted) await sleep(retryDelayMs, signal);
  }
}
