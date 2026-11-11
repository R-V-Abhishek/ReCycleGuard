import { useState, type ReactNode } from "react";
import type { AgentConfig, EvidenceRef, Json, TraceEvent } from "../api/types";
import { eventParts, findByOperation, findPlan, resultForProposal } from "../state/traceStore";
import { Badge, IssueList, JsonView, Mono, Unavailable } from "./common";
import { EvidenceChips } from "./evidence";
import { PromptInspector } from "./PromptInspector";

// Latency and token usage come from the retained ModelCallResult (timing/usage); nothing is estimated.
export function modelTiming(event: TraceEvent): { seconds: number | null; tokens: number | null } {
  if (event.kind !== "MODEL_RESULT" || !event.response || typeof event.response !== "object" || Array.isArray(event.response)) {
    return { seconds: null, tokens: null };
  }
  const response = event.response as Record<string, Json>;
  const timing = response.timing as Record<string, Json> | null | undefined;
  const usage = response.usage as Record<string, Json> | null | undefined;
  const seconds = timing && typeof timing.elapsed_seconds === "number" ? timing.elapsed_seconds : null;
  const tokens = usage && typeof usage.total_tokens === "number" ? usage.total_tokens : null;
  return { seconds, tokens };
}

// "PLAN_REPAIR" and "plan_repair" both read as "plan repair".
const phaseName = (value: string) => value.toLowerCase().replace(/_/g, " ");

export function rowSummary(event: TraceEvent, events: TraceEvent[] = []): { kind: string; title: string; detail?: string; status?: string } {
  switch (event.kind) {
    case "PROMPT_PREPARED":
      return { kind: "Context", title: `Prompt prepared for ${phaseName(event.phase)}` };
    case "MODEL_RESULT":
      return { kind: "Model call", title: `Model call: ${phaseName(eventParts(event).name)}`, status: event.status };
    case "PLAN":
      return {
        kind: "Plan",
        title: event.data.previous_plan_ref ? `Plan revised · revision ${event.data.revision}` : "Plan",
        detail: event.data.objective,
      };
    case "TOOL_PROPOSED":
      return { kind: "Tool proposed", title: event.data.allowed_operation, detail: event.data.concise_reason };
    case "ASSESSMENT":
      return {
        kind: "Assessment",
        title: `${phaseName(event.data.verdict)}, then ${phaseName(event.data.disposition)}`,
        detail: event.data.next_check_or_stop,
      };
    case "BRIEF":
      return {
        kind: "Brief",
        title: `Reviewer brief: ${event.data.issue_type}`,
        detail: event.data.reason ?? event.data.what_to_check ?? undefined,
        status: event.data.status,
      };
    case "TOOL_OR_STAGE_RESULT": {
      const { family, name } = eventParts(event);
      const proposal = family === "tool" ? events.find((candidate) =>
        candidate.kind === "TOOL_PROPOSED" && resultForProposal(events, candidate)?.event_id === event.event_id
      ) : undefined;
      return {
        kind: family === "tool" ? "Tool result" : "Stage",
        title: proposal?.kind === "TOOL_PROPOSED" ? proposal.data.allowed_operation : name,
        detail: event.data?.concise_decision,
        status: event.status,
      };
    }
    case "AUDIT":
      return isRefusal(event)
        ? { kind: "Refused", title: "Proposed arguments refused", detail: "They could not run. The model was asked once more; nothing was corrected for it.", status: "REJECTED" }
        : { kind: "Audit", title: event.event_type };
  }
}

function PlanBody({ plan, events, onSelect }: { plan: Extract<TraceEvent, { kind: "PLAN" }>["data"]; events: TraceEvent[]; onSelect(id: string): void }) {
  const list = (label: string, items: string[]) =>
    items.length > 0 && (
      <>
        <h4>{label}</h4>
        <ul>{items.map((item, i) => <li key={i}>{item}</li>)}</ul>
      </>
    );
  const previous = findPlan(events, plan.previous_plan_ref);
  const trigger = findByOperation(events, plan.triggering_operation_ref);
  return (
    <div>
      <p><strong>{plan.objective}</strong></p>
      {plan.previous_plan_ref && (
        <p className="note">
          Revises {previous ? <button className="link" onClick={() => onSelect(previous.event_id)}>the previous plan</button> : <Mono>{plan.previous_plan_ref}</Mono>}
          {plan.triggering_operation_ref && (
            <>
              , triggered by{" "}
              {trigger ? <button className="link" onClick={() => onSelect(trigger.event_id)}>this observation</button> : <Mono>{plan.triggering_operation_ref}</Mono>}
            </>
          )}
          .
        </p>
      )}
      {list("Hypotheses", plan.hypotheses)}
      {list("Proposed checks", plan.proposed_checks)}
      {list("Expected evidence", plan.expected_evidence)}
      {list("Stopping criteria", plan.stopping_criteria)}
    </div>
  );
}

function Decision({ event, events, onSelect }: { event: TraceEvent; events: TraceEvent[]; onSelect(id: string): void }) {
  switch (event.kind) {
    case "TOOL_PROPOSED": {
      const plan = findPlan(events, event.data.plan_ref);
      return (
        <div>
          <h4>Model's recorded reason</h4>
          <p>{event.data.concise_reason}</p>
          <dl className="pairs">
            <dt>Action</dt>
            <dd>{event.data.action_kind}</dd>
            <dt>Finding</dt>
            <dd><Mono>{event.data.finding_id}</Mono></dd>
            <dt>Plan</dt>
            <dd>{plan ? <button className="link" onClick={() => onSelect(plan.event_id)}>{plan.kind === "PLAN" ? plan.data.objective : plan.event_id}</button> : <Mono>{event.data.plan_ref}</Mono>}</dd>
          </dl>
          {plan?.kind === "PLAN" && plan.data.hypotheses.length > 0 && (
            <>
              <h4>Current hypotheses</h4>
              <ul>{plan.data.hypotheses.map((h, i) => <li key={i}>{h}</li>)}</ul>
            </>
          )}
        </div>
      );
    }
    case "PLAN":
      return <PlanBody plan={event.data} events={events} onSelect={onSelect} />;
    case "ASSESSMENT":
      return (
        <div>
          <p><Badge value={event.data.verdict} /> <Badge value={event.data.disposition} /></p>
          <h4>Next check or stop</h4>
          <p>{event.data.next_check_or_stop}</p>
          {event.data.weak_result_or_mistake && (
            <>
              <h4>Weak result or mistake</h4>
              <p>{event.data.weak_result_or_mistake}</p>
            </>
          )}
          {event.data.revised_plan_ref && (
            <p className="note">
              Led to a revised plan:{" "}
              {(() => {
                const plan = findPlan(events, event.data.revised_plan_ref);
                return plan ? <button className="link" onClick={() => onSelect(plan.event_id)}>open it</button> : <Mono>{event.data.revised_plan_ref}</Mono>;
              })()}
            </p>
          )}
        </div>
      );
    case "TOOL_OR_STAGE_RESULT":
    case "MODEL_RESULT":
      return (
        <div>
          <p><Badge value={event.status} /> {event.data && <Badge value={event.data.disposition} />}</p>
          {event.data?.concise_decision ? <p>{event.data.concise_decision}</p> : <Unavailable label="no recorded decision" />}
          <IssueList issues={event.issues} />
        </div>
      );
    default:
      return <Unavailable label="no recorded decision for this entry" />;
  }
}

function argumentsOf(event: TraceEvent): Record<string, Json> | undefined {
  return event.kind === "TOOL_PROPOSED" ? event.data.typed_arguments : undefined;
}

function resultOf(event: TraceEvent, events: TraceEvent[]): ReactNode {
  const target = event.kind === "TOOL_PROPOSED" ? resultForProposal(events, event) : event;
  if (!target) return <Unavailable label="no result recorded yet" />;
  if (target.kind === "TOOL_OR_STAGE_RESULT" || target.kind === "MODEL_RESULT") {
    return (
      <div>
        <p><Badge value={target.status} /></p>
        <IssueList issues={target.issues} />
        <h4>Structured result</h4>
        <JsonView value={target.result} />
        <h4>Outcome envelope</h4>
        <JsonView value={target.data} />
      </div>
    );
  }
  if (target.kind === "ASSESSMENT" || target.kind === "PLAN" || target.kind === "BRIEF") return <JsonView value={target.data} />;
  return <Unavailable label="this entry has no result" />;
}

function evidenceOf(event: TraceEvent, events: TraceEvent[]): { refs: EvidenceRef[]; calculations: string[] } {
  if (event.kind === "TOOL_PROPOSED") {
    const result = resultForProposal(events, event);
    const later = result && "data" in result && result.kind === "TOOL_OR_STAGE_RESULT" ? result.data : undefined;
    return { refs: [...event.data.evidence_refs, ...(later?.evidence_refs ?? [])], calculations: later?.calculation_ids ?? [] };
  }
  if (event.kind === "ASSESSMENT") return { refs: event.data.observation_refs, calculations: [] };
  if (event.kind === "BRIEF") return { refs: event.data.evidence_refs, calculations: [] };
  if (event.kind === "TOOL_OR_STAGE_RESULT" || event.kind === "MODEL_RESULT") {
    return { refs: event.data?.evidence_refs ?? [], calculations: event.data?.calculation_ids ?? [] };
  }
  return { refs: [], calculations: [] };
}

const TABS = ["Decision", "Arguments", "Result", "Evidence", "Prompt", "Audit"] as const;
type Tab = (typeof TABS)[number];

export function EventDetail({
  event,
  events,
  dossierId,
  agent,
  onSelect,
}: {
  event: TraceEvent;
  events: TraceEvent[];
  dossierId?: string;
  agent?: AgentConfig;
  onSelect(id: string): void;
}) {
  const [tab, setTab] = useState<Tab>("Decision");
  const evidence = evidenceOf(event, events);
  const args = argumentsOf(event);
  return (
    <div>
      <div className="tabs" role="tablist">
        {TABS.map((name) => (
          <button key={name} role="tab" aria-selected={tab === name} className={tab === name ? "on" : ""} onClick={() => setTab(name)}>
            {name}
          </button>
        ))}
      </div>
      <div className="tab-body">
        {tab === "Decision" && <Decision event={event} events={events} onSelect={onSelect} />}
        {tab === "Arguments" && (args ? (<><p className="note">Validated arguments as recorded in the proposal.</p><JsonView value={args} /></>) : <Unavailable label="this entry has no tool arguments" />)}
        {tab === "Result" && resultOf(event, events)}
        {tab === "Evidence" && (
          <div>
            <EvidenceChips refs={evidence.refs} dossierId={dossierId} />
            {evidence.calculations.length > 0 && (
              <>
                <h4>Calculations</h4>
                <ul>{evidence.calculations.map((id) => <li key={id}><Mono>{id}</Mono></li>)}</ul>
              </>
            )}
          </div>
        )}
        {tab === "Prompt" &&
          (event.kind === "MODEL_RESULT" || event.kind === "PROMPT_PREPARED" ? (
            <PromptInspector key={event.event_id} event={event} events={events} agent={agent} />
          ) : (
            <Unavailable label="Prompts belong to model calls. Select a model call in the timeline." />
          ))}
        {tab === "Audit" && (
          <dl className="pairs">
            <dt>Sequence</dt><dd>{event.sequence}</dd>
            <dt>Event</dt><dd><Mono>{event.event_id}</Mono></dd>
            <dt>Type</dt><dd><Mono>{event.event_type}</Mono></dd>
            <dt>Operation</dt><dd>{event.operation_id ? <Mono>{event.operation_id}</Mono> : <Unavailable />}</dd>
            <dt>Turn</dt><dd>{event.turn_id ? <Mono>{event.turn_id}</Mono> : <Unavailable />}</dd>
            <dt>Attempt</dt><dd>{event.attempt_id ? <Mono>{event.attempt_id}</Mono> : <Unavailable />}</dd>
            <dt>Payload digest</dt><dd><Mono>{event.payload_ref.sha256}</Mono></dd>
            <dt>Duration</dt><dd>{(() => {
              const timing = modelTiming(event);
              return timing.seconds === null ? <Unavailable label="recorded for model calls only" /> : `${timing.seconds.toFixed(1)} s`;
            })()}</dd>
            {event.kind === "MODEL_RESULT" && (
              <>
                <dt>Tokens (provider)</dt><dd>{modelTiming(event).tokens ?? <Unavailable label="not reported" />}</dd>
              </>
            )}
          </dl>
        )}
      </div>
    </div>
  );
}

export type Actor = "model" | "engine" | "person" | "record" | "refused";

export const ACTOR_LABEL: Record<Actor, string> = {
  model: "Model",
  engine: "Engine",
  person: "Reviewer",
  record: "Audit",
  refused: "Engine",
};

// The workflow refused a proposed action's arguments before anything ran (runner._checked_plan_proposal).
export const isRefusal = (event: TraceEvent) => event.event_type === "graph.action_rejected.result";

// Who acted, from the event kind alone. The model only proposes and assesses; prepared context,
// tool and stage results come from code; review events record a person's decision.
export function actorOf(event: TraceEvent): Actor {
  switch (event.kind) {
    case "MODEL_RESULT":
    case "PLAN":
    case "TOOL_PROPOSED":
    case "ASSESSMENT":
    case "BRIEF":
      return "model";
    case "PROMPT_PREPARED":
    case "TOOL_OR_STAGE_RESULT":
      return "engine";
    case "AUDIT":
      if (isRefusal(event)) return "refused";
      return event.event_type.startsWith("graph.review_projection") ? "person" : "record";
  }
}

// Consecutive events of one workflow turn, in sequence order.
function turns(events: TraceEvent[]) {
  const groups: { key: string; events: TraceEvent[] }[] = [];
  for (const event of events) {
    const key = event.turn_id ?? `event:${event.event_id}`;
    const last = groups[groups.length - 1];
    if (last && last.key === key) last.events.push(event);
    else groups.push({ key, events: [event] });
  }
  return groups;
}

function turnName(events: TraceEvent[]) {
  const stage = events.find((event) => event.kind === "TOOL_OR_STAGE_RESULT" && eventParts(event).family === "stage");
  if (stage) {
    const name = eventParts(stage).name;
    return name.charAt(0).toUpperCase() + name.slice(1);
  }
  if (events.some((event) => event.kind === "MODEL_RESULT")) return "Investigate";
  return "Workflow";
}

export function Timeline({
  events,
  selectedId,
  onSelect,
  showAudit,
}: {
  events: TraceEvent[];
  selectedId?: string;
  onSelect(id: string): void;
  showAudit: boolean;
}) {
  // Refusals stay visible without the audit stream: they are the workflow overruling the model.
  const visible = showAudit ? events : events.filter((event) => event.kind !== "AUDIT" || isRefusal(event));
  if (!visible.length) return <p className="muted">No recorded activity yet.</p>;
  return (
    <ol className="timeline">
      {turns(visible).map((group, index) => (
        <li key={group.key} className="tl-turn">
          <div className="tl-turn-head">
            Step {index + 1}: {turnName(group.events)}
            <span>{group.events.length} {group.events.length === 1 ? "event" : "events"}</span>
          </div>
          <ol>
            {group.events.map((event) => {
              const row = rowSummary(event, events);
              const actor = actorOf(event);
              return (
                <li key={event.event_id}>
                  <button className={`tl-row actor-${actor} ${selectedId === event.event_id ? "on" : ""}`} onClick={() => onSelect(event.event_id)}>
                    <span className="tl-actor">{ACTOR_LABEL[actor]}<small>{row.kind}</small></span>
                    <span className="tl-main">
                      <span className="tl-title">{row.title}</span>
                      {row.detail && <span className="tl-detail">{row.detail}</span>}
                    </span>
                    {row.status && <Badge value={row.status} />}
                  </button>
                </li>
              );
            })}
          </ol>
        </li>
      ))}
    </ol>
  );
}
