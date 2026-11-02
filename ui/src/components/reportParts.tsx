import type { ReactNode } from "react";
import type { BucketResult, InvestigationReport, Issue, ReportClaim } from "../api/types";
import { Badge, Mono, Qty, Unavailable } from "./common";
import { EvidenceChips } from "./evidence";

// Claims grouped by section, each with its support status and clickable evidence.
// The status is the backend's; nothing here is derived or recomputed.
export function ClaimsBySection({ report, dossierId, onCalculation }: { report: InvestigationReport["report"]; dossierId?: string; onCalculation(id: string): void }) {
  const claims = new Map<string, ReportClaim>(report.claims.map((claim) => [claim.claim_id, claim]));
  if (!report.sections.length) return <p className="muted">This report has no sections.</p>;
  return (
    <>
      {report.sections.map((section) => (
        <article key={section.section_id} className="finding">
          <header className="row">
            <h3>{section.title}</h3>
            <Badge value={section.coverage_state} />
          </header>
          {section.claim_ids.length === 0 && <p className="muted small">No claims in this section.</p>}
          {section.claim_ids.map((id) => {
            const claim = claims.get(id);
            if (!claim) return <p key={id} className="banner warn">Claim <Mono>{id}</Mono> is listed in this section but missing from the report.</p>;
            return (
              <div key={id} className="claim">
                <p>
                  <Badge value={claim.support_status} /> <span className="muted small">{claim.kind.replace(/_/g, " ")}</span>
                </p>
                <p>{claim.template_or_text}</p>
                <EvidenceChips refs={claim.evidence_refs} dossierId={dossierId} onCalculation={onCalculation} />
              </div>
            );
          })}
          {section.evidence_refs.length > 0 && (
            <details>
              <summary>Section evidence ({section.evidence_refs.length})</summary>
              <EvidenceChips refs={section.evidence_refs} dossierId={dossierId} onCalculation={onCalculation} />
            </details>
          )}
        </article>
      ))}
    </>
  );
}

// The ledger side of the comparison and the records behind a bucket's numbers.
export function BucketDetails({ bucket, dossierId }: { bucket: BucketResult; dossierId?: string }) {
  return (
    <details>
      <summary><Mono>{bucket.bucket_id}</Mono> details</summary>
      <dl className="pairs">
        <dt>Ledger supported</dt><dd><Qty value={bucket.ledger_supported} /></dd>
        <dt>Snapshot comparison</dt><dd>{bucket.snapshot_comparison_ref ? <Mono>{bucket.snapshot_comparison_ref}</Mono> : <Unavailable label="no comparison" />}</dd>
        <dt>Allocations</dt>
        <dd>{bucket.allocation_ids.length ? bucket.allocation_ids.map((id) => <div key={id}><Mono>{id}</Mono></div>) : <Unavailable label="none" />}</dd>
        <dt>Qualifications</dt>
        <dd><EvidenceChips refs={bucket.qualification_refs} dossierId={dossierId} /></dd>
      </dl>
    </details>
  );
}

// Light, text-only rendering of the backend's markdown: headings, bullets and paragraphs.
// A trailing [ref, ref] is shown as references. No HTML is ever interpreted.
export function ReportText({ markdown }: { markdown: string }) {
  const blocks: ReactNode[] = [];
  let bullets: string[] = [];
  const flush = () => {
    if (!bullets.length) return;
    const items = bullets;
    bullets = [];
    blocks.push(<ul key={`l${blocks.length}`}>{items.map((item, i) => <li key={i}><BulletText text={item} /></li>)}</ul>);
  };
  markdown.split("\n").forEach((line) => {
    const heading = /^(#{1,3})\s+(.*)$/.exec(line);
    if (heading) {
      flush();
      const level = heading[1].length;
      const key = `h${blocks.length}`;
      blocks.push(level === 1 ? <h3 key={key}>{heading[2]}</h3> : <h4 key={key}>{heading[2]}</h4>);
    } else if (line.startsWith("- ")) bullets.push(line.slice(2));
    else if (line.trim()) {
      flush();
      blocks.push(<p key={`p${blocks.length}`}>{line}</p>);
    }
  });
  flush();
  if (!blocks.length) return <Unavailable label="no report text" />;
  return <div className="report-text">{blocks}</div>;
}

function BulletText({ text }: { text: string }) {
  const match = /^(.*?)\s*\[([^\]]*)\]$/.exec(text);
  if (!match) return <>{text}</>;
  return (
    <>
      {match[1]} {match[2] && <span className="muted small">[<Mono>{match[2]}</Mono>]</span>}
    </>
  );
}

// Unresolved issue ids from the review packet, with the message when the report carries it.
export function UnresolvedIssues({ ids, report }: { ids: string[]; report: InvestigationReport }) {
  if (!ids.length) return <Unavailable label="none" />;
  const known = new Map<string, Issue>();
  for (const issue of report.verification.issues) known.set(issue.issue_id, issue);
  for (const calculation of report.report.calculations) for (const issue of calculation.issues) known.set(issue.issue_id, issue);
  return (
    <ul className="issues">
      {ids.map((id) => {
        const issue = known.get(id);
        return issue ? (
          <li key={id}><Badge value={issue.severity} /> <Mono>{issue.code}</Mono> {issue.message}</li>
        ) : (
          <li key={id}><Mono>{id}</Mono> <span className="muted small">details are not in this report</span></li>
        );
      })}
    </ul>
  );
}

// Verifier checks as a table; every check's own keys are shown, booleans as the literal value.
export function ChecksTable({ checks }: { checks: Record<string, string | boolean>[] }) {
  if (!checks.length) return <Unavailable label="no checks recorded" />;
  const columns = [...new Set(checks.flatMap((check) => Object.keys(check)))];
  return (
    <table>
      <thead><tr>{columns.map((column) => <th key={column}>{column.replace(/_/g, " ")}</th>)}</tr></thead>
      <tbody>
        {checks.map((check, i) => (
          <tr key={i}>{columns.map((column) => <td key={column}>{column in check ? String(check[column]) : <Unavailable label="–" />}</td>)}</tr>
        ))}
      </tbody>
    </table>
  );
}
