import { describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { ApiClient, ApiError, normalizeError, ROUTES } from "../api/client";
import { followRun, SseParser, validateTraceEvent, type StreamHandlers } from "../api/sse";
import type { TraceEvent } from "../api/types";
import { useRoute } from "../state/session";
import { applyEvents, emptyTrace, findByOperation, resultForProposal } from "../state/traceStore";

const bytes = (value: string) => new TextEncoder().encode(value);
const event = (sequence: number, extra: object = {}): TraceEvent => ({
  kind: "AUDIT", event_id: `event:${sequence}`, sequence, event_type: "graph.turn.result",
  operation_id: `op:${sequence}`, attempt_id: `attempt:${sequence}`, turn_id: "turn:1",
  payload_ref: { sha256: "a".repeat(64), byte_length: 1, media_type: "application/json" }, ...extra,
}) as TraceEvent;
const frame = (value: TraceEvent, id = String(value.sequence)) =>
  `id: ${id}\nevent: trace\ndata: ${JSON.stringify(value)}\n\n`;
const stopped = (status = "STOPPED") => `event: stopped\ndata: ${JSON.stringify({
  run_id: "run:1", dossier_id: "dossier:1", status, detail: null, cancel_requested: 0,
})}\n\n`;
function stream(text: string, cancel = vi.fn()) {
  return new Response(new ReadableStream<Uint8Array>({
    start(controller) { controller.enqueue(bytes(text)); controller.close(); }, cancel,
  }), { headers: { "Content-Type": "text/event-stream" } });
}
const handlers = (): StreamHandlers => ({ onTrace: vi.fn(), onStopped: vi.fn(), onConnection: vi.fn() });
const clientFor = (fetcher: unknown) => new ApiClient("http://api", "transport-token", fetcher as typeof fetch);


describe("mutation outcome and authenticated transport", () => {
  it("preserves uncertain POST outcomes on abort, truncated bodies, invalid JSON and server errors", async () => {
    const responses = [
      () => { throw new DOMException("aborted", "AbortError"); },
      () => new Response(new ReadableStream({ start(controller) { controller.error(new Error("lost body")); } }), { status: 201 }),
      () => new Response("invalid json", { status: 201 }),
      () => new Response(JSON.stringify({ code: "PROJECTION_FAILED", message: "Committed; projection failed" }), { status: 503 }),
    ];
    for (const response of responses) {
      const fetcher = vi.fn(response);
      const failure = await clientFor(fetcher).select("case_001").catch(error => error);
      expect(failure).toBeInstanceOf(ApiError);
      expect(failure.kind).toBe("UNKNOWN_OUTCOME");
      expect(fetcher).toHaveBeenCalledTimes(1);
      if (failure.status === 503) {
        expect(failure.code).toBe("PROJECTION_FAILED");
        expect(failure.message).toContain("Committed; projection failed");
      }
    }
  });

  it("distinguishes predispatch cancellation, known validation rejection and malformed reads", async () => {
    const fetcher = vi.fn(async () => new Response("{}"));
    const controller = new AbortController(); controller.abort();
    await expect(clientFor(fetcher).send(ROUTES.select, { signal: controller.signal })).rejects.toMatchObject({ name: "AbortError" });
    expect(fetcher).not.toHaveBeenCalled();
    await expect(clientFor(async () => new Response('{"code":"INVALID_SCHEMA","errors":[]}', { status: 422 })).select("x"))
      .rejects.toMatchObject({ kind: "HTTP", status: 422 });
    await expect(clientFor(async () => new Response("not json")).health()).rejects.toMatchObject({ kind: "PROTOCOL" });
    expect(() => normalizeError(422, { errors: [null, { loc: "bad", msg: "invalid" }] })).not.toThrow();
  });

  it("pins bearer headers, forbids redirect forwarding and encodes read-only reconciliation filters", async () => {
    const fetcher = vi.fn(async () => new Response('{"runs":[]}'));
    const client = clientFor(fetcher);
    await client.send(ROUTES.health, { headers: { authorization: "Bearer override" } });
    const init = fetcher.mock.calls[0] as unknown as [string, RequestInit];
    expect(init[1]).toMatchObject({ redirect: "error", credentials: "omit", cache: "no-store" });
    expect(init[1].headers).toEqual({ Authorization: "Bearer transport-token" });
    await client.runs("dossier:1&other=2");
    expect((fetcher.mock.calls[1] as unknown as [string])[0]).toBe("http://api/api/v1/runs?dossier_id=dossier%3A1%26other%3D2");
  });
});


describe("SSE protocol and lifecycle", () => {
  it("parses mixed line endings, multiline data, comments and split UTF-8 without partial frames", () => {
    const parser = new SseParser();
    const wire = bytes(': heartbeat\r\nevent: trace\rdata: {"name":\ndata: "café"}\r\n\n');
    const result = [...wire].flatMap(byte => parser.feed(new Uint8Array([byte])));
    expect(result).toEqual([{ event: "trace", id: null, data: '{"name":\n"café"}' }]);
    expect(parser.feed(bytes("event: stopped\ndata: {}"))).toEqual([]);
  });

  it("rejects malformed UTF-8 and ignores NUL-containing event ids", () => {
    expect(() => new SseParser().feed(new Uint8Array([255]))).toThrow("UTF-8");
    expect(new SseParser().feed(bytes("id: bad\0id\ndata: {}\n\n"))[0].id).toBeNull();
  });

  it.each([
    'id: NaN\nevent: trace\ndata: {}\n\n',
    frame(event(1), "9007199254740992"), frame(event(1), "2"),
    frame(event(1, { kind: "PLAN", data: {} })),
    'id: 1\nevent: trace\ndata: broken\n\n',
    'event: stopped\ndata: {"status":"RUNNING"}\n\n',
  ])("fails malformed frames without poisoning the cursor or retrying a permanent error", async wire => {
    const response = stream(wire), fetcher = vi.fn(async () => response), callbacks = handlers();
    await followRun(clientFor(fetcher), "run:1", 0, callbacks, new AbortController().signal, 0);
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(callbacks.onTrace).not.toHaveBeenCalled();
    expect(callbacks.onStopped).not.toHaveBeenCalled();
    expect(callbacks.onConnection).toHaveBeenLastCalledWith("failed", expect.any(String));
    expect(response.body?.locked).toBe(false);
  });

  it("replays a truncated frame after disconnect from the last applied sequence", async () => {
    const partial = frame(event(2)).slice(0, -2);
    const responses = [stream(frame(event(1)) + partial), stream(frame(event(2)) + stopped())];
    const fetcher = vi.fn().mockResolvedValueOnce(responses[0]).mockResolvedValueOnce(responses[1]);
    const callbacks = handlers();
    await followRun(clientFor(fetcher), "run:1", 0, callbacks, new AbortController().signal, 0);
    expect((fetcher.mock.calls[1] as [string])[0]).toContain("after=1");
    expect(vi.mocked(callbacks.onTrace).mock.calls.map(([value]) => value.sequence)).toEqual([1, 2]);
    expect(responses.every(response => !response.body?.locked)).toBe(true);
  });

  it("recovers a sequence gap without skipping evidence and cancels before reconnecting", async () => {
    let state = emptyTrace;
    const fetcher = vi.fn().mockResolvedValueOnce(stream(frame(event(1)) + frame(event(3))))
      .mockResolvedValueOnce(stream(frame(event(1)) + frame(event(2)) + frame(event(3)) + stopped()));
    await followRun(clientFor(fetcher), "run:1", 0, { ...handlers(), onTrace(value) { state = applyEvents(state, [value]); } }, new AbortController().signal, 0);
    expect((fetcher.mock.calls[1] as [string])[0]).toContain("after=1");
    expect(state.events.map(value => value.sequence)).toEqual([1, 2, 3]);
    expect(state.cursor).toBe(3);
  });

  it("cancels a blocked reader on abort and releases its lock without reconnecting", async () => {
    const cancel = vi.fn();
    const response = new Response(new ReadableStream<Uint8Array>({ cancel }), { headers: { "Content-Type": "text/event-stream" } });
    const fetcher = vi.fn(async () => response), controller = new AbortController();
    const callbacks = handlers();
    callbacks.onConnection = state => { if (state === "live") queueMicrotask(() => controller.abort()); };
    await followRun(clientFor(fetcher), "run:1", 0, callbacks, controller.signal, 0);
    expect(cancel).toHaveBeenCalledOnce();
    expect(response.body?.locked).toBe(false);
    expect(fetcher).toHaveBeenCalledOnce();
  });

  it("retries transient read failures, but surfaces failed workers and wrong content types", async () => {
    const fetcher = vi.fn().mockResolvedValueOnce(new Response("unavailable", { status: 503 }))
      .mockResolvedValueOnce(stream(stopped("FAILED")));
    const callbacks = handlers();
    await followRun(clientFor(fetcher), "run:1", 0, callbacks, new AbortController().signal, 0);
    expect(fetcher).toHaveBeenCalledTimes(2);
    expect(callbacks.onStopped).toHaveBeenCalledOnce();
    expect(callbacks.onConnection).toHaveBeenLastCalledWith("failed", expect.stringContaining("failed"));
    const wrong = vi.fn(async () => new Response("<html>wrong route</html>", { headers: { "Content-Type": "text/html" } }));
    await followRun(clientFor(wrong), "run:1", 0, handlers(), new AbortController().signal, 0);
    expect(wrong).toHaveBeenCalledOnce();
  });
});


describe("immutable trace identity and causal association", () => {
  it("retains gaps until filled and rejects changed records without modifying state", () => {
    let state = applyEvents(emptyTrace, [event(1), event(3)]);
    expect(state.cursor).toBe(1);
    expect(() => applyEvents(state, [event(1, { event_type: "changed" })])).toThrow("Conflicting");
    expect(state.events).toHaveLength(2);
    expect(() => applyEvents(state, [event(2, { event_id: "event:1" })])).toThrow("Conflicting");
    state = applyEvents(state, [event(2)]);
    expect(state.cursor).toBe(3);
    expect(applyEvents(state, [event(3)])).toBe(state);
  });

  it("links exact referenced operations and refuses cross-turn, null-turn and ambiguous retry guesses", () => {
    const proposal = event(1, { kind: "TOOL_PROPOSED", data: { plan_ref: "plan:1", allowed_operation: "check" } });
    const foreign = event(2, { kind: "TOOL_OR_STAGE_RESULT", event_type: "graph.tool.check.result", turn_id: "turn:other" });
    const actual = event(3, { kind: "TOOL_OR_STAGE_RESULT", event_type: "graph.tool.check.result", operation_id: "op:actual" });
    const assessment = event(4, { kind: "ASSESSMENT", data: { plan_ref: "plan:1", operation_ref: "op:actual" } });
    expect(resultForProposal([proposal, foreign, actual, assessment], proposal)).toBe(actual);
    expect(resultForProposal([proposal, foreign], proposal)).toBeUndefined();
    expect(resultForProposal([proposal, actual], { ...proposal, turn_id: null })).toBeUndefined();
    const retry = event(2, { ...actual, event_id: "event:retry", sequence: 2, attempt_id: "attempt:retry" });
    expect(resultForProposal([proposal, retry, actual, assessment], proposal)).toBeUndefined();
    expect(findByOperation([retry, actual], "op:actual")).toBeUndefined();
    expect(findByOperation([retry, actual], "op:actual", "attempt:retry")).toBe(retry);
  });
});


it("handles malformed route encodings and removes reconnect abort listeners", async () => {
  const oldHash = window.location.hash;
  window.history.replaceState(null, "", "#/runs/%E0%A4%A");
  const hook = renderHook(useRoute);
  try {
    expect(hook.result.current).toEqual([]);
    act(() => {
      window.history.replaceState(null, "", "#/runs/run%3A1");
      window.dispatchEvent(new HashChangeEvent("hashchange"));
    });
    expect(hook.result.current).toEqual(["runs", "run:1"]);
  } finally {
    hook.unmount();
    window.history.replaceState(null, "", oldHash || window.location.pathname);
  }
  const controller = new AbortController();
  const add = vi.spyOn(controller.signal, "addEventListener");
  const remove = vi.spyOn(controller.signal, "removeEventListener");
  const callbacks = handlers();
  callbacks.onConnection = state => { if (state === "reconnecting") queueMicrotask(() => controller.abort()); };
  const fetcher = vi.fn(async () => { throw new TypeError("disconnected"); });
  await followRun(clientFor(fetcher), "run:1", 0, callbacks, controller.signal, 100_000);
  expect(fetcher).toHaveBeenCalledOnce();
  expect(add.mock.calls.filter(([name]) => name === "abort")).toHaveLength(1);
  expect(remove.mock.calls.filter(([name]) => name === "abort")).toHaveLength(1);
});


it("links real C09 generic tool events through the assessment operation reference", () => {
  const proposal = event(1, { kind: "TOOL_PROPOSED", event_type: "graph.action.result", data: {
    action_kind: "CHECK", allowed_operation: "search_rules", typed_arguments: { query: "producer" },
    finding_id: "finding:1", concise_reason: "Inspect the applicable rule", evidence_refs: [], plan_ref: "plan:1",
  } });
  const result = event(3, { kind: "TOOL_OR_STAGE_RESULT", event_type: "graph.tool.tool.result",
    operation_id: "operation:consumed", status: "PARTIAL", issues: [], data: {
      disposition: "QUALIFIED", service_operation_ids: [], retrieval_attempt_ids: ["retrieval:1"],
      calculation_ids: [], finding_revision_ids: [], evidence_refs: [], output_blob: null,
      concise_decision: "Applicability remains unresolved",
    },
  });
  const assessment = event(5, { kind: "ASSESSMENT", event_type: "graph.assessment.result", data: {
    assessment_id: "assessment:1", operation_ref: "operation:consumed", plan_ref: "plan:1",
    observation_refs: [], verdict: "UNKNOWN", weak_result_or_mistake: null,
    next_check_or_stop: "Request qualified review", revised_plan_ref: null, disposition: "ABSTAIN",
  } });
  const unrelated = event(2, { ...result, sequence: 2, event_id: "event:unrelated", operation_id: "operation:other" });
  const foreign = event(4, { ...result, sequence: 4, event_id: "event:foreign", turn_id: "turn:other" });
  for (const value of [proposal, result, assessment, unrelated, foreign]) validateTraceEvent(value);
  expect(resultForProposal([proposal, unrelated, result, foreign, assessment], proposal)).toBe(result);
  expect(resultForProposal([proposal, result], proposal)).toBe(result); // live, unique same-turn action/result
  expect(resultForProposal([proposal, foreign, assessment], proposal)).toBeUndefined();
  expect(resultForProposal([proposal, unrelated, assessment], proposal)).toBeUndefined();
  const wrongPlan = { ...assessment, data: { ...(assessment.kind === "ASSESSMENT" ? assessment.data : {}), plan_ref: "plan:other" } } as TraceEvent;
  expect(resultForProposal([proposal, result, wrongPlan], proposal)).toBeUndefined();
  expect(resultForProposal([proposal, unrelated, result], proposal)).toBeUndefined();
});
