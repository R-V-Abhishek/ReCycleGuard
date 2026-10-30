import { useEffect, useMemo, useState } from "react";
import type { Dossier, EvidenceRef, SupportAssertion } from "../api/types";
import { Badge, ErrorBanner, IssueList, JsonView, Mono, PasswordField, Section, Stat, TextField, Unavailable, useAction, useLoad } from "../components/common";
import { ArtifactViewer, describeLocator } from "../components/evidence";
import { useHeader } from "../components/Shell";
import { href, useClient } from "../state/session";

function ReviewerSetup() {
  const client = useClient();
  const [actor, setActor] = useState("");
  const [password, setPassword] = useState("");
  const [done, setDone] = useState(false);
  const { busy, error, run } = useAction();
  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    const secret = password;
    setPassword("");
    void run(async () => {
      await client.enroll(actor.trim(), secret);
      setDone(true);
    });
  };
  return (
    <details className="card">
      <summary>Reviewer setup</summary>
      <p className="muted small">
        Enroll the local reviewer once. The API can't report whether one is already enrolled, and it refuses to replace existing credentials, so an error here can simply mean setup is already done.
      </p>
      <form onSubmit={submit}>
        <TextField label="Actor ID" value={actor} onChange={setActor} placeholder="actor:reviewer" />
        <PasswordField value={password} onChange={setPassword} label="New reviewer password" />
        <ErrorBanner error={error} />
        {done && <div className="banner good">Reviewer enrolled.</div>}
        <button disabled={busy || !actor.trim() || !password}>Enroll reviewer</button>
      </form>
    </details>
  );
}

function FoundationReview({ dossier, onDone }: { dossier: Dossier; onDone(next: Dossier): void }) {
  const client = useClient();
  const [password, setPassword] = useState("");
  const [qualifications, setQualifications] = useState("");
  const { busy, error, run } = useAction();
  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    const secret = password;
    setPassword("");
    void run(async () => {
      onDone(
        await client.reviewFoundation(dossier.dossier_id, {
          password: secret,
          candidate_digest: dossier.candidate_digest ?? "",
          accepted_qualifications: qualifications,
        }),
      );
    });
  };
  return (
    <Section title="Foundation review" aside={<span className="muted small">Decision 1 of 3</span>}>
      <p className="muted small">
        Approves these prepared inputs so an investigation can start. It doesn't approve certificate or allocation support, or the final report.
      </p>
      <p className="small">Binds to candidate <Mono>{dossier.candidate_digest}</Mono></p>
      <form onSubmit={submit}>
        <TextField multiline label="Accepted qualifications" value={qualifications} onChange={setQualifications} placeholder="What you reviewed and which limitations you accept" />
        <PasswordField value={password} onChange={setPassword} />
        <ErrorBanner error={error} />
        <button className="primary" disabled={busy || !password || !qualifications.trim()}>Approve foundation</button>
      </form>
    </Section>
  );
}

function SupportReview({ dossierId, onDone }: { dossierId: string; onDone(next: Dossier): void }) {
  const client = useClient();
  const { data: evidence, error: loadError, reload } = useLoad(() => client.evidence(dossierId), [client, dossierId]);
  const [recordId, setRecordId] = useState("");
  const [picked, setPicked] = useState<string[]>([]);
  const [assertionReason, setAssertionReason] = useState("");
  const [assertions, setAssertions] = useState<SupportAssertion[]>([]);
  const [reason, setReason] = useState("");
  const [password, setPassword] = useState("");
  const { busy, error, run } = useAction();
  const record = evidence?.records.find((item) => item.record_revision_id === recordId);
  // Evidence references come only from observations the API returned for this record.
  const candidates = useMemo(
    () => (evidence && record ? evidence.observations.filter((o) => record.observation_refs.includes(o.observation_id)) : []),
    [evidence, record],
  );
  const add = () => {
    const refs: EvidenceRef[] = candidates
      .filter((o) => picked.includes(o.observation_id))
      .map((o) => ({
        ref_kind: "OBSERVATION",
        ref_id: o.observation_id,
        artifact_revision_id: o.artifact_revision_id,
        locator: o.locator,
      }));
    setAssertions([...assertions, { target_record_revision_id: recordId, evidence_refs: refs, reason: assertionReason }]);
    setRecordId("");
    setPicked([]);
    setAssertionReason("");
  };
  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    if (!evidence) return;
    const secret = password;
    setPassword("");
    void run(async () => {
      const next = await client.supportReview(dossierId, {
        password: secret,
        snapshot_digest: evidence.snapshot.membership_digest,
        assertions,
        reason,
      });
      setAssertions([]);
      setReason("");
      await reload();
      onDone(next);
    });
  };
  return (
    <details className="card">
      <summary>Record support review (optional · decision 2 of 3)</summary>
      <p className="muted small">
        Asserts that specific extracted observations support a record. The backend validates each assertion and publishes a new snapshot. Without this, foundation approval alone gives no certificate or allocation support.
      </p>
      <ErrorBanner error={loadError} />
      {evidence && (
        <form onSubmit={submit}>
          <p className="small">Binds to snapshot <Mono>{evidence.snapshot.membership_digest}</Mono></p>
          <label className="field">
            <span>Record</span>
            <select value={recordId} onChange={(e) => { setRecordId(e.target.value); setPicked([]); }}>
              <option value="">Choose a record…</option>
              {evidence.records.map((item) => (
                <option key={item.record_revision_id} value={item.record_revision_id}>
                  {item.record_id} · {item.validation_state}
                </option>
              ))}
            </select>
          </label>
          {record && (
            <>
              <fieldset>
                <legend>Observations for this record</legend>
                {candidates.length === 0 && <Unavailable label="None returned for this record." />}
                {candidates.map((o) => (
                  <label key={o.observation_id} className="check">
                    <input
                      type="checkbox"
                      checked={picked.includes(o.observation_id)}
                      onChange={(e) => setPicked(e.target.checked ? [...picked, o.observation_id] : picked.filter((id) => id !== o.observation_id))}
                    />
                    <Mono>{o.observation_id}</Mono> <span className="muted small">{describeLocator(o.locator)}</span>
                  </label>
                ))}
              </fieldset>
              <TextField label="Why this evidence supports the record" value={assertionReason} onChange={setAssertionReason} />
              <button type="button" disabled={!picked.length || !assertionReason.trim()} onClick={add}>Add assertion</button>
            </>
          )}
          {assertions.length > 0 && (
            <ul>
              {assertions.map((item, index) => (
                <li key={index}>
                  <Mono>{item.target_record_revision_id}</Mono>, {item.evidence_refs.length} observation(s)
                  <button type="button" className="link" onClick={() => setAssertions(assertions.filter((_, i) => i !== index))}>Remove</button>
                </li>
              ))}
            </ul>
          )}
          <TextField label="Overall reason" value={reason} onChange={setReason} />
          <PasswordField value={password} onChange={setPassword} />
          <ErrorBanner error={error} />
          <button className="primary" disabled={busy || !assertions.length || !reason.trim() || !password}>Submit support review</button>
        </form>
      )}
    </details>
  );
}

function EvidenceBrowser({ dossierId }: { dossierId: string }) {
  const client = useClient();
  const { data, error, loading } = useLoad(() => client.evidence(dossierId), [client, dossierId]);
  const [open, setOpen] = useState<{ id: string; name: string | null; locator?: import("../api/types").Locator } | null>(null);
  const [onlyFlagged, setOnlyFlagged] = useState(true);
  const flagged = data?.observations.filter((o) => o.validation_state !== "VALID") ?? [];
  const shown = onlyFlagged ? flagged : data?.observations ?? [];
  const nameOf = (id: string) => data?.originals.find((f) => f.artifact_revision_id === id)?.original_filename ?? null;
  return (
    <>
      <Section title="Original files">
        <ErrorBanner error={error} />
        {loading && <p>Loading…</p>}
        {data && (
          <table>
            <thead><tr><th>File</th><th>Source</th><th>Type</th><th>Media</th><th>Bytes</th><th /></tr></thead>
            <tbody>
              {data.originals.map((file) => (
                <tr key={file.artifact_revision_id}>
                  <td>{file.original_filename ?? <Unavailable />}</td>
                  <td>{file.source_kind}</td>
                  <td>{file.doc_type}</td>
                  <td>{file.blob.media_type}</td>
                  <td>{file.blob.byte_length}</td>
                  <td><button onClick={() => setOpen({ id: file.artifact_revision_id, name: file.original_filename })}>View</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Section>
      <Section
        title="Extracted observations"
        aside={
          <label className="check">
            <input type="checkbox" checked={onlyFlagged} onChange={(e) => setOnlyFlagged(e.target.checked)} /> Only needing review ({flagged.length})
          </label>
        }
      >
        {shown.length === 0 && <p className="muted">{onlyFlagged ? "No observations are flagged for review." : "No observations."}</p>}
        {shown.length > 0 && (
          <table>
            <thead><tr><th>Observation</th><th>Type</th><th>Where</th><th>State</th><th>Method</th></tr></thead>
            <tbody>
              {shown.map((o) => (
                <tr key={o.observation_id}>
                  <td><Mono>{o.observation_id}</Mono></td>
                  <td>{o.observation_type}</td>
                  <td>
                    <button className="link" onClick={() => setOpen({ id: o.artifact_revision_id, name: nameOf(o.artifact_revision_id), locator: o.locator })}>
                      {describeLocator(o.locator)}
                    </button>
                  </td>
                  <td><Badge value={o.validation_state} /></td>
                  <td>{o.extraction_method}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Section>
      {data && (
        <details className="card">
          <summary>Normalized records ({data.records.length})</summary>
          <JsonView value={data.records} />
        </details>
      )}
      {open && (
        <ArtifactViewer dossierId={dossierId} revisionId={open.id} name={open.name} locator={open.locator} onClose={() => setOpen(null)} />
      )}
    </>
  );
}

export function Readiness({ dossierId }: { dossierId: string }) {
  const client = useClient();
  const { data: dossier, error, loading, setData } = useLoad(() => client.dossier(dossierId), [client, dossierId]);
  const prepare = useAction();
  const { setHeader } = useHeader();
  useEffect(() => {
    setHeader({ dossierId, dossierName: dossier?.name });
  }, [dossierId, dossier?.name, setHeader]);

  const foundation = dossier?.foundation;
  return (
    <>
      <ErrorBanner error={error} />
      {loading && !dossier && <p>Loading…</p>}
      {dossier && (
        <>
          <Section title={dossier.name} aside={<Badge value={dossier.status} title="Approval status. This says nothing about evidence completeness." />}>
            <p className="small"><Mono>{dossier.dossier_id}</Mono></p>
            {dossier.status === "UPLOADED" && (
              <>
                <p>Files are registered. Prepare them to extract and normalize a draft for review.</p>
                <ErrorBanner error={prepare.error} />
                <button className="primary" disabled={prepare.busy} onClick={() => void prepare.run(async () => setData(await client.prepare(dossierId)))}>
                  {prepare.busy ? "Preparing…" : "Prepare draft inputs"}
                </button>
              </>
            )}
            {foundation && (
              <>
                <div className="stats">
                  <Stat label="Files" value={foundation.inventory_count} />
                  <Stat label="Extractions" value={foundation.extraction_count} />
                  <Stat label="Observations" value={foundation.observation_count} />
                  <Stat label="Records" value={foundation.record_count} />
                  <Stat label="Quarantined in normalization" value={foundation.normalization_quarantine_count} />
                </div>
                <h3>Preparation issues</h3>
                {foundation.issues.length ? <IssueList issues={foundation.issues} /> : <p className="muted">None reported. This doesn't mean the evidence is complete.</p>}
                <p className="muted small">Page-level coverage isn't exposed by the API, so missing or quarantined pages appear only through the issues and flagged observations here.</p>
              </>
            )}
          </Section>
          {dossier.status === "APPROVED" && (
            <div className="next">
              <span>Inputs are approved, so an investigation can start.</span>
              <a className="button primary" href={href("dossiers", dossierId, "start")}>Set up investigation</a>
            </div>
          )}
          {dossier.status !== "UPLOADED" && <ReviewerSetup />}
          {dossier.status === "DRAFT" && <FoundationReview dossier={dossier} onDone={setData} />}
          {dossier.status === "APPROVED" && <SupportReview dossierId={dossierId} onDone={setData} />}
          {dossier.status !== "UPLOADED" && <EvidenceBrowser key={foundation?.case_snapshot.membership_digest} dossierId={dossierId} />}
        </>
      )}
    </>
  );
}
