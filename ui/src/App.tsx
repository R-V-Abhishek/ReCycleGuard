import { useMemo, useState } from "react";
import type { ApiClient } from "./api/client";
import { Shell } from "./components/Shell";
import { Connect } from "./screens/Connect";
import { Dossiers } from "./screens/Dossiers";
import { Investigation } from "./screens/Investigation";
import { Readiness } from "./screens/Readiness";
import { Report } from "./screens/Report";
import { StartRun } from "./screens/StartRun";
import { SessionContext, useRoute } from "./state/session";

function Screen({ route }: { route: string[] }) {
  const [root, id, sub] = route;
  if (root === "dossiers" && id && sub === "start") return <StartRun key={id} dossierId={id} />;
  if (root === "dossiers" && id) return <Readiness key={id} dossierId={id} />;
  if (root === "runs" && id && sub === "report") return <Report key={id} runId={id} />;
  if (root === "runs" && id) return <Investigation key={id} runId={id} />;
  return <Dossiers />;
}

export function App() {
  const [client, setClient] = useState<ApiClient | null>(null);
  const [sessionId, setSessionId] = useState(0);
  const route = useRoute();
  const session = useMemo(
    () => (client ? { client, disconnect: () => setClient(null) } : null),
    [client],
  );
  // The route stays in the URL hash, so reconnecting returns to the same dossier or run.
  if (!session) return <Connect onConnected={(next) => { setSessionId((old) => old + 1); setClient(next); }} />;
  return (
    <SessionContext.Provider key={sessionId} value={session}>
      <Shell route={route} onDisconnect={session.disconnect}>
        <Screen route={route} />
      </Shell>
    </SessionContext.Provider>
  );
}
