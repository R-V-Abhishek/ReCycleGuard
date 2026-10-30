import { useState } from "react";
import { ApiClient } from "../api/client";
import { ErrorBanner, PasswordField, TextField, useAction } from "../components/common";

const BASE_KEY = "recycleguard.apiBase";

// The API address is remembered because it isn't a secret. The token is never stored.
export function Connect({ onConnected }: { onConnected(client: ApiClient): void }) {
  const [base, setBase] = useState(() => localStorage.getItem(BASE_KEY) ?? "http://localhost:8000");
  const [token, setToken] = useState("");
  const { busy, error, run } = useAction();
  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    void run(async () => {
      const client = new ApiClient(base.trim(), token);
      await client.health();
      localStorage.setItem(BASE_KEY, base.trim());
      setToken("");
      onConnected(client);
    });
  };
  return (
    <main className="connect">
      <form className="card" onSubmit={submit}>
        <h1>ReCycleGuard</h1>
        <p className="muted">Connect to the local investigation API.</p>
        <TextField label="API address" value={base} onChange={setBase} />
        <PasswordField label="API token" value={token} onChange={setToken} />
        <ErrorBanner error={error} />
        <button className="primary" disabled={busy || !token || !base.trim()}>
          {busy ? "Connecting…" : "Connect"}
        </button>
        <p className="muted small">The token stays in this page's memory, so you'll re-enter it after a reload.</p>
      </form>
    </main>
  );
}
