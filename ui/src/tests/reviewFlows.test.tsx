import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiClient } from "../api/client";
import type { Dossier, Evidence, InvestigationReport, Locator, ReviewPacket } from "../api/types";
import { ArtifactViewer, EvidenceChips } from "../components/evidence";
import { Readiness, SupportReview } from "../screens/Readiness";
import { ReviewForm } from "../screens/Report";
import { SessionContext } from "../state/session";

afterEach(() => { cleanup(); vi.restoreAllMocks(); });
const client = () => new ApiClient("http://api", "token");
const session = (api: ApiClient, node: React.ReactNode) => <SessionContext.Provider value={{ client: api, disconnect() {} }}>{node}</SessionContext.Provider>;
const deferred = <T,>() => {
  let resolve!: (value: T) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
};
const locator: Locator = { kind: "JSON_POINTER", json_pointer: "/0", page_index_1based: null, printed_page_label: null, row_index_1based: null, column_name: null, text_start: null, text_end: null, table_id: null, cell_row: null, cell_column: null };
const evidence = (): Evidence => {
  const payload = { record_type: "Allocation", record_id: "record:one", allocation_id: "allocation:one", state: "SUPPORTED", quantity: { decimal: "25.0000", unit: "KG" } };
  return {
    snapshot: { snapshot_id: "snapshot:one", membership_digest: "a".repeat(64) },
    originals: [{ artifact_id: "artifact:one", artifact_revision_id: "artifact_revision:one", blob: { sha256: "b".repeat(64), byte_length: 1, media_type: "application/json" }, original_filename: "original.json", source_kind: "PRODUCER", doc_type: "OTHER", synthetic: true }],
    observations: [{ observation_id: "observation:one", artifact_revision_id: "artifact_revision:one", locator, observation_type: "STRUCTURED", raw_fields: {}, parsed_fields: payload, validation_state: "VALID", extraction_method: "JSON" }],
    records: [{ ...payload, state: "PENDING", record_revision_id: "revision:one", observation_refs: ["observation:one"], validation_state: "VALID" }],
  };
};
const report = (): InvestigationReport => ({ report: { revision: { report_id: "report:one", report_revision_id: "revision:report", review_dependency_digest: "d".repeat(64), supersedes_report_revision_id: null }, sections: [], claims: [], calculations: [], rendered_markdown: "Qualified" }, findings: [], available_evidence_refs: [], verification: { verification_id: "verification:one", report_revision_id: "revision:report", verdict: "QUALIFIED", checks: [], issues: [], verifier_version: "1", verified_dependency_digest: "d".repeat(64) } });
const packet = (): ReviewPacket => ({ packet_id: "packet:one", run_id: "run:one", report_revision_id: "revision:report", review_dependency_digest: "d".repeat(64), input_snapshot_refs: [{ snapshot_id: "snapshot:one", membership_digest: "a".repeat(64) }], proposed_action_refs: [], unresolved_issue_refs: [], permitted_decisions: ["APPROVE", "REQUEST_CHANGES", "REJECT", "ESCALATE"], created_at: "2026-10-30T00:00:00Z" });
const fill = (label: string | RegExp, value: string) => fireEvent.change(screen.getByLabelText(label), { target: { value } });

describe("support review", () => {
  it("refreshes the support snapshot without duplicate sibling keys or orphaned forms after navigation", async () => {
    const api = client();
    const logged = vi.spyOn(console, "error").mockImplementation(() => {});
    const initial = evidence();
    const next = { ...initial, snapshot: { snapshot_id: "snapshot:reviewed", membership_digest: "c".repeat(64) } };
    const snapshot = { ...initial.snapshot, snapshot_kind: "CASE" as const, review_state: "APPROVED" as const, created_at: "2026-10-30T00:00:00Z" };
    const dossier: Dossier = {
      dossier_id: "dossier:one", name: "Case one", status: "APPROVED",
      foundation: { case_snapshot: snapshot, corpus_snapshot: { ...snapshot, snapshot_id: "snapshot:corpus", snapshot_kind: "CORPUS" }, inventory_count: 1, extraction_count: 1, observation_count: 1, record_count: 1, normalization_quarantine_count: 0, issues: [] },
    };
    let reviewed = false;
    vi.spyOn(api, "dossier").mockResolvedValue(dossier);
    vi.spyOn(api, "evidence").mockImplementation(async () => reviewed ? next : initial);
    vi.spyOn(api, "supportReview").mockImplementation(async () => {
      reviewed = true;
      return { ...dossier, foundation: { ...dossier.foundation!, case_snapshot: { ...snapshot, ...next.snapshot } } };
    });
    const view = render(session(api, <Readiness dossierId="dossier:one" />));
    fireEvent.click(await screen.findByText(/Record support review/));
    await screen.findByText(/Binds to snapshot/);
    fill("Reason for each selected record", "Reviewed exact original");
    fireEvent.click(screen.getByRole("button", { name: "Select all matching current records for review" }));
    fill("Overall reason", "Support scope reviewed"); fill("Reviewer password", "secret");
    fireEvent.click(screen.getByLabelText(/I reviewed the 1 selected/));
    fireEvent.click(screen.getByRole("button", { name: "Submit support review" }));
    await screen.findByText(next.snapshot.membership_digest);
    expect(screen.getAllByText(/Record support review/)).toHaveLength(1);
    expect(screen.queryByText(initial.snapshot.membership_digest)).toBeNull();
    expect((screen.getByLabelText("Reviewer password") as HTMLInputElement).value).toBe("");
    view.rerender(session(api, <div>Agent setup destination</div>));
    expect(screen.queryByText(/Record support review/)).toBeNull();
    expect(view.container.querySelector("form")).toBeNull();
    expect(view.container.textContent).toBe("Agent setup destination");
    expect(logged.mock.calls.some((call) => call.map(String).join(" ").includes("same key"))).toBe(false);
  });

  it("invalidates draft support assertions after an unknown response and reloads evidence", async () => {
    const api = client();
    const load = vi.spyOn(api, "evidence").mockResolvedValue(evidence());
    const pending = deferred<Dossier>();
    vi.spyOn(api, "supportReview").mockReturnValue(pending.promise);
    const done = vi.fn();
    render(session(api, <SupportReview dossierId="dossier:one" onDone={done} />));
    fireEvent.click(screen.getByText(/Record support review/));
    await screen.findByText(/Binds to snapshot/);
    fill("Reason for each selected record", "Checked original allocation");
    fireEvent.click(screen.getByRole("button", { name: "Select all matching current records for review" }));
    fill("Overall reason", "Reviewed support only");
    fill("Reviewer password", "secret");
    fireEvent.click(screen.getByLabelText(/I reviewed the 1 selected/));
    fireEvent.click(screen.getByRole("button", { name: "Submit support review" }));
    await act(async () => pending.reject(new Error("Response lost; support may already be committed")));
    expect(screen.getByText("0 record assertion(s) selected for this exact snapshot.")).toBeTruthy();
    expect((screen.getByLabelText("Reviewer password") as HTMLInputElement).value).toBe("");
    expect(load).toHaveBeenCalledTimes(2);
    expect(done).not.toHaveBeenCalled();
    expect(screen.getByRole("alert").textContent).toContain("Response lost");
  });

  it("keeps bulk selection as explicit draft assertions, preserves exact refs and never generates reasons", async () => {
    const api = client();
    vi.spyOn(api, "evidence").mockResolvedValue(evidence());
    const submit = vi.spyOn(api, "supportReview").mockResolvedValue({ dossier_id: "dossier:one" } as Dossier);
    render(session(api, <SupportReview dossierId="dossier:one" onDone={() => {}} />));
    fireEvent.click(screen.getByText(/Record support review/));
    await screen.findByText(/Binds to snapshot/);
    const bulk = screen.getByRole("button", { name: "Select all matching current records for review" });
    expect((bulk as HTMLButtonElement).disabled).toBe(true);
    fill("Reason for each selected record", "I checked the exact original payload");
    fireEvent.click(bulk);
    fireEvent.click(bulk);
    expect(screen.getByText("1 record assertion(s) selected for this exact snapshot.")).toBeTruthy();
    expect((screen.getByLabelText("Overall reason") as HTMLInputElement).value).toBe("");
    expect(submit).not.toHaveBeenCalled();
    fill("Overall reason", "Reviewed structured support only");
    fill("Reviewer password", "secret");
    const button = screen.getByRole("button", { name: "Submit support review" });
    expect((button as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByLabelText(/I reviewed the 1 selected/));
    fireEvent.click(button);
    await waitFor(() => expect(submit).toHaveBeenCalledTimes(1));
    expect(submit.mock.calls[0][1]).toEqual({ password: "secret", snapshot_digest: "a".repeat(64), reason: "Reviewed structured support only", assertions: [{ target_record_revision_id: "revision:one", reason: "I checked the exact original payload", evidence_refs: [{ ref_kind: "OBSERVATION", ref_id: "observation:one", artifact_revision_id: "artifact_revision:one", locator }] }] });
    expect((screen.getByLabelText("Reviewer password") as HTMLInputElement).value).toBe("");
  });

  it.each(["payload", "missing_state", "missing_type"])("excludes superseded records and %s candidates from bulk drafts", async (invalid) => {
    const api = client(); const data = evidence();
    data.records.push({ ...data.records[0], record_revision_id: "revision:new", supersedes_revision_id: "revision:one" });
    if (invalid === "payload") data.observations[0].parsed_fields.quantity = { decimal: "999", unit: "KG" };
    if (invalid === "missing_state") delete data.observations[0].parsed_fields.state;
    if (invalid === "missing_type") delete data.observations[0].parsed_fields.record_type;
    vi.spyOn(api, "evidence").mockResolvedValue(data);
    render(session(api, <SupportReview dossierId="dossier:one" onDone={() => {}} />));
    fireEvent.click(screen.getByText(/Record support review/));
    await screen.findByText(/Binds to snapshot/);
    expect(screen.getAllByRole("option")).toHaveLength(2);
    fill("Reason for each selected record", "Investigated source");
    fireEvent.click(screen.getByRole("button", { name: "Select all matching current records for review" }));
    expect(screen.getByText("0 record assertion(s) selected for this exact snapshot.")).toBeTruthy();
  });
});

describe("version-bound human decision", () => {
  it.each(["digest", "run", "state"])("blocks a packet with stale %s", async (changed) => {
    const api = client(); const value = report(); const opened = packet();
    vi.spyOn(api, "packet").mockResolvedValue(opened);
    const submit = vi.spyOn(api, "review");
    const view = render(session(api, <ReviewForm runId="run:one" report={value} canRequest onDone={() => {}} />));
    fireEvent.click(screen.getByRole("button", { name: "Open review packet" }));
    await screen.findByText("Dependency digest");
    fireEvent.click(screen.getByLabelText("Approve"));
    if (changed === "digest") value.report.revision.review_dependency_digest = "x".repeat(64);
    view.rerender(session(api, <ReviewForm runId={changed === "run" ? "run:other" : "run:one"} report={value} canRequest={changed !== "state"} onDone={() => {}} />));
    expect(screen.getByText(/packet no longer matches/)).toBeTruthy();
    fill("Reason", "Reviewed"); fill("Reviewer password", "secret");
    fireEvent.submit(screen.getByRole("button", { name: "Submit decision" }).closest("form")!);
    expect(submit).not.toHaveBeenCalled();
  });

  it("submits exact packet and digest, clears credentials and invalidates packet after lost response", async () => {
    const api = client(); vi.spyOn(api, "packet").mockResolvedValue(packet());
    const pending = deferred<Awaited<ReturnType<ApiClient["review"]>>>();
    const submit = vi.spyOn(api, "review").mockReturnValue(pending.promise);
    const done = vi.fn();
    render(session(api, <ReviewForm runId="run:one" report={report()} canRequest onDone={done} />));
    fireEvent.click(screen.getByRole("button", { name: "Open review packet" }));
    await screen.findByText("Dependency digest");
    fireEvent.click(screen.getByLabelText("Request changes"));
    fill("Reason", "Evidence is incomplete"); fill("Reviewer password", "secret");
    fireEvent.click(screen.getByRole("button", { name: "Submit decision" }));
    expect(submit).toHaveBeenCalledWith("run:one", { password: "secret", packet_id: "packet:one", expected_dependency_digest: "d".repeat(64), decision: "REQUEST_CHANGES", reason: "Evidence is incomplete" });
    expect((screen.getByLabelText("Reviewer password") as HTMLInputElement).value).toBe("");
    await act(async () => pending.reject(new Error("Response lost; outcome unknown")));
    expect(screen.queryByRole("button", { name: "Submit decision" })).toBeNull();
    expect(screen.queryByText(/Recorded:/)).toBeNull();
    expect(done).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("alert").textContent).toContain("Response lost");
  });
});

describe("exact evidence display", () => {
  it("fails closed when a cited PDF page is outside the original instead of substituting a page", async () => {
    const api = client();
    const getPage = vi.fn();
    vi.doMock("pdfjs-dist", () => ({
      GlobalWorkerOptions: {},
      getDocument: () => ({ promise: Promise.resolve({ numPages: 3, getPage }), destroy: vi.fn() }),
    }));
    vi.doMock("pdfjs-dist/build/pdf.worker.min.mjs?url", () => ({ default: "mock-worker" }));
    vi.spyOn(api, "artifact").mockResolvedValue({ type: "application/pdf", arrayBuffer: async () => new ArrayBuffer(0) } as Blob);
    try {
      render(session(api, <ArtifactViewer dossierId="dossier:one" revisionId="artifact_revision:one" locator={{ ...locator, kind: "PDF_PAGE", page_index_1based: 150 }} onClose={() => {}} />));
      expect((await screen.findByRole("alert")).textContent).toContain("Requested page 150 is outside this 3-page original");
      expect(screen.getByRole("alert").textContent).toContain("no page has been substituted");
      expect(getPage).not.toHaveBeenCalled();
      expect((screen.getByRole("button", { name: "Previous" }) as HTMLButtonElement).disabled).toBe(true);
      expect((screen.getByRole("button", { name: "Next" }) as HTMLButtonElement).disabled).toBe(true);
    } finally {
      vi.doUnmock("pdfjs-dist");
      vi.doUnmock("pdfjs-dist/build/pdf.worker.min.mjs?url");
    }
  });

  it("refuses to substitute a current observation for a different cited locator", async () => {
    const api = client();
    vi.spyOn(api, "evidence").mockResolvedValue(evidence());
    const artifact = vi.spyOn(api, "artifact");
    render(session(api, <EvidenceChips dossierId="dossier:one" refs={[{ ref_kind: "OBSERVATION", ref_id: "observation:one", artifact_revision_id: null, locator: { ...locator, json_pointer: "/different" } }]} />));
    fireEvent.click(screen.getByRole("button"));
    expect((await screen.findByRole("alert")).textContent).toContain("different locator");
    expect(artifact).not.toHaveBeenCalled();
  });

  it("uses source character offsets rather than UTF-16 offsets for text spans", async () => {
    const api = client();
    vi.spyOn(api, "artifact").mockResolvedValue({ type: "text/plain", text: async () => "😀evidence" } as Blob);
    const { container } = render(session(api, <ArtifactViewer dossierId="dossier:one" revisionId="artifact_revision:one" locator={{ ...locator, kind: "TEXT_SPAN", text_start: 1, text_end: 9 }} onClose={() => {}} />));
    await waitFor(() => expect(container.querySelector("mark")?.textContent).toBe("evidence"));
  });

  it("ignores a previous dossier's late observation resolution", async () => {
    const api = client(); const pending = deferred<Evidence>();
    vi.spyOn(api, "evidence").mockReturnValue(pending.promise);
    const artifact = vi.spyOn(api, "artifact");
    const refs = [{ ref_kind: "OBSERVATION" as const, ref_id: "observation:one", artifact_revision_id: null, locator: null }];
    const view = render(session(api, <EvidenceChips dossierId="dossier:old" refs={refs} />));
    fireEvent.click(screen.getByRole("button"));
    view.rerender(session(api, <EvidenceChips dossierId="dossier:new" refs={refs} />));
    await act(async () => pending.resolve(evidence()));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(artifact).not.toHaveBeenCalled();
  });

  it("highlights a complete logical CSV row containing quoted newlines", async () => {
    const api = client();
    vi.spyOn(api, "artifact").mockResolvedValue({ type: "text/csv", text: async () => 'id,note\n1,"line one\nline two"\n2,last\n' } as Blob);
    const { container } = render(session(api, <ArtifactViewer dossierId="dossier:one" revisionId="artifact_revision:one" locator={{ ...locator, kind: "CSV_ROW", row_index_1based: 2 }} onClose={() => {}} />));
    await waitFor(() => expect(container.querySelector("mark")?.textContent).toBe("2,last\n"));
  });
});
