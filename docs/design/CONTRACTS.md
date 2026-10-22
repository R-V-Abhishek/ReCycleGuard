# ReCycleGuard component and data contracts

**Contract version:** 1.1 — corrected 22 October 2026.

**Status:** Normative specification for implementation; no APIs, generated schemas or datasets are implied to exist yet.

**Final consistency review:** 22 October 2026.

**Architecture:** [SYSTEM_DESIGN.md](SYSTEM_DESIGN.md).

**Rule:** A component may change its internals without changing these contracts. Changing a shared field, meaning, permission, status or side effect requires a versioned contract change and consumer updates.

## 1. Scope, conventions and versioning

These are primarily **Python service/function contracts and persisted artifact formats**, not a commitment to HTTP microservices. C00 can invoke them through the CLI; a future web adapter must preserve the same validation, identity and audit guarantees.

`MUST`, `MUST NOT` and `SHOULD` express implementation requirements. Pydantic boundary models will generate JSON Schemas under `schemas/v1/`; hand-maintained schemas must not drift from runtime models. Unknown fields are rejected at strict boundaries. Missing, unknown, not applicable, withheld and explicitly zero are different states.

- Required fields are listed without `?`; `field?: T` may be omitted. `T | null` permits explicit null; omission is otherwise invalid.
- `ID` is an opaque string with a type prefix, such as `case:001` or `observation:abc`. It never encodes fault labels or hidden answers.
- `Digest` is lowercase SHA-256 hex, exactly 64 characters. `BlobRef = {sha256: Digest, byte_length: integer >= 0, media_type: string}`. Blob resolution additionally checks access scope.
- `Timestamp` is timezone-aware RFC 3339. Runtime timestamps use UTC; source dates retain original precision/timezone as defined below.
- `Date` is ISO `YYYY-MM-DD`. `FiscalYear` is `YYYY-YYYY`, for example `2024-2025`, with exact start/end dates in the case manifest. UI labels may display `2024–25`.
- `DecimalString` matches `^-?(0|[1-9][0-9]*)(\.[0-9]+)?$`, with at most 18 integral and 8 fractional digits in v1. No commas, exponent, NaN, infinity or binary-float JSON quantities. Positive-only fields add a range constraint. Raw out-of-range source strings remain observations with blocking validation issues.
- JSON/JSONL is UTF-8. Canonical hashing uses JSON sorted by key, compact separators, Unicode preserved, no NaN, and no trailing newline. Arrays are ordered; membership sets are sorted by typed ID before serialization. Money/quantities are strings before hashing. JSONL file hashes include their actual LF bytes.
- A profile fixes decimal precision, rounding and output scale; changing them creates a new profile/result. v1 defaults are precision 28, four display decimal places, `ROUND_HALF_EVEN`.
- Conversion and aggregation trap inexact arithmetic and overflow. Return `NUMERIC_PRECISION_EXCEEDED` for an intermediate result exceeding the supported context, even when individual inputs fit. Only explicit final display quantization may round, with its delta retained.
- Stable source aliases such as `R02` are not globally unique version IDs. Persist the alias **and** exact artifact/provision revision.

Contract version is a major/minor string. Breaking semantics require a new major. Adding an optional field still requires coordinated schema publication because strict consumers reject unrecognized input. Preserve old serialized objects; migrate into new revisions with `derived_from`, never rewrite historical bytes.

## 2. Common request, result and error protocol

### 2.1 CommandContext

Every call carries:

```text
CommandContext {
  contract_version: "1.1"
  command_id: ID
  operation_id: ID
  attempt_id: ID
  idempotency_key: string
  actor: ActorRef
  case_version_id: ID | null
  run_id: ID | null
  turn_id: ID | null
  correlation_id: ID
  parent_operation_id: ID | null
}
ActorRef {
  actor_id: ID
  actor_kind: HUMAN | SERVICE | MODEL_PROPOSAL | EVALUATOR
  authenticated_session_ref: ID | null
}
```

The dispatcher creates operation/attempt IDs and resolves permissions from the authenticated local session or service capability. A caller's `actor_kind="HUMAN"` string does not grant approval rights. C00 cannot accept an untrusted model-produced actor or capability token as proof of authority.

Bootstrap acquisition may have no case/run/turn. Once a run starts, all its calls must reference its pinned case version. A tool receives an opaque capability-scoped context; no arbitrary filesystem root, SQL or network credential is passed by the model.

### 2.2 ServiceResult<T>

```text
ServiceResult<T> {
  contract_version: "1.1"
  operation_id: ID
  attempt_id: ID
  status: SUCCESS | PARTIAL | FAILED | REJECTED | CANCELLED | OUTCOME_UNKNOWN
  output: T | null
  output_blob: BlobRef | null
  issues: Issue[]
  dependencies: EvidenceRef[]
  audit_event_ids: ID[]
}
Issue {
  issue_id: ID
  code: ErrorCode
  severity: INFO | WARNING | BLOCKING
  message: string
  field_path: string | null
  evidence_refs: EvidenceRef[]
  retryable: boolean
}
```

`output_blob` contains the complete canonical output when present; `output` is its decoded bounded object or a typed page. Large results use `Page<T> = {items, total_count, next_cursor, full_result_blob}` with a stable snapshot-bound cursor. Tool/context truncation never truncates the archived full result. Partial success must enumerate every unresolved item and prohibit downstream consumers from treating it as complete.

Errors include `INVALID_SCHEMA`, `ACCESS_DENIED`, `HASH_MISMATCH`, `MISSING_ARTIFACT`, `INCOMPLETE_COVERAGE`, `EXTRACTION_FAILED`, `UNCONFIRMED_IDENTIFIER`, `AMBIGUOUS_IDENTITY`, `AMBIGUOUS_EVENT`, `DIMENSION_MISMATCH`, `NUMERIC_PRECISION_EXCEEDED`, `EARLIER_LIABILITY_UNMET`, `LIABILITY_PRIORITY_UNRESOLVED`, `UNSUPPORTED_PROFILE`, `UNAPPROVED_PROFILE`, `APPLICABILITY_UNRESOLVED`, `RULE_CONFLICT`, `SOURCE_INCOMPLETE`, `STALE_SNAPSHOT`, `BUDGET_EXHAUSTED`, `CYCLE_DETECTED`, `PROVIDER_TIMEOUT`, `PROVIDER_INVALID_OUTPUT`, `AUDIT_UNAVAILABLE`, `CONCURRENT_MODIFICATION`, `STALE_REVIEW`, `EXPORT_RESTRICTED`, `PROHIBITED_VERDICT`, `CANCELLED` and `INTEGRITY_FAILED`.

Domain unknowns are normally `PARTIAL` results with findings; process/integrity failures are `FAILED` or `REJECTED`. A model timeout with unknown provider completion may be `OUTCOME_UNKNOWN`. Do not use generic empty lists as failure fallbacks.

### 2.3 Idempotency and retry

Same operation key plus identical canonical input returns the previously committed result. Reusing a key with different input is rejected. Every retry has a new attempt ID under the same logical operation; attempted external calls remain separately audited. A caller cannot reset budgets by regenerating IDs. Automatic retries are allowed only for declared retryable errors and within configured attempt limits. Human review and snapshot publication require expected-version checks.

## 3. Core evidence and storage contracts

### 3.1 AssetReceipt and ArtifactRevision

```text
AssetReceipt {
  receipt_id: ID
  batch_id: ID
  declared_asset_id: ID | null
  supplied_path_or_url: string
  intake_status: RECEIVED | DECLARED_MISSING | REJECTED_ACCESS | FETCH_FAILED
  artifact_revision_id: ID | null
  reason: string | null
  received_at: Timestamp
}
ArtifactRevision {
  artifact_id: ID
  artifact_revision_id: ID
  blob: BlobRef
  original_filename: string | null
  source_kind: GAZETTE | OFFICIAL_GUIDANCE | PORTAL_CAPTURE | COMPANY_RECORD |
               SYNTHETIC_RECORD | AGGREGATE_STATISTICS | RESEARCH_NOTE
  doc_type: DocumentType
  establishes: EvidenceCapability[]
  does_not_establish: EvidenceCapability[]
  source_url: string | null
  fetch_attempt_id: ID | null
  captured_at: TemporalValue
  ingested_at: Timestamp
  access_policy_id: ID
  rights_decision_id: ID
  synthetic: boolean
  derived_from: ID[]
}
```

Every file discovered inside the submitted batch boundary gets a receipt, including undeclared extras and duplicate bytes. Reject symlink/path traversal and oversized/unsupported inputs with receipts. Register declared missing items without inventing a blob. Two receipts may reference the same bytes while preserving distinct origin/permissions.

`RightsDecision = {id, owner_or_provider, intended_use, license_or_basis, evidence_refs, access_allowed, model_use_allowed, local_retention_allowed, redistribution_status, reviewer_id, reviewed_at}`. Permission fields are `ALLOW | DENY | REVIEW_REQUIRED`, never silently inferred from a public URL. `redistribution_status` uses the same three states. Unknown rights fields remain review-required. No API keys, OTPs, public-key dispatch secrets or auth headers belong in artifacts or logs.

Seed Gazette redistribution decisions as `REVIEW_REQUIRED`, with the claimed statutory exception and intended use recorded for review; neither a Gazette label nor a public URL seeds `ALLOW`.

`DocumentType` is `STATUTORY_INSTRUMENT | SOP | TECHNICAL_FRAMEWORK | FAQ | PORTAL_INSTRUCTION | NOTICE | REGISTRATION_CERTIFICATE | PORTAL_SNAPSHOT | PORTAL_EPR_CERTIFICATE | GST_INVOICE | ERP_CSV | CONTRACT | PURCHASE_ORDER | PAYMENT_RECORD | WEIGHT_TICKET | RECYCLING_ACKNOWLEDGMENT | DESTRUCTION_CERTIFICATE | AWARENESS_PROOF | RETURN_DRAFT | FILING_ACKNOWLEDGMENT | OTHER`.

`EvidenceCapability` is `IDENTITY | REGISTRATION_COVERAGE | REPORTED_ACCOUNT_POSITION | CERTIFICATE_IDENTITY | TRANSFER_STAGE | LIABILITY_ALLOCATION | PAYMENT | PHYSICAL_MOVEMENT | DESTRUCTION | AWARENESS_ACTIVITY | FILING_RECEIPT | RULE_TEXT | CONTEXT_ONLY`. These lists describe evidence scope, not automatic proof. A weight ticket may support physical movement, a destruction certificate destruction, and a portal snapshot a reported account position; none alone establishes a supported liability allocation. C03/C04 record the observed scope and C12 checks claims against it.

### 3.2 TemporalValue, Quantity and EvidenceRef

```text
TemporalValue {
  raw: string | null
  value: string | null
  precision: INSTANT | DATE | MONTH | YEAR | UNKNOWN
  timezone: string | null
  interpretation_status: PARSED | REVIEWED | AMBIGUOUS | UNKNOWN
}
Quantity {
  decimal: DecimalString
  unit: KG | TONNE | INR | UNIT_COUNT
  dimension: METAL_MASS | EQUIPMENT_MASS | MONEY | COUNT
  metal: AU | CU | AL | FE | null
}
EvidenceRef {
  ref_kind: ARTIFACT | OBSERVATION | RECORD | PROVISION | CALCULATION | FINDING
  ref_id: ID
  artifact_revision_id: ID | null
  locator: Locator | null
}
Locator {
  kind: PDF_PAGE | PDF_CELL | CSV_ROW | JSON_POINTER | TEXT_SPAN | DB_RECORD
  page_index_1based: integer | null
  printed_page_label: string | null
  row_index_1based: integer | null
  column_name: string | null
  json_pointer: string | null
  text_start: integer | null
  text_end: integer | null
  table_id: ID | null
  cell_row: integer | null
  cell_column: integer | null
}
```

`Quantity` requires a metal iff dimension is `METAL_MASS`; INR iff `MONEY`; integral decimal value iff `COUNT`. KG/TONNE apply only to mass. Negative values are permitted only in signed adjustment/gap fields, not certificate face values or allocations. Raw source quantity/unit fields are retained in observations.

A locator must populate the fields appropriate to its kind. Text offsets use Unicode code points with a half-open span into an exact extraction-text blob. CSV rows count data rows excluding the header, not raw newline count. PDF page indexes are physical one-based indexes; printed labels never replace them. A higher-level record reference resolves transitively to its original observations or an explicit reviewed user assertion.

### 3.3 ExtractionResult, CoverageItem and Observation

```text
ExtractionResult {
  extraction_id: ID
  artifact_revision_id: ID
  adapter_id: string
  adapter_version: string
  configuration_digest: Digest
  text_blob: BlobRef | null
  observations_blob: BlobRef
  coverage_blob: BlobRef
  status: COMPLETE | PARTIAL | FAILED
  issues: Issue[]
}
CoverageItem {
  coverage_item_id: ID
  artifact_revision_id: ID
  locator: Locator
  disposition: PARSED | QUARANTINED | EXCLUDED | FAILED | NOT_APPLICABLE
  reason_code: string
  child_observation_ids: ID[]
}
Observation {
  observation_id: ID
  extraction_id: ID
  artifact_revision_id: ID
  locator: Locator
  observation_type: string
  raw_fields: object
  parsed_fields: object
  validation_state: VALID | REVIEW_REQUIRED | INVALID
  extraction_method: CSV | JSON | PDF_TEXT | PDF_TABLE | OCR | HUMAN_ASSERTION
  field_quality: object
  event_time: TemporalValue
  source_capture_time: TemporalValue
  ingestion_time: Timestamp
}
```

`raw_fields` and `parsed_fields` are adapter-versioned JSON objects with explicit schemas, not arbitrary shape guessing. `field_quality` maps field names to `{raw_score, score_scale, engine, validation_checks, review_state}`. A raw OCR score cannot independently authorize an identity join.

Coverage summary includes declared/discovered counts, unknown-count flags, actual pages/rows, terminal disposition counts, file truncation/pagination status and time coverage. For row-based sources, terminal row dispositions must sum to discovered rows. Page and row counts are separate dimensions; one page can contain many rows. Unknown expected count cannot be serialized as `0` or `complete=true`.

### 3.4 NormalizedRecord envelope

All domain records share `{record_id, record_revision_id, record_type, case_id, observation_refs[], derived_from_record_refs[], validation_state, created_by_operation_id, supersedes_revision_id}`. A record must have source observations, reviewed human-assertion evidence, or explicit derivation inputs. No provenance-free “cleaned” values.

The record payload catalog below defines visible synthetic JSONL rows and normalization outputs. `?` marks optional data; absent evidence stays absent.

| Record type / file | Required payload | Optional payload / constraints |
| --- | --- | --- |
| `Entity` / `entities.jsonl` | `entity_id: ID`, `legal_name: string`, `roles: Role[]`, `identifiers: Identifier[]`, `synthetic: boolean` | `aliases?: DatedAlias[]`. Role is PRODUCER/MANUFACTURER/RECYCLER/REFURBISHER; other roles preserved as unsupported observations. Identifier = type/value/evidence, not a universal primary key. |
| `Registration` / `registrations.jsonl` | `entity_id`, `registration_ref: string`, `validity: ReviewedInterval`, `covered_eee_codes: string[]`, `status_assertion: string`, `evidence_as_of: TemporalValue` | `facility_id?`, `capacity?: Quantity`, `consent_refs?: EvidenceRef[]`. Unknown validity is not false; stale evidence is labelled. |
| `ProductMapping` / `product_mappings.jsonl` | `mapping_id`, `entity_id`, `sku`, `eee_code`, `unit_weight: Quantity`, `weight_basis: NET_EEE \| GROSS_PACKAGED \| COMPONENT`, `validity`, `review_ref` | `hsn?`, `lifespan_ref?`, `composition_ref?`. Numeric regulatory parameters require reviewed provenance. |
| `SalesRecord` / `sales.jsonl` | `entity_id`, `sku`, `fiscal_year`, `quantity_units: DecimalString`, `source_record_ref` | `mass?: Quantity`, `adjustment_refs?: ID[]`. Does not independently establish a statutory obligation. |
| `ObligationBucket` / `obligations.jsonl` | `bucket_id`, `producer_entity_id`, `liability_year`, `component: string`, `metal`, `target: Quantity`, `basis: SUPPLIED_ACCOUNT \| REVIEWED_CALCULATION`, `basis_refs: EvidenceRef[]`, `profile_id` | `adjustments?: SignedAdjustment[]`; historical liabilities are their own dated buckets. `component` distinguishes incompatible obligations even for one metal/year. |
| `Certificate` / `certificates.jsonl` | `certificate_id: ID`, `external_certificate_ref: string`, `issuer_entity_id`, `metal`, `face_quantity: Quantity`, `identity_evidence: EvidenceRef[]` | `generation_time?`, `expiry_time?`, `raw_status?`. No assumed number encoding or hard-coded denomination list. |
| `CertificateEvent` / `certificate_events.jsonl` | `event_id`, `certificate_id`, `credit_lot_id: ID \| null`, `event_kind: GENERATED \| TRANSFERRED \| ADJUSTED \| EXPIRED \| CANCELLED \| STATUS_OBSERVED`, `event_time`, `quantity: Quantity`, `assertion_state: SUPPORTED \| PENDING \| CONFLICTING`, `supporting_observations: ID[]` | `external_event_ref?`, `from_entity_id?`, `to_entity_id?`, `equivalence_assertion_id?`, `transfer_stage?: TransferStage`, `transfer_stage_mapping_ref?`. Intermediate stages are historical-screen observations, not assumed export fields or proof of completed transfer. |
| `Allocation` / `allocations.jsonl` | `allocation_id`, `credit_lot_id`, `event_id`, `bucket_id`, `quantity: Quantity`, `basis_refs`, `state: SUPPORTED \| PENDING \| REJECTED`, `profile_id` | `supersedes_allocation_id?`. All active allocations consume the shared lot capacity, not separate event capacities. |
| `AccountBalanceObservation` / `account_balances.jsonl` | `balance_observation_id`, `producer_entity_id`, `bucket_id`, `reported_supported: Quantity`, `source_capture_time`, `business_cutoff: TemporalValue`, `basis_refs` | `reported_pending?: Quantity`. Comparison-only in v1; cannot replace missing allocation history. |
| `CommercialRecord` / `commercial_records.jsonl` | `commercial_id`, `record_kind: CONTRACT \| PO \| INVOICE \| PAYMENT`, `issuer_entity_id`, `recipient_entity_id`, `external_ref`, `event_time`, `linked_credit_refs: ID[]` | `money?: Quantity`, `credit_quantity?: Quantity`, `tax_observations?: object`. Financial payment is not a fulfillment allocation. |
| `ReturnDraft` / `return_drafts.jsonl` | `draft_id`, `producer_entity_id`, `fiscal_year`, `quarter: Q1 \| Q2 \| Q3 \| Q4 \| ANNUAL`, `reported_bucket_values: object[]`, `source_refs`, `section_dispositions: ReturnSectionDisposition[]` | `supporting_section_refs?: EvidenceRef[]`, `submission_ack_ref?`. Each bucket value has bucket_id/Quantity; draft status and actual acknowledgment remain separate. |

`Identifier = {kind: GSTIN | PAN | CIN | IEC | PROJECT_ID | OTHER, value, validation_state, evidence_refs}`. `DatedAlias` has alias, interval and evidence. `SignedAdjustment` has ID, signed Quantity, approved basis and review reference. `ReviewedInterval` has start/end Date or null, `end_open_ended: boolean`, `review_state`, applicability scope and evidence; intervals are half-open. A null date with unreviewed status means unknown, not unlimited validity.

`CertificateObservation` is an observation payload containing certificate ref, raw status/quantity, source capture and optional event references. `EventEquivalence` explicitly lists observation IDs, resolved event ID, matching basis, review state and conflicts. It is stored by C04 even though it need not be present in generated source files.

`TransferStage` is `NOT_OBSERVED | INITIATED | OTP_INITIATED | PUBLIC_KEY_DISPATCHED | COMPLETED | UNKNOWN`. These are internal mappings from documented historical screens, not a current portal API schema. Nontrivial mappings require `transfer_stage_mapping_ref` plus source observations. Preserve the raw label; OTP/key values are excluded. An intermediate stage does not authorize a SUPPORTED transfer/allocation.

`ReturnSectionDisposition = {section: OBLIGATION | AWARENESS | SOLAR | OTHER, applicability: REQUIRED | NOT_APPLICABLE | UNKNOWN, state: PRESENT | MISSING | EXCLUDED | UNSUPPORTED | NOT_APPLICABLE, evidence_refs, reason}`. Missing required awareness evidence, or an applicable excluded/unsupported solar section, prevents `READY_WITHIN_CHECKED_SECTIONS` from being presented as readiness of the complete return. Unknown applicability yields `READINESS_UNDETERMINED`.

`CreditLot = {credit_lot_id, certificate_id, supported_capacity: Quantity, supporting_refs, resolution_state: SUPPORTED | PENDING | CONFLICTING}` is derived by C04 from visible evidence, not a privileged clean generator table. V1 uses one lot per resolved certificate. All linked transfer/adjustment events reference this lot. Ambiguous lot identity/capacity blocks supported allocations. The effective allocation set consists only of the latest non-superseded revisions in the frozen case; old revisions remain auditable. Conservation spans every liability year and every linked event in that set.

## 4. Source knowledge, profiles and snapshots

### 4.1 SourceLead, SourceVersion and ProvisionVersion

```text
SourceLead {
  source_lead_id: ID
  aliases: string[]
  official_url: string
  discovery_evidence_refs: EvidenceRef[]
  source_class: SourceClass
  regime: string
  state: DISCOVERED | FETCH_FAILED | ACQUIRED | EXTRACTED | REVIEW_REQUIRED | READY | EXCLUDED
  acquired_artifact_revision_id: ID | null
}
SourceVersion {
  source_version_id: ID
  source_lead_id: ID
  artifact_revision_id: ID
  title: string
  issuer: string
  notification_number: string | null
  notification_date: TemporalValue
  publication_date: TemporalValue
  commencement: TemporalValue
  commencement_basis_refs: EvidenceRef[]
  website_upload_date: TemporalValue
  completeness: COMPLETE_TEXT | PARTIAL_TEXT | HTML_SHELL | NOTICE_LEAD
  review_state: DRAFT | APPROVED | REJECTED
}
ProvisionVersion {
  provision_version_id: ID
  source_version_id: ID
  parent_provision_id: ID | null
  locator: Locator
  legal_path: string
  text_blob: BlobRef
  regime: string
  role_scope: GENERAL | SPECIFIC | UNKNOWN
  affected_roles: Role[]
  applicability_assertion_id: ID | null
  table_context_refs: EvidenceRef[]
  review_state: DRAFT | APPROVED | REJECTED
}
```

`ApplicabilityAssertion` stores provision version, reviewed half-open interval, event/filing/reporting basis, affected roles/categories, transition conditions, scope/exception notes, reviewer and sources. `AmendmentEdge` stores from/to provision IDs, relation `AMENDS | REPLACES | INSERTS | RELAXES_DEADLINE | REFERENCES`, affected scope, applicability assertion and review state. A link from the rule allowing extensions is not itself evidence that a particular extension was issued.

Role filtering retains reviewed GENERAL provisions as well as matching SPECIFIC provisions. UNKNOWN scope is recorded as unresolved and can be fetched diagnostically; it cannot establish an affirmative role-specific conclusion until reviewed. An empty `affected_roles` array has no implicit universal meaning.

`SourceClass` is `STATUTE | GAZETTE_RULE | ORDER | TECHNICAL_FRAMEWORK | SOP | PORTAL_INSTRUCTION | FAQ | NOTICE_LEAD | SUPPORTING_CONTEXT`. Preserve this class through source versions, provision references and authority grades; OFFICIAL_GUIDANCE is only a broad artifact-origin class. SourceVersion.commencement records instrument-level commencement or an explicit unknown; clause-specific ApplicabilityAssertions control exceptions and overrides. Notification date never substitutes automatically for publication or commencement.

### 4.2 FrozenSnapshot and CalculationProfile

`FrozenSnapshot = {snapshot_id, snapshot_kind: CASE | CORPUS, schema_version, parent_snapshot_id, membership_blob, membership_digest, coverage_blob, created_at, created_by, source_receipt_ids, review_state}`. Membership entries are ordered typed references to exact revisions/hashes plus inclusion/exclusion reason. Artifacts, records, extraction issues and declared missing evidence are included, not only usable rows. Publishing a snapshot does not mark uncertain records valid.

`CaseScope = {case_id, producer_entity_id, fiscal_year, period_start, period_end_exclusive, quarter, allowed_eee_codes, allowed_metals, business_cutoff: TemporalValue, knowledge_cutoff: Timestamp, calculation_profile_id, access_scope_id, authorized_signatory_ref: AuthorizedSignatoryRef | null, deadline_entry_ids: ID[]}`. `business_cutoff` is the decision's event boundary; `knowledge_cutoff` limits available captured evidence. An unknown or date-only cut-off preserves its precision and prevents ambiguous automated eligibility decisions.

`AuthorizedSignatoryRef = {person_ref, masked_display_name, authority_evidence_refs, permitted_actions: REVIEW_WORKING_PAPER | APPROVE_CORRECTION | SUBMIT_RETURN, validity: ReviewedInterval}`; permitted_actions is an array. Missing authority blocks an approval/submission claim, not evidence intake. It is distinct from reviewer authentication and contains no raw PAN/Aadhaar. C13 checks the actor's authority for the requested decision; no internal capability grants official portal access.

`CalculationProfile = {profile_id, profile_version, review_state, review_refs, supported_regime, target_basis, supported_components, allowed_metals, category_scope, applicability_assertion_refs, eligibility_rules, allocation_policy, event_equivalence_policy, purchase_ceiling_policy, numeric_policy, unsupported_features, source_dependencies, digest}`.

Only APPROVED profiles run calculations. V1 uses supplied targets, reviewed compatible allocations and separate historical buckets. Gold offsets, refurbishing deferrals, full sales-derived target computation, tax/pricing, solar and EC calculations are unsupported features. The profile must declare which eligibility conditions are actually testable; unavailable facts cannot be silently treated as passed.

`EventEquivalencePolicy` lists required exact fields (resolved certificate/lot, event kind/stage, full source time value/precision/timezone, exact normalized quantity/dimension/metal, from/to parties), corroboration requirements, missing-field handling and policy version. Different overlapping export windows are corroborating context, not identity proof by themselves. F02 may resolve to SUPPORTED only when an authoritative external event ID agrees or the complete compound key agrees **and** export provenance/source continuity excludes multiple indistinguishable events. Any absent key, contradiction or coarse-time collision remains PENDING unless reviewed. The oracle records the expected equivalence state and supporting visible observations.

`allocation_policy.priority_check` requires checking each later-year allocation against earlier compatible outstanding liabilities **at allocation time**, using the full pinned historical state. A confirmed prohibited later-year allocation emits `EARLIER_LIABILITY_UNMET` and cannot enter derived supported totals; missing opening history or ordering emits `LIABILITY_PRIORITY_UNRESOLVED`, not an invented violation. Preserve the account's observed allocation as evidence in both cases.

`PurchaseCeilingPolicy = {state: DISABLED_REVIEW_REQUIRED | APPROVED, source_refs, applicability_refs, current_liability_basis, prior_liability_basis, buffer_rate: DecimalString | null, review_ref}`. Rule 15(1)'s published text was checked on 22 October 2026; it includes current liability, prior leftover liability and 5% of current liability. Period/component applicability and purchase-data completeness still need profile review. Seed this slot DISABLED_REVIEW_REQUIRED and return NOT_EVALUATED; it cannot impose a hard-coded purchase verdict before approval. [Official Rules, Rule 15(1)](https://eprewaste.cpcb.gov.in/assets/PDF/e-waste_rules_2022.pdf).

### 4.3 Deadline register

`DeadlineEntry = {deadline_id, producer_or_role_scope, fiscal_year, quarter, kind: OBLIGATION_ACHIEVEMENT | CREDIT_EVENT | RETURN_FILING, baseline_due: TemporalValue, baseline_basis_refs, extended_due: TemporalValue | null, extension_order_refs: EvidenceRef[], enabling_provision_refs: EvidenceRef[], unverified_notice: boolean, review_state, supersedes_deadline_id}`. Freeze entries in corpus/profile/case dependencies. A missing baseline stays unknown; a notice lead never creates a verified extension. Rule 9A is an enabling provision, not the extension order itself. A RETURN_FILING entry cannot extend OBLIGATION_ACHIEVEMENT or CREDIT_EVENT without separate reviewed authority. C07 resolves the relevant deadline ID/basis, and C08 tests only approved, sufficiently evidenced deadlines.

## 5. Visible synthetic dataset contract

### 5.1 DatasetManifest and CaseManifest

`DatasetManifest` includes dataset/version, schema version, generator code revision, public license/attributions, opaque case IDs, split assignments, source/profile/corpus versions and the aggregate visible-assets digest. It does **not** expose held-out seeds or fault families to the runtime. Evaluator-only generation metadata is separate.

`CaseManifest` includes case scope, `synthetic=true`, watermark text, input assets, optional-table dispositions, evidence expectations and schema/adapter versions. Asset entries include relative path, media type, body digest, byte length, logical record type, source-capture temporal value and `visibility=VISIBLE`. No hidden oracle path is allowed.

Example intake template below is valid JSON but intentionally has an empty asset list; it represents a draft template, not a runnable or populated case. Actual manifests must pass the required-evidence checks before snapshot publication.

```json
{
  "schema_version": "1.0",
  "case_id": "case:demo001",
  "synthetic": true,
  "watermark": "SYNTHETIC — NOT A CPCB RECORD",
  "producer_entity_id": "entity:demo001",
  "fiscal_year": "2024-2025",
  "period_start": "2024-04-01",
  "period_end_exclusive": "2025-04-01",
  "quarter": "ANNUAL",
  "allowed_eee_codes": [],
  "allowed_metals": ["CU", "AL", "FE"],
  "calculation_profile_id": "profile:producer_snapshot_v1",
  "assets": [],
  "optional_table_dispositions": [],
  "status": "DRAFT"
}
```

The final import supplies business/knowledge cut-offs, real generated asset digests, approved codes and all required scope fields. Empty template fields cannot activate a case. Case IDs and document filenames must not encode expected balances, corruption names or clean/error labels.

### 5.2 JSONL, CSV and document rendering

JSONL uses one typed domain record per line, canonical decimal strings, ISO source dates and stable internal references. Transport row IDs do not replace business IDs. Each file names its record schema in the manifest; no mixed untagged record types.

Optional CSV uses UTF-8, comma delimiter, double-quote escaping, LF, a mandatory header and adapter-versioned column names. Empty cell means missing, never zero. Decimal/unit/metal are separate columns; strings such as `1,000 kg` remain raw values until explicitly parsed. Schema invalidity can be an intentional defect; ingestion preserves it and emits observations/issues instead of refusing to record the asset.

PDF/CSV renderings derive from the same clean world before corruption. Record the mapping from visible row/page to the generator object **only in the hidden generation manifest** when it would disclose answers. Visible provenance resolves between visible records and their actual rendered sources, not hidden truth. All fictional PDFs bear the watermark; do not copy official seals or imply genuine account exports.

### 5.3 Hidden benchmark contracts

```text
GenerationManifest {
  dataset_version, generator_revision, seed, profile_digest,
  case_ids, world_blob, visible_asset_manifest_blob,
  corruption_manifest_blob, oracle_blob, split_policy, rights_manifest_ref
}
CorruptionRecord {
  corruption_id, case_id, fault_family: FaultFamily, affected_visible_asset_refs,
  transformation, before_refs, after_refs, intended_evidence_effect
}
OracleCase {
  case_id, expected_world_balances, visible_evidence_balances,
  expected_findings, required_abstentions, permitted_alternatives,
  forbidden_actions, reference_calculation_refs, review_rubric_version
}
```

These types are evaluator-only. They must never be imported into the investigator registry, logs, checkpoints, search corpus, cache, context, artifact browser or public run export. Development answers may be released separately for developers but remain outside benchmark run mounts. Oracle labels are not evidence the agent may cite.

### 5.4 Shared fault-family taxonomy

Use the same `FaultFamily` enum in generator configuration/CorruptionRecord, `FindingRecord.issue_type` and OracleCase expected findings. Case-specific hidden labels remain inaccessible to the agent; knowing the shared taxonomy does not reveal which fault a case contains. F01 is a clean control, not an anomaly. Ordinary infrastructure errors remain ErrorCode values rather than fabricated business fault families.

| FaultFamily enum value | Distinction required |
| --- | --- |
| F01_CLEAN_BASELINE | Clean control; no false-positive anomaly. |
| F02_OVERLAPPING_EXPORT | One event observed repeatedly; oracle explicitly records equivalence support. |
| F03_MULTISTAGE_ID_REUSE | Distinct legitimate lifecycle events sharing an instrument. |
| F04_UNIT_DIMENSION_MIX | Units/dimensions cannot be summed blindly. |
| F05_WRONG_ENTITY_ALIAS | Entity mismatch versus supported alias. |
| F06_STALE_SNAPSHOT | Capture-time mismatch. |
| F07_PAID_NO_TRANSFER | Commercial payment or intermediate stage without completed supported transfer/allocation. |
| F08_PRIOR_ARREARS_DRAIN | Earlier liability and allocation priority. |
| F09_EXPIRED_CANCELLED | Expired/cancelled instruments or unresolved lifecycle evidence. |
| F10_CAPABILITY_MISMATCH | Recycler capability, independently of metal compatibility. |
| F11_WRONG_PERIOD_RULE | Wrong period/regime or superseded interpretation. |
| F12_UNSEEN_NOTICE_LEAD | Missing signed authority. |
| F13_WEIGHT_BASIS_CONFLICT | Incompatible approved/product/packaging weight basis. |
| F14_OUT_OF_SCOPE_REGIME | Unsupported profile feature. |
| F15_EXTRACTION_PAGE_LOSS | Incomplete/corrupt extraction, not proof of a missing event. |
| F16_PROMPT_INJECTION | Hostile evidence content cannot change permissions/control. |

## 6. Retrieval, model and calculation payloads

### 6.1 SearchRulesRequest and RetrievalAttempt

`SearchRulesRequest = {query, corpus_snapshot_id, index_id, question_basis, target_event_time, target_reporting_period, target_filing_date, deadline_entry_ids, regimes, roles, eee_codes, top_k, diagnostic_mode}`. Nullable dates are explicit; `question_basis` selects which date/period drives applicability and uses the frozen deadline register where relevant. Filters are enforced server-side and cannot expand access or override the run's pinned corpus. Diagnostic mode can inspect excluded sources but marks them ineligible for affirmative claims.

`LocatorLookupRequest = {corpus_snapshot_id, source_alias_or_source_version_id, legal_path, question_basis, applicability_context, expansion_policy: ExpansionPolicy}`. `resolve_locator` returns the exact provision revision and resolution evidence; ambiguous alias/version/locator matches return APPLICABILITY_UNRESOLVED rather than choosing latest. This supports fallback before a search has supplied a provision ID.

`ExpansionPolicy = {include_parent: boolean, include_table_header: boolean, include_footnotes: boolean, include_applicable_amendments: boolean, include_references: boolean, max_depth: integer, max_nodes: integer}`. Defaults include parents/header/footnotes/applicable amendments, exclude general reference traversal, and bound depth to 2 and nodes to 20. The run pins this policy; access, regime, temporal qualifications and budgets apply to every expanded node.

`IndexManifest = {index_id, corpus_snapshot_id, eligible_members_digest, extraction_versions, lexical_configuration, dense_configuration_or_null, build_code_revision, index_files, integrity_digest}`. Dense configuration includes exact model/revision, dimensions, normalization, tokenizer/chunk strategy and vector blob digests. No changing embeddings under an existing index ID.

`RetrievalAttempt` includes input request, eligibility-set reference, filter-disposition blob, engine candidate lists with scores/ranks, graph-expansion edges, grading assessments, selected refs, excluded refs, full-result blob and execution versions. `CandidateDisposition` is one of `FILTERED_OUT`, `NOT_SCORED`, `OUTSIDE_ENGINE_WINDOW`, `SCORED`, `EXPANDED_CONTEXT`, `SELECTED`, `REJECTED_SUPPORT` or `OMITTED_CONTEXT_BUDGET`, with reason and operation reference. These are stage-specific records, not a single mutable final flag.

`EvidenceGrade = {candidate_ref, authority: PASS | FAIL | UNRESOLVED, temporal_fit, direct_support, completeness, contradiction, reasons[], assessed_by, assessment_version, evidence_refs}`; the remaining four dimensions use the same verdict enum. A semantic grader's PASS is a recorded assessment, not legal proof. Missing order text cannot be repaired by a high similarity score.

### 6.2 CalculationRequest and CalculationResult

```text
CalculationRequest {
  case_version_id: ID
  profile_id: ID
  bucket_ids: ID[]
  expected_input_membership_digest: Digest | null
}
CalculationResult {
  calculation_id: ID
  case_version_id: ID
  profile_id: ID
  tool_version: string
  input_digest: Digest
  analyzed_input_membership_blob: BlobRef
  analyzed_bucket_ids: ID[]
  bucket_results: BucketResult[]
  quantity_dispositions_blob: BlobRef
  derivation_blob: BlobRef
  coverage: COMPLETE_WITHIN_SCOPE | QUALIFIED | BLOCKED
  issues: Issue[]
}
BucketResult {
  bucket_id: ID
  required: Quantity
  supported: Quantity
  signed_gap: Quantity
  shortfall: Quantity
  surplus: Quantity
  pending: Quantity
  portal_reported: Quantity | null
  ledger_supported: Quantity
  delta: Quantity | null
  snapshot_comparison_ref: ID | null
  allocation_ids: ID[]
  qualification_refs: EvidenceRef[]
}
```

`QuantityDisposition` contains input quantity/record, state `INCLUDED | EXCLUDED | PENDING | OUT_OF_SCOPE`, allocated amounts/bucket refs, reason and evidence. Every candidate input has a disposition. The calculation result includes all considered amounts even when the report omits them for brevity.

Validate dimension/metal/entity/profile compatibility, allocation conservation, prior/current bucket separation and a single authoritative basis per bucket. Observed transfers and already-adjusted balances are comparison views unless supported allocations distinguish them; summing both is rejected. An event's uncertain eligibility means PENDING, not zero-quantity proof. Exact formulas are in the system design; each result retains operands, conversion factors and rounding/display deltas.

C08, not its caller, computes the full candidate-input universe from the pinned case snapshot, including conflicting assertions, related lot events and historical allocations. `bucket_ids` selects requested output buckets, not permission to omit adverse inputs; whole-case reports additionally require coverage of every in-scope bucket. If supplied, `expected_input_membership_digest` must match this server-computed set. Every member gets a disposition; caller-filtered record arrays cannot create `COMPLETE_WITHIN_SCOPE` results.

Supported amounts in v1 derive solely from supported allocations. AccountBalanceObservation records are comparison-only; lack of allocation evidence yields QUALIFIED/BLOCKED coverage even when an aggregate account figure is present. No tool invents allocations from that total. Lot-level conservation covers all active allocation revisions across events and years.

`ledger_supported` equals `supported`; it is not another quantity to add. `portal_reported` references a compatible dated AccountBalanceObservation. `delta = portal_reported - ledger_supported` and the comparison reference preserves both views, scope and cut-offs. This differs from `signed_gap = required - ledger_supported`. Absent/incompatible portal evidence yields null portal/delta values, never zero. The priority and purchase-ceiling check results are archived in the calculation derivation with PASS/FAIL/UNKNOWN/NOT_EVALUATED states.

### 6.3 FindingRecord and structured claims

`FindingRecord = {finding_id, finding_revision_id, case_version_id, bucket_ids, issue_type: FaultFamily, advisory_status, priority: HIGH | MEDIUM | LOW, priority_basis, portal_reported_value_ref, ledger_supported_value_ref, delta_value_ref, snapshot_comparison_ref, fact_refs, calculation_refs, provision_refs, evidence_assessments, hypotheses, abstention_reason: AbstentionReason | null, withheld_claim_scopes: string[], next_action, action_owner_ref, scope_limits, supersedes_finding_revision_id}`. Value refs point to BucketResult fields rather than copying unchecked numbers; nullable comparison fields follow BucketResult's null semantics.

Advisory statuses are `RECONCILED_WITHIN_SCOPE`, `DISCREPANCY_DETECTED`, `PENDING_VERIFICATION`, `REQUIRES_EXPERT_REVIEW`. A hypothesis has text, support state and refs; it cannot be rendered as a verified fact. `next_action` is a typed recommendation, not an executable approval or filing command.

Abstention is represented by PENDING_VERIFICATION or REQUIRES_EXPERT_REVIEW plus a non-null `AbstentionReason`: `MISSING_EVIDENCE | MISSING_AUTHORITY | RULE_CONFLICT | TEMPORAL_UNCERTAINTY | UNSUPPORTED_FEATURE | INCOMPLETE_HISTORY | BUDGET_LIMIT`. `withheld_claim_scopes` identifies the conclusion/amount not established. No verified numeric/legal claim is permitted for that unresolved scope; separately evidenced figures may still be reported with their limits. C16 scores this explicit state rather than guessing abstention from prose.

`Claim = {claim_id, kind: FACT | NUMERIC | INTERPRETATION | LIMITATION | RECOMMENDATION, template_or_text, evidence_refs, calculation_value_ref, support_status: SUPPORTED | QUALIFIED | UNSUPPORTED}`. Numeric claims reference calculation ID/bucket/field; the renderer supplies values. Uncited numerical narrative is either labelled illustrative or rejected. Removing an UNSUPPORTED claim from the final report does not remove its draft/audit history.

### 6.4 ModelCall and ContextManifest

`ModelCallRequest = {model_configuration_id, prompt_template_id, prompt_template_digest, exact_request_blob, context_manifest_id, allowed_tool_schema_digest, response_schema_id, budget_ref}`. The gateway fills secrets from environment outside the archived request and records only redacted provider configuration. Exact request content must already satisfy model-use permissions.

`ModelCallResult = {model_call_id, provider_request_ref, exact_response_blob, validated_output_or_null, validation_issues, usage, timing, outcome}`. Usage includes token counts/cost if available; unavailable is null, not zero. Provider internal state and hidden reasoning are not fabricated or required.

`ContextManifest` records ordered included items, exact serialized payload refs, lengths/token counts where measurable, omitted candidate refs/reasons, pinned source/case versions and access/redaction policy. All data used in a model input must be accounted for here. Non-retrieved sources remain discoverable through the full snapshot membership rather than being copied into every prompt.

## 7. Component-by-component interfaces

The following call signatures omit `CommandContext` and `ServiceResult<T>` for readability; **all calls use both**. Each producer owns validation of its output and each consumer revalidates version/access before use. C11 mediates all durable state transitions.

### C00 — CLI and human interface

**Accepts:** `AcquireCommand`, `ImportCaseCommand`, `BuildIndexCommand`, `StartRunCommand`, `InspectCommand`, `SubmitReviewCommand`, `ExportCommand`, `ReplayCommand`, `EvaluateCommand`. Each selects explicit case/corpus/profile versions and actor session; paths are restricted to configured intake/output roots.

**Produces:** CommandReceipt with command ID, accepted/rejected state, operation/run refs and issues. Display views include all-asset coverage, unused/quarantined evidence, report qualifications and actual review state.

**Control:** Calls C01/C05/C06/C09/C13/C14/C16; never writes tables directly. The model has no access to the trusted human review handler. CLI design examples are planned `uv run recycleguard case import`, `run start`, `review submit`, `audit export`; these commands are not implemented yet.

### C01 — Source acquisition and dossier intake

**Calls:** `register_source(SourceLeadDraft) -> SourceLead`; `fetch_source(FetchRequest) -> FetchReceipt`; `import_batch(BatchManifest, intake_root) -> IntakeResult`.

**Inputs:** URLs/declared assets, permitted access policy and optional expected digests. HTTP policy is configured by the operator, not model-provided arbitrary headers. Fetch redirects and final URL are recorded; content type/size are validated.

**Outputs:** Receipts for every declared and discovered item; FetchReceipt includes attempt times, final URL, HTTP status/error, response metadata and artifact revision if bytes were received. `IntakeResult` includes receipts, discovered-extra refs and missing declarations.

**Side effects/dependencies:** C02 stores exact bytes; C11 commits attempts/receipts. Retryable network failures retain attempts. No runtime agent network browsing or authenticated CPCB scraping is exposed by this interface.

### C02 — Immutable artifact store and catalog

**Calls:** `put_artifact(ArtifactDraft, bytes_stream) -> ArtifactRevision`; `read_blob(BlobRef, access_scope) -> permitted bytes`; `register_derivative(parent_refs, bytes, transformation) -> ArtifactRevision`.

**Inputs:** Raw bytes, source/intake metadata, permissions and rights state. Hash is computed from received bytes, not trusted from caller alone.

**Outputs:** Exact content-addressed blob and artifact revision; derivative has transformation/configuration/parent refs. Identical content may share byte storage but retains origin/access records.

**Side effects/dependencies:** Atomic blob placement then C11 catalog transaction. Denied reads emit audit metadata without exposing bytes. No in-place overwrite or delete endpoint in v1.

The underlying `write_blob` primitive only writes/hashes bytes; it does not recursively start another audited service operation. C11 uses this primitive to persist its own request/result/event payloads. Catalog registration and domain events are audited once by the enclosing operation, avoiding a C02–C11 recursion.

### C03 — Extraction

**Call:** `extract(artifact_revision_id, adapter_id, adapter_version, configuration_digest) -> ExtractionResult`.

**Inputs:** Permitted immutable asset and explicit adapter. Unknown template is an issue, not an invitation to try incompatible schemas until one appears to fit.

**Outputs:** All observations, text/table derivatives, page/row coverage and issues, including failed/blank/excluded pages. Expected and discovered counts are explicit.

**Side effects/dependencies:** C02 stores derivatives; C11 commits extraction metadata. Retry creates a new extraction revision if adapter/configuration changes; same version/input is idempotent. Original files are never changed by extraction or injection detection.

### C04 — Normalization and fact relationships

**Call:** `normalize(extraction_ids, case_scope, adapter_mapping_version) -> NormalizationBatch`.

**Inputs:** Observations, approved mapping/identity assertions and schema version. Parse normalization is separate from legal eligibility approval.

**Outputs:** Typed records, explicit ObservationDisposition entries (`ACCEPTED | QUARANTINED | EXCLUDED | OUT_OF_SCOPE`), equivalence/link assertions and unresolved conflicts. Each observation gets one normalization disposition; derived records may depend on many observations.

**Side effects/dependencies:** Commits immutable record revisions through C11. No name-only merge or timestamp-hash-only dedup. A proposed correction creates a new assertion; it does not silently replace source evidence.

### C05 — Case/corpus snapshots and reviewed profiles

**Calls:** `publish_case(scope, intake_and_normalization_refs, expected_parent) -> FrozenSnapshot`; `publish_corpus(source_revision_refs, applicability_refs) -> FrozenSnapshot`; `approve_profile(profile_draft, human_review_ref) -> CalculationProfile`; `reopen_case(parent, added_or_revised_refs, reason) -> FrozenSnapshot`.

**Inputs:** Complete manifests including unavailable/uncertain members, checked source/profile references and trusted review decisions.

**Outputs:** Immutable snapshots with content digests, coverage and parent lineage. Reopening does not mutate an old snapshot or its approvals.

**Side effects/dependencies:** C11 atomic publication and version checks. Corpus may contain incomplete notice leads labelled as such; they cannot automatically activate calculation rules. Profiles need explicit approval separate from corpus inclusion.

### C06 — Index construction

**Call:** `build_index(corpus_snapshot_id, retrieval_configuration_id) -> IndexManifest`.

**Inputs:** Frozen clause/table revisions, access eligibility and exact index/model settings. Wrong-regime and unreviewed content is separated and labelled.

**Outputs:** FTS index, optional vectors, membership/ranking configuration and integrity manifest. Every clause has an indexed/excluded/unindexable disposition.

**Side effects/dependencies:** Uses C10 for permitted external embeddings if enabled; saves artifacts through C02 and publication through C11. FTS absence fails capability preflight; no silent replacement with an unrelated search backend. Never import oracle/test labels into the corpus.

### C07 — Retrieval and evidence grading

**Calls:** `search_rules(SearchRulesRequest) -> RetrievalAttempt`; `get_source_passage(provision_version_id, expansion_policy: ExpansionPolicy) -> EvidenceBundle`; `resolve_locator(LocatorLookupRequest) -> EvidenceBundle`; `grade_evidence(bundle_id, question, basis) -> EvidenceGrade[]`.

**Inputs:** Run-pinned corpus/index, actor scope, finding question, reviewed temporal basis and bounded expansion settings.

**Outputs:** Full candidates, dispositions, context expansions and grades. `EvidenceBundle` contains exact passages, parents/footnotes, provenance and applicability qualifiers, not only excerpt text.

**Side effects/dependencies:** C11 records attempts; C10 may assess direct support under a constrained schema. Graph traversal is bounded. An unresolved grade returns an explicit issue/reformulation request; it never silently replaces governing law with a lower-authority passage.

### C08 — Deterministic domain tool service

**Accepts:** Validated allowlisted operations over pinned records; no raw model SQL or shell.

| Operation | Input payload | Output payload |
| --- | --- | --- |
| `read_scope` | case version | CaseScope + coverage |
| `list_evidence` | case/corpus snapshot, typed filters, page cursor | Page of metadata/refs, total count/full manifest |
| `inspect_evidence` | artifact/observation/record refs | permitted raw/parsed values, provenance and issues |
| `check_identity_capability` | entity/registration/category refs, event basis | structured matches/conflicts/unresolved checks |
| `check_product_sales` | mapping/sales refs, period | reviewed totals and mapping/coverage issues; no unsupported target generation |
| `load_obligations` | bucket IDs/profile | supplied targets, adjustments and historical buckets |
| `trace_certificate` | certificate/event refs | observations, event assertions, equivalence and allocation history |
| `match_commercial` | commercial refs, event refs | link assertions, mismatches and pending evidence |
| `compute_reconciliation` | CalculationRequest | CalculationResult |
| `compare_versions` | explicit snapshot/result/draft pairs, compare kind | typed deltas with before/after refs and uncertainty |
| `compare_return_draft` | draft revision, calculation IDs, section dispositions and deadline refs | ReturnReadinessComparison with bucket deltas, missing/excluded/unsupported sections and scoped readiness |

**Side effects:** Domain tools write only new results/derivations, never source records, profiles, reviews or official portal state. Operations may compose shared functions but must report suboperation dependencies and total budget cost. All inputs considered and excluded remain in archived results.

### C09 — Bounded workflow/orchestrator

**Calls:** `start_run(RunSpec) -> RunState`; `advance(run_id, expected_state_version) -> TurnManifest`; `resume(run_id, checkpoint_ref) -> RunState`; `cancel(run_id, reason) -> RunState`.

`RunSpec` pins case/corpus/profile/index versions, code revision, dependency lock digest, adapter/tool/prompt/model configurations, retrieval/audit/security policies, topology, experiment variant and all budgets; optional `parent_run_id` links an explicitly authorized correction/re-run. `RunState` stores run status, current turn, pending finding queue, result/finding refs, consumed budgets, stop reason, review_outcome and last committed audit sequence.

**Outputs:** Turns, finding revisions, calculations and review-ready report refs. The investigator produces only `ActionProposal = {action_kind, allowed_operation, typed_arguments, finding_id, plan_ref, concise_reason, evidence_refs}`. The dispatcher validates capability and budget before execution.

`PlanRecord = {plan_id, revision, previous_plan_ref, finding_id, objective, hypotheses, proposed_checks, expected_evidence, stopping_criteria}` is persisted **before** action. `ObservationAssessment = {operation_ref, plan_ref, observation_refs, verdict: SUPPORTS | REFUTES | WEAK | NO_PROGRESS | UNKNOWN, weak_result_or_mistake, next_check_or_stop, revised_plan_ref}` is persisted after the observation. A revised plan references its predecessor and a specific observation; when no revision is made, revised_plan_ref is null and the assessment records an explicit continuation or stop. These are concise visible decision records, not private model chain-of-thought.

**Control:** Mandatory deterministic preflight → investigation → drafting → verification → human review or qualified closure. Every turn has frozen input/output state refs. Restarts use committed operations and preserve budgets; no duplicate application of completed review/derivation operations.

**Statuses:** `CREATED`, `PREFLIGHT`, `INVESTIGATING`, `DRAFTING`, `VERIFYING`, `AWAITING_REVIEW`, `COMPLETED`, `BLOCKED_INPUT`, `BLOCKED_OUTPUT`, `FAILED`, `CANCELLED`. `stop_reason` separately identifies `RESOLVED_WITHIN_SCOPE`, `NO_NEW_EVIDENCE`, `EXPERT_REVIEW_REQUIRED`, `BUDGET_EXHAUSTED`, `CYCLE_DETECTED`, `PROVIDER_FAILURE`, `AUDIT_FAILURE`, `REVIEW_REJECTED`, `CHANGES_REQUESTED` or `MANUAL_CLOSURE`. Exhaustion can finish a qualified report; it cannot mark uncertain findings reconciled.

`review_outcome` is `NOT_REQUESTED | PENDING | APPROVED | REJECTED | CHANGES_REQUESTED | ESCALATED | CLOSED_WITHOUT_DECISION`, separate from RunStatus. After a trusted C13 decision: APPROVE transitions AWAITING_REVIEW to COMPLETED; REJECT to BLOCKED_OUTPUT with REVIEW_REJECTED; REQUEST_CHANGES to BLOCKED_OUTPUT with CHANGES_REQUESTED; ESCALATE remains AWAITING_REVIEW/ESCALATED awaiting an external reviewer event. Explicit authorized manual closure may complete with CLOSED_WITHOUT_DECISION and MANUAL_CLOSURE, never APPROVED. Terminal runs do not resume silently: corrections create a new authorized RunSpec with parent_run_id and new case version if evidence changed. The state diagram in SYSTEM_DESIGN §7.2 must cover every RunStatus and these review transitions.

### C10 — Model and embedding gateway

**Calls:** `invoke(ModelCallRequest) -> ModelCallResult`; `embed(EmbeddingRequest) -> EmbeddingResult`.

**Inputs:** Exact access-cleared/redacted content and pinned provider/model/schema settings. Only this service performs provider calls; no component reaches a provider outside audit capture.

**Outputs:** Exact response/vector artifacts, validated typed output or issues, usage/latency, provider request reference and terminal/unknown outcome. Invalid structured output receives one budgeted retry if policy permits; malformed responses remain archived.

**Side effects/dependencies:** C11 commits intent before dispatch and response/error after. Credentials are never archived. Model proposals cannot supply human authentication, approve profiles, alter record quantities or invoke unrestricted code. Provider randomness means a new call is a new attempt, not deterministic replay.

### C11 — Audit kernel and commit coordinator

**Calls:** `begin_operation(context, input_blob, expected_state) -> OperationReceipt`; `commit_operation(result, domain_mutations, audit_payloads) -> CommitReceipt`; `record_turn(TurnManifest) -> CommitReceipt`; `verify_stream(stream_id) -> IntegrityResult`.

**Inputs:** Canonical payload blobs, trusted actor/operation identity, expected state version and limited declared mutations owned by the component. Components cannot submit writes to tables they do not own.

**Outputs:** Durable ordered events, operation results, new state version and commit sequence. Input/output blobs must exist and match their hashes before references are committed.

**Control:** One writer queue, SQLite transaction for results + domain changes + events, durable blob protocol before commit. `AUDIT_UNAVAILABLE` blocks dispatch and terminal report publication. A hash chain detects tampering relative to an external/retained anchor; it is not a claim of incorruptible storage.

Full event and turn formats are specified in Section 8.

### C12 — Report builder and claim/citation verifier

**Calls:** `build_report(findings, calculation_refs, coverage_ref, run_id) -> ReportRevision`; `verify_report(report_revision_id) -> VerificationResult`.

**Inputs:** Structured claims, exact result/provision refs, scope/coverage and model-proposed explanations where allowed.

**Outputs:** Report JSON, deterministic Markdown/HTML render, claims/citation matrix, verified/qualified/blocked result and issue list. Verification resolves dependency versions and locators, validates numerical references and discloses all unresolved/missing evidence. An optional narrative LLM uses C10.

**Side effects:** Store all drafts and rejected claims. The final `review_dependency_digest` covers report bytes, claims, calculations, case/corpus/profile versions and coverage. Numerical agreement and locator validity alone do not establish semantic/legal correctness; unsupported interpretations remain qualified or blocked.

C12 must explicitly test generated claims for a legal-compliance verdict, allegation of intent/fraud/concealment, and compensation/penalty amount. Such agent-authored conclusions are prohibited in v1, regardless of a fluent rationale or attached citation: emit `PROHIBITED_VERDICT`, reject the claim and block publication until removed. A faithful attributed source quotation is distinct from a new system verdict and must retain its scope. A generic “qualified” label cannot allow a prohibited conclusion through. The checker combines structured claim classification, rule checks and review; it must not claim that keyword matching alone proves semantic safety.

`ReportSection = {section_id, title, claim_ids, evidence_refs, structured_content_ref, coverage_state}`. Reports contain these eight section IDs in order: `CASE_SCOPE`, `EVIDENCE_COVERAGE`, `BUCKET_RECONCILIATION`, `FINDING_REGISTER`, `INVESTIGATION_HISTORY`, `NEXT_ACTIONS`, `HUMAN_DECISIONS`, `LIMITATIONS_AND_REPRODUCIBILITY`. Empty/not-applicable content is explicitly explained, not omitted. NEXT_ACTIONS includes named owner and priority; INVESTIGATION_HISTORY references plans, weak observations/mistakes, corrections and unresolved hypotheses. Sections do not replace the full audit inventory.

### C13 — Authenticated human review

**Calls:** `create_review_packet(report_revision_id) -> ReviewPacket`; `submit_review(packet_id, expected_dependency_digest, ReviewDecision) -> ReviewRecord`; `attach_acknowledgment(artifact_revision_id, reviewed_link) -> AcknowledgmentRecord`.

`ReviewPacket` contains full report/result/snapshot refs, dependency digest, proposed action deltas, unresolved items and permitted review actions. `ReviewDecision` contains `APPROVE | REJECT | REQUEST_CHANGES | ESCALATE`, authenticated reviewer, reason and timestamp. `APPROVE` means approval of this working paper/action proposal, never official compliance or successful filing.

**Permission:** Only authenticated human sessions with reviewer capability can submit decisions/profile approvals. The investigator can request a packet but cannot call a privileged decision endpoint. A local demo username is recorded as local asserted identity; stronger authentication is required before real multiuser deployment.

**Side effects:** Append a version-bound decision; changed dependencies yield `STALE_REVIEW`. Acknowledgment data remains a supplied artifact/assertion with validation state; do not generate an official receipt from a report hash.

C13 emits the authenticated decision event; C09 projects the specific transition defined above. Recording REJECT, REQUEST_CHANGES or ESCALATE must not automatically mark the run COMPLETED. A decision submitted against a closed/stale packet is rejected rather than reviving its run; correction/review uses a new authorized packet/run.

### C14 — Audit export, publication export and replay

**Calls:** `export_bundle(BundleRequest) -> BundleManifest`; `verify_bundle(bundle_id) -> IntegrityResult`; `replay(ReplayRequest) -> ReplayResult`.

`BundleRequest` selects `COMPLETE_LOCAL | PUBLICATION`, explicit run/case versions and export policy. Complete-local export requires permission to all included raw material; denied items produce an explicit partial-export result, not a claim of completeness. Publication recursively checks rights/sensitivity of originals, excerpts, prompts, responses and derivatives.

**Outputs:** Manifest of included objects/hashes, excluded objects or permitted opaque omission refs, reasons, attribution, dependency heads and validation results. No hidden oracle labels in either investigator bundle. A research release may carry a separate evaluator dataset under its own access/license policy.

**Replay:** `ARTIFACT` reconstructs recorded state without calls; `RECOMPUTE` compares deterministic outputs under pinned versions; `MODEL_RERUN` creates a new measured run. Missing objects or dependency mismatch is a failure, never silently substituted with latest online content.

### C15 — Synthetic generator and renderer

**Call:** `generate(GeneratorSpec) -> GeneratedDatasetReceipt`.

`GeneratorSpec` supplies code/schema version, reviewed profile, deterministic seed, dossier-size limits, templates, split policy and fault configuration. It resides only in the generator/evaluator environment.

**Outputs:** Visible case directories conforming to Section 5; hidden GenerationManifest/world/corruptions/oracle artifacts in a separate root; generator invariant results and rights/attribution manifest. Receipt to runtime includes only visible inputs and checksums.

**Side effects:** Never writes hidden truth to runtime roots. Faults operate on visible renderings/records with recorded transformations; true answers are independently reviewed. Generation success does not imply legal-profile approval or realism validation.

### C16 — Evaluation coordinator

**Call:** `evaluate(EvaluationSpec) -> EvaluationReport`.

`EvaluationSpec` pins visible dataset/split, oracle version, code/profile/corpus/model/prompt/tool versions, variant budgets, repetition count, scorer/rubric version and isolated runtime configuration.

**Control:** Launch investigator with visible-only mounts and no generator/oracle/held-out-label capability. Close run artifacts, then load oracle in evaluator process for scoring. Keep evaluator logs out of agent/reviewer browsing paths. A developer's host filesystem permissions alone are not a benchmark isolation mechanism; use a constrained child runtime/container or equivalent enforced boundary and test attempted access.

**Outputs:** Per-case/trial results, exact counts/denominators, variant costs, error categories, repeated-run reliability and isolation checks. Failures are scored as failures or explicitly invalid trials under a predeclared rule; never dropped to improve metrics. Oracle changes invalidate comparisons unless the entire affected trial set is rescored.

## 8. Audit event, operation and turn contracts

### 8.1 AuditEvent

```text
AuditEvent {
  event_id: ID
  stream_id: ID
  sequence: integer >= 1
  event_type: string
  recorded_at: Timestamp
  actor: ActorRef
  command_id: ID
  operation_id: ID
  attempt_id: ID
  case_version_id: ID | null
  run_id: ID | null
  turn_id: ID | null
  input_refs: BlobRef[]
  output_refs: BlobRef[]
  dependency_refs: EvidenceRef[]
  payload_blob: BlobRef
  previous_event_hash: Digest | null
  event_hash: Digest
}
```

Sequence is unique/monotonic within a stream. The first previous hash is null; subsequent hashes match the previous event. Compute `event_hash` from the canonical event excluding its own `event_hash`, including payload/input/output digests. Creation time and sequence are service-controlled. Duplicate writes return the existing committed result under the idempotency rule.

Required event families include acquisition intent/result/failure; artifact registered/derivative; extraction coverage; normalization disposition; snapshot/profile publication; index build; retrieval attempt/grade; turn start/end/failure; tool/model intent/result/error/unknown; finding revision; report draft/verification; review decision; export/integrity; run stop/recovery. Payloads contain the complete details or durable blob references, not truncated console logs.

### 8.2 Operation lifecycle

```text
REQUESTED -> VALIDATED -> STARTED -> SUCCEEDED | PARTIAL | FAILED |
                                      REJECTED | CANCELLED | OUTCOME_UNKNOWN
```

Validation rejection can terminate before STARTED. Commit the intended request before external dispatch. Commit domain mutations/results and their terminal event together. A started operation with no terminal event is pending/unknown on recovery; the recovery process records what is known, never retroactively invents success.

Terminal operation `SUCCEEDED` maps to service status `SUCCESS`; the other terminal names map directly. Operation state and run state are separate enumerations.

### 8.3 TurnManifest

```text
TurnManifest {
  turn_id: ID
  run_id: ID
  turn_index: integer >= 1
  previous_turn_id: ID | null
  input_state_blob: BlobRef
  output_state_blob: BlobRef | null
  pinned_membership_refs: ID[]
  operation_ids_in_order: ID[]
  context_manifest_ids: ID[]
  retrieval_attempt_ids: ID[]
  calculation_ids: ID[]
  finding_revision_ids: ID[]
  plan_refs: ID[]
  observation_assessment_refs: ID[]
  plan_revised: boolean
  coverage_summary_blob: BlobRef
  budget_before: object
  budget_after: object
  turn_status: STARTED | COMPLETED | FAILED | CANCELLED
  concise_decision: string | null
  stop_reason: string | null
  first_event_sequence: integer
  last_event_sequence: integer
}
```

Budget objects have schema-defined tool/model calls, retries, token/cost usage and elapsed time with null for unavailable provider metrics. A failed turn still preserves completed and pending operations. The next turn cannot reference a state that has not been durably committed.

For investigative turns, plan refs precede action events and observation assessments follow result events; `plan_revised` agrees with the linked revision chain. A trace must demonstrate an actual weak-result/mistake observation and adaptation in the corresponding feedback-loop fixture, rather than merely filling explanation fields after the run.

### 8.4 Full versus selected evidence

The audit must support these questions independently:

1. What was expected, received, missing or inaccessible at intake?
2. What pages/rows were parsed, quarantined, ignored or failed?
3. Which exact observations/records/provisions belonged to this frozen run?
4. Which were eligible, scored, selected, expanded, rejected or not considered for a query?
5. Which exact bytes/messages were sent to the model, and which were omitted for context limits?
6. Which tool/model outputs were returned, including unused results and validation failures?
7. Which claims were drafted, rejected, revised and approved?

Membership/disposition references provide completeness without copying all bytes each turn. A report's citation list is never used as a surrogate for the evidence inventory. Private raw data retained locally may be omitted from a public export only through an explicit export disposition.

## 9. End-to-end data and control flow

### 9.1 Normative corpus path

`C00 -> C01 source leads/fetch -> C02 originals -> C03 clauses/tables/coverage -> C04 typed metadata -> C05 reviewed applicability + frozen corpus -> C06 index -> C07 retrieval`.

Every acquisition/extraction/index operation is recorded through C11. C07 consumes only pinned index/provision revisions; changes in an online source trigger a new acquisition/review/snapshot, never mutation of an active run.

### 9.2 Operational case path

`C00 -> C01 intake receipts -> C02 originals -> C03 observations -> C04 records/equivalence -> C05 frozen case -> C08 preflight/results -> C09 investigation -> C12 report -> C13 review -> C14 bundle`.

C09 calls C07/C08 through a capability-limited dispatcher and C10 for structured decisions. Additional evidence or human corrections create a new case version, not an unlogged modification of the active frozen input. A run can derive new findings/results over its existing snapshot; that differs from adding new source material.

### 9.3 Benchmark path

`C15 -> visible dossiers -> normal case path`. Separately, `C15 -> hidden world/oracle -> C16 scorer after runtime completion`. No edge from hidden truth to C04/C07/C09/C10/C12/C13.

### 9.4 Per-action order

1. C09 records a proposed action and current budget/state.
2. Dispatcher validates tool allowlist, arguments, access, pinned versions and remaining budgets.
3. C11 commits intent + exact request refs.
4. Component executes and writes full output blobs through C02.
5. C11 atomically commits result, domain derivations and terminal audit event.
6. C09 updates budget/state by committed references, records selected context and advances/checkpoints.

No state transition can skip step 5. A storage failure after execution leaves a recoverable unknown outcome. A retry reuses the logical operation with a new attempt and does not conceal the first attempt.

## 10. Contract acceptance matrix

| Boundary | Required fixture / failure test |
| --- | --- |
| Common envelope | Unknown schema field, wrong version, forged actor and mismatched idempotency key rejected. |
| C01–C03 | Duplicate bytes, undeclared file, missing page, invalid CSV and failed OCR are all inventoried. |
| C03–C04 | Raw source survives normalization; every observation has a disposition; ambiguous identifiers cannot hard-join. |
| C04–C08 | Same certificate with multiple events retained; ambiguous equal-time transfers unresolved; conservation enforced. |
| C05–C07 | Clause-level amendment, historical exception and missing order handled without source-wide blanket expiry. |
| C06–C07 | Index membership/version mismatch blocks search; lexical/dense windows and NOT_SCORED candidates preserved. |
| C08–C12 | Exact decimal strings round-trip; prior/current quantities and transfer/adjustment evidence cannot double-count. |
| C09–C11 | Crash before/after intent/result commit, timeout, retry and checkpoint lag remain auditable and recoverable. |
| C10–C11 | Exact redacted request/response stored; usage unknown remains null; unauthorized tool proposal rejected. |
| C12–C13 | Invalid citation/numeric claim blocks or qualifies report; edited dependencies invalidate approval. |
| C13 permission | Model/service caller cannot create a trusted HUMAN approval or filing acknowledgment. |
| C09/C13 review transitions | All eleven RunStatus values are represented; APPROVE completes, REJECT/REQUEST_CHANGES block output, ESCALATE waits, and manual closure records no invented approval. |
| C14 | Local completeness verified; public exports inspect derivatives/prompts and enumerate restricted omissions. |
| C15–C16 | Hidden labels/seeds/oracle inaccessible through files, search, logs, cache and UI; isolation attempts recorded. |

Implement these focused tests with shared fixtures before component integration. The examples above describe contracts, not evidence that the current repository already passes these tests.

## 11. Task coverage and change control

| Officer tasks | Contract owners |
| --- | --- |
| T01 scope | C00/C05/C08 |
| T02 applicable sources/calendar | C01/C03/C05/C06/C07 |
| T03 identity/registration | C04/C08 |
| T04 evidence ingestion | C01/C02/C03/C04 |
| T05 product/weights; T06 history | C04/C08, reviewed inputs in v1 |
| T07 obligation baseline | C05/C08 |
| T08 recycler capability | C04/C08 |
| T09 commercial matching; T10 lifecycle | C04/C08 |
| T11 investigation/reconciliation | C07/C08/C09/C10 |
| T12 draft working papers | C08/C12 |
| T13 human review | C13, with trusted C00 session |
| T14 submission/rectification | Human outside runtime; C13 stores supplied acknowledgment |
| T15 archive/audit | C02/C11/C14 |
| T16 reopen | C05/C09/C13/C14 |

When a producer changes a contract, update the boundary model, generated schema, consumer, fixtures and both design documents in the same reviewed change. Never change a field name in one component and add speculative fallback parsing in another. The stored `contract_version`, snapshot versions and full audit references allow older runs to remain interpretable.

## 12. Remaining boundary payloads and required fields

These field lists complete the named service payloads used above. They inherit the shared primitive types, null/optional rules and ServiceResult envelope. `*_refs` are typed ID/EvidenceRef arrays as appropriate; `*_blob` fields are BlobRef. IDs in these payloads always resolve to the exact revision selected, never a mutable “latest” alias.

| Payload | Required fields / boundary semantics |
| --- | --- |
| `CommandReceipt` | `command_id`, `accepted: boolean`, `operation_ids: ID[]`, `run_id: ID \| null`, `issues: Issue[]`. |
| `FetchRequest` | `source_lead_id`, `url`, `access_policy_id`, `max_bytes: integer`, `timeout_seconds: integer`, `expected_digest: Digest \| null`. Policy defines redirects/hosts; caller cannot override it. |
| `FetchReceipt` | `fetch_attempt_id`, `source_lead_id`, `started_at`, `finished_at`, `final_url`, `http_status: integer \| null`, `response_metadata_blob`, `asset_receipt_id`, `issues`. |
| `BatchManifest` | `batch_id`, `declared_assets` containing paths/types/expected digests, `case_scope_draft`, `adapter_versions`, `optional_table_dispositions`, `access_policy_id`. The service independently inventories actual intake paths. |
| `IntakeResult` | `batch_id`, `asset_receipt_ids`, `declared_count`, `discovered_count`, `undeclared_receipt_ids`, `missing_receipt_ids`, `inventory_blob`, `coverage_state`. |
| `NormalizationBatch` | `batch_id`, `extraction_ids`, `record_revision_ids`, `observation_dispositions_blob`, `equivalence_assertion_ids`, `coverage_blob`, `mapping_version`, `issues`. |
| `EvidenceBundle` | `bundle_id`, `retrieval_attempt_id: ID \| null`, `passage_refs`, `parent_context_refs`, `applicability_refs`, `completeness`, `full_content_blob`, `grade_refs`, `issues`. |
| `StructuredCheckResult` | `check_id`, `check_kind`, `input_membership_blob`, `results[]` each containing target refs, `verdict: PASS \| FAIL \| UNKNOWN`, reasons and evidence; `tool_version`, `issues`. Used by identity/capability/product/transaction checks. |
| `ComparisonResult` | `comparison_id`, `compare_kind: CASE \| ACCOUNT_SNAPSHOT \| CALCULATION \| RETURN_DRAFT`, exact left/right refs, `delta_records_blob`, `unchanged_members_digest`, `coverage_blob`, `tool_version`, `issues`. Matching is versioned and does not merge conflicting facts. |
| `BudgetPolicy` | `max_tools_per_finding`, `max_tools_per_case`, `max_model_calls`, `max_query_reformulations`, `max_report_repairs`, `max_retries_per_operation`, `max_input_tokens`, `max_output_tokens`, `max_elapsed_seconds`, `max_cost_or_null`, `pricing_snapshot_ref_or_null`. All counts/ceilings are positive, except an optional feature may have zero permitted calls. |
| `ReportRevision` | `report_id`, `report_revision_id`, `run_id`, `section_refs: ID[]`, `claim_ids`, `finding_revision_ids`, `calculation_ids`, `coverage_ref`, `report_json_blob`, `rendered_blobs`, `review_dependency_digest`, `supersedes_report_revision_id: ID \| null`. Section refs resolve to the eight required ReportSections. |
| `VerificationResult` | `verification_id`, `report_revision_id`, `verdict: PASS \| QUALIFIED \| BLOCKED`, `checks_blob`, `issues`, `verifier_version`, `verified_dependency_digest`. |
| `ReviewPacket` | `packet_id`, `report_revision_id`, `review_dependency_digest`, `input_snapshot_refs`, `proposed_action_refs`, `unresolved_issue_refs`, `permitted_decisions`, `created_at`. |
| `ReviewRecord` | `review_id`, `packet_id`, `review_dependency_digest`, `decision`, `authenticated_reviewer_ref`, `reason`, `recorded_at`, `supersedes_review_id: ID \| null`. A stale old approval remains historical; it never approves a changed dependency set. |
| `AcknowledgmentRecord` | `acknowledgment_id`, `artifact_revision_id`, `linked_case_version_id`, `linked_report_revision_id: ID \| null`, `claimed_external_reference`, `validation_state`, `review_ref`. No automatic filing-success inference. |
| `BundleManifest` | `bundle_id`, `bundle_kind`, `selected_run_refs`, `included_objects_blob`, `omission_dispositions_blob`, `attribution_blob`, `audit_head_refs`, `dependency_digest`, `completeness: COMPLETE_LOCAL \| QUALIFIED_PUBLIC \| PARTIAL`, `integrity_result_ref`. |
| `IntegrityResult` | `check_id`, `target_ref`, `checked_at`, `verdict: PASS \| FAIL \| PARTIAL`, `checked_count`, `missing_or_mismatched_refs`, `issues`, `verifier_version`. |
| `ReplayRequest` | `bundle_id`, `mode: ARTIFACT \| RECOMPUTE \| MODEL_RERUN`, `dependency_environment_ref`, `access_scope_id`. No network acquisition is permitted in ARTIFACT mode. |
| `ReplayResult` | `replay_id`, `mode`, `source_bundle_id`, `reconstructed_state_refs`, `comparison_refs`, `new_run_id: ID \| null`, `integrity_result_ref`, `issues`. |
| `GeneratedDatasetReceipt` | `dataset_version`, `visible_manifest_ref`, `visible_case_ids`, `generation_integrity_ref`, `hidden_bundle_ref`. Only the evaluator receives `hidden_bundle_ref`; the runtime intake projection omits the field. |
| `EvaluationReport` | `evaluation_id`, `evaluation_spec_digest`, `trial_ids`, `scores_blob`, `counts_and_denominators_blob`, `costs_blob`, `isolation_results_blob`, `invalid_trial_reasons_blob`, `versions_manifest_blob`. |

`SourceLeadDraft` is SourceLead without generated ID/state/acquired-artifact fields. `ArtifactDraft` is ArtifactRevision without generated IDs/blob/ingested timestamp. The receiving service generates those fields. Profile/case drafts cannot assert that they are already approved.

Request types such as `StartRunCommand`, `EvaluationSpec` and `GeneratorSpec` are projections of their explicitly described specifications, plus CommandContext. Path roots, actor privileges, retry counts and secrets are injected by trusted configuration, never accepted from a model argument. Generic `object` in a versioned payload means a separately declared adapter/configuration schema; production implementations must register that schema, not accept arbitrary dictionaries.

With a monetary ceiling, configuration must pin a pricing table and a conservative estimate before dispatch. Without known prices, use hard call/token/time bounds and report monetary cost as unavailable; do not claim that an unenforceable currency ceiling was honored. Retries and embedding calls are charged to the same run or corpus-build budget as their original operation.

## 13. Research-tool alias reconciliation

Earlier research names describe capabilities, not extra privileged tools. The dispatcher maps them to these contracts; no fallback guessing of argument shapes or permissions is allowed.

| Research name | Contract operation / owner |
| --- | --- |
| `read_case_manifest` | C08 `read_scope` plus pinned membership metadata. |
| `list_evidence` | C08 `list_evidence`. |
| `inspect_document`, `get_record` | C08 `inspect_evidence` over exact permitted refs. |
| `validate_records` | C04 normalization validation; C08 consumes its frozen issues. |
| `compare_identity`, `lookup_registration_evidence`, `check_capability` | C08 `check_identity_capability`, with explicit check kind. |
| `lookup_product_mapping`, `compare_weight_basis`, `aggregate_sales` | C08 `check_product_sales`, with explicit mapping/weight/history check kind. |
| `load_obligations` | C08 `load_obligations`. |
| `compare_obligation_basis` | C08 `compare_versions` on obligation assertions/results. |
| `get_certificate_history`, `check_credit_events` | C08 `trace_certificate` and its lifecycle/equivalence checks. |
| `match_transactions` | C08 `match_commercial`. |
| `compute_reconciliation` | C08 `compute_reconciliation`. |
| `compare_snapshots`, `diff_case_evidence` | C08 `compare_versions` with ACCOUNT_SNAPSHOT or CASE kind. |
| `compare_return_draft` | C08 `compare_return_draft`; emits ReturnReadinessComparison. |
| `search_rules` | C07 `search_rules`. |
| `get_source_passage(provision_version_id, expansion_policy)` | C07 exact-ID passage lookup. |
| `get_source_passage(source_id, clause_locator)` | C07 `resolve_locator(LocatorLookupRequest)`; explicit alias, not an overloaded shape guess. |
| `grade_retrieved_evidence` | C07 `grade_evidence`. |
| `validate_report`, `verify_evidence_links` | C12 `verify_report` and its citation/claim checks. |
| `prepare_action_note` | C12 `build_report`, NEXT_ACTIONS section; C13 may package it for human review. |
| `create_review_packet`, `record_review_decision` | C13 packet/decision handlers; the latter remains human-only. |
| `attach_acknowledgment` | C13 `attach_acknowledgment`. |
| `export_case_bundle` | C14 `export_bundle`. |
| `reopen_findings` | C05 `reopen_case` plus C08 `compare_versions`; C09 creates superseding affected finding revisions in a new run. Old findings/reviews remain unchanged. |

`ReturnReadinessComparison = {comparison_id, draft_revision_id, calculation_refs, bucket_deltas, section_dispositions: ReturnSectionDisposition[], deadline_refs, readiness: READY_WITHIN_CHECKED_SECTIONS | NOT_READY | READINESS_UNDETERMINED, scope_limits, issues}`. Excluded/unsupported applicable sections prevent a claim of whole-return readiness even when all numerical comparisons match.
