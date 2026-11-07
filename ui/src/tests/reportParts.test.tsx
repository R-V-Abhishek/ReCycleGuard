import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { ApiClient } from "../api/client";
import type { InvestigationReport, Issue, Quantity, ReviewerBrief, RunBriefs } from "../api/types";
import { BriefPanel, ChecksTable, ClaimsBySection, ReportText, UnresolvedIssues } from "../components/reportParts";
import { SessionContext } from "../state/session";

afterEach(cleanup);

const withSession = (node: React.ReactNode) => (
  <SessionContext.Provider value={{ client: new ApiClient("http://api", "t"), disconnect() {} }}>{node}</SessionContext.Provider>
);

const q = (decimal: string): Quantity => ({ decimal, unit: "KG", dimension: "METAL_MASS", metal: "AU" });
const ref = { ref_kind: "OBSERVATION" as const, ref_id: "observation:one", artifact_revision_id: null, locator: null };
const body: InvestigationReport["report"] = {
  revision: { report_id: "r", report_revision_id: "rr", review_dependency_digest: "d".repeat(64), supersedes_report_revision_id: null },
  sections: [
    { section_id: "s1", title: "Balances", claim_ids: ["c1", "c9"], evidence_refs: [], coverage_state: "QUALIFIED" },
  ],
  claims: [{ claim_id: "c1", kind: "NUMERIC", template_or_text: "Shortfall is {value}", evidence_refs: [ref], calculation_value_ref: { calculation_id: "calc:1", bucket_id: "bucket:au", field: "shortfall" }, support_status: "UNSUPPORTED" }],
  calculations: [{ calculation_id: "calc:1", analyzed_bucket_ids: ["bucket:au"], bucket_results: [{ bucket_id: "bucket:au", required: q("12.3400"), supported: q("0.1"), signed_gap: q("-12.2400"), shortfall: q("12.2400"), surplus: q("0"), pending: q("0"), portal_reported: null, ledger_supported: q("0.1"), delta: null, snapshot_comparison_ref: null, allocation_ids: [], qualification_refs: [] }], coverage: "QUALIFIED", issues: [] }],
  rendered_markdown: "",
};

describe("claims", () => {
  it("shows each claim's backend support status and evidence, and flags a missing claim", () => {
    render(withSession(<ClaimsBySection report={body} onCalculation={() => {}} />));
    expect(screen.getByText("UNSUPPORTED")).toBeTruthy();
    expect(screen.getByText("QUALIFIED")).toBeTruthy();
    expect(screen.getByText("Shortfall is 12.2400 KG")).toBeTruthy();
    expect(screen.getByText("observation:one")).toBeTruthy();
    expect(screen.getByText("c9")).toBeTruthy();
    expect(screen.getByText(/missing from the report/)).toBeTruthy();
  });
});

describe("report text", () => {
  it("renders headings and bullets as text and never interprets HTML", () => {
    const { container } = render(<ReportText markdown={'# Title\n\n## Part\n\n- A claim <img src=x onerror="window.pwned=1"> [ref:1, ref:2]\n'} />);
    expect(container.querySelector("h3")?.textContent).toBe("Title");
    expect(container.querySelector("h4")?.textContent).toBe("Part");
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("li")?.textContent).toContain("ref:1, ref:2");
  });

  it("says so when there is no text", () => {
    render(<ReportText markdown="" />);
    expect(screen.getByText("no report text")).toBeTruthy();
  });
});

describe("unresolved issues and checks", () => {
  const issue: Issue = { issue_id: "issue:1", code: "MISSING_PORTAL", severity: "WARNING", message: "Portal value absent", field_path: null, evidence_refs: [], retryable: false };
  it("resolves issue ids that the report carries and labels the rest", () => {
    const report = { report: body, findings: [], available_evidence_refs: [], verification: { issues: [issue] } } as unknown as InvestigationReport;
    render(<UnresolvedIssues ids={["issue:1", "issue:2"]} report={report} />);
    expect(screen.getByText("MISSING_PORTAL")).toBeTruthy();
    expect(screen.getByText("issue:2")).toBeTruthy();
    expect(screen.getByText("details are not in this report")).toBeTruthy();
  });

  it("shows every check key, with absent values marked and booleans literal", () => {
    render(<ChecksTable checks={[{ check: "citations", passed: true }, { check: "scope" }]} />);
    expect(screen.getByText("true")).toBeTruthy();
    expect(screen.getAllByText("–")).toHaveLength(1);
  });
});

describe("reviewer brief", () => {
  const brief = (over: Partial<ReviewerBrief>): ReviewerBrief => ({
    brief_id: "brief:template_1", run_id: "run:1", report_revision_id: "rr", finding_revision_id: "finding_revision:1",
    issue_type: "F07_PAID_NO_TRANSFER", source: "TEMPLATE", status: "ACCEPTED", reason: null,
    what_to_check: "Template check", explanation: "Template basis", evidence_request: "Template request",
    evidence_refs: [ref], figures: [{ label: "Supported, bucket:au", value: "0.1 KG", value_ref: { calculation_id: "calc:1", bucket_id: "bucket:au", field: "supported" } }],
    label: "Template brief, generated from the finding.", model_operation_ref: null, ...over,
  });
  const model = brief({
    brief_id: "brief:model_1", source: "MODEL", what_to_check: "Model check", explanation: "Model basis",
    evidence_request: "Model request", label: "Advisory, model-drafted; it changes no finding, number or decision.",
    model_operation_ref: "operation:brief_0",
  });
  const set = (models: ReviewerBrief[]): RunBriefs => ({ run_id: "run:1", report_revision_id: "rr", model_briefs: models, template_briefs: [brief({})] });

  it("labels an accepted model brief as advisory and keeps the template beside it", () => {
    render(withSession(<BriefPanel findingRevisionId="finding_revision:1" briefs={set([model])} />));
    expect(screen.getByText(/Advisory, model-drafted/)).toBeTruthy();
    expect(screen.getByText("Model check")).toBeTruthy();
    expect(screen.getAllByText("0.1 KG").length).toBeGreaterThan(0);
    expect(screen.getByText("Template brief")).toBeTruthy();
  });

  it("states a rejected model brief's reason, never its text, and shows the template", () => {
    const rejected = { ...model, status: "REJECTED" as const, reason: "DIGITS_IN_TEXT", what_to_check: null, explanation: null, evidence_request: null, figures: [], evidence_refs: [] };
    render(withSession(<BriefPanel findingRevisionId="finding_revision:1" briefs={set([rejected])} />));
    expect(screen.getByText(/DIGITS_IN_TEXT/)).toBeTruthy();
    expect(screen.queryByText("Model check")).toBeNull();
    expect(screen.getByText("Template check")).toBeTruthy();
    expect(screen.getByText(/Template brief, generated/)).toBeTruthy();
  });

  it("renders nothing when the finding has no brief", () => {
    const { container } = render(withSession(<BriefPanel findingRevisionId="finding_revision:other" briefs={set([])} />));
    expect(container.textContent).toBe("");
  });
});
