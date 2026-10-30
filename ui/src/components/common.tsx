import { useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { ApiError } from "../api/client";
import type { Issue, Quantity } from "../api/types";
import { SessionContext } from "../state/session";

export function useLoad<T>(load: () => Promise<T>, deps: unknown[]) {
  const [data, setData] = useState<T | undefined>();
  const [error, setError] = useState<unknown>();
  const [loading, setLoading] = useState(true);
  const latest = useRef(0);
  const reload = useCallback(async () => {
    const ticket = ++latest.current;
    setLoading(true);
    try {
      const value = await load();
      if (ticket === latest.current) {
        setData(value);
        setError(undefined);
      }
    } catch (cause) {
      if (ticket === latest.current) setError(cause);
    } finally {
      if (ticket === latest.current) setLoading(false);
    }
  }, deps);
  useEffect(() => {
    void reload();
  }, [reload]);
  return { data, error, loading, reload, setData };
}

// Runs one mutation at a time and never retries it.
export function useAction() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const run = async <T,>(action: () => Promise<T>): Promise<T | undefined> => {
    if (busy) return undefined;
    setBusy(true);
    setError(undefined);
    try {
      return await action();
    } catch (cause) {
      setError(cause);
      return undefined;
    } finally {
      setBusy(false);
    }
  };
  return { busy, error, run, clearError: () => setError(undefined) };
}

export function ErrorBanner({ error }: { error: unknown }) {
  const session = useContext(SessionContext);
  if (!error) return null;
  const api = error instanceof ApiError ? error : null;
  const unknown = api?.kind === "UNKNOWN_OUTCOME";
  return (
    <div className={unknown ? "banner warn" : "banner error"} role="alert">
      <strong>
        {unknown ? "Unknown outcome" : api?.status ? `Error ${api.status}` : "Error"}
        {api?.code ? ` · ${api.code}` : ""}
      </strong>
      <div className="prewrap">{error instanceof Error ? error.message : String(error)}</div>
      {api?.status === 401 && session && (
        <button className="link" onClick={session.disconnect}>
          Re-enter the API token
        </button>
      )}
    </div>
  );
}

export const Unavailable = ({ label = "unavailable" }: { label?: string }) => (
  <span className="muted">{label}</span>
);

const TONES: Record<string, string> = {
  APPROVED: "good",
  COMPLETED: "good",
  PASS: "good",
  SUPPORTED: "good",
  SUPPORTS: "good",
  SUCCESS: "good",
  VALID: "good",
  VERIFIED_INTEGRITY: "good",
  RECONCILED_WITHIN_SCOPE: "good",
  COMPLETE_WITHIN_SCOPE: "good",
  live: "good",
  MODEL_BACKED: "accent",
  RUNNING: "accent",
  INVESTIGATING: "accent",
  DRAFTING: "accent",
  VERIFYING: "accent",
  PREFLIGHT: "accent",
  QUEUED: "accent",
  AWAITING_REVIEW: "warn",
  QUALIFIED: "warn",
  PARTIAL: "warn",
  WEAK: "warn",
  DRAFT: "warn",
  PENDING: "warn",
  PENDING_VERIFICATION: "warn",
  REQUIRES_EXPERT_REVIEW: "warn",
  REVIEW_REQUIRED: "warn",
  INTERRUPTED: "warn",
  SCRIPTED_TEST: "warn",
  UNVERIFIED_METADATA: "warn",
  OUTCOME_UNKNOWN: "warn",
  ESCALATED: "warn",
  CHANGES_REQUESTED: "warn",
  reconnecting: "warn",
  WARNING: "warn",
  FAILED: "bad",
  BLOCKED: "bad",
  BLOCKED_INPUT: "bad",
  BLOCKED_OUTPUT: "bad",
  REJECTED: "bad",
  REFUTES: "bad",
  INVALID: "bad",
  UNSUPPORTED: "bad",
  CANCELLED: "bad",
  DISCREPANCY_DETECTED: "bad",
  BLOCKING: "bad",
  failed: "bad",
};

export function Badge({ value, title }: { value: string; title?: string }) {
  return (
    <span className={`badge ${TONES[value] ?? ""}`} title={title}>
      {value.replace(/_/g, " ")}
    </span>
  );
}

export const Mono = ({ children }: { children: ReactNode }) => (
  <code className="mono">{children}</code>
);

// Exact backend decimal string and unit. Missing is never rendered as zero.
export function Qty({ value, missing = "not reported" }: { value: Quantity | null | undefined; missing?: string }) {
  if (!value) return <Unavailable label={missing} />;
  return (
    <span className="qty">
      {value.decimal} <span className="muted">{value.unit}</span>
    </span>
  );
}

export function JsonView({ value }: { value: unknown }) {
  if (value === undefined) return <Unavailable />;
  return <pre className="block">{JSON.stringify(value, null, 2)}</pre>;
}

export function IssueList({ issues }: { issues: Issue[] }) {
  if (!issues.length) return null;
  return (
    <ul className="issues">
      {issues.map((issue) => (
        <li key={issue.issue_id}>
          <Badge value={issue.severity} /> <Mono>{issue.code}</Mono> <span>{issue.message}</span>
        </li>
      ))}
    </ul>
  );
}

// Holds the password only in this input's state. Forms clear it after every submission.
export function PasswordField({
  value,
  onChange,
  label = "Reviewer password",
}: {
  value: string;
  onChange(value: string): void;
  label?: string;
}) {
  return (
    <label className="field">
      <span>{label}</span>
      <input
        type="password"
        autoComplete="off"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  );
}

export function TextField({
  label,
  value,
  onChange,
  multiline,
  placeholder,
}: {
  label: string;
  value: string;
  onChange(value: string): void;
  multiline?: boolean;
  placeholder?: string;
}) {
  return (
    <label className="field">
      <span>{label}</span>
      {multiline ? (
        <textarea
          rows={3}
          value={value}
          placeholder={placeholder}
          onChange={(event) => onChange(event.target.value)}
        />
      ) : (
        <input value={value} placeholder={placeholder} onChange={(event) => onChange(event.target.value)} />
      )}
    </label>
  );
}

export const Section = ({
  title,
  aside,
  children,
}: {
  title: ReactNode;
  aside?: ReactNode;
  children: ReactNode;
}) => (
  <section className="card">
    <header className="card-head">
      <h2>{title}</h2>
      {aside}
    </header>
    {children}
  </section>
);

export function Stat({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="stat">
      <div className="stat-value">{value}</div>
      <div className="stat-label">{label}</div>
    </div>
  );
}
