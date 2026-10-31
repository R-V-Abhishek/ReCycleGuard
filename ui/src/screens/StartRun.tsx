import { useEffect, useState } from "react";
import { ApiError } from "../api/client";
import type { BudgetLimits, RunMode } from "../api/types";
import { Badge, ErrorBanner, JsonView, Mono, Section, Unavailable, useAction, useLoad } from "../components/common";
import { useHeader } from "../components/Shell";
import { href, navigate, useClient } from "../state/session";

const BUDGET_FIELDS: [keyof BudgetLimits, string][] = [
  ["max_model_calls", "Model calls"],
  ["max_case_actions", "Case actions"],
  ["max_total_tokens", "Total tokens"],
  ["tokens_per_model_call", "Tokens per call"],
  ["max_wall_seconds", "Wall-clock seconds"],
];

export function StartRun({ dossierId }: { dossierId: string }) {
  const client = useClient();
  const agent = useLoad(() => client.agent(), [client]);
  const health = useLoad(() => client.health(), [client]);
  const dossier = useLoad(() => client.dossier(dossierId), [client, dossierId]);
  const recent = useLoad(() => client.runs(dossierId), [client, dossierId]);
  const [mode, setMode] = useState<RunMode>("MODEL_BACKED");
  const [budgets, setBudgets] = useState<Partial<Record<keyof BudgetLimits, string>>>({});
  const [locked, setLocked] = useState(false);
  const start = useAction();
  const { setHeader } = useHeader();
  const availableModes = health.data?.available_modes;
  useEffect(() => {
    if (availableModes?.length && !availableModes.includes(mode)) setMode(availableModes[0]);
  }, [availableModes, mode]);
  useEffect(() => {
    setHeader({ dossierId, dossierName: dossier.data?.name, mode });
  }, [dossierId, dossier.data?.name, mode, setHeader]);

  const parsedBudgets = () => {
    const out: Record<string, number> = {};
    for (const [key] of BUDGET_FIELDS) {
      const raw = budgets[key]?.trim();
      if (raw) {
        const value = Number(raw);
        if (!Number.isSafeInteger(value) || value < 1) throw new Error(`${key} must be a positive whole number`);
        out[key] = value;
      }
    }
    return Object.keys(out).length ? out : undefined;
  };
  const begin = () =>
    void start.run(async (signal) => {
      const chosen = parsedBudgets();
      try {
        const run = await client.startRun(dossierId, mode, chosen);
        if (!signal.aborted) navigate("runs", run.run_id);
      } catch (cause) {
        // The run may exist, and the API has no run list or idempotency key. Don't offer a
        // second start until a person has deliberately unlocked it.
        if (!signal.aborted && cause instanceof ApiError && cause.kind === "UNKNOWN_OUTCOME") {
          setLocked(true);
          await recent.reload();
        }
        throw cause;
      }
    });

  const approved = dossier.data?.status === "APPROVED";
  const config = agent.data;
  return (
    <>
      <ErrorBanner error={dossier.error} />
      <ErrorBanner error={health.error} />
      <Section title="Agent setup" aside={<Badge value="TEMPLATE" title="Configuration, not proof of a call" />}>
        <ErrorBanner error={agent.error} />
        <p className="note">
          These are configured templates. The exact prompt for each model call appears in the investigation timeline after that call finishes.
        </p>
        <dl className="pairs">
          <dt>Model</dt>
          <dd>{config?.model_id ? <Mono>{config.model_id}</Mono> : <Unavailable label="not configured" />}</dd>
          <dt>Prompt pin</dt>
          <dd>{config?.prompt_pin ? <Mono>{config.prompt_pin.configuration_id}</Mono> : <Unavailable />}</dd>
          <dt>Model readiness</dt>
          <dd>
            {health.data?.model_configured ? "Configured, not probed. Starting a run does not establish model quality or compatibility." : <Unavailable label="not configured on the server" />}
          </dd>
        </dl>
        {config && (
          <>
            <details>
              <summary>System template</summary>
              <pre className="block">{config.system_template}</pre>
            </details>
            <details>
              <summary>Phase rules</summary>
              <JsonView value={config.phase_rules} />
            </details>
            <details>
              <summary>Response schemas</summary>
              <JsonView value={config.response_schemas} />
            </details>
          </>
        )}
      </Section>

      <Section title="Start investigation">
        {dossier.data && !approved && (
          <div className="banner warn">This dossier's foundation isn't approved yet, so a run can't start.</div>
        )}
        <fieldset>
          <legend>Execution mode</legend>
          <label className="check">
            <input type="radio" disabled={!availableModes?.includes("MODEL_BACKED")} checked={mode === "MODEL_BACKED"} onChange={() => setMode("MODEL_BACKED")} /> Model-backed: the local model proposes each step
          </label>
          <label className="check">
            <input type="radio" disabled={!availableModes?.includes("SCRIPTED_TEST")} checked={mode === "SCRIPTED_TEST"} onChange={() => setMode("SCRIPTED_TEST")} /> Scripted test: replayed proposals, shows no model reasoning. The server must have test adapters enabled.
          </label>
        </fieldset>
        {availableModes?.length === 0 && <div className="banner warn">The server has no enabled investigation mode.</div>}
        <details>
          <summary>Budget overrides (optional)</summary>
          <p className="muted small">
            Leave all blank to use the server's defaults. If you set any, the contract's defaults apply to the rest instead of the server's model-specific ones.
          </p>
          <div className="budget-grid">
            {BUDGET_FIELDS.map(([key, label]) => (
              <label className="field" key={key}>
                <span>{label}</span>
                <input type="number" min={1} step={1} value={budgets[key] ?? ""} onChange={(e) => setBudgets({ ...budgets, [key]: e.target.value })} />
              </label>
            ))}
          </div>
        </details>
        <ErrorBanner error={start.error} />
        {locked && (
          <div className="banner warn">
            Starting is locked because the last request may have created a run. Refresh the read-only run list below and open its recorded investigation instead of resubmitting. An empty list alone does not prove the request failed.
          </div>
        )}
        <button className="primary" disabled={!approved || start.busy || locked || Boolean(health.error) || !availableModes?.includes(mode) || (mode === "MODEL_BACKED" && !config?.configured)} onClick={begin}>
          {start.busy ? "Starting…" : "Start investigation"}
        </button>
      </Section>
      <Section title="Investigations for this dossier" aside={<button disabled={recent.loading} onClick={() => void recent.reload()}>Refresh runs</button>}>
        <ErrorBanner error={recent.error} />
        {recent.loading && <p className="muted">Loading run records…</p>}
        {recent.data?.runs.map((run) => <p key={run.state.run_id}>
          <a href={href("runs", run.state.run_id)}><Mono>{run.state.run_id}</Mono></a>{" "}
          <Badge value={run.state.status} /> <Badge value={run.job.status} />
          <Badge value={run.configuration.execution_kind} />
        </p>)}
        {!recent.loading && recent.data?.runs.length === 0 && <p className="muted">No recorded runs for this dossier.</p>}
      </Section>
    </>
  );
}
