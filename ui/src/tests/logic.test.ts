import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it, vi } from "vitest";
import { API_PREFIX, ApiClient, ApiError, normalizeError, ROUTES } from "../api/client";
import { followRun, SseParser } from "../api/sse";
import type { ModelResultEvent, TraceEvent } from "../api/types";
import { preparedFor, sentPrompt } from "../state/promptLayers";
import { applyEvents, emptyTrace, resultForProposal } from "../state/traceStore";

// Hand-written from api/trace.py. These prove the UI's logic, not agreement with a real server.
const base = (sequence: number, extra: object = {}) => ({
  sequence,
  event_id: `event:${sequence}`,
  operation_id: `operation:${sequence}`,
  turn_id: "turn:1",
  attempt_id: null,
  event_type: "graph.turn.started",
  payload_ref: { sha256: "a".repeat(64), byte_length: 1, media_type: "application/json" },
  kind: "AUDIT",
  ...extra,
}) as TraceEvent;

const model = (extra: object) =>
  base(5, { kind: "MODEL_RESULT", event_type: "graph.model.plan.result", status: "SUCCESS", issues: [], ...extra }) as ModelResultEvent;

const bytes = (text: string) => new TextEncoder().encode(text);

describe("SseParser", () => {
  it("handles chunks split inside lines, JSON and UTF-8 characters", () => {
    const whole = bytes('id: 7\nevent: trace\ndata: {"title":"café"}\n\n');
    const parser = new SseParser();
    const frames = [...whole].flatMap((byte) => parser.feed(new Uint8Array([byte])));
    expect(frames).toEqual([{ event: "trace", id: "7", data: '{"title":"café"}' }]);
  });

  it("ignores heartbeat comments and handles stopped frames without an id", () => {
    const parser = new SseParser();
    const frames = parser.feed(bytes(': heartbeat\n\nevent: stopped\ndata: {"status":"STOPPED"}\n\n'));
    expect(frames).toEqual([{ event: "stopped", id: null, data: '{"status":"STOPPED"}' }]);
  });

  it("holds an incomplete frame until its blank line arrives", () => {
    const parser = new SseParser();
    expect(parser.feed(bytes("event: trace\ndata: {}\n"))).toEqual([]);
    expect(parser.feed(bytes("\n"))).toHaveLength(1);
  });

  it("parses CRLF frames", () => {
    expect(new SseParser().feed(bytes("event: trace\r\ndata: {}\r\n\r\n"))).toHaveLength(1);
  });
});

describe("trace store", () => {
  it("ignores replays and keeps sequence order", () => {
    let state = applyEvents(emptyTrace, [base(2), base(1)]);
    state = applyEvents(state, [base(2), base(3)]);
    expect(state.events.map((e) => e.sequence)).toEqual([1, 2, 3]);
    expect(state.cursor).toBe(3);
  });

  it("returns the same state when nothing is new", () => {
    const state = applyEvents(emptyTrace, [base(1)]);
    expect(applyEvents(state, [base(1)])).toBe(state);
  });

  it("links a proposal to its tool result but not across a later proposal", () => {
    const proposal = base(1, { kind: "TOOL_PROPOSED" });
    const stage = base(2, { kind: "TOOL_OR_STAGE_RESULT", event_type: "graph.stage.draft.result" });
    const tool = base(3, { kind: "TOOL_OR_STAGE_RESULT", event_type: "graph.tool.search.result" });
    expect(resultForProposal([proposal, stage, tool], proposal)).toBe(tool);
    const next = base(2, { kind: "TOOL_PROPOSED" });
    expect(resultForProposal([proposal, next, tool], proposal)).toBeUndefined();
  });
});

describe("followRun", () => {
  const stream = (...chunks: string[]) =>
    new Response(
      new ReadableStream({
        start(controller) {
          chunks.forEach((chunk) => controller.enqueue(bytes(chunk)));
          controller.close();
        },
      }),
      { status: 200 },
    );
  const noop = { onStopped() {}, onConnection() {} };
  const traceFrame = (n: number) => `id: ${n}\nevent: trace\ndata: ${JSON.stringify(base(n))}\n\n`;
  const stopped = 'event: stopped\ndata: {"status":"STOPPED"}\n\n';

  it("sends the bearer in a header, never in the URL", async () => {
    const fetchImpl = vi.fn(async () => stream(stopped));
    const client = new ApiClient("http://api", "secret-token", fetchImpl as unknown as typeof fetch);
    await followRun(client, "run:1", 4, { onTrace() {}, ...noop }, new AbortController().signal);
    const [url, init] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("http://api/api/v1/runs/run%3A1/events?after=4");
    expect(url).not.toContain("secret-token");
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer secret-token");
    expect((init.headers as Record<string, string>)["Last-Event-ID"]).toBe("4");
  });

  it("does not advance the cursor past a frame that failed to apply", async () => {
    const fetchImpl = vi
      .fn()
      .mockResolvedValueOnce(stream(traceFrame(5), traceFrame(6)))
      .mockResolvedValueOnce(stream(stopped));
    const client = new ApiClient("http://api", "t", fetchImpl as unknown as typeof fetch);
    const onTrace = vi.fn((event: TraceEvent) => {
      if (event.sequence === 6 && onTrace.mock.calls.length === 2) throw new Error("apply failed");
    });
    await followRun(client, "run:1", 4, { onTrace, ...noop }, new AbortController().signal, 0);
    const second = fetchImpl.mock.calls[1] as unknown as [string, RequestInit];
    expect(second[0]).toContain("after=5");
    expect((second[1].headers as Record<string, string>)["Last-Event-ID"]).toBe("5");
  });

  it("stops retrying on an HTTP error", async () => {
    const fetchImpl = vi.fn(async () => new Response(JSON.stringify({ detail: "no" }), { status: 401 }));
    const client = new ApiClient("http://api", "t", fetchImpl as unknown as typeof fetch);
    const states: string[] = [];
    await followRun(client, "run:1", 0, { onTrace() {}, onStopped() {}, onConnection: (s) => states.push(s) }, new AbortController().signal, 0);
    expect(fetchImpl).toHaveBeenCalledTimes(1);
    expect(states.at(-1)).toBe("failed");
  });
});

describe("prompt layers", () => {
  it("reports a missing provider trace", () => {
    expect(sentPrompt(model({})).state).toBe("NO_TRACE");
  });

  it("reports a null body as not dispatched", () => {
    expect(sentPrompt(model({ provider_trace: { request_body_utf8: null } })).state).toBe("NOT_DISPATCHED");
  });

  it("parses the wire body and keeps the raw text untouched", () => {
    const raw = '{"prompt":"<|im_start|>system\\nx","max_tokens":10}';
    const sent = sentPrompt(model({ provider_trace: { request_body_utf8: raw } }));
    expect(sent).toMatchObject({ state: "SENT", raw, prompt: "<|im_start|>system\nx", parameters: { max_tokens: 10 } });
  });

  it("keeps an unparseable body rather than inventing a prompt", () => {
    expect(sentPrompt(model({ provider_trace: { request_body_utf8: "not json" } }))).toMatchObject({ state: "UNPARSEABLE", raw: "not json" });
  });

  it("matches prepared context from the same turn only", () => {
    const other = base(1, { kind: "PROMPT_PREPARED", turn_id: "turn:0" });
    const mine = base(2, { kind: "PROMPT_PREPARED" });
    const later = base(9, { kind: "PROMPT_PREPARED" });
    expect(preparedFor([other, mine, later], model({}))).toBe(mine);
    expect(preparedFor([other], model({}))).toBeUndefined();
  });
});

describe("normalizeError", () => {
  it.each([
    [{ detail: "ZIP exceeds" }, null, "ZIP exceeds"],
    [{ detail: { code: "BUSY", message: "Another operation" } }, "BUSY", "Another operation"],
    [{ code: "PRECONDITION_FAILED", message: "prepare first" }, "PRECONDITION_FAILED", "prepare first"],
    [{ code: "INVALID_SCHEMA", errors: [{ loc: ["body", "reason"], msg: "required", type: "x" }] }, "INVALID_SCHEMA", "body.reason: required"],
    ["plain", null, "plain"],
    ["", null, "HTTP 500"],
  ])("normalizes %j", (body, code, message) => {
    const error = normalizeError(500, body);
    expect(error.code).toBe(code);
    expect(error.message).toBe(message);
  });
});

describe("mutations", () => {
  it("reports a lost POST response as an unknown outcome, once", async () => {
    const fetchImpl = vi.fn(async () => {
      throw new TypeError("network");
    });
    const client = new ApiClient("http://api", "t", fetchImpl as unknown as typeof fetch);
    const failure = await client.startRun("dossier:1", "MODEL_BACKED").catch((e: unknown) => e);
    expect(failure).toBeInstanceOf(ApiError);
    expect((failure as ApiError).kind).toBe("UNKNOWN_OUTCOME");
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });

  it("uploads raw ZIP bytes, not multipart", async () => {
    const fetchImpl = vi.fn(async () => new Response("{}", { status: 201 }));
    const client = new ApiClient("http://api", "t", fetchImpl as unknown as typeof fetch);
    const zip = new Blob(["PK"]);
    await client.upload(zip);
    const init = (fetchImpl.mock.calls[0] as unknown as [string, RequestInit])[1];
    expect(init.body).toBe(zip);
    expect((init.headers as Record<string, string>)["Content-Type"]).toBe("application/zip");
  });
});

describe("route coverage", () => {
  it("binds exactly the operations in docs/api/openapi.json", () => {
    const spec = JSON.parse(readFileSync(resolve(__dirname, "../../../docs/api/openapi.json"), "utf-8")) as {
      paths: Record<string, Record<string, unknown>>;
    };
    const documented = Object.entries(spec.paths)
      .flatMap(([path, methods]) => Object.keys(methods).map((m) => `${m.toUpperCase()} ${path}`))
      .sort();
    const bound = Object.values(ROUTES)
      .map(([method, path]) => `${method} ${API_PREFIX}${path}`)
      .sort();
    expect(bound).toEqual(documented);
  });
});
