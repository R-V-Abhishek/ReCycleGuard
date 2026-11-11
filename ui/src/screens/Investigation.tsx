import { useCallback, useEffect, useReducer, useState } from "react";
import { ApiError } from "../api/client";
import { followRun, type StreamConnection } from "../api/sse";
import type { BudgetLimits, BudgetUsage, RunState, TraceEvent } from "../api/types";
import { Badge, ErrorBanner, Mono, Section, Unavailable, useAction, useLoad } from "../components/common";
import { useHeader } from "../components/Shell";
import { EventDetail, isRefusal, Timeline } from "../components/Timeline";
import { href, useClient } from "../state/session";
import { applyEvents, emptyTrace, type TraceState } from "../state/traceStore";

const TERMINAL = new Set(["COMPLETED", "FAILED", "CANCELLED", "BLOCKED_INPUT", "BLOCKED_OUTPUT"]);
const PAUSED = new Set([...TERMINAL, "AWAITING_REVIEW"]);

const LONG_RUN_SECONDS = 60;

// Says what a stopped run means. It reports the recorded status and adds no compliance conclusion.
export function stoppedRunNotice(status: string, stopReason: string | null): string | null {
  if (status === "FAILED") {
    return stopReason === "AUDIT_FAILURE"
      ? "The audit record could not be verified, so this run stopped. Its output must not be relied on."
      : "A model or tool call failed, or its result could not be accepted. Every attempt is kept in the timeline. A call with an uncertain outcome is not repeated automatically, so start a new run if you need another attempt.";
  }
  if (status === "BLOCKED_INPUT") {
    return "The dossier could not be investigated, for example because declared pages are missing. No model call was made. Correct the dossier and start a new run.";
  }
  if (status === "BLOCKED_OUTPUT") {
    return "The model proposed an action the workflow refused, so nothing ran for it. The refused proposal is kept in the timeline.";
  }
  if (stopReason === "BUDGET_EXHAUSTED") {
    return "A budget ceiling stopped this run, so its checks may be incomplete. Any report is qualified accordingly.";
  }
  return null;
}

export function elapsedSeconds(from: string, now: number): number | null {
  const started = Date.parse(from);
  return Number.isNaN(started) ? null : Math.max(0, Math.floor((now - started) / 1000));
}

function RunProgress({ createdAt, updatedAt }: { createdAt: string; updatedAt: string }) {
  const now = Date.now();
  const elapsed = elapsedSeconds(createdAt, now);
  const idle = elapsedSeconds(updatedAt, now);
  if (elapsed === null) return null;
  return (
    <span className="muted small">
      Running for {elapsed} s{idle === null ? "" : `; last recorded step ${idle} s ago`}.
      {elapsed >= LONG_RUN_SECONDS && " A local model call can take minutes. Budget ceilings stop the run if it runs too long."}
    </span>
  );
}

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

// Counts come from the recorded trace and state only; nothing is inferred about quality.
export function Ledger({ events, state }: { events: TraceEvent[]; state?: RunState }) {
  const count = (test: (event: TraceEvent) => boolean) => events.filter(test).length;
  const modelCalls = count((e) => e.kind === "MODEL_RESULT");
  const proposals = count((e) => e.kind === "TOOL_PROPOSED");
  const assessments = count((e) => e.kind === "ASSESSMENT");
  const results = count((e) => e.kind === "TOOL_OR_STAGE_RESULT");
  const refused = count(isRefusal);
  const fact = (value: number, label: string, className?: string) => (
    <li className={className}><b>{value}</b>{label}</li>
  );
  return (
    <section className="ledger" aria-label="Who acted in this run">
      <div className="lane lane-model">
        <div className="lane-name"><strong>Model</strong><span className="lane-role">proposes and assesses</span></div>
        <ul className="lane-facts">
          {fact(modelCalls, modelCalls === 1 ? "call" : "calls")}
          {fact(proposals, proposals === 1 ? "proposed check" : "proposed checks")}
          {fact(assessments, assessments === 1 ? "assessment" : "assessments")}
        </ul>
      </div>
      <div className="lane lane-engine">
        <div className="lane-name"><strong>Engine</strong><span className="lane-role">computes and decides what runs</span></div>
        <ul className="lane-facts">
          {fact(results, results === 1 ? "tool or stage result" : "tool and stage results")}
          {fact(refused, refused === 1 ? "proposal refused" : "proposals refused", refused ? "refused" : undefined)}
        </ul>
      </div>
      <div className="lane lane-person">
        <div className="lane-name"><strong>Reviewer</strong><span className="lane-role">approves the exact report</span></div>
        <ul className="lane-facts">
          {state ? (
            <>
              {(() => {
                const toConfirm = state.resolved_finding_ids.length + state.abstained_finding_ids.length;
                return fact(toConfirm, toConfirm === 1 ? "finding to confirm" : "findings to confirm");
              })()}
              <li><Badge value={state.review_outcome} /></li>
            </>
          ) : <li><Unavailable /></li>}
        </ul>
      </div>
    </section>
  );
}

function Meters({ usage, limits }: { usage: BudgetUsage; limits?: BudgetLimits }) {
  const rows: [string, number | null, number | undefined][] = [
    ["Model calls", usage.model_calls, limits?.max_model_calls],
    ["Case actions", usage.actions, limits?.max_case_actions],
    ["Tokens reserved", usage.reserved_tokens, limits?.max_total_tokens],
    ["Report repairs", usage.report_repairs, limits?.report_repairs],
  ];
  return (
    <ul className="meters">
      {rows.map(([label, used, limit]) => {
        const share = used !== null && limit ? Math.min(1, used / limit) : null;
        return (
          <li key={label}>
            <div className="meter-label">
              <span>{label}</span>
              <span>{used === null ? <Unavailable /> : <b>{used.toLocaleString()}</b>} of {limit === undefined ? <Unavailable label="not exposed" /> : limit.toLocaleString()}</span>
            </div>
            {share !== null && (
              <div className="meter-track" role="meter" aria-label={label} aria-valuemin={0} aria-valuemax={limit} aria-valuenow={used ?? undefined}>
                <div className={`meter-fill ${share >= 0.75 ? "high" : ""}`} style={{ width: `${share * 100}%` }} />
              </div>
            )}
          </li>
        );
      })}
    </ul>
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
          {(job.status === "RUNNING" || job.status === "QUEUED") && !PAUSED.has(state.status) && (
            <RunProgress createdAt={state.created_at} updatedAt={state.updated_at} />
          )}
          {job.status === "FAILED" && job.detail && <div className="banner error prewrap">Worker failure: {job.detail}</div>}
          {stoppedRunNotice(state.status, state.stop_reason) && (
            <div className="banner error" role="status">{stoppedRunNotice(state.status, state.stop_reason)}</div>
          )}
        </section>
      )}

      <Ledger events={trace.events} state={state} />

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
              <p className="muted small">The run stops at any ceiling. Wall-clock time is limited to {run.data?.configuration.budgets?.max_wall_seconds ?? "the server default"} s.</p>
              <Meters usage={state.budget} limits={run.data?.configuration.budgets} />
              <details>
                <summary>All budget counters</summary>
                <Budget usage={state.budget} limits={run.data?.configuration.budgets} />
              </details>
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
