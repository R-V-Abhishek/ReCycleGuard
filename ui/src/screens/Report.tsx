import { useEffect, useState } from "react";
import type { BucketResult, InvestigationReport, ReviewDecisionKind, ReviewPacket } from "../api/types";
import { Badge, ErrorBanner, IssueList, Mono, PasswordField, Qty, Section, TextField, Unavailable, useAction, useLoad } from "../components/common";
import { EvidenceChips } from "../components/evidence";
import { useHeader } from "../components/Shell";
import { href, useClient } from "../state/session";

// One row per bucket. Metals are never summed, and each column stays its own number.
export function BucketTable({ buckets }: { buckets: BucketResult[] }) {
  return (
    <table>
      <thead>
        <tr>
          <th>Bucket</th><th>Metal</th><th>Target</th><th>Supported</th><th>Pending (not credited)</th><th>Portal reported</th><th>Gap</th><th>Shortfall</th><th>Surplus</th><th>Portal delta</th>
        </tr>
      </thead>
      <tbody>
        {buckets.map((bucket) => (
          <tr key={bucket.bucket_id}>
            <td><Mono>{bucket.bucket_id}</Mono></td>
            <td>{bucket.required.metal ?? <Unavailable />}</td>
            <td><Qty value={bucket.required} /></td>
            <td><Qty value={bucket.supported} /></td>
            <td><Qty value={bucket.pending} /></td>
            <td><Qty value={bucket.portal_reported} /></td>
            <td><Qty value={bucket.signed_gap} /></td>
            <td><Qty value={bucket.shortfall} /></td>
            <td><Qty value={bucket.surplus} /></td>
            <td><Qty value={bucket.delta} missing="no comparison" /></td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Findings({ report, dossierId, onCalculation }: { report: InvestigationReport; dossierId?: string; onCalculation(id: string): void }) {
  if (!report.findings.length) return <p className="muted">No findings were recorded in this report.</p>;
  return (
    <>
      {report.findings.map((finding) => (
        <article key={finding.finding_revision_id} className="finding">
          <header className="row">
            <Badge value={finding.advisory_status} />
            <Badge value={finding.priority} title={finding.priority_basis} />
            <Mono>{finding.issue_type}</Mono>
            <span className="muted small">{finding.bucket_ids.join(", ")}</span>
          </header>
          {finding.abstention_reason && (
            <div className="banner warn">
              <strong>Abstained: {finding.abstention_reason.replace(/_/g, " ")}</strong>
              <div>Withheld: {finding.withheld_claim_scopes.join("; ")}</div>
            </div>
          )}
          {finding.hypotheses.length > 0 && (
            <>
              <h4>Hypotheses</h4>
              <ul>{finding.hypotheses.map((h, i) => <li key={i}><Badge value={h.support_state} /> {h.text}</li>)}</ul>
            </>
          )}
          <h4>Facts</h4>
          <EvidenceChips refs={finding.fact_refs} dossierId={dossierId} onCalculation={onCalculation} />
          <h4>Provisions</h4>
          <EvidenceChips refs={finding.provision_refs} dossierId={dossierId} />
          {finding.calculation_refs.length > 0 && (
            <>
              <h4>Calculations</h4>
              <div className="chips">
                {finding.calculation_refs.map((id) => (
                  <button key={id} className="chip" onClick={() => onCalculation(id)}><Mono>{id}</Mono></button>
                ))}
              </div>
            </>
          )}
          <h4>Next action</h4>
          <p>
            <Badge value={finding.next_action.kind} /> {finding.next_action.description}{" "}
            <span className="muted small">Owner: {finding.action_owner_ref ?? "not recorded"}</span>
          </p>
          {finding.scope_limits.length > 0 && (
            <>
              <h4>Scope limits</h4>
              <ul>{finding.scope_limits.map((item, i) => <li key={i}>{item}</li>)}</ul>
            </>
          )}
        </article>
      ))}
    </>
  );
}

const DECISION_LABEL: Record<ReviewDecisionKind, string> = {
  APPROVE: "Approve",
  REJECT: "Reject",
  REQUEST_CHANGES: "Request changes",
  ESCALATE: "Escalate",
};

export function ReviewForm({ runId, report, canRequest, onDone }: { runId: string; report: InvestigationReport; canRequest: boolean; onDone(): void }) {
  const client = useClient();
  const [packet, setPacket] = useState<ReviewPacket>();
  const [decision, setDecision] = useState<ReviewDecisionKind>();
  const [reason, setReason] = useState("");
  const [password, setPassword] = useState("");
  const [lastDecision, setLastDecision] = useState<string>();
  const action = useAction();
  const revision = report.report.revision.report_revision_id;
  const stale = packet !== undefined && (
    !canRequest || packet.run_id !== runId || packet.report_revision_id !== revision ||
    packet.review_dependency_digest !== report.report.revision.review_dependency_digest
  );
  useEffect(() => { if (stale) setPassword(""); }, [stale]);

  const requestPacket = () => void action.run(async (signal) => {
    const next = await client.packet(runId);
    if (signal.aborted) return;
    setPacket(next);
    setDecision(undefined);
    setLastDecision(undefined);
  });
  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    if (action.busy || !packet || stale || !decision || !packet.permitted_decisions.includes(decision) || !reason.trim() || !password) return;
    const secret = password;
    setPassword("");
    void action.run(async (signal) => {
      try {
        await client.review(runId, {
          password: secret,
          packet_id: packet.packet_id,
          expected_dependency_digest: packet.review_dependency_digest,
          decision,
          reason,
        });
        if (signal.aborted) return;
        setLastDecision(DECISION_LABEL[decision]);
        setReason("");
      } finally {
        // Success, a stale version or a lost response all need a fresh packet from current state.
        if (!signal.aborted) {
          setPacket(undefined);
          setDecision(undefined);
          onDone();
        }
      }
    });
  };

  return (
    <Section title="Human review" aside={<span className="muted small">Decision 3 of 3</span>}>
      <ErrorBanner error={action.error} />
      {lastDecision && <div className="banner good">Recorded: {lastDecision}. See the review outcome above.</div>}
      {!packet && (
        <>
          {canRequest ? (
            <button className="primary" disabled={action.busy} onClick={requestPacket}>Open review packet</button>
          ) : (
            <p className="muted">Review opens when the run is awaiting review.</p>
          )}
        </>
      )}
      {packet && (
        <form onSubmit={submit}>
          {stale && <div className="banner warn">This packet no longer matches the current run, report, dependencies or review state. Reload before reviewing.</div>}
          <dl className="pairs">
            <dt>Report revision</dt><dd><Mono>{packet.report_revision_id}</Mono></dd>
            <dt>Dependency digest</dt><dd><Mono>{packet.review_dependency_digest}</Mono></dd>
            <dt>Input snapshots</dt>
            <dd>{packet.input_snapshot_refs.map((ref) => <div key={ref.snapshot_id}><Mono>{ref.snapshot_id}</Mono> · <Mono>{ref.membership_digest}</Mono></div>)}</dd>
            <dt>Unresolved issues</dt><dd>{packet.unresolved_issue_refs.length}</dd>
          </dl>
          <fieldset disabled={action.busy || stale}>
            <legend>Decision for this exact revision</legend>
            {packet.permitted_decisions.map((kind) => (
              <label className="check" key={kind}>
                <input type="radio" checked={decision === kind} onChange={() => setDecision(kind)} /> {DECISION_LABEL[kind]}
              </label>
            ))}
          </fieldset>
          <TextField multiline label="Reason" value={reason} onChange={setReason} />
          <PasswordField value={password} onChange={setPassword} />
          <button className="primary" disabled={action.busy || stale || !decision || !reason.trim() || !password}>Submit decision</button>
        </form>
      )}
    </Section>
  );
}

export function Report({ runId }: { runId: string }) {
  const client = useClient();
  const run = useLoad(() => client.run(runId), [client, runId]);
  const report = useLoad(() => client.report(runId), [client, runId]);
  const audit = useLoad(() => client.audit(runId), [client, runId]);
  const dossierId = run.data?.job.dossier_id;
  const dossier = useLoad(async () => (dossierId ? client.dossier(dossierId) : undefined), [client, dossierId]);
  const { setHeader } = useHeader();
  const mode = audit.data?.runtime_metadata.execution_kind;
  useEffect(() => {
    setHeader({ dossierId, dossierName: dossier.data?.name, runId, mode });
  }, [dossierId, dossier.data?.name, runId, mode, setHeader]);

  const scrollToCalculation = (id: string) => document.getElementById(`calc-${id}`)?.scrollIntoView({ behavior: "smooth" });
  const state = run.data?.state;
  const body = report.data;
  const refresh = () => {
    void run.reload();
    void report.reload();
    void audit.reload();
  };

  return (
    <>
      <ErrorBanner error={run.error} />
      {state && (
        <section className="card run-bar">
          <div className="run-badges">
            <span className="muted small">Workflow</span> <Badge value={state.status} />
            <span className="muted small">Verifier</span> {body ? <Badge value={body.verification.verdict} /> : <Unavailable />}
            <span className="muted small">Integrity audit</span> {audit.data ? <Badge value={audit.data.verification_status} /> : <Unavailable />}
            <span className="muted small">Human review</span> <Badge value={state.review_outcome} />
            {state.stop_reason && (<><span className="muted small">Stop reason</span> <Badge value={state.stop_reason} /></>)}
          </div>
          <a className="button" href={href("runs", runId)}>Back to investigation</a>
        </section>
      )}
      <p className="muted small">
        Advisory results{dossier.data?.synthetic === true ? " for a synthetic dossier" : ""}. This doesn't file returns, trade certificates, certify legal compliance or calculate compensation.
      </p>
      {report.error ? <ErrorBanner error={report.error} /> : null}
      {report.loading && !body && <p>Loading…</p>}
      {body && (
        <>
          <Section title="Balances" aside={<span className="small">Revision <Mono>{body.report.revision.report_revision_id}</Mono></span>}>
            {body.report.calculations.length === 0 && <p className="muted">No calculations in this report.</p>}
            {body.report.calculations.map((calculation) => (
              <div key={calculation.calculation_id} id={`calc-${calculation.calculation_id}`}>
                <p className="small"><Badge value={calculation.coverage} /> <Mono>{calculation.calculation_id}</Mono></p>
                <BucketTable buckets={calculation.bucket_results} />
                <IssueList issues={calculation.issues} />
              </div>
            ))}
          </Section>
          <Section title="Findings"><Findings report={body} dossierId={dossierId} onCalculation={scrollToCalculation} /></Section>
          <Section title="Verifier" aside={<Badge value={body.verification.verdict} />}>
            <p className="muted small">Checks this report's claims and dependencies. This isn't the integrity audit or a human decision.</p>
            <IssueList issues={body.verification.issues} />
            <details>
              <summary>Checks ({body.verification.checks.length})</summary>
              <pre className="block">{JSON.stringify(body.verification.checks, null, 2)}</pre>
            </details>
          </Section>
          <details className="card">
            <summary>Report text</summary>
            <pre className="block">{body.report.rendered_markdown}</pre>
          </details>
          <ReviewForm key={`${runId}:${body.report.revision.report_revision_id}:${body.report.revision.review_dependency_digest}`} runId={runId} report={body} canRequest={state?.status === "AWAITING_REVIEW"} onDone={refresh} />
        </>
      )}
      <Section title="Integrity audit" aside={audit.data && <Badge value={audit.data.verification_status} />}>
        <p className="muted small">Verifies frozen bytes, pins, index publication and ledger chains. It doesn't establish legal correctness or model quality.</p>
        <ErrorBanner error={audit.error} />
        {audit.data && (
          <>
            <h4>Verified checks</h4>
            {audit.data.verified_checks.length ? <ul>{audit.data.verified_checks.map((c) => <li key={c}>{c}</li>)}</ul> : <Unavailable label="none" />}
            <h4>Limitations</h4>
            {audit.data.limitations.length ? (
              <ul>{audit.data.limitations.map((l) => <li key={l.limitation_id}><Mono>{l.kind}</Mono> {l.description}</li>)}</ul>
            ) : (
              <Unavailable label="none recorded" />
            )}
          </>
        )}
      </Section>
    </>
  );
}
