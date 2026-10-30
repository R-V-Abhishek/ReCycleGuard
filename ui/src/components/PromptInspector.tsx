import { useState } from "react";
import type { AgentConfig, ModelResultEvent, PromptPreparedEvent, TraceEvent } from "../api/types";
import { preparedFor, sentPrompt } from "../state/promptLayers";
import { JsonView, Mono, Unavailable } from "./common";

type Layer = "sent" | "prepared" | "template" | "response";

const NO_SENT: Record<string, string> = {
  NOT_DISPATCHED:
    "No request body was recorded for this call, for example because it was rejected before dispatch. Nothing can be shown as sent.",
  NO_TRACE:
    "No provider transport was recorded. Transport data is unavailable or this call was scripted. Scripted calls have no wire prompt.",
  NOT_MODEL:
    "This entry is prepared context, not a completed model call. Select the model call that follows it to see what was sent.",
};

function SentLayer({ model }: { model?: ModelResultEvent }) {
  const [raw, setRaw] = useState(false);
  if (!model) return <p className="muted">{NO_SENT.NOT_MODEL}</p>;
  const sent = sentPrompt(model);
  if (sent.state === "NOT_DISPATCHED" || sent.state === "NO_TRACE") {
    return (
      <div>
        <p className="muted">{NO_SENT[sent.state]}</p>
        {sent.state === "NOT_DISPATCHED" && <JsonView value={sent.trace} />}
      </div>
    );
  }
  const trace = sent.trace;
  return (
    <div>
      <p className="note">
        Recorded wire request for this call. This is what the adapter sent, including transport markers.
      </p>
      <dl className="pairs">
        <dt>Endpoint</dt>
        <dd>
          <Mono>
            {trace.method ?? "unavailable"} {trace.endpoint ?? ""}
          </Mono>
        </dd>
        <dt>Response status</dt>
        <dd>{trace.response_status ?? <Unavailable label="no response recorded" />}</dd>
        {trace.error && (
          <>
            <dt>Error</dt>
            <dd className="prewrap">{trace.error}</dd>
          </>
        )}
      </dl>
      {sent.state === "UNPARSEABLE" || raw ? (
        <>
          {sent.state === "UNPARSEABLE" && <p className="muted">The recorded body isn't a JSON object, so it's shown untouched.</p>}
          <pre className="block">{sent.raw}</pre>
        </>
      ) : (
        <>
          <h4>Prompt</h4>
          {sent.prompt === null ? <Unavailable label="no prompt field in the recorded body" /> : <pre className="block">{sent.prompt}</pre>}
          <h4>Transport parameters</h4>
          <JsonView value={sent.parameters} />
        </>
      )}
      {sent.state === "SENT" && (
        <button className="link" onClick={() => setRaw(!raw)}>
          {raw ? "Show formatted" : "Show untouched request text"}
        </button>
      )}
    </div>
  );
}

function PreparedLayer({ prepared }: { prepared?: PromptPreparedEvent }) {
  if (!prepared) return <p className="muted">No prepared context was found for this call in its turn.</p>;
  return (
    <div>
      <p className="note">Prepared context. This shows what was prepared, not proof of what the provider received.</p>
      <p>
        Phase <Mono>{prepared.phase}</Mono>
      </p>
      <h4>Logical request</h4>
      <JsonView value={prepared.request} />
      <h4>System template preview</h4>
      {prepared.system_template === null ? <Unavailable label="none for this run" /> : <pre className="block">{prepared.system_template}</pre>}
    </div>
  );
}

function TemplateLayer({ agent, phase }: { agent?: AgentConfig; phase?: string }) {
  if (!agent) return <p className="muted">Agent configuration hasn't loaded.</p>;
  return (
    <div>
      <p className="note">Configured template only. It does not show what any specific call sent. {agent.note}</p>
      <h4>System template</h4>
      <pre className="block">{agent.system_template}</pre>
      {phase && agent.phase_rules[phase] !== undefined && (
        <>
          <h4>Phase rules: {phase}</h4>
          <pre className="block">{agent.phase_rules[phase]}</pre>
        </>
      )}
    </div>
  );
}

function ResponseLayer({ model }: { model?: ModelResultEvent }) {
  if (!model) return <p className="muted">Select a model call to see its response.</p>;
  return (
    <div>
      <h4>Validated structured response</h4>
      <JsonView value={model.response} />
      <h4>Exact response text</h4>
      {model.exact_response === undefined ? <Unavailable /> : <pre className="block">{model.exact_response}</pre>}
      <h4>Raw provider response body</h4>
      {model.provider_trace?.response_body_utf8 ? (
        <pre className="block">{model.provider_trace.response_body_utf8}</pre>
      ) : (
        <Unavailable label="not recorded" />
      )}
    </div>
  );
}

export function PromptInspector({
  event,
  events,
  agent,
}: {
  event: ModelResultEvent | PromptPreparedEvent;
  events: TraceEvent[];
  agent?: AgentConfig;
}) {
  const [layer, setLayer] = useState<Layer>(event.kind === "MODEL_RESULT" ? "sent" : "prepared");
  const model = event.kind === "MODEL_RESULT" ? event : undefined;
  const prepared = event.kind === "PROMPT_PREPARED" ? event : model && preparedFor(events, model);
  const tabs: [Layer, string][] = [
    ["sent", "Sent"],
    ["prepared", "Prepared"],
    ["template", "Template"],
    ["response", "Response"],
  ];
  return (
    <div>
      <div className="subtabs" role="tablist">
        {tabs.map(([key, label]) => (
          <button key={key} role="tab" aria-selected={layer === key} className={layer === key ? "on" : ""} onClick={() => setLayer(key)}>
            {label}
          </button>
        ))}
      </div>
      {layer === "sent" && <SentLayer model={model} />}
      {layer === "prepared" && <PreparedLayer prepared={prepared} />}
      {layer === "template" && <TemplateLayer agent={agent} phase={prepared?.phase} />}
      {layer === "response" && <ResponseLayer model={model} />}
    </div>
  );
}
