"""Boundary models for C06 index construction and C07 retrieval (CONTRACTS §6.1).

Owned by Sampreeth (H05 / H06).
"""

import hashlib
from typing import Annotated, Any, Literal

from pydantic import Field

from .core import ID, BlobRef, BoundaryModel, Digest, EvidenceRef, Locator, TemporalValue
from .sources import Role

GradeVerdict = Literal["PASS", "FAIL", "UNRESOLVED"]

CandidateDispositionKind = Literal[
    "FILTERED_OUT",
    "NOT_SCORED",
    "OUTSIDE_ENGINE_WINDOW",
    "SCORED",
    "EXPANDED_CONTEXT",
    "SELECTED",
    "REJECTED_SUPPORT",
    "OMITTED_CONTEXT_BUDGET",
]


class LexicalConfiguration(BoundaryModel):
    """Configuration parameters for SQLite FTS5 lexical index."""

    tokenizer: str = "unicode61"
    bm25_k1: float = 1.2
    bm25_b: float = 0.75
    indexed_columns: list[str] = Field(
        default_factory=lambda: [
            "legal_path",
            "title",
            "text",
            "regime",
            "role_scope",
            "affected_roles",
        ]
    )


class DenseConfiguration(BoundaryModel):
    """Dense vector indexing configuration if external embeddings enabled."""

    model_name: str
    revision: str
    dimension: int
    normalize: bool = True
    tokenizer_name: str
    vector_blob_digest: Digest


class IndexManifest(BoundaryModel):
    """Integrity and membership manifest for a frozen index (CONTRACTS §6.1)."""

    index_id: ID
    corpus_snapshot_id: ID
    eligible_members_digest: Digest
    extraction_versions: dict[str, str]
    lexical_configuration: LexicalConfiguration
    dense_configuration_or_null: DenseConfiguration | None = None
    build_code_revision: str
    index_files: list[str]
    integrity_digest: Digest
    total_chunks: int = 0
    corpus_membership_digest: Digest | None = None
    index_blob: BlobRef | None = None
    retrieval_configuration_id: ID | None = None

    def pin(self):
        from recycleguard.contracts.workflow import ConfigurationPin
        from recycleguard.storage import canonical_json_bytes

        return ConfigurationPin(
            configuration_id=self.index_id,
            digest=hashlib.sha256(canonical_json_bytes(self.model_dump(mode="json"))).hexdigest(),
        )


class ExpansionPolicy(BoundaryModel):
    """Context expansion settings for retrieval evidence bundles (CONTRACTS §6.1)."""

    include_parent: bool = True
    include_table_header: bool = True
    include_footnotes: bool = True
    include_applicable_amendments: bool = True
    include_references: bool = False
    max_depth: Annotated[int, Field(ge=0, le=8)] = 2
    max_nodes: Annotated[int, Field(ge=0, le=100)] = 20


class CandidateDisposition(BoundaryModel):
    """Stage-specific candidate outcome during retrieval (CONTRACTS §6.1)."""

    candidate_ref: ID
    disposition: CandidateDispositionKind
    reason: str | None = None
    operation_ref: str | None = None
    score: float | None = None
    rank: int | None = None


class EvidenceGrade(BoundaryModel):
    """Five-dimensional evidence grade assessing candidate support (CONTRACTS §6.1)."""

    candidate_ref: ID
    authority: GradeVerdict
    temporal_fit: GradeVerdict
    direct_support: GradeVerdict
    completeness: GradeVerdict
    contradiction: GradeVerdict
    reasons: list[str] = Field(default_factory=list)
    assessed_by: str
    assessment_version: str
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)


class SearchRulesRequest(BoundaryModel):
    """Search request to frozen regulatory index (CONTRACTS §6.1)."""

    query: str
    corpus_snapshot_id: ID
    index_id: ID
    question_basis: Literal[
        "TRANSACTION_DATE", "CAPTURE_DATE", "REPORTING_PERIOD", "FILING_DATE"
    ] = "REPORTING_PERIOD"
    target_event_time: TemporalValue | None = None
    target_reporting_period: str | None = None
    target_filing_date: TemporalValue | None = None
    deadline_entry_ids: list[ID] = Field(default_factory=list)
    regimes: list[str] = Field(default_factory=list)
    roles: list[Role] = Field(default_factory=list)
    eee_codes: list[str] = Field(default_factory=list)
    top_k: Annotated[int, Field(ge=1, le=50)] = 10
    diagnostic_mode: bool = False
    expected_index_digest: Digest | None = None
    expected_corpus_membership_digest: Digest | None = None


class LocatorLookupRequest(BoundaryModel):
    """Direct locator resolution request (CONTRACTS §6.1)."""

    corpus_snapshot_id: ID
    source_alias_or_source_version_id: str
    legal_path: str
    question_basis: Literal[
        "TRANSACTION_DATE", "CAPTURE_DATE", "REPORTING_PERIOD", "FILING_DATE"
    ] = "REPORTING_PERIOD"
    applicability_context: dict[str, Any] = Field(default_factory=dict)
    expansion_policy: ExpansionPolicy = Field(default_factory=ExpansionPolicy)


class EvidenceBundle(BoundaryModel):
    """Rich evidence passage with context, provenance, and qualifiers (CONTRACTS §6.1)."""

    bundle_id: ID
    primary_passage: str
    provision_version_id: ID
    source_version_id: ID
    legal_path: str
    locator: Locator
    parents: list[dict[str, Any]] = Field(default_factory=list)
    footnotes: list[dict[str, Any]] = Field(default_factory=list)
    table_headers: list[dict[str, Any]] = Field(default_factory=list)
    applicable_amendments: list[dict[str, Any]] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)
    applicability_qualifiers: list[str] = Field(default_factory=list)


class RetrievalAttempt(BoundaryModel):
    """Complete audited retrieval attempt record (CONTRACTS §6.1)."""

    attempt_id: ID
    request: SearchRulesRequest
    eligibility_set_reference: str
    candidate_dispositions: list[CandidateDisposition]
    engine_candidates: list[dict[str, Any]]
    graph_expansion_edges: list[dict[str, Any]]
    grading_assessments: list[EvidenceGrade]
    selected_refs: list[ID]
    excluded_refs: list[ID]
    full_result_blob: BlobRef | None = None
    execution_versions: dict[str, str] = Field(default_factory=dict)
