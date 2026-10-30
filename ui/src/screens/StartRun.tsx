import { useEffect, useState } from "react";
import { ApiError } from "../api/client";
import type { BudgetLimits, RunMode } from "../api/types";
import { Badge, ErrorBanner, JsonView, Mono, Section, Unavailable, useAction, useLoad } from "../components/common";
import { useHeader } from "../components/Shell";
import { navigate, startedBudgets, useClient } from "../state/session";

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
  const [mode, setMode] = useState<RunMode>("MODEL_BACKED");
  const [budgets, setBudgets] = useState<Partial<Record<keyof BudgetLimits, string>>>({});
  const [locked, setLocked] = useState(false);
  const start = useAction();
  const { setHeader } = useHeader();
  useEffect(() => {
    setHeader({ dossierId, dossierName: dossier.data?.name, mode });
  }, [dossierId, dossier.data?.name, mode, setHeader]);

  const parsedBudgets = () => {
    const out: Record<string, number> = {};
    for (const [key] of BUDGET_FIELDS) {
      const raw = budgets[key]?.trim();
      if (raw) out[key] = parseInt(raw, 10);
    }
    return Object.keys(out).length ? out : undefined;
  };
  const begin = () =>
    void start.run(async () => {
      const chosen = parsedBudgets();
      try {
        const run = await client.startRun(dossierId, mode, chosen);
        if (chosen) startedBudgets.set(run.run_id, chosen);
        navigate("runs", run.run_id);
      } catch (cause) {
        // The run may exist, and the API has no run list or idempotency key. Don't offer a
        // second start until a person has deliberately unlocked it.
        if (cause instanceof ApiError && cause.kind === "UNKNOWN_OUTCOME") setLocked(true);
        throw cause;
      }
    });

  const approved = dossier.data?.status === "APPROVED";
  const config = agent.data;
  return (
    <>
      <ErrorBanner error={dossier.error} />
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
            {health.data?.model_configured ? "Configured, not probed. Readiness is only confirmed when a run starts." : <Unavailable label="not configured on the server" />}
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
            <input type="radio" checked={mode === "MODEL_BACKED"} onChange={() => setMode("MODEL_BACKED")} /> Model-backed: the local model proposes each step
          </label>
          <label className="check">
            <input type="radio" checked={mode === "SCRIPTED_TEST"} onChange={() => setMode("SCRIPTED_TEST")} /> Scripted test: replayed proposals, shows no model reasoning. The server must have test adapters enabled.
          </label>
        </fieldset>
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
            Starting is locked because the last request may have created a run. The server allows one active run at a time, so if one is running, another start returns a conflict.
            <button className="link" onClick={() => { setLocked(false); start.clearError(); }}>I've checked, unlock start</button>
          </div>
        )}
        <button className="primary" disabled={!approved || start.busy || locked} onClick={begin}>
          {start.busy ? "Starting…" : "Start investigation"}
        </button>
      </Section>
    </>
  );
}
