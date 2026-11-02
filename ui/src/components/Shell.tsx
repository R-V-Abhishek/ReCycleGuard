import { createContext, useContext, useMemo, useState, type ReactNode } from "react";
import { href, useClient } from "../state/session";
import { Badge, Mono, Unavailable, useLoad } from "./common";

export interface HeaderInfo {
  dossierId?: string;
  dossierName?: string;
  runId?: string;
  mode?: string;
  connection?: string;
}

const HeaderContext = createContext<{ setHeader(info: HeaderInfo): void }>({ setHeader: () => {} });
export const useHeader = () => useContext(HeaderContext);

export function Shell({ route, onDisconnect, children }: { route: string[]; onDisconnect(): void; children: ReactNode }) {
  const [info, setHeader] = useState<HeaderInfo>({});
  const context = useMemo(() => ({ setHeader }), []);
  const onHome = route.length === 0 || route[0] === "dossiers" && route.length === 1;
  const shown: HeaderInfo = onHome ? {} : info;
  const client = useClient();
  const { data: catalogue } = useLoad(() => client.catalogue(), [client, shown.dossierName]);
  // Only fixture dossiers have a known year: the API returns it in the fixture list alone.
  const fiscalYear = catalogue?.fixtures.find((f) => f.fixture_id === shown.dossierName)?.fiscal_year;
  const steps: { label: string; to?: string; active: boolean }[] = [
    { label: "Dossiers", to: href("dossiers"), active: onHome },
    { label: "Readiness", to: shown.dossierId && href("dossiers", shown.dossierId), active: route[0] === "dossiers" && route.length === 2 },
    { label: "Agent setup", to: shown.dossierId && href("dossiers", shown.dossierId, "start"), active: route[2] === "start" },
    { label: "Investigation", to: shown.runId && href("runs", shown.runId), active: route[0] === "runs" && route.length === 2 },
    { label: "Report and review", to: shown.runId && href("runs", shown.runId, "report"), active: route[2] === "report" },
  ];
  return (
    <HeaderContext.Provider value={context}>
      <header className="app-head">
        <div className="brand">ReCycleGuard</div>
        <dl className="identity">
          <div><dt>Dossier</dt><dd>{shown.dossierName ?? <Unavailable label="none" />}</dd></div>
          <div><dt>Fiscal year</dt><dd>{fiscalYear ?? <Unavailable />}</dd></div>
          <div><dt>Run</dt><dd>{shown.runId ? <Mono>{shown.runId}</Mono> : <Unavailable label="none" />}</dd></div>
          <div><dt>Mode</dt><dd>{shown.mode ? <Badge value={shown.mode} /> : <Unavailable label="not shown" />}</dd></div>
          {shown.connection && <div><dt>Stream</dt><dd><Badge value={shown.connection} /></dd></div>}
        </dl>
        <button className="link" onClick={onDisconnect}>Disconnect</button>
      </header>
      <nav className="steps" aria-label="Workflow">
        {steps.map((step) =>
          step.to ? (
            <a key={step.label} href={step.to} className={step.active ? "on" : ""}>{step.label}</a>
          ) : (
            <span key={step.label} className="off">{step.label}</span>
          ),
        )}
      </nav>
      <main className="content">{children}</main>
    </HeaderContext.Provider>
  );
}
