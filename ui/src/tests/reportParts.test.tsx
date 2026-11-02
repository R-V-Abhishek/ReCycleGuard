import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { ApiClient } from "../api/client";
import type { InvestigationReport, Issue, Quantity } from "../api/types";
import { ChecksTable, ClaimsBySection, ReportText, UnresolvedIssues } from "../components/reportParts";
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
