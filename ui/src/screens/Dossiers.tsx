import { useState } from "react";
import { Badge, ErrorBanner, Mono, Section, TextField, Unavailable, useAction, useLoad } from "../components/common";
import { navigate, useClient } from "../state/session";

const MAX_UPLOAD = 25 * 1024 * 1024;

export function Dossiers() {
  const client = useClient();
  const { data, error, loading } = useLoad(() => client.catalogue(), [client]);
  const action = useAction();
  const [zip, setZip] = useState<File | null>(null);
  const [runId, setRunId] = useState("");
  const tooLarge = zip !== null && zip.size > MAX_UPLOAD;

  const select = (fixtureId: string) =>
    action.run(async () => navigate("dossiers", (await client.select(fixtureId)).dossier_id));
  const upload = () =>
    zip && action.run(async () => navigate("dossiers", (await client.upload(zip)).dossier_id));

  return (
    <>
      <ErrorBanner error={error} />
      <ErrorBanner error={action.error} />
      <Section title="Development dossiers" aside={<span className="muted small">Synthetic fixtures. Held-out cases aren't served.</span>}>
        {loading && <p>Loading…</p>}
        {data && data.fixtures.length === 0 && <p className="muted">The API returned no fixtures.</p>}
        {data && data.fixtures.length > 0 && (
          <div className="fixture-grid">
            {data.fixtures.map((fixture) => (
              <button key={fixture.fixture_id} className="fixture" disabled={action.busy} onClick={() => void select(fixture.fixture_id)}>
                <strong>{fixture.fixture_id}</strong>
                <span className="muted small">FY {fixture.fiscal_year}</span>
              </button>
            ))}
          </div>
        )}
      </Section>

      <Section title="Registered dossiers">
        {data?.dossiers.length ? (
          <table>
            <thead>
              <tr><th>Name</th><th>ID</th><th>Status</th></tr>
            </thead>
            <tbody>
              {data.dossiers.map((dossier) => (
                <tr key={dossier.dossier_id} className="clickable" onClick={() => navigate("dossiers", dossier.dossier_id)}>
                  <td>{dossier.name}</td>
                  <td><Mono>{dossier.dossier_id}</Mono></td>
                  <td><Badge value={dossier.status} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <Unavailable label="None yet. Choose a fixture above or upload a dossier." />
        )}
      </Section>

      <div className="two">
        <Section title="Upload a dossier package">
          <p className="muted small">
            A ZIP with exactly one <Mono>case_manifest.json</Mono> and its supported CSV, JSON, JSONL and PDF files. This isn't arbitrary PDF conversion.
            Limits: 25 MiB uploaded, 100 MiB expanded, 500 entries.
          </p>
          <input type="file" accept=".zip,application/zip" onChange={(event) => setZip(event.target.files?.[0] ?? null)} />
          {tooLarge && <div className="banner error">This file is over the 25 MiB upload limit.</div>}
          <div className="row">
            <button className="primary" disabled={!zip || tooLarge || action.busy} onClick={() => void upload()}>
              {action.busy ? "Working…" : "Upload"}
            </button>
          </div>
          <p className="muted small">A successful upload only means the bytes were accepted. Preparation and review come next.</p>
        </Section>
        <Section title="Open an existing run">
          <p className="muted small">The API can't list runs, so open one by its ID.</p>
          <TextField label="Run ID" value={runId} onChange={setRunId} placeholder="run:…" />
          <button disabled={!runId.trim()} onClick={() => navigate("runs", runId.trim())}>Open run</button>
        </Section>
      </div>
    </>
  );
}
