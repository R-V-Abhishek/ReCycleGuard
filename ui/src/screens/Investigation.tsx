import { useCallback, useEffect, useReducer, useState } from "react";
import { ApiError } from "../api/client";
import { followRun, type StreamConnection } from "../api/sse";
import type { BudgetLimits, BudgetUsage, TraceEvent } from "../api/types";
import { Badge, ErrorBanner, Mono, Section, Unavailable, useAction, useLoad } from "../components/common";
import { useHeader } from "../components/Shell";
import { EventDetail, Timeline } from "../components/Timeline";
import { href, useClient } from "../state/session";
import { applyEvents, emptyTrace, type TraceState } from "../state/traceStore";

const TERMINAL = new Set(["COMPLETED", "FAILED", "CANCELLED", "BLOCKED_INPUT", "BLOCKED_OUTPUT"]);
const PAUSED = new Set([...TERMINAL, "AWAITING_REVIEW"]);

type TraceAction = { type: "merge"; events: TraceEvent[] } | { type: "reset" };
const traceReducer = (state: TraceState, action: TraceAction) =>
  action.type === "reset" ? emptyTrace : applyEvents(state, action.events);

function Budget({ usage, limits }: { usage: BudgetUsage; limits?: BudgetLimits }) {
  const row = (label: string, used: number | string | null, limit?: number) => (
    <tr key={label}>
      <td>{label}</td>
      <td>{used ?? <Unavailable />}</td>
      <td>{limit ?? <Unavailable label="not exposed" />}</td>
    </tr>
  );
  return (
    <table className="compact">
      <thead><tr><th>Budget</th><th>Used</th><th>Ceiling</th></tr></thead>
      <tbody>
        {row("Model calls", usage.model_calls, limits?.max_model_calls)}
        {row("Tool calls", usage.tool_calls)}
        {row("Case actions", usage.actions, limits?.max_case_actions)}
        {row("Retries", usage.retries)}
        {row("Retry allowance per operation", null, limits?.retries_per_operation)}
        {row("Report repairs", usage.report_repairs, limits?.report_repairs)}
        {Object.entries(usage.finding_actions).map(([id, used]) => row(`Tool actions: ${id}`, used, limits?.tools_per_finding))}
        {Object.entries(usage.finding_reformulations).map(([id, used]) => row(`Reformulations: ${id}`, used, limits?.reformulations_per_finding))}
        {row("Wall-clock seconds", null, limits?.max_wall_seconds)}
        {row("Token allowance per call", null, limits?.tokens_per_model_call)}
        {row("Tokens reserved", usage.reserved_tokens, limits?.max_total_tokens)}
        {row("Tokens measured", usage.observed_tokens)}
        {row("Cost measured (USD)", usage.observed_cost_usd)}
      </tbody>
    </table>
  );
}

export function Investigation({ runId }: { runId: string }) {
  return <InvestigationRun key={runId} runId={runId} />;
}

function InvestigationRun({ runId }: { runId: string }) {
  const client = useClient();
  const run = useLoad(() => client.run(runId), [client, runId]);
  const agent = useLoad(() => client.agent(), [client]);
  const dossierId = run.data?.job.dossier_id;
  const dossier = useLoad(async () => (dossierId ? client.dossier(dossierId) : undefined), [client, dossierId]);
  const [trace, dispatch] = useReducer(traceReducer, emptyTrace);
  const [traceError, setTraceError] = useState<unknown>();
  const [connection, setConnection] = useState<StreamConnection>("connecting");
  const [connectionDetail, setConnectionDetail] = useState<string>();
  const [selectedId, setSelectedId] = useState<string>();
  const [showAudit, setShowAudit] = useState(false);
  const [generation, setGeneration] = useState(0);
  const action = useAction();
  const reloadRun = run.reload;
  const mode = run.data?.configuration.execution_kind;
  const { setHeader } = useHeader();

  useEffect(() => {
    setHeader({ dossierId, dossierName: dossier.data?.name, runId, mode, connection });
  }, [dossierId, dossier.data?.name, runId, mode, connection, setHeader]);

  // Snapshot first, then subscribe after the last sequence. The server replays anything newer.
  useEffect(() => {
    const controller = new AbortController();
    dispatch({ type: "reset" });
    setSelectedId(undefined);
    setTraceError(undefined);
    setConnection("connecting");
    setConnectionDetail(undefined);
    (async () => {
      try {
        const page = await client.trace(runId, 0);
        if (controller.signal.aborted) return;
        let projection = applyEvents(emptyTrace, page.events);
        if (page.run_id !== runId || projection.cursor !== page.last_sequence) {
          throw new ApiError("PROTOCOL", null, null, "Trace snapshot identity or sequence coverage is invalid; live updates were not started.");
        }
        dispatch({ type: "merge", events: page.events });
        setTraceError(undefined);
        await followRun(
          client,
          runId,
          projection.cursor,
          {
            onTrace: (event) => {
              if (!controller.signal.aborted) {
                projection = applyEvents(projection, [event]);
                dispatch({ type: "merge", events: [event] });
              }
            },
            onStopped: () => {
              if (!controller.signal.aborted) void reloadRun();
            },
            onConnection: (state, detail) => {
              if (!controller.signal.aborted) {
                setConnection(state);
                setConnectionDetail(detail);
              }
            },
          },
          controller.signal,
        );
      } catch (cause) {
        if (!controller.signal.aborted) {
          setTraceError(cause);
          setConnection("failed");
        }
      }
    })();
    return () => controller.abort();
  }, [client, runId, generation, reloadRun]);

  // SSE is the trace transport; workflow state/budgets come from authoritative
  // server snapshots while the worker is active, even before a stopped frame.
  const workerStatus = run.data?.job.status;
  useEffect(() => {
    if (workerStatus !== "RUNNING" && workerStatus !== "QUEUED") return;
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      await reloadRun();
      if (active) timer = setTimeout(() => { void poll(); }, 1000);
    };
    timer = setTimeout(() => { void poll(); }, 1000);
    return () => { active = false; clearTimeout(timer); };
  }, [client, runId, workerStatus, reloadRun]);

  const select = useCallback((id: string) => setSelectedId(id), []);
  const selected = trace.events.find((event) => event.event_id === selectedId);
  const state = run.data?.state;
  const job = run.data?.job;
  const cancelRequested = Boolean(job?.cancel_requested);

  const cancel = () =>
    void action.run(async (signal) => {
      try {
        await client.cancel(runId);
      } finally {
        if (!signal.aborted) await reloadRun();
      }
    });
  const resume = () =>
    void action.run(async (signal) => {
      try {
        await client.resume(runId);
      } finally {
        if (!signal.aborted) await reloadRun();
      }
      if (!signal.aborted) setGeneration((value) => value + 1);
    });

  return (
    <>
      <ErrorBanner error={run.error} />
      <ErrorBanner error={traceError} />
      <ErrorBanner error={action.error} />
      {connection === "failed" && <div className="banner error">
        Live updates stopped: {connectionDetail ?? "stream unavailable"}
        <button onClick={() => setGeneration((value) => value + 1)}>Reconnect stream</button>
      </div>}
      {state && job && (
        <section className="card run-bar">
          <div className="run-badges">
            <span className="muted small">Workflow</span> <Badge value={state.status} />
            <span className="muted small">Worker</span> <Badge value={job.status} />
            <span className="muted small">Review</span> <Badge value={state.review_outcome} />
            {state.stop_reason && (<><span className="muted small">Stop reason</span> <Badge value={state.stop_reason} /></>)}
          </div>
          <div className="row">
            {cancelRequested && !TERMINAL.has(state.status) && <span className="muted small">Cancellation requested. It takes effect between turns.</span>}
            {!TERMINAL.has(state.status) && !cancelRequested && (
              <button disabled={action.busy || Boolean(run.error)} onClick={cancel}>Request cancellation</button>
            )}
            {job.status === "INTERRUPTED" && !PAUSED.has(state.status) && (
              <button disabled={action.busy || Boolean(run.error)} onClick={resume}>Resume run</button>
            )}
            <a className="button" href={href("runs", runId, "report")}>Report and review</a>
          </div>
          {job.status === "FAILED" && job.detail && <div className="banner error prewrap">Worker failure: {job.detail}</div>}
        </section>
      )}

      <div className="workspace">
        <div>
          <Section
            title="Timeline"
            aside={
              <label className="check small">
                <input type="checkbox" checked={showAudit} onChange={(e) => setShowAudit(e.target.checked)} /> Show audit events
              </label>
            }
          >
            <Timeline events={trace.events} selectedId={selectedId} onSelect={select} showAudit={showAudit} />
          </Section>
        </div>
        <div className="detail-col">
          <Section title="Details">
            {selected ? (
              <>
                <p className="small muted">Pinned to sequence {selected.sequence}, <Mono>{selected.event_id}</Mono></p>
                <EventDetail key={selected.event_id} event={selected} events={trace.events} dossierId={dossierId} agent={agent.data} onSelect={select} />
              </>
            ) : (
              <p className="muted">Select a timeline entry to inspect it.</p>
            )}
          </Section>
          {state && (
            <Section title="Bounded autonomy">
              <Budget usage={state.budget} limits={run.data?.configuration.budgets} />
              <h4>Findings</h4>
              <p className="small">
                {state.pending_finding_ids.length} pending · {state.resolved_finding_ids.length} resolved · {state.abstained_finding_ids.length} abstained
              </p>
            </Section>
          )}
        </div>
      </div>
    </>
  );
}
