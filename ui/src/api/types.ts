// Hand-written from the backend contracts because docs/api/openapi.json declares empty
// response schemas. Sources: api/app.py, api/trace.py, contracts/{core,workflow,review,results,
// extraction,artifacts,foundation}.py, reporting/baseline.py, knowledge/corpus_audit.py.

export type Json = null | boolean | number | string | Json[] | { [key: string]: Json };

export interface BlobRef {
  sha256: string;
  byte_length: number;
  media_type: string;
}

export interface Locator {
  kind: "PDF_PAGE" | "PDF_CELL" | "CSV_ROW" | "JSON_POINTER" | "TEXT_SPAN" | "DB_RECORD";
  page_index_1based: number | null;
  printed_page_label: string | null;
  row_index_1based: number | null;
  column_name: string | null;
  json_pointer: string | null;
  text_start: number | null;
  text_end: number | null;
  table_id: string | null;
  cell_row: number | null;
  cell_column: number | null;
}

export interface EvidenceRef {
  ref_kind: "ARTIFACT" | "OBSERVATION" | "RECORD" | "PROVISION" | "CALCULATION" | "FINDING";
  ref_id: string;
  artifact_revision_id: string | null;
  locator: Locator | null;
}

export interface Issue {
  issue_id: string;
  code: string;
  severity: "INFO" | "WARNING" | "BLOCKING";
  message: string;
  field_path: string | null;
  evidence_refs: EvidenceRef[];
  retryable: boolean;
}

// Decimals stay strings end to end. Never convert them to numbers.
export interface Quantity {
  decimal: string;
  unit: "KG" | "TONNE" | "INR" | "UNIT_COUNT";
  dimension: "METAL_MASS" | "EQUIPMENT_MASS" | "MONEY" | "COUNT";
  metal: "AU" | "CU" | "AL" | "FE" | null;
}

// Health and agent

export interface Health {
  status: string;
  model_configured: boolean;
  model_probed: boolean;
  concurrency: number;
  ui_implemented?: boolean;
}

export interface AgentConfig {
  configured: boolean;
  model_id: string | null;
  prompt_pin: { configuration_id: string; digest: string } | null;
  system_template: string;
  phase_rules: Record<string, string>;
  response_schemas: Record<string, Json>;
  note: string;
}

// Dossiers

export interface Fixture {
  fixture_id: string;
  case_id: string;
  fiscal_year: string;
  synthetic: boolean;
}

export interface FrozenSnapshot {
  snapshot_id: string;
  snapshot_kind: "CASE" | "CORPUS";
  membership_digest: string;
  review_state: "DRAFT" | "APPROVED" | "REJECTED";
  created_at: string;
}

export interface FoundationResult {
  case_snapshot: FrozenSnapshot;
  corpus_snapshot: FrozenSnapshot;
  inventory_count: number;
  extraction_count: number;
  observation_count: number;
  record_count: number;
  normalization_quarantine_count: number;
  issues: Issue[];
}

export type DossierStatus = "UPLOADED" | "DRAFT" | "APPROVED";

export interface Dossier {
  dossier_id: string;
  name: string;
  status: DossierStatus;
  synthetic?: boolean;
  case_id?: string;
  candidate_digest?: string;
  foundation?: FoundationResult;
  foundation_blob?: BlobRef;
}

export interface Catalogue {
  fixtures: Fixture[];
  dossiers: Dossier[];
}

export interface OriginalFile {
  artifact_id: string;
  artifact_revision_id: string;
  blob: BlobRef;
  original_filename: string | null;
  source_kind: string;
  doc_type: string;
  synthetic?: boolean;
}

export interface EvidenceObservation {
  observation_id: string;
  artifact_revision_id: string;
  locator: Locator;
  observation_type: string;
  raw_fields: Record<string, Json>;
  parsed_fields: Record<string, Json>;
  validation_state: "VALID" | "REVIEW_REQUIRED" | "INVALID";
  extraction_method: string;
}

export interface EvidenceRecord {
  record_id: string;
  record_revision_id: string;
  record_type?: string;
  observation_refs: string[];
  validation_state: string;
  [key: string]: unknown;
}

export interface Evidence {
  snapshot: { snapshot_id: string; membership_digest: string };
  records: EvidenceRecord[];
  observations: EvidenceObservation[];
  originals: OriginalFile[];
}

export interface SupportAssertion {
  target_record_revision_id: string;
  evidence_refs: EvidenceRef[];
  reason: string;
}

// Runs

export type RunStatus =
  | "CREATED"
  | "PREFLIGHT"
  | "INVESTIGATING"
  | "DRAFTING"
  | "VERIFYING"
  | "AWAITING_REVIEW"
  | "COMPLETED"
  | "BLOCKED_INPUT"
  | "BLOCKED_OUTPUT"
  | "FAILED"
  | "CANCELLED";

export type RunMode = "MODEL_BACKED" | "SCRIPTED_TEST";

export interface BudgetLimits {
  max_case_actions?: number;
  max_model_calls?: number;
  max_total_tokens?: number;
  tokens_per_model_call?: number;
  max_wall_seconds?: number;
  tools_per_finding?: number;
  reformulations_per_finding?: number;
  retries_per_operation?: number;
  report_repairs?: number;
  preflight_actions?: number;
  verification_actions?: number;
}

export interface BudgetUsage {
  actions: number;
  model_calls: number;
  tool_calls: number;
  retries: number;
  reserved_tokens: number;
  observed_tokens: number | null;
  observed_cost_usd: string | null;
  usage_known_calls: number;
  cost_known_calls: number;
  preflight_actions: number;
  verification_actions: number;
  report_repairs: number;
  finding_actions: Record<string, number>;
  finding_reformulations: Record<string, number>;
}

export interface RunState {
  run_id: string;
  version: number;
  status: RunStatus;
  current_turn: number;
  pending_finding_ids: string[];
  resolved_finding_ids: string[];
  abstained_finding_ids: string[];
  budget: BudgetUsage;
  created_at: string;
  updated_at: string;
  stop_reason: string | null;
  review_outcome: string;
}

export type JobStatus = "QUEUED" | "RUNNING" | "STOPPED" | "FAILED" | "INTERRUPTED";

export interface Job {
  run_id: string;
  dossier_id: string;
  status: JobStatus;
  detail: string | null;
  cancel_requested: number;
}

export interface RunView {
  state: RunState;
  job: Job;
}

// Trace

export interface PlanRecord {
  plan_id: string;
  revision: number;
  previous_plan_ref: string | null;
  triggering_operation_ref: string | null;
  finding_id: string;
  objective: string;
  hypotheses: string[];
  proposed_checks: string[];
  expected_evidence: string[];
  stopping_criteria: string[];
}

export interface ActionProposal {
  action_kind: "CHECK" | "REFORMULATE";
  allowed_operation: string;
  typed_arguments: Record<string, Json>;
  finding_id: string;
  concise_reason: string;
  evidence_refs: EvidenceRef[];
  plan_ref: string;
}

export interface ObservationAssessment {
  assessment_id: string;
  operation_ref: string;
  plan_ref: string;
  observation_refs: EvidenceRef[];
  verdict: "SUPPORTS" | "REFUTES" | "WEAK" | "NO_PROGRESS" | "UNKNOWN";
  weak_result_or_mistake: string | null;
  next_check_or_stop: string;
  revised_plan_ref: string | null;
  disposition: "CONTINUE" | "RESOLVE" | "ABSTAIN";
}

export interface StageOutcome {
  service_operation_ids: string[];
  retrieval_attempt_ids: string[];
  calculation_ids: string[];
  finding_revision_ids: string[];
  disposition: "PASS" | "QUALIFIED" | "BLOCKED";
  evidence_refs: EvidenceRef[];
  output_blob: BlobRef | null;
  concise_decision: string;
}

export interface ProviderTrace {
  configuration?: Json;
  endpoint?: string;
  method?: string;
  request_body_utf8: string | null;
  response_body_utf8?: string | null;
  response_body_blob?: BlobRef | null;
  response_status?: number | null;
  response_headers?: string[][];
  error?: string | null;
}

interface TraceBase {
  sequence: number;
  event_id: string;
  operation_id: string | null;
  turn_id: string | null;
  attempt_id: string | null;
  event_type: string;
  payload_ref: BlobRef;
}

export interface PromptPreparedEvent extends TraceBase {
  kind: "PROMPT_PREPARED";
  phase: "PLAN" | "ASSESS";
  request: Json;
  system_template: string | null;
  note: string;
}

export interface PlanEvent extends TraceBase {
  kind: "PLAN";
  data: PlanRecord;
}

export interface ToolProposedEvent extends TraceBase {
  kind: "TOOL_PROPOSED";
  data: ActionProposal;
}

export interface AssessmentEvent extends TraceBase {
  kind: "ASSESSMENT";
  data: ObservationAssessment;
}

export interface ModelResultEvent extends TraceBase {
  kind: "MODEL_RESULT";
  status: string;
  issues: Issue[];
  data?: StageOutcome;
  result?: Json;
  response?: Json;
  exact_response?: string;
  provider_trace?: ProviderTrace;
}

export interface ToolOrStageResultEvent extends TraceBase {
  kind: "TOOL_OR_STAGE_RESULT";
  status: string;
  issues: Issue[];
  data?: StageOutcome;
  result?: Json;
}

export interface AuditEvent extends TraceBase {
  kind: "AUDIT";
}

export type TraceEvent =
  | PromptPreparedEvent
  | PlanEvent
  | ToolProposedEvent
  | AssessmentEvent
  | ModelResultEvent
  | ToolOrStageResultEvent
  | AuditEvent;

export interface TracePage {
  run_id: string;
  events: TraceEvent[];
  last_sequence: number;
}

// Report and review

export interface BucketResult {
  bucket_id: string;
  required: Quantity;
  supported: Quantity;
  signed_gap: Quantity;
  shortfall: Quantity;
  surplus: Quantity;
  pending: Quantity;
  portal_reported: Quantity | null;
  ledger_supported: Quantity;
  delta: Quantity | null;
  snapshot_comparison_ref: string | null;
  allocation_ids: string[];
  qualification_refs: EvidenceRef[];
}

export interface CalculationResult {
  calculation_id: string;
  analyzed_bucket_ids: string[];
  bucket_results: BucketResult[];
  coverage: "COMPLETE_WITHIN_SCOPE" | "QUALIFIED" | "BLOCKED";
  issues: Issue[];
}

export interface ReportClaim {
  claim_id: string;
  kind: string;
  template_or_text: string;
  evidence_refs: EvidenceRef[];
  support_status: "SUPPORTED" | "QUALIFIED" | "UNSUPPORTED";
}

export interface ReportSection {
  section_id: string;
  title: string;
  claim_ids: string[];
  evidence_refs: EvidenceRef[];
  coverage_state: "COMPLETE_WITHIN_SCOPE" | "QUALIFIED" | "BLOCKED";
}

export interface FindingRecord {
  finding_id: string;
  finding_revision_id: string;
  bucket_ids: string[];
  issue_type: string;
  advisory_status: string;
  priority: "HIGH" | "MEDIUM" | "LOW";
  priority_basis: string;
  fact_refs: EvidenceRef[];
  calculation_refs: string[];
  provision_refs: EvidenceRef[];
  hypotheses: { text: string; support_state: string; refs: EvidenceRef[] }[];
  abstention_reason: string | null;
  withheld_claim_scopes: string[];
  next_action: { kind: string; description: string; evidence_refs: EvidenceRef[] };
  action_owner_ref: string | null;
  scope_limits: string[];
}

export interface VerificationResult {
  verification_id: string;
  report_revision_id: string;
  verdict: "PASS" | "QUALIFIED" | "BLOCKED";
  checks: Record<string, string | boolean>[];
  issues: Issue[];
  verifier_version: string;
  verified_dependency_digest: string;
}

export interface InvestigationReport {
  report: {
    revision: {
      report_id: string;
      report_revision_id: string;
      review_dependency_digest: string;
      supersedes_report_revision_id: string | null;
    };
    sections: ReportSection[];
    claims: ReportClaim[];
    calculations: CalculationResult[];
    rendered_markdown: string;
  };
  findings: FindingRecord[];
  available_evidence_refs: EvidenceRef[];
  verification: VerificationResult;
}

export type ReviewDecisionKind = "APPROVE" | "REJECT" | "REQUEST_CHANGES" | "ESCALATE";

export interface ReviewPacket {
  packet_id: string;
  run_id: string;
  report_revision_id: string;
  review_dependency_digest: string;
  input_snapshot_refs: { snapshot_id: string; membership_digest: string }[];
  proposed_action_refs: string[];
  unresolved_issue_refs: string[];
  permitted_decisions: ReviewDecisionKind[];
  created_at: string;
}

export interface AuditManifest {
  verification_status: "UNVERIFIED_METADATA" | "VERIFIED_INTEGRITY";
  runtime_metadata: Record<string, string>;
  verified_checks: string[];
  verified_audit_streams: string[];
  generated_at: string;
  sources: { source_alias: string; document_title: string; sha256_digest: string }[];
  limitations: { limitation_id: string; kind: string; scope: string; description: string }[];
}
