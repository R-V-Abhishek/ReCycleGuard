import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { ApiClient } from "../api/client";
import type { BucketResult, Quantity, TraceEvent } from "../api/types";
import { IssueList, Qty } from "../components/common";
import { actorOf, EventDetail, Timeline } from "../components/Timeline";
import { BucketBar, BucketTable } from "../screens/Report";
import { SessionContext } from "../state/session";

afterEach(cleanup);

const quantity = (decimal: string): Quantity => ({ decimal, unit: "KG", dimension: "METAL_MASS", metal: "AU" });
const HOSTILE = '<img src=x onerror="window.pwned=1"><script>window.pwned=1</script>';

const bucket = (extra: Partial<BucketResult> = {}): BucketResult => ({
  bucket_id: "bucket:au",
  required: quantity("12.3400"),
  supported: quantity("0.10000000"),
  signed_gap: quantity("-12.2400"),
  shortfall: quantity("12.2400"),
  surplus: quantity("0"),
  pending: quantity("5.5000"),
  portal_reported: null,
  ledger_supported: quantity("0.10000000"),
  delta: null,
  snapshot_comparison_ref: null,
  allocation_ids: [],
  qualification_refs: [],
  ...extra,
});

const event = (sequence: number, extra: object): TraceEvent =>
  ({
    sequence,
    event_id: `event:${sequence}`,
    operation_id: `operation:${sequence}`,
    turn_id: "turn:1",
    attempt_id: null,
    event_type: "graph.tool.search.result",
    payload_ref: { sha256: "a".repeat(64), byte_length: 1, media_type: "application/json" },
    ...extra,
  }) as TraceEvent;

const proposal = (reason: string) =>
  event(1, {
    kind: "TOOL_PROPOSED",
    data: {
      action_kind: "CHECK",
      allowed_operation: "compute_reconciliation",
      typed_arguments: { bucket_ids: ["bucket:au"] },
      finding_id: "finding:1",
      concise_reason: reason,
      evidence_refs: [],
      plan_ref: "plan:missing",
    },
  });

const withSession = (node: React.ReactNode) => (
  <SessionContext.Provider value={{ client: new ApiClient("http://api", "t"), disconnect() {} }}>{node}</SessionContext.Provider>
);

describe("quantities", () => {
  it("renders decimal strings verbatim, without rounding or trimming", () => {
    render(<BucketTable buckets={[bucket()]} />);
    expect(screen.getAllByText("0.10000000")).toHaveLength(1);
    expect(screen.getByText("12.3400")).toBeTruthy();
  });

  it("shows pending separately and doesn't subtract it from the gap", () => {
    render(<BucketTable buckets={[bucket()]} />);
    expect(screen.getByText("5.5000")).toBeTruthy();
    expect(screen.getByText("-12.2400")).toBeTruthy();
  });

  it("never renders a missing value as zero", () => {
    const { container, unmount } = render(<Qty value={null} />);
    expect(container.textContent).toBe("not reported");
    unmount();
    render(<BucketTable buckets={[bucket()]} />);
    expect(screen.getByText("not reported")).toBeTruthy();
    expect(screen.getByText("no comparison")).toBeTruthy();
  });

  it("keeps a real zero distinct from missing", () => {
    const { container } = render(<Qty value={quantity("0")} />);
    expect(container.textContent).toContain("0");
    expect(container.textContent).not.toContain("not reported");
  });
});

describe("untrusted text", () => {
  it("keeps HTML in model text inert in the timeline and details", () => {
    const hostile = proposal(HOSTILE);
    const { container } = render(
      withSession(
        <>
          <Timeline events={[hostile]} onSelect={() => {}} showAudit={false} />
          <EventDetail event={hostile} events={[hostile]} onSelect={() => {}} />
        </>,
      ),
    );
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("script")).toBeNull();
    expect(container.textContent).toContain(HOSTILE);
    expect((window as unknown as { pwned?: number }).pwned).toBeUndefined();
  });
});

describe("event details", () => {
  it("shows the recorded reason and the exact arguments", () => {
    const item = proposal("Balance must be computed first");
    render(withSession(<EventDetail event={item} events={[item]} onSelect={() => {}} />));
    expect(screen.getByText("Balance must be computed first")).toBeTruthy();
    fireEvent.click(screen.getByRole("tab", { name: "Arguments" }));
    expect(screen.getByText(/bucket:au/)).toBeTruthy();
  });

  it("explains a scripted call rather than inventing a sent prompt", () => {
    const item = event(2, { kind: "MODEL_RESULT", event_type: "graph.model.plan.result", status: "SUCCESS", issues: [] });
    render(withSession(<EventDetail event={item} events={[item]} onSelect={() => {}} agent={{ configured: true, model_id: "m", prompt_pin: null, system_template: "TEMPLATE TEXT", phase_rules: {}, response_schemas: {}, note: "" }} />));
    fireEvent.click(screen.getByRole("tab", { name: "Prompt" }));
    expect(screen.getByText(/No provider transport was recorded/)).toBeTruthy();
    expect(screen.queryByText("TEMPLATE TEXT")).toBeNull();
  });

  it("hides audit rows unless asked and keeps the selection marked", () => {
    const audit = event(3, { kind: "AUDIT", event_type: "graph.turn.started" });
    const item = proposal("reason");
    const { container, rerender } = render(<Timeline events={[item, audit]} selectedId="event:1" onSelect={() => {}} showAudit={false} />);
    expect(screen.queryByText("graph.turn.started")).toBeNull();
    expect(container.querySelector(".tl-row.on")).toBeTruthy();
    rerender(<Timeline events={[item, audit]} onSelect={() => {}} showAudit />);
    expect(screen.getByText("graph.turn.started")).toBeTruthy();
  });

  it("names who acted from the event kind and keeps refusals visible without the audit stream", () => {
    const refused = event(4, { kind: "AUDIT", event_type: "graph.action_rejected.result" });
    const review = event(5, { kind: "AUDIT", event_type: "graph.review_projection.result" });
    const stage = event(6, { kind: "TOOL_OR_STAGE_RESULT", event_type: "graph.stage.preflight.result", status: "SUCCESS", issues: [], data: null });
    expect(actorOf(proposal("r"))).toBe("model");
    expect(actorOf(stage)).toBe("engine");
    expect(actorOf(refused)).toBe("refused");
    expect(actorOf(review)).toBe("person");
    expect(actorOf(event(7, { kind: "AUDIT", event_type: "graph.turn.started" }))).toBe("record");
    render(<Timeline events={[proposal("r"), refused, review]} onSelect={() => {}} showAudit={false} />);
    expect(screen.getByText("Proposed arguments refused")).toBeTruthy();
    expect(screen.queryByText("graph.review_projection.result")).toBeNull();
  });

  it("shows repeated issues once with a count, blocking first", () => {
    const issue = (id: string, severity: "WARNING" | "BLOCKING", message: string) =>
      ({ issue_id: id, code: "CODE", severity, message, field_path: null, evidence_refs: [], retryable: false });
    const { container } = render(<IssueList issues={[issue("a", "WARNING", "same"), issue("b", "WARNING", "same"), issue("c", "BLOCKING", "stop")]} />);
    const rows = [...container.querySelectorAll("li")].map((li) => li.textContent);
    expect(rows).toEqual(["BLOCKING CODE stop", "WARNING CODE same ×2"]);
  });

  it("draws a bucket with exact figures and no bar for a zero target", () => {
    render(<BucketBar bucket={bucket()} />);
    expect(screen.getByRole("img").getAttribute("aria-label")).toBe("Supported 0.10000000 of 12.3400 KG; 5.5000 pending and not credited");
    expect(screen.getByText("12.2400")).toBeTruthy();
    cleanup();
    const zero = quantity("0");
    const { container } = render(<BucketBar bucket={bucket({ required: zero, supported: zero, pending: zero })} />);
    expect(container.firstChild).toBeNull();
  });
});
