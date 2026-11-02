import type {
  AgentConfig,
  AuditManifest,
  BudgetLimits,
  Catalogue,
  Dossier,
  Evidence,
  Health,
  InvestigationReport,
  ReviewDecisionKind,
  ReviewPacket,
  RunMode,
  RunState,
  RunView,
  SupportAssertion,
  TracePage,
} from "./types";

export const API_PREFIX = "/api/v1";

// Every backend route the UI binds to. tests/routes.test.ts compares this with openapi.json.
export const ROUTES = {
  health: ["GET", "/health"],
  agent: ["GET", "/agent"],
  enroll: ["POST", "/reviewer"],
  dossiers: ["GET", "/dossiers"],
  upload: ["POST", "/dossiers"],
  select: ["POST", "/dossiers/select"],
  dossier: ["GET", "/dossiers/{dossier_id}"],
  prepare: ["POST", "/dossiers/{dossier_id}/prepare"],
  reviewFoundation: ["POST", "/dossiers/{dossier_id}/review-foundation"],
  evidence: ["GET", "/dossiers/{dossier_id}/evidence"],
  artifact: ["GET", "/dossiers/{dossier_id}/artifacts/{artifact_revision_id}"],
  supportReview: ["POST", "/dossiers/{dossier_id}/support-review"],
  runs: ["GET", "/runs"],
  startRun: ["POST", "/runs"],
  run: ["GET", "/runs/{run_id}"],
  resume: ["POST", "/runs/{run_id}/resume"],
  cancel: ["POST", "/runs/{run_id}/cancel"],
  trace: ["GET", "/runs/{run_id}/trace"],
  events: ["GET", "/runs/{run_id}/events"],
  audit: ["GET", "/runs/{run_id}/audit"],
  report: ["GET", "/runs/{run_id}/report"],
  packet: ["POST", "/runs/{run_id}/packet"],
  review: ["POST", "/runs/{run_id}/review"],
} as const;

export type ErrorKind = "HTTP" | "NETWORK" | "UNKNOWN_OUTCOME" | "PROTOCOL";

export class ApiError extends Error {
  constructor(
    readonly kind: ErrorKind,
    readonly status: number | null,
    readonly code: string | null,
    message: string,
    readonly fieldErrors: { loc: string; msg: string }[] = [],
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function text(value: unknown): string {
  return typeof value === "string" ? value : (JSON.stringify(value) ?? "Unknown error");
}

function interrupted(route: Route, status: number | null = null): ApiError {
  return route[0] === "POST"
    ? new ApiError("UNKNOWN_OUTCOME", status, null,
        "The request may already have been applied, but its outcome could not be confirmed. Check the current state before trying again.")
    : new ApiError("NETWORK", status, null, "The connection ended before the response was received.");
}

// The API has three error envelopes: `detail` (string or object), `code` + `errors`,
// and `code` + `message`. Anything else is kept verbatim so diagnostics are not lost.
export function normalizeError(status: number, body: unknown): ApiError {
  if (body && typeof body === "object") {
    const value = body as Record<string, unknown>;
    if (Array.isArray(value.errors)) {
      const fieldErrors = value.errors.map((raw) => {
        const error = raw && typeof raw === "object" ? raw as Record<string, unknown> : {};
        return { loc: Array.isArray(error.loc) ? error.loc.join(".") : "request", msg: text(error.msg ?? raw) };
      });
      const message = fieldErrors.map((e) => `${e.loc}: ${e.msg}`).join("; ");
      return new ApiError("HTTP", status, value.code === undefined ? null : text(value.code), message, fieldErrors);
    }
    if (value.detail !== undefined) {
      if (value.detail && typeof value.detail === "object") {
        const detail = value.detail as Record<string, unknown>;
        return new ApiError(
          "HTTP",
          status,
          detail.code === undefined ? null : text(detail.code),
          text(detail.message ?? value.detail),
        );
      }
      return new ApiError("HTTP", status, null, text(value.detail));
    }
    if (value.message !== undefined) {
      const code = value.code === undefined ? null : text(value.code);
      return new ApiError("HTTP", status, code, text(value.message));
    }
  }
  const message = body === undefined || body === null || body === "" ? `HTTP ${status}` : text(body);
  return new ApiError("HTTP", status, null, message);
}

function fill(path: string, params: Record<string, string>): string {
  return path.replace(/\{(\w+)\}/g, (_, name: string) => encodeURIComponent(params[name]));
}

async function bodyOf(response: Response): Promise<unknown> {
  const raw = await response.text();
  try {
    return JSON.parse(raw);
  } catch {
    return raw;
  }
}

type Route = readonly ["GET" | "POST", string];

export class ApiClient {
  constructor(
    readonly baseUrl: string,
    private readonly token: string,
    private readonly fetchImpl: typeof fetch = (...args) => fetch(...args),
  ) {}

  url(route: Route, params: Record<string, string> = {}, query = ""): string {
    return `${this.baseUrl.replace(/\/+$/, "")}${API_PREFIX}${fill(route[1], params)}${query}`;
  }

  // Sends once and never retries. A lost response to a POST is reported as an unknown outcome,
  // because the backend may have applied it.
  async send(
    route: Route,
    options: {
      params?: Record<string, string>;
      query?: string;
      json?: unknown;
      body?: BodyInit;
      contentType?: string;
      headers?: Record<string, string>;
      signal?: AbortSignal;
    } = {},
  ): Promise<Response> {
    // Encoding errors happen before dispatch and must not be described as applied mutations.
    const body = options.json !== undefined ? JSON.stringify(options.json) : options.body;
    if (options.signal?.aborted) throw new DOMException("Request aborted before dispatch", "AbortError");
    const headers: Record<string, string> = { ...options.headers };
    for (const key of Object.keys(headers)) {
      if (key.toLowerCase() === "authorization") delete headers[key];
    }
    headers.Authorization = `Bearer ${this.token}`;
    if (options.json !== undefined) headers["Content-Type"] = "application/json";
    if (options.contentType) headers["Content-Type"] = options.contentType;
    let response: Response;
    try {
      response = await this.fetchImpl(this.url(route, options.params, options.query), {
        method: route[0], headers, body, signal: options.signal,
        redirect: "error", credentials: "omit", cache: "no-store",
      });
    } catch (cause) {
      if (route[0] === "GET" && (options.signal?.aborted ||
          (cause && typeof cause === "object" && "name" in cause && cause.name === "AbortError"))) {
        throw cause;
      }
      throw interrupted(route);
    }
    if (!response.ok) {
      let error: ApiError;
      try { error = normalizeError(response.status, await bodyOf(response)); }
      catch { error = normalizeError(response.status, null); }
      if (route[0] === "POST" && response.status >= 500) {
        const uncertain = interrupted(route, response.status);
        throw new ApiError("UNKNOWN_OUTCOME", response.status, error.code,
          `${error.message} ${uncertain.message}`, error.fieldErrors);
      }
      throw error;
    }
    return response;
  }

  private async json<T>(route: Route, options: Parameters<ApiClient["send"]>[1] = {}): Promise<T> {
    const response = await this.send(route, options);
    let raw: string;
    try { raw = await response.text(); }
    catch (cause) {
      if (route[0] === "GET" && options.signal?.aborted) throw cause;
      throw interrupted(route, response.status);
    }
    try { return JSON.parse(raw) as T; }
    catch {
      if (route[0] === "POST") throw interrupted(route, response.status);
      throw new ApiError("PROTOCOL", response.status, null, "The API returned invalid JSON.");
    }
  }

  health = () => this.json<Health>(ROUTES.health);
  agent = () => this.json<AgentConfig>(ROUTES.agent);
  enroll = (actor_id: string, password: string) =>
    this.json<{ status: string }>(ROUTES.enroll, { json: { actor_id, password } });

  catalogue = () => this.json<Catalogue>(ROUTES.dossiers);
  select = (fixture_id: string) => this.json<Dossier>(ROUTES.select, { json: { fixture_id } });
  upload = (zip: Blob) =>
    this.json<Dossier>(ROUTES.upload, { body: zip, contentType: "application/zip" });
  dossier = (dossier_id: string) =>
    this.json<Dossier>(ROUTES.dossier, { params: { dossier_id } });
  prepare = (dossier_id: string) =>
    this.json<Dossier>(ROUTES.prepare, { params: { dossier_id } });
  reviewFoundation = (
    dossier_id: string,
    body: { password: string; candidate_digest: string; accepted_qualifications: string },
  ) => this.json<Dossier>(ROUTES.reviewFoundation, { params: { dossier_id }, json: body });
  evidence = (dossier_id: string) =>
    this.json<Evidence>(ROUTES.evidence, { params: { dossier_id } });
  supportReview = (
    dossier_id: string,
    body: {
      password: string;
      snapshot_digest: string;
      assertions: SupportAssertion[];
      reason: string;
    },
  ) => this.json<Dossier>(ROUTES.supportReview, { params: { dossier_id }, json: body });

  async artifact(dossier_id: string, artifact_revision_id: string): Promise<Blob> {
    const response = await this.send(ROUTES.artifact, {
      params: { dossier_id, artifact_revision_id },
    });
    try { return await response.blob(); }
    catch { throw interrupted(ROUTES.artifact, response.status); }
  }

  startRun = (dossier_id: string, mode: RunMode, budgets?: BudgetLimits) =>
    this.json<{ run_id: string; status: string; mode: RunMode }>(ROUTES.startRun, {
      json: budgets ? { dossier_id, mode, budgets } : { dossier_id, mode },
    });
  runs = (dossierId?: string) => this.json<{ runs: RunView[] }>(ROUTES.runs, {
    query: dossierId === undefined ? "" : `?dossier_id=${encodeURIComponent(dossierId)}`,
  });
  run = (run_id: string) => this.json<RunView>(ROUTES.run, { params: { run_id } });
  resume = (run_id: string) =>
    this.json<{ run_id: string; status: string }>(ROUTES.resume, { params: { run_id } });
  cancel = (run_id: string) =>
    this.json<{ run_id: string; cancellation_requested: boolean; note: string }>(ROUTES.cancel, {
      params: { run_id },
    });
  trace = (run_id: string, after = 0) =>
    this.json<TracePage>(ROUTES.trace, { params: { run_id }, query: `?after=${after}` });
  audit = (run_id: string) => this.json<AuditManifest>(ROUTES.audit, { params: { run_id } });
  report = (run_id: string) =>
    this.json<InvestigationReport>(ROUTES.report, { params: { run_id } });
  packet = (run_id: string) => this.json<ReviewPacket>(ROUTES.packet, { params: { run_id } });
  review = (
    run_id: string,
    body: {
      password: string;
      packet_id: string;
      expected_dependency_digest: string;
      decision: ReviewDecisionKind;
      reason: string;
    },
  ) => this.json<RunState>(ROUTES.review, { params: { run_id }, json: body });
}
