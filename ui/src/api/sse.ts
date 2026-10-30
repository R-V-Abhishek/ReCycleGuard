import { ApiClient, ApiError, ROUTES } from "./client";
import type { Job, TraceEvent } from "./types";

export interface SseFrame {
  event: string;
  id: string | null;
  data: string;
}

// Incremental parser. Network chunks can split anywhere, so frames are only emitted once
// their terminating blank line has arrived. Comment lines such as heartbeats are dropped.
export class SseParser {
  private buffer = "";
  private readonly decoder = new TextDecoder();

  feed(chunk: Uint8Array): SseFrame[] {
    this.buffer += this.decoder.decode(chunk, { stream: true });
    const frames: SseFrame[] = [];
    for (;;) {
      const match = /\r\n\r\n|\n\n|\r\r/.exec(this.buffer);
      if (!match) return frames;
      const block = this.buffer.slice(0, match.index);
      this.buffer = this.buffer.slice(match.index + match[0].length);
      const frame = parseBlock(block);
      if (frame) frames.push(frame);
    }
  }
}

function parseBlock(block: string): SseFrame | null {
  let event = "message";
  let id: string | null = null;
  const data: string[] = [];
  for (const line of block.split(/\r\n|\n|\r/)) {
    if (line === "" || line.startsWith(":")) continue;
    const colon = line.indexOf(":");
    const field = colon === -1 ? line : line.slice(0, colon);
    let value = colon === -1 ? "" : line.slice(colon + 1);
    if (value.startsWith(" ")) value = value.slice(1);
    if (field === "event") event = value;
    else if (field === "id") id = value;
    else if (field === "data") data.push(value);
  }
  return data.length ? { event, id, data: data.join("\n") } : null;
}

export type StreamConnection = "connecting" | "live" | "reconnecting" | "stopped" | "failed";

export interface StreamHandlers {
  onTrace(event: TraceEvent): void;
  onStopped(job: Job): void;
  onConnection(state: StreamConnection, detail?: string): void;
}

const sleep = (ms: number, signal: AbortSignal) =>
  new Promise<void>((resolve) => {
    if (signal.aborted) return resolve();
    const timer = setTimeout(resolve, ms);
    signal.addEventListener("abort", () => (clearTimeout(timer), resolve()), { once: true });
  });

// Read-only subscription using authenticated fetch, since EventSource cannot send a bearer
// header. The cursor only moves after a frame has been applied, so a failure replays it.
export async function followRun(
  client: ApiClient,
  runId: string,
  after: number,
  handlers: StreamHandlers,
  signal: AbortSignal,
  retryDelayMs = 2000,
): Promise<void> {
  let cursor = after;
  while (!signal.aborted) {
    handlers.onConnection(cursor === after ? "connecting" : "reconnecting");
    try {
      const response = await client.send(ROUTES.events, {
        params: { run_id: runId },
        query: `?after=${cursor}`,
        headers: { "Last-Event-ID": String(cursor) },
        signal,
      });
      if (!response.body) throw new ApiError("NETWORK", null, null, "No stream body");
      handlers.onConnection("live");
      const parser = new SseParser();
      const reader = response.body.getReader();
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        for (const frame of parser.feed(value)) {
          if (frame.event === "trace") {
            handlers.onTrace(JSON.parse(frame.data) as TraceEvent);
            if (frame.id !== null) cursor = Number(frame.id);
          } else if (frame.event === "stopped") {
            handlers.onStopped(JSON.parse(frame.data) as Job);
            handlers.onConnection("stopped");
            return;
          }
        }
      }
    } catch (cause) {
      if (signal.aborted) return;
      // Credentials or the run itself are wrong; retrying cannot help.
      if (cause instanceof ApiError && cause.kind === "HTTP") {
        handlers.onConnection("failed", cause.message);
        return;
      }
    }
    if (signal.aborted) return;
    handlers.onConnection("reconnecting");
    await sleep(retryDelayMs, signal);
  }
}
