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
    const address = base.trim();
    const secret = token;
    setToken("");
    void run(async (signal) => {
      const client = new ApiClient(address, secret);
      await client.health();
      if (signal.aborted) return;
      localStorage.setItem(BASE_KEY, address);
      onConnected(client);
    });
  };
  return (
    <main className="connect">
      <section className="connect-intro" aria-labelledby="connect-title">
        <div className="brand"><span className="brand-mark" aria-hidden="true"><i /><i /><i /></span>ReCycleGuard</div>
        <h1 id="connect-title" className="roles">
          <span className="role-model">The model proposes.</span>
          <span className="role-engine">The engine checks.</span>
          <span className="role-person">A person decides.</span>
        </h1>
        <p>
          An audited assistant for e-waste EPR reconciliation under the E-Waste (Management) Rules, 2022.
          For one producer and period, it shows which obligation balances verified evidence supports,
          what needs follow-up, and what a reviewer must confirm.
        </p>
        <p className="muted small">Advisory working papers only: no filing, credit trading or compliance verdict.</p>
      </section>
      <form className="card connect-form" onSubmit={submit}>
        <h2>Connect to the local investigation API</h2>
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
