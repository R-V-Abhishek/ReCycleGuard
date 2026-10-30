import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { ApiClient } from "../api/client";
import type { BucketResult, Quantity, TraceEvent } from "../api/types";
import { Qty } from "../components/common";
import { EventDetail, Timeline } from "../components/Timeline";
import { BucketTable } from "../screens/Report";
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
});
