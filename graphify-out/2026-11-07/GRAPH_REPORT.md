# Graph Report - ReCycleGuard  (2026-11-05)

## Corpus Check
- Large corpus: 3474 files · ~2,648,673 words. Semantic extraction will be expensive (many Claude tokens). Consider running on a subfolder.

## Summary
- 2153 nodes · 7823 edges · 87 communities (68 shown, 19 thin omitted)
- Extraction: 86% EXTRACTED · 14% INFERRED · 0% AMBIGUOUS · INFERRED: 1125 edges (avg confidence: 0.93)
- Token cost: 52,904 input · 0 output

## Community Hubs (Navigation)
- Agent Runner And Workflow Store
- Calculation Inputs And Findings
- UI API Types
- Reconciliation And Allocation Arithmetic
- UI Transport And SSE
- UI Shell And Common Components
- Export Bundles Service
- Verification Scripts
- CLI Options And Entry
- FTS Index And VLM Parsing
- Schema Export And LangGraph Deps
- Units And Domain Equivalence
- Extraction Contracts And Extractors
- Benchmark Sweep And Freeze
- Audit And Commit Boundary
- Case Catalog And Snapshots
- Retrieval And Evidence Expansion
- API Investigation Endpoints
- Benchmark Trial Runner
- Trial Child And Prompt Measurement
- Local Model Tool Queries
- Model Ports And Playback
- Universe And Service Results
- UI Package Dependencies
- Domain Rules Documentation
- API Responses And FastAPI
- Isolated Runtime Sandbox
- Audit Kernel And Blob Store
- Corpus Audit
- Trace Timeline And Prompt Inspector
- Foundation Review And Profiles
- UI API Client
- Foundation Sources Contracts
- Intake Batch And Acquisition
- Baseline Reports And Repair
- Structured Check Requests
- CLI Command Dispatch
- UI Report Rendering Tests
- Commercial Link Checks
- Human Review Service
- Investigation Inspection
- API App Authorization
- Calculation Profile Policies
- Evaluation Funnel And Rubric
- Evaluator Oracle Isolation
- Finding Gate
- Trial Scoring
- Lifecycle And Chronology Rules
- UI Investigation Budget View
- Deadline Register
- Reviewer Local Session Auth
- UI TypeScript Config
- Report Baseline Builder
- API Job Store
- Host Sandbox Probe
- Allocation Priority And Chronology
- Regulatory Claim Checks
- Prompt Pinning Config
- Snapshot Reference Contracts
- Profile Store
- Local Model Configuration Script
- Amendment Overlay Service
- Reasoning Replay Script
- Case Service
- Provision Applicability Assertions
- Fake Model Server
- CP4 Verification Script
- Baseline Service
- UI Evidence Viewer
- Workflow Ports And Bindings
- Dev Split Generator
- Investigation Run Validation
- Evaluation Budgets
- Support Review
- Corpus Loading And Amendments
- Investigation Backend Config
- CLI Version Callback
- Engine Rejection Errors
- Outcome Unknown Errors
- Reviewed Source Registration
- Export Results Script
- Import Hidden Script

## God Nodes (most connected - your core abstractions)
1. `BoundaryModel` - 234 edges
2. `canonical_json_bytes()` - 128 edges
3. `EvidenceRef` - 108 edges
4. `create_app()` - 93 edges
5. `Issue` - 78 edges
6. `InvestigationService` - 68 edges
7. `BlobRef` - 66 edges
8. `WorkflowRunner` - 63 edges
9. `OperationResult` - 57 edges
10. `OperationIntent` - 56 edges

## Surprising Connections (you probably didn't know these)
- `save()` --calls--> `canonical_json_bytes()`  [INFERRED]
  scripts/verify_api.py → src/recycleguard/storage/blob_store.py
- `All Decisions And Calculations Stay In Backend` --semantically_similar_to--> `Decimal Strings, 4dp ROUND_HALF_EVEN, Never Float`  [INFERRED] [semantically similar]
  ui/README.md → src/recycleguard/domain/README.md
- `llama_cpp_config()` --uses--> `LocalModelConfig`  [INFERRED]
  scripts/configure_local_model.py → src/recycleguard/local_model.py
- `mlx_config()` --uses--> `LocalModelConfig`  [INFERRED]
  scripts/configure_local_model.py → src/recycleguard/local_model.py
- `with_options()` --uses--> `LocalModelConfig`  [INFERRED]
  scripts/configure_local_model.py → src/recycleguard/local_model.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **C08 Domain Verdict Rules (UNKNOWN-on-missing, demote-only)** — src_recycleguard_domain_readme_lifecycle_rule, src_recycleguard_domain_readme_chronology_rule, src_recycleguard_domain_readme_capability_rule, src_recycleguard_domain_readme_commercial_rule, src_recycleguard_domain_readme_weight_basis_conflict [EXTRACTED 1.00]
- **Deterministic Check Reproducibility (dispatcher, check_id, TOOL_VERSION)** — src_recycleguard_domain_readme_run_check, src_recycleguard_domain_readme_check_id_hash, src_recycleguard_domain_readme_tool_version, src_recycleguard_domain_readme_structuredcheckresult [INFERRED 0.85]
- **UI Run And Review Safety Guards** — ui_readme_duplicate_submission_lock, ui_readme_in_memory_token, ui_readme_stale_digest_rejection, ui_readme_failure_cases_checklist [INFERRED 0.75]

## Communities (87 total, 19 thin omitted)

### Community 0 - "Agent Runner And Workflow Store"
Cohesion: 0.06
Nodes (22): plan(), ScriptedPort, exchanges(), ActionDraft, ActionProposal, AssessmentProposal, BudgetUsage, CancellationRequest (+14 more)

### Community 1 - "Calculation Inputs And Findings"
Cohesion: 0.08
Nodes (33): ProductMapping, Registration, ReviewedInterval, SalesRecord, multiply(), apply_capability(), capability_finding(), code_covers() (+25 more)

### Community 2 - "UI API Types"
Cohesion: 0.05
Nodes (48): ErrorKind, Route, ActionProposal, AssessmentEvent, AuditEvent, AuditManifest, BlobRef, CalculationResult (+40 more)

### Community 3 - "Reconciliation And Allocation Arithmetic"
Cohesion: 0.11
Nodes (34): Quantity, Allocation, BucketResult, decide_allocations(), Decision, _enforce_event_caps(), enforce_lot_caps(), _exclude() (+26 more)

### Community 4 - "UI Transport And SSE"
Cohesion: 0.07
Nodes (31): API_PREFIX, ApiError, bodyOf(), interrupted(), normalizeError(), ROUTES, text(), followRun() (+23 more)

### Community 5 - "UI Shell And Common Components"
Cohesion: 0.19
Nodes (43): react, App(), Screen(), Badge(), ErrorBanner(), IssueList(), Mono(), PasswordField() (+35 more)

### Community 6 - "Export Bundles Service"
Cohesion: 0.08
Nodes (16): AttributionRecord, BundleManifest, IncludedObjectEntry, IntegrityResult, OmissionDisposition, ReplayRequest, ReplayResult, RightsDecision (+8 more)

### Community 7 - "Verification Scripts"
Cohesion: 0.08
Nodes (23): pin(), run(), lookup(), result(), stage(), source_revision(), run(), invoke() (+15 more)

### Community 8 - "CLI Options And Entry"
Cohesion: 0.10
Nodes (24): main(), application_options(), run(), save(), ApiOptions, audit_export(), audit_verify(), baseline_audit() (+16 more)

### Community 9 - "FTS Index And VLM Parsing"
Cohesion: 0.06
Nodes (10): LexicalConfiguration, DeterministicVLMPdfParser, VLMPageExtraction, VLMPdfParser, VLMTable, IndexBuilder, ProvisionChunker, FTS5Index (+2 more)

### Community 10 - "Schema Export And LangGraph Deps"
Cohesion: 0.10
Nodes (11): trace_events(), BaselineRequest, StructuredCheckResult, BlobRef, AssetEntry, CalculationRequest, ContextManifest, ObservationAssessment (+3 more)

### Community 11 - "Units And Domain Equivalence"
Cohesion: 0.10
Nodes (20): AccountBalanceObservation, CertificateEvent, Entity, Identifier, NonnegativeMass, NormalizedRecord, EquivalenceResolutionResult, EventCompoundKey (+12 more)

### Community 12 - "Extraction Contracts And Extractors"
Cohesion: 0.13
Nodes (15): Issue, Locator, TemporalValue, CoverageItem, ExtractionResult, Observation, extract_csv(), _utc_now_rfc3339() (+7 more)

### Community 13 - "Benchmark Sweep And Freeze"
Cohesion: 0.08
Nodes (17): export(), main(), _by_variant(), compare(), configure_module(), _counts(), load_sweep(), main() (+9 more)

### Community 14 - "Audit And Commit Boundary"
Cohesion: 0.13
Nodes (8): AuditEvent, OperationIntent, OperationResult, _logical(), LocalAuthority, TrustedPrincipal, canonical_json_bytes(), CommitBoundary

### Community 15 - "Case Catalog And Snapshots"
Cohesion: 0.11
Nodes (5): FrozenSnapshot, SnapshotStore, mutation(), ArtifactCatalog, CatalogError

### Community 16 - "Retrieval And Evidence Expansion"
Cohesion: 0.11
Nodes (10): CandidateDisposition, EvidenceBundle, EvidenceGrade, ExpansionPolicy, LocatorLookupRequest, RetrievalAttempt, SearchRulesRequest, ContextExpander (+2 more)

### Community 17 - "API Investigation Endpoints"
Cohesion: 0.13
Nodes (26): approve_foundation(), artifact(), audit(), cancel(), dossier_view(), drive(), evidence(), foundation_value() (+18 more)

### Community 18 - "Benchmark Trial Runner"
Cohesion: 0.09
Nodes (21): child_command(), container_command(), coordinate(), forbidden_paths(), freeze(), held_out_case_ids(), Launch, main() (+13 more)

### Community 19 - "Trial Child And Prompt Measurement"
Cohesion: 0.10
Nodes (16): main(), call_summary(), caller(), call(), census(), decision_trace(), main(), model_calls() (+8 more)

### Community 20 - "Local Model Tool Queries"
Cohesion: 0.08
Nodes (28): Query, Calculate, SupportReviewRequest, TraceEventResponse, RecordSupportAssertion, BoundaryModel, CreditLot, DatedAlias (+20 more)

### Community 21 - "Model Ports And Playback"
Cohesion: 0.09
Nodes (9): ScriptedInvestigator, LocalModelPort, _retry_problem(), ModelCallRequest, ModelCallResult, ModelPort, _key(), load_recordings() (+1 more)

### Community 22 - "Universe And Service Results"
Cohesion: 0.14
Nodes (16): CommandContext, ServiceResult, CalculationProfile, _failure(), run_check(), run_check_on_universe(), make_issue(), compute_reconciliation() (+8 more)

### Community 23 - "UI Package Dependencies"
Cohesion: 0.07
Nodes (32): jsdom, pdfjs-dist, react-dom, @types/node, @types/react, @types/react-dom, typescript, vite (+24 more)

### Community 24 - "Domain Rules Documentation"
Cohesion: 0.08
Nodes (24): C08 Deterministic Domain Tools README, Lot Capacity And Allocation Conservation (S03), Deterministic check_id Hash, Decimal Strings, 4dp ROUND_HALF_EVEN, Never Float, Earlier-Liability Order (F08), Identity And Registrations (F05), Reconciliation Engine And ServiceResult Wrapper, run_check Allowlisted Dispatcher (+16 more)

### Community 25 - "API Responses And FastAPI"
Cohesion: 0.09
Nodes (19): DecisionRequest, Enrollment, FoundationReviewRequest, Selection, AgentResponse, CancellationResponse, CatalogueResponse, DossierResponse (+11 more)

### Community 26 - "Isolated Runtime Sandbox"
Cohesion: 0.11
Nodes (16): _check_arguments(), _check_mount(), _connect(), container_entry(), _denied_when_raising(), docker_arguments(), _durable_record(), main() (+8 more)

### Community 27 - "Audit Kernel And Blob Store"
Cohesion: 0.12
Nodes (7): record_acquisition(), AuditKernel, _encode(), _now(), Capability, BlobIntegrityError, BlobStore

### Community 28 - "Corpus Audit"
Cohesion: 0.12
Nodes (13): audit_corpus_sources(), audit_frozen_corpus_profile(), audit_profile(), AuditLimitation, build_audit_limitations(), build_corpus_profile_audit_manifest(), build_index_audit_record(), CorpusProfileAuditManifest (+5 more)

### Community 29 - "Trace Timeline And Prompt Inspector"
Cohesion: 0.16
Nodes (28): TraceEvent, JsonView(), Unavailable(), Layer, NO_SENT, preparedContext(), PreparedLayer(), PromptInspector() (+20 more)

### Community 30 - "Foundation Review And Profiles"
Cohesion: 0.14
Nodes (11): prepare(), ProfileRef, FoundationApproval, FoundationRequest, ProfilePublication, ProfileReview, CaseReopen, SnapshotPublication (+3 more)

### Community 31 - "UI API Client"
Cohesion: 0.13
Nodes (4): ApiClient, fill(), Connect(), Session

### Community 32 - "Foundation Sources Contracts"
Cohesion: 0.13
Nodes (10): ApplicabilityProposal, ExtractedBatch, SourceBatch, ProvisionVersion, RightsMetadata, SourceLead, SourceVersion, extract() (+2 more)

### Community 33 - "Intake Batch And Acquisition"
Cohesion: 0.13
Nodes (12): ArtifactRevision, AssetReceipt, CaseManifest, AcquisitionOutcome, _prepare_acquisition(), _utc_now_rfc3339(), intake_batch(), receipt() (+4 more)

### Community 34 - "Baseline Reports And Repair"
Cohesion: 0.20
Nodes (14): BaselineOutput, VerifiedReport, CalculationResult, FindingRecord, InvestigationReport, BaselineReport, BaselineReportBuilder, inspection_limitations() (+6 more)

### Community 35 - "Structured Check Requests"
Cohesion: 0.13
Nodes (16): CheckRequest, CheckTarget, _arity(), _capability(), CheckRejected, _credit_events(), _evidence(), _history() (+8 more)

### Community 36 - "CLI Command Dispatch"
Cohesion: 0.18
Nodes (11): baseline_run(), _dispatch(), foundation_build(), investigation_start(), profile_publish(), profile_review(), snapshot_publish(), snapshot_reopen() (+3 more)

### Community 37 - "UI Report Rendering Tests"
Cohesion: 0.12
Nodes (21): @testing-library/react, vitest, BucketResult, InvestigationReport, Issue, Quantity, ReportClaim, Qty() (+13 more)

### Community 38 - "Commercial Link Checks"
Cohesion: 0.16
Nodes (11): CommercialRecord, _check_link(), CommercialOutcome, _groups(), _Index, _lead(), match_commercial(), _mismatch() (+3 more)

### Community 39 - "Human Review Service"
Cohesion: 0.19
Nodes (5): AcknowledgmentRecord, ReviewTransitionResult, _now(), ReviewService, decide()

### Community 40 - "Investigation Inspection"
Cohesion: 0.17
Nodes (13): Inspection, draft(), inspect(), locator(), plan_context(), preflight(), reconcile(), search() (+5 more)

### Community 41 - "API App Authorization"
Cohesion: 0.11
Nodes (12): create_app(), dossiers(), get_run(), lifespan(), list_runs(), register(), require_idle(), resume_run() (+4 more)

### Community 42 - "Calculation Profile Policies"
Cohesion: 0.18
Nodes (10): AllocationPolicy, EligibilityRule, EventEquivalencePolicy, NumericPolicy, profile_digest(), ProfileDefinition, PurchaseCeilingPolicy, SourceDependency (+2 more)

### Community 43 - "Evaluation Funnel And Rubric"
Cohesion: 0.16
Nodes (12): _codes(), _compact(), main(), results_by_trial(), rows_for(), _source(), stage(), case_label() (+4 more)

### Community 44 - "Evaluator Oracle Isolation"
Cohesion: 0.15
Nodes (4): IsolationReport, IsolationViolation, OracleAccessDeniedError, RuntimeIsolationEnforcer

### Community 45 - "Finding Gate"
Cohesion: 0.19
Nodes (11): EvidenceRef, Hypothesis, Recommendation, FindingProposal, _calculation_ref(), _finding(), _finding(), gate_finding_proposals() (+3 more)

### Community 46 - "Trial Scoring"
Cohesion: 0.14
Nodes (8): call_metrics(), canary_signature(), compare_canaries(), main(), report_metrics(), score_trial(), classified(), summarize()

### Community 47 - "Lifecycle And Chronology Rules"
Cohesion: 0.19
Nodes (10): Certificate, span(), span_before(), apply_lifecycle(), credit_event_findings(), judge(), Terminal, terminals() (+2 more)

### Community 48 - "UI Investigation Budget View"
Cohesion: 0.12
Nodes (14): AgentConfig, BudgetLimits, BudgetUsage, RunView, Budget(), elapsedSeconds(), PAUSED, RunProgress() (+6 more)

### Community 49 - "Deadline Register"
Cohesion: 0.15
Nodes (3): DeadlineEntry, DeadlineCheckResult, DeadlineRegister

### Community 50 - "Reviewer Local Session Auth"
Cohesion: 0.24
Nodes (8): enroll(), authenticate_reviewer(), _derive(), initialize_reviewer(), ReviewerCredential, _windows_acl(), _windows_regular_file(), AuthorizationError

### Community 51 - "UI TypeScript Config"
Cohesion: 0.12
Nodes (16): compilerOptions, isolatedModules, jsx, lib, module, moduleResolution, noEmit, noFallthroughCasesInSwitch (+8 more)

### Community 52 - "Report Baseline Builder"
Cohesion: 0.23
Nodes (11): CalculationValueRef, add(), _calc_ref(), inspection_limitation(), _quantity(), _quantity_label(), render_markdown(), ReportClaim (+3 more)

### Community 54 - "Host Sandbox Probe"
Cohesion: 0.18
Nodes (7): _attempt(), _evaluator_key(), _literal(), probe_boundary(), sandbox_command(), sandbox_environment(), sandbox_profile()

### Community 55 - "Allocation Priority And Chronology"
Cohesion: 0.23
Nodes (6): ObligationBucket, Chronology, PriorityCheck, _evaluate(), evaluate_priority(), _year()

### Community 56 - "Regulatory Claim Checks"
Cohesion: 0.22
Nodes (8): decimal_string(), utc_timestamp(), inspect_regulatory_claims(), _period(), RegulatoryCheckRequest, RegulatoryCheckResult, RegulatoryClaimFinding, RuleApplicabilityChecker

### Community 57 - "Prompt Pinning Config"
Cohesion: 0.25
Nodes (5): _run_prompt(), ConfigurationPin, LocalModelConfig, prompt_digest(), PromptText

### Community 58 - "Snapshot Reference Contracts"
Cohesion: 0.22
Nodes (5): SnapshotRef, DenseConfiguration, IndexManifest, ReviewPacket, ReviewRecord

### Community 59 - "Profile Store"
Cohesion: 0.31
Nodes (5): ProfileError, ProfileStore, mutation(), build(), build()

### Community 60 - "Local Model Configuration Script"
Cohesion: 0.28
Nodes (9): config_name(), digest(), llama_cpp_config(), main(), mlx_config(), take(), with_options(), write_llama_cpp() (+1 more)

### Community 62 - "Reasoning Replay Script"
Cohesion: 0.26
Nodes (8): attempts(), jobs(), main(), original_text(), phase_of(), selected_trials(), events(), stream()

### Community 69 - "UI Evidence Viewer"
Cohesion: 0.36
Nodes (7): EvidenceRef, ArtifactBody(), csvRecords(), DownloadOnly(), isText(), PdfView(), TextView()

### Community 70 - "Workflow Ports And Bindings"
Cohesion: 0.36
Nodes (3): RunSpec, ToolBinding, WorkflowStages

### Community 71 - "Dev Split Generator"
Cohesion: 0.36
Nodes (4): main(), _order(), protocol(), split_cases()

### Community 72 - "Investigation Run Validation"
Cohesion: 0.39
Nodes (5): dependency_lock_path(), experiment_variant(), validate_model_run(), pin(), source_revision()

### Community 73 - "Evaluation Budgets"
Cohesion: 0.33
Nodes (5): RunRequest, RunConfigurationResponse, BudgetLimits, evaluation_budgets(), resolve_budgets()

### Community 74 - "Support Review"
Cohesion: 0.43
Nodes (3): support_review(), RecordSupportReview, SupportReviewer

### Community 75 - "Corpus Loading And Amendments"
Cohesion: 0.48
Nodes (4): AmendmentEdge, CorpusView, _date(), load_corpus()

## Knowledge Gaps
- **8 isolated node(s):** `StructuredCheckResult`, `Reconciliation Engine And ServiceResult Wrapper`, `Deferred From S04 (read_scope, list_evidence, A07 Wiring)`, `src/api/types.ts Mirrors docs/api/openapi.json`, `recycleguard serve With --cors-origin` (+3 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 635 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **19 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `BoundaryModel` connect `Local Model Tool Queries` to `Agent Runner And Workflow Store`, `Calculation Inputs And Findings`, `Reconciliation And Allocation Arithmetic`, `Export Bundles Service`, `FTS Index And VLM Parsing`, `Schema Export And LangGraph Deps`, `Units And Domain Equivalence`, `Extraction Contracts And Extractors`, `Audit And Commit Boundary`, `Case Catalog And Snapshots`, `Retrieval And Evidence Expansion`, `API Investigation Endpoints`, `Model Ports And Playback`, `Universe And Service Results`, `API Responses And FastAPI`, `Corpus Audit`, `Foundation Review And Profiles`, `Foundation Sources Contracts`, `Intake Batch And Acquisition`, `Baseline Reports And Repair`, `Structured Check Requests`, `Human Review Service`, `Investigation Inspection`, `API App Authorization`, `Calculation Profile Policies`, `Evaluator Oracle Isolation`, `Finding Gate`, `Deadline Register`, `Reviewer Local Session Auth`, `Report Baseline Builder`, `Allocation Priority And Chronology`, `Regulatory Claim Checks`, `Prompt Pinning Config`, `Snapshot Reference Contracts`, `Provision Applicability Assertions`, `Workflow Ports And Bindings`, `Evaluation Budgets`, `Support Review`, `Corpus Loading And Amendments`, `Investigation Backend Config`?**
  _High betweenness centrality (0.113) - this node is a cross-community bridge._
- **Are the 2 inferred relationships involving `BoundaryModel` (e.g. with `ToolBinding` and `GraphStore`) actually correct?**
  _`BoundaryModel` has 2 INFERRED edges - model-reasoned connections that need verification._
- **What connects `StructuredCheckResult`, `Reconciliation Engine And ServiceResult Wrapper`, `Deferred From S04 (read_scope, list_evidence, A07 Wiring)` to the rest of the system?**
  _8 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Agent Runner And Workflow Store` be split into smaller, more focused modules?**
  _Cohesion score 0.06491885143570537 - nodes in this community are weakly interconnected._
- **Why does `canonical_json_bytes()` connect `Audit And Commit Boundary` to `Agent Runner And Workflow Store`, `Calculation Inputs And Findings`, `Reconciliation And Allocation Arithmetic`, `Export Bundles Service`, `Verification Scripts`, `CLI Options And Entry`, `FTS Index And VLM Parsing`, `Schema Export And LangGraph Deps`, `Units And Domain Equivalence`, `Extraction Contracts And Extractors`, `Benchmark Sweep And Freeze`, `Case Catalog And Snapshots`, `Retrieval And Evidence Expansion`, `API Investigation Endpoints`, `Local Model Tool Queries`, `Model Ports And Playback`, `Universe And Service Results`, `API Responses And FastAPI`, `Audit Kernel And Blob Store`, `Corpus Audit`, `Foundation Review And Profiles`, `Foundation Sources Contracts`, `Intake Batch And Acquisition`, `Baseline Reports And Repair`, `Structured Check Requests`, `Human Review Service`, `Investigation Inspection`, `API App Authorization`, `Finding Gate`, `Report Baseline Builder`, `Prompt Pinning Config`, `Profile Store`, `Case Service`, `Baseline Service`, `Investigation Run Validation`, `Support Review`, `Corpus Loading And Amendments`, `Investigation Backend Config`?**
  _High betweenness centrality (0.075) - this node is a cross-community bridge._
- **Are the 5 inferred relationships involving `canonical_json_bytes()` (e.g. with `.invoke()` and `save()`) actually correct?**
  _`canonical_json_bytes()` has 5 INFERRED edges - model-reasoned connections that need verification._
- **Should `Calculation Inputs And Findings` be split into smaller, more focused modules?**
  _Cohesion score 0.08408249603384453 - nodes in this community are weakly interconnected._