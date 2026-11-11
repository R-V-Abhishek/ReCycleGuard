# Document 1: Overall Architecture Guide

## 1. System Purpose & Operational Boundary
ReCycleGuard is an audited, agentic compliance-verification system for Indian E-Waste Extended Producer Responsibility (EPR) regulations (governed by CPCB under E-Waste Management Rules, 2022).
- **Core Function**: Takes a frozen case dossier (producer filings, invoices, ledgers) and normative corpus (CPCB gazettes, guidelines), reconciles physical mass allocations per metal against statutory obligations, investigates discrepancy findings using an audited LangGraph agent, and drafts a verifiable working paper for a human reviewer.
- **Strict Boundary**: The system *never* autonomously files with CPCB, executes financial transactions, asserts legal verdicts of statutory compliance/fraud, or invents evidence.

---

## 2. Visual Architecture Diagram

```mermaid
flowchart TD
    subgraph INTAKE_AND_STORAGE["1. Ingestion & Storage Subsystem"]
        Files["Raw Case Files\n(PDFs, CSVs, JSON)"] --> Acquisition["Acquisition & Receipts\n(recycleguard/intake/acquisition.py)"]
        Acquisition --> BlobStore["Content-Addressed BlobStore\n(storage/blob_store.py)"]
        BlobStore --> AuditKernel["Append-Only Audit Kernel & Catalog\n(storage/audit_kernel.py, catalog.py)"]
    end

    subgraph NORMALIZATION_AND_INDEX["2. Normalization & Knowledge Subsystem"]
        BlobStore --> Extractors["Extractors (PDF, CSV, JSON)\n(recycleguard/extraction/)"]
        Extractors --> Observations["Granular Document Observations\n(contracts/extraction.py)"]
        Observations --> Normalization["Unit/Entity Normalization\n(recycleguard/normalization/)"]
        Normalization --> Snapshots["Frozen Snapshots (CASE & CORPUS)\n(recycleguard/snapshots.py)"]
        Snapshots --> IndexBuilder["FTS5 Lexical Index Builder\n(indexing/builder.py, fts_index.py)"]
    end

    subgraph AGENT_HARNESS["3. LangGraph Agent Harness (C09/C10)"]
        Snapshots --> WorkflowRunner["WorkflowRunner (LangGraph Engine)\n(workflow/runner.py)"]
        IndexBuilder --> WorkflowRunner

        subgraph LANGGRAPH_STATES["StateGraph Node Pipeline"]
            direction LR
            Preflight["preflight"] --> Investigate["investigate\n(2-phase agent loop)"]
            Investigate --> Draft["draft"]
            Draft --> Verify["verify"]
        end

        WorkflowRunner --> LANGGRAPH_STATES
        WorkflowRunner <--> Checkpointer["SqliteSaver Checkpointer\n(workflow/store.py)"]
        WorkflowRunner <--> AuditKernel
    end

    subgraph AGENT_INTERACTIONS["4. Agent Decision & Tool Execution"]
        Investigate <-->|PLAN & ASSESS| LocalModelPort["Local MLX-LM Model Port / Qwen 3.5\n(local_model.py, model_port.py)"]
        Investigate -->|Execute Action| ToolsRegistry["Audited Tool Registry (investigation.py)"]
        ToolsRegistry --> Tool1["inspect_evidence"]
        ToolsRegistry --> Tool2["lookup_locator"]
        ToolsRegistry --> Tool3["trace_certificate"]
        ToolsRegistry --> Tool4["compute_reconciliation"]
        ToolsRegistry --> Tool5["compare_return"]
        ToolsRegistry --> Tool6["search_rules (FTS5 + Grader)"]
    end

    subgraph REPORTING_AND_REVIEW["5. Reporting & Human Review Subsystem"]
        Draft --> BaselineReport["BaselineReportBuilder\n(reporting/baseline.py)"]
        Verify --> ReportVerifier["ReportVerifier (Exact Check)\n(reporting/baseline.py)"]
        ReportVerifier --> ReviewPacket["Human Review Packet\n(review/service.py)"]
        ReviewPacket --> HumanReviewer["Human Expert Reviewer"]
    end
```

---

## 3. Subsystem Breakdown & Codebase Map

| Subsystem | Key Files | Code Symbols / Classes | Core Responsibility |
|---|---|---|---|
| **Intake & Raw Storage** | [`src/recycleguard/intake/acquisition.py`](../../src/recycleguard/intake/acquisition.py)<br>[`src/recycleguard/storage/blob_store.py`](../../src/recycleguard/storage/blob_store.py)<br>[`src/recycleguard/storage/audit_kernel.py`](../../src/recycleguard/storage/audit_kernel.py) | `AcquisitionService`<br>`DiskBlobStore`<br>`AuditKernel` | Ingests untrusted files, hashes raw bytes (SHA-256), issues receipts, and commits immutable audit trails. |
| **Extraction & Normalization** | [`src/recycleguard/extraction/service.py`](../../src/recycleguard/extraction/service.py)<br>[`src/recycleguard/extraction/pdf_extractor.py`](../../src/recycleguard/extraction/pdf_extractor.py)<br>[`src/recycleguard/normalization/service.py`](../../src/recycleguard/normalization/service.py) | `ExtractionService`<br>`PdfExtractor`<br>`NormalizationService` | Parses PDF, CSV, JSON into granular `Observation` records with exact page/line locators; normalizes metal units and entity aliases. |
| **Snapshots & Profiles** | [`src/recycleguard/snapshots.py`](../../src/recycleguard/snapshots.py)<br>[`src/recycleguard/profiles.py`](../../src/recycleguard/profiles.py) | `SnapshotService`<br>`ProfileCatalog` | Freezes immutable `CASE` and `CORPUS` snapshots with sha256 digests. Pins calculation profile rules. |
| **Indexing & Retrieval** | [`src/recycleguard/indexing/builder.py`](../../src/recycleguard/indexing/builder.py)<br>[`src/recycleguard/indexing/fts_index.py`](../../src/recycleguard/indexing/fts_index.py)<br>[`src/recycleguard/retrieval/service.py`](../../src/recycleguard/retrieval/service.py) | `IndexBuilder`<br>`FTS5Index`<br>`RetrievalService` | Builds SQLite FTS5 BM25 index over normative regulatory clauses. Enforces temporal validity and multi-grade evidence evaluation. |
| **Domain Reconciler** | [`src/recycleguard/domain/reconcile.py`](../../src/recycleguard/domain/reconcile.py)<br>[`src/recycleguard/domain/arith.py`](../../src/recycleguard/domain/arith.py)<br>[`src/recycleguard/baseline.py`](../../src/recycleguard/baseline.py) | `reconcile_universe`<br>`ExactDecimal`<br>`BaselineService` | Deterministic exact decimal arithmetic: balances supported allocations vs statutory liability buckets; detects gaps. |
| **Agent Workflow Runner** | [`src/recycleguard/workflow/runner.py`](../../src/recycleguard/workflow/runner.py)<br>[`src/recycleguard/workflow/store.py`](../../src/recycleguard/workflow/store.py) | `WorkflowRunner`<br>`GraphStore` | LangGraph StateGraph engine: enforces turn bounds, model token reservations, checkpoint recovery, and idempotent state transitions. |
| **Investigation & Tools** | [`src/recycleguard/investigation.py`](../../src/recycleguard/investigation.py) | `InvestigationService`<br>`IntegratedRunner` | Integrates tool bindings (`inspect_evidence`, `lookup_locator`, `trace_certificate`, `compute_reconciliation`, `search_rules`). |
| **Model Gateway** | [`src/recycleguard/local_model.py`](../../src/recycleguard/local_model.py)<br>[`src/recycleguard/model_port.py`](../../src/recycleguard/model_port.py) | `LocalModelPort`<br>`LocalModelConfig` | Pinned loopback MLX-LM client for Qwen 3.5 9B 4-bit with byte-bound tokenizer checks and schema validation. |
| **Reporting & Review** | [`src/recycleguard/reporting/baseline.py`](../../src/recycleguard/reporting/baseline.py)<br>[`src/recycleguard/review/service.py`](../../src/recycleguard/review/service.py) | `BaselineReportBuilder`<br>`ReportVerifier`<br>`ReviewService` | Generates structured Markdown working papers; verifies mathematical & citation integrity; presents packets for human review. |

---

## 4. Architectural Invariants to Cite in the Review
1. **Deterministic Separation**: Math and report verification are purely deterministic (`arith.py`, `baseline.py`). The LLM only proposes inspection plans and evaluates evidence hypotheses.
2. **Immutable Content Addressing**: Every ingested document and internal state is hashed and stored in `DiskBlobStore` via SHA-256.
3. **No Unaudited Side-Effects**: Every tool invocation and model call requires a pre-allocated token/action budget reservation before execution, recorded in SQLite.
4. **Resilience & Idempotency**: All graph state updates use Compare-And-Swap (CAS) versions (`expected_version`). Interrupted runs resume cleanly via `WorkflowRunner.resume()`.

