import { act, cleanup, fireEvent, render, renderHook, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiClient, ApiError } from "../api/client";
import type { AgentConfig, RunView, TraceEvent } from "../api/types";
import { preparedContext } from "../components/PromptInspector";
import { useAction, useLoad } from "../components/common";
import { Connect } from "../screens/Connect";
import { Dossiers } from "../screens/Dossiers";
import { Investigation } from "../screens/Investigation";
import { StartRun } from "../screens/StartRun";
import { SessionContext } from "../state/session";

const streaming = vi.hoisted(() => vi.fn());
vi.mock("../api/sse", async (original) => ({
  ...await original<typeof import("../api/sse")>(), followRun: streaming,
}));

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (cause: unknown) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

const agent: AgentConfig = { configured: true, model_id: "local", prompt_pin: null,
  system_template: "current template", phase_rules: {}, response_schemas: {}, note: "" };
function runView(id = "run:one", status = "INVESTIGATING"): RunView {
  return {
    state: { run_id: id, version: 1, status, current_turn: 1,
      pending_finding_ids: [], resolved_finding_ids: [], abstained_finding_ids: [],
      review_outcome: "NOT_REQUESTED", stop_reason: null, created_at: "", updated_at: "",
      budget: { actions: 0, model_calls: 0, tool_calls: 0, retries: 0, reserved_tokens: 0,
        observed_tokens: null, observed_cost_usd: null, usage_known_calls: 0, cost_known_calls: 0,
        preflight_actions: 0, verification_actions: 0, report_repairs: 0,
        finding_actions: {}, finding_reformulations: {} } },
    job: { run_id: id, dossier_id: "dossier:one", status: "RUNNING", detail: null, cancel_requested: 0 },
    configuration: { execution_kind: "MODEL_BACKED", budgets: { max_model_calls: 999 },
      model_configuration_id: "configuration:model", prompt_configuration_id: "configuration:prompt",
      case_snapshot: { snapshot_id: "snapshot:case", membership_digest: "a".repeat(64) },
      corpus_snapshot: { snapshot_id: "snapshot:corpus", membership_digest: "b".repeat(64) },
      profile: { profile_id: "profile:one", profile_version: "one", digest: "c".repeat(64) },
      index: { configuration_id: "index:one", digest: "d".repeat(64) } },
  } as RunView;
}
const session = (client: ApiClient, node: React.ReactNode) =>
  <SessionContext.Provider value={{ client, disconnect() {} }}>{node}</SessionContext.Provider>;

function clientFixture() {
  const client = new ApiClient("http://api", "token");
  vi.spyOn(client, "agent").mockResolvedValue(agent);
  vi.spyOn(client, "dossier").mockResolvedValue({ dossier_id: "dossier:one", name: "Current dossier", status: "APPROVED" });
  vi.spyOn(client, "runs").mockResolvedValue({ runs: [] });
  vi.spyOn(client, "trace").mockImplementation(async (id) => ({ run_id: id, events: [], last_sequence: 0 }));
  return client;
}

beforeEach(() => {
  streaming.mockImplementation((_client, _run, _after, _callbacks, signal: AbortSignal) =>
    new Promise<void>((resolve) => signal.addEventListener("abort", () => resolve(), { once: true })));
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); streaming.mockReset(); });

describe("load lifecycle", () => {
  it("does not show old-resource data or accept a late old response", async () => {
    const old = deferred<string>();
    const fresh = deferred<string>();
    const { result, rerender } = renderHook(({ id }) => useLoad(
      () => id === "old" ? old.promise : fresh.promise, [id]), { initialProps: { id: "old" } });
    rerender({ id: "new" });
    await act(async () => fresh.resolve("new evidence"));
    expect(result.current.data).toBe("new evidence");
    await act(async () => old.resolve("stale secret"));
    expect(result.current.data).toBe("new evidence");
    rerender({ id: "other" });
    expect(result.current.data).toBeUndefined();
  });

  it("does not issue requests through a captured reload after unmount", async () => {
    const load = vi.fn().mockResolvedValue("value");
    const { result, unmount } = renderHook(() => useLoad(load, [load]));
    await waitFor(() => expect(result.current.data).toBe("value"));
    const reload = result.current.reload;
    unmount();
    await reload();
    expect(load).toHaveBeenCalledTimes(1);
  });
});

it("admits one mutation even when called twice before React rerenders", async () => {
  const pending = deferred<string>();
  const action = vi.fn((_signal: AbortSignal) => pending.promise);
  const { result, unmount } = renderHook(useAction);
  act(() => { void result.current.run(action); void result.current.run(action); });
  expect(action).toHaveBeenCalledTimes(1);
  const signal = action.mock.calls[0][0] as AbortSignal;
  unmount();
  expect(signal.aborted).toBe(true);
  await act(async () => pending.resolve("complete"));
});

it("clears the API token on submit and rejects a late connection after unmount", async () => {
  const health = deferred<Response>();
  vi.stubGlobal("fetch", vi.fn(() => health.promise));
  const connected = vi.fn();
  const { unmount } = render(<Connect onConnected={connected} />);
  const token = screen.getByLabelText("API token") as HTMLInputElement;
  fireEvent.change(token, { target: { value: "temporary-private-token" } });
  fireEvent.click(screen.getByRole("button", { name: "Connect" }));
  expect(token.value).toBe("");
  unmount();
  await act(async () => health.resolve(new Response(JSON.stringify({ status: "OK", model_configured: true, model_probed: false, concurrency: 1, available_modes: ["MODEL_BACKED"] }), { headers: { "Content-Type": "application/json" } })));
  expect(connected).not.toHaveBeenCalled();
});

it("does not navigate to a dossier when selection completes after leaving the screen", async () => {
  const client = clientFixture();
  vi.spyOn(client, "catalogue").mockResolvedValue({ dossiers: [], fixtures: [
    { fixture_id: "case_one", case_id: "case:one", fiscal_year: "2024-25", synthetic: true },
  ] });
  const pending = deferred<Awaited<ReturnType<ApiClient["select"]>>>();
  vi.spyOn(client, "select").mockReturnValue(pending.promise);
  window.location.hash = "#/dossiers";
  const { unmount } = render(session(client, <Dossiers />));
  fireEvent.click(await screen.findByRole("button", { name: /case_one/ }));
  unmount();
  await act(async () => pending.resolve({ dossier_id: "dossier:obsolete", name: "Old", status: "UPLOADED" }));
  expect(window.location.hash).toBe("#/dossiers");
});

it("refreshes workflow state while SSE is live and uses server ceilings on reopening", async () => {
  const client = clientFixture();
  vi.spyOn(client, "run").mockResolvedValueOnce(runView()).mockResolvedValue(runView("run:one", "DRAFTING"));
  const { unmount } = render(session(client, <Investigation runId="run:one" />));
  expect(await screen.findByText("INVESTIGATING")).toBeTruthy();
  expect(screen.getByText("999")).toBeTruthy();
  await waitFor(() => expect(screen.getByText("DRAFTING")).toBeTruthy(), { timeout: 2500 });
  expect(streaming).toHaveBeenCalledTimes(1);
  unmount();
});

it("ignores callbacks from an abandoned run stream", async () => {
  const client = clientFixture();
  vi.spyOn(client, "run").mockImplementation(async (id) => runView(id));
  const { rerender } = render(session(client, <Investigation runId="run:old" />));
  await waitFor(() => expect(streaming).toHaveBeenCalledTimes(1));
  const oldCallbacks = streaming.mock.calls[0][3];
  rerender(session(client, <Investigation runId="run:new" />));
  await waitFor(() => expect(streaming).toHaveBeenCalledTimes(2));
  const stale = { sequence: 1, event_id: "event:obsolete", kind: "AUDIT", event_type: "obsolete-private-event" } as TraceEvent;
  act(() => { oldCallbacks.onTrace(stale); oldCallbacks.onConnection("failed", "obsolete error"); });
  expect(screen.queryByText(/obsolete/)).toBeNull();
});

it("associates prepared context by recorded turn and model phase only", () => {
  const base = { operation_id: "operation:one", turn_id: "turn:one", attempt_id: "attempt:one",
    payload_ref: { sha256: "a".repeat(64), byte_length: 1, media_type: "application/json" } };
  const prepared = { ...base, sequence: 1, event_id: "event:plan", kind: "PROMPT_PREPARED", phase: "PLAN",
    request: {}, system_template: "plan context", note: "", event_type: "graph.context.result" } as TraceEvent;
  const assess = { ...prepared, sequence: 2, event_id: "event:assess", phase: "ASSESS" } as TraceEvent;
  const model = { ...base, sequence: 3, event_id: "event:model", kind: "MODEL_RESULT",
    event_type: "graph.model.plan.result", status: "SUCCESS", issues: [] } as Extract<TraceEvent, { kind: "MODEL_RESULT" }>;
  expect(preparedContext([prepared, assess], model)?.event_id).toBe("event:plan");
  expect(preparedContext([prepared], { ...model, turn_id: null })).toBeUndefined();
  expect(preparedContext([prepared, { ...prepared, event_id: "event:ambiguous", sequence: 2 }], model)).toBeUndefined();
});


it("keeps an unknown start locked while exposing read-only run recovery", async () => {
  const client = clientFixture();
  vi.spyOn(client, "health").mockResolvedValue({ status: "OK", model_configured: true, model_probed: false, concurrency: 1, available_modes: ["MODEL_BACKED"] });
  vi.mocked(client.runs).mockResolvedValueOnce({ runs: [] }).mockResolvedValue({ runs: [runView()] });
  const start = vi.spyOn(client, "startRun").mockRejectedValue(new ApiError("UNKNOWN_OUTCOME", null, null, "Start acknowledgement lost"));
  render(session(client, <StartRun dossierId="dossier:one" />));
  const button = await screen.findByRole("button", { name: "Start investigation" });
  await waitFor(() => expect((button as HTMLButtonElement).disabled).toBe(false));
  fireEvent.click(button);
  expect(await screen.findByText(/Starting is locked/)).toBeTruthy();
  expect(await screen.findByRole("link", { name: "run:one" })).toBeTruthy();
  expect((screen.getByRole("button", { name: "Start investigation" }) as HTMLButtonElement).disabled).toBe(true);
  expect(screen.queryByRole("button", { name: /unlock/i })).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Refresh runs" }));
  await waitFor(() => expect(client.runs).toHaveBeenCalledTimes(3));
  expect(start).toHaveBeenCalledTimes(1);
});

it("rejects fractional budget input instead of truncating it", async () => {
  const client = clientFixture();
  vi.spyOn(client, "health").mockResolvedValue({ status: "OK", model_configured: true, model_probed: false, concurrency: 1, available_modes: ["MODEL_BACKED"] });
  const start = vi.spyOn(client, "startRun");
  render(session(client, <StartRun dossierId="dossier:one" />));
  const button = await screen.findByRole("button", { name: "Start investigation" });
  await waitFor(() => expect((button as HTMLButtonElement).disabled).toBe(false));
  fireEvent.change(screen.getByLabelText("Model calls"), { target: { value: "2.5" } });
  fireEvent.click(button);
  expect(await screen.findByText(/must be a positive whole number/)).toBeTruthy();
  expect(start).not.toHaveBeenCalled();
});


it("does not subscribe past a missing snapshot sequence", async () => {
  const client = clientFixture();
  vi.spyOn(client, "run").mockResolvedValue(runView());
  vi.mocked(client.trace).mockResolvedValue({ run_id: "run:one", last_sequence: 2, events: [{
    sequence: 2, event_id: "event:gap", operation_id: "operation:one", turn_id: "turn:one",
    attempt_id: "attempt:one", event_type: "graph.state.result", kind: "AUDIT",
    payload_ref: { sha256: "a".repeat(64), byte_length: 1, media_type: "application/json" },
  }] });
  render(session(client, <Investigation runId="run:one" />));
  expect(await screen.findByText(/Trace snapshot identity or sequence coverage is invalid/)).toBeTruthy();
  expect(streaming).not.toHaveBeenCalled();
});


it("offers only server-enabled execution modes before dispatch", async () => {
  const client = clientFixture();
  vi.spyOn(client, "health").mockResolvedValue({ status: "OK", model_configured: true,
    model_probed: false, concurrency: 1, available_modes: ["SCRIPTED_TEST"] });
  const start = vi.spyOn(client, "startRun").mockResolvedValue({ run_id: "run:script", status: "QUEUED", mode: "SCRIPTED_TEST" });
  render(session(client, <StartRun dossierId="dossier:one" />));
  const script = await screen.findByLabelText(/Scripted test: replayed proposals/);
  await waitFor(() => expect((script as HTMLInputElement).checked).toBe(true));
  expect((screen.getByLabelText(/Model-backed: the local model/) as HTMLInputElement).disabled).toBe(true);
  const button = screen.getByRole("button", { name: "Start investigation" });
  await waitFor(() => expect((button as HTMLButtonElement).disabled).toBe(false));
  fireEvent.click(button);
  await waitFor(() => expect(start).toHaveBeenCalledWith("dossier:one", "SCRIPTED_TEST", undefined));
});
