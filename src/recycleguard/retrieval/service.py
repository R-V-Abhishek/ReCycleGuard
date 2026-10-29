"""C07 Retrieval, locator resolution, and evidence grading service.

Owned by Sampreeth (H06).
Implements CONTRACTS §6.1:
- search_rules(SearchRulesRequest) -> RetrievalAttempt
- get_source_passage(provision_version_id, expansion_policy) -> EvidenceBundle
- resolve_locator(LocatorLookupRequest) -> EvidenceBundle
- grade_evidence(bundle_id, question, basis) -> list[EvidenceGrade]
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from uuid import uuid4

from recycleguard.contracts.audit import OperationIntent, OperationResult
from recycleguard.contracts.foundation import SourceBatch
from recycleguard.contracts.retrieval import (
    CandidateDisposition,
    EvidenceBundle,
    EvidenceGrade,
    ExpansionPolicy,
    LocatorLookupRequest,
    RetrievalAttempt,
    SearchRulesRequest,
)
from recycleguard.contracts.snapshots import SnapshotPublication
from recycleguard.contracts.sources import ProvisionVersion
from recycleguard.retrieval.expansion import ContextExpander
from recycleguard.retrieval.grader import EvidenceGrader
from recycleguard.storage.blob_store import canonical_json_bytes

if TYPE_CHECKING:
    from recycleguard.contracts.core import CommandContext
    from recycleguard.indexing.fts_index import FTS5Index
    from recycleguard.storage.audit_kernel import AuditKernel
    from recycleguard.storage.authority import Capability
    from recycleguard.storage.blob_store import BlobStore


class RetrievalService:
    """Regulatory retrieval, locator resolution, and evidence grading service."""

    def __init__(
        self,
        index: FTS5Index,
        corpus_snapshot: SnapshotPublication,
        blob_store: BlobStore,
        *,
        kernel: AuditKernel | None = None,
    ):
        self.index = index
        self.corpus_snapshot = corpus_snapshot
        self.blob_store = blob_store
        self.kernel = kernel

        # Load provisions map from corpus snapshot membership
        raw_membership = blob_store.get(corpus_snapshot.membership_blob)
        membership_dict = json.loads(raw_membership.decode("utf-8"))
        source_batch = SourceBatch.model_validate(membership_dict)

        self.provisions_map: dict[str, ProvisionVersion] = {
            p.provision_version_id: p for p in source_batch.provisions
        }
        self.sources_map = {s.source_version_id: s for s in source_batch.source_versions}
        self.leads_map = {lead.source_lead_id: lead for lead in source_batch.leads}

        self.expander = ContextExpander(self.blob_store, self.provisions_map)
        self.grader = EvidenceGrader()
        self.bundles_cache: dict[str, EvidenceBundle] = {}

    def search_rules(
        self,
        request: SearchRulesRequest,
        *,
        context: CommandContext | None = None,
        capability: Capability | None = None,
    ) -> RetrievalAttempt:
        """Search regulatory index with server-side filters and candidate dispositions."""
        attempt_id = f"retrieval:{uuid4().hex[:12]}"
        candidates = self.index.search(request.query, limit=request.top_k * 3)

        dispositions: list[CandidateDisposition] = []
        engine_candidates: list[dict[str, object]] = []
        grading_assessments: list[EvidenceGrade] = []
        selected_refs: list[str] = []
        excluded_refs: list[str] = []
        expansion_edges: list[dict[str, object]] = []

        valid_count = 0
        for chunk, score in candidates:
            # 1. Server-side Regime Filter
            if request.regimes and chunk.regime not in request.regimes:
                dispositions.append(
                    CandidateDisposition(
                        candidate_ref=chunk.chunk_id,
                        disposition="FILTERED_OUT",
                        reason=f"Regime {chunk.regime} not in requested {request.regimes}",
                        score=score,
                    )
                )
                excluded_refs.append(chunk.chunk_id)
                continue

            # 2. Server-side Role Filter
            if request.roles and not any(r in chunk.affected_roles for r in request.roles):
                dispositions.append(
                    CandidateDisposition(
                        candidate_ref=chunk.chunk_id,
                        disposition="FILTERED_OUT",
                        reason=(
                            f"Roles {chunk.affected_roles} do not match requested {request.roles}"
                        ),
                        score=score,
                    )
                )
                excluded_refs.append(chunk.chunk_id)
                continue

            # 3. Window & Ranking Check
            valid_count += 1
            if valid_count <= request.top_k:
                dispositions.append(
                    CandidateDisposition(
                        candidate_ref=chunk.chunk_id,
                        disposition="SCORED",
                        reason="Top-k engine match",
                        score=score,
                        rank=valid_count,
                    )
                )
                selected_refs.append(chunk.chunk_id)
                engine_candidates.append(
                    {
                        "chunk_id": chunk.chunk_id,
                        "provision_version_id": chunk.provision_version_id,
                        "legal_path": chunk.legal_path,
                        "text": chunk.text,
                        "score": score,
                        "rank": valid_count,
                    }
                )

                # Grade candidate
                grade = self.grader.grade_candidate(
                    chunk,
                    request.query,
                    target_period=request.target_reporting_period,
                )
                grading_assessments.append(grade)
            else:
                dispositions.append(
                    CandidateDisposition(
                        candidate_ref=chunk.chunk_id,
                        disposition="OUTSIDE_ENGINE_WINDOW",
                        reason=f"Rank {valid_count} exceeds top_k limit {request.top_k}",
                        score=score,
                        rank=valid_count,
                    )
                )
                excluded_refs.append(chunk.chunk_id)

        # Build full result blob in BlobStore
        attempt = RetrievalAttempt(
            attempt_id=attempt_id,
            request=request,
            eligibility_set_reference=self.corpus_snapshot.snapshot_id,
            candidate_dispositions=dispositions,
            engine_candidates=engine_candidates,
            graph_expansion_edges=expansion_edges,
            grading_assessments=grading_assessments,
            selected_refs=selected_refs,
            excluded_refs=excluded_refs,
            execution_versions={"retrieval_engine": "1.0", "grader": "1.0"},
        )

        attempt_blob = self.blob_store.put(
            canonical_json_bytes(attempt.model_dump(mode="json")), "application/json"
        )
        attempt = attempt.model_copy(update={"full_result_blob": attempt_blob})

        # Audited commit if kernel and capability are present
        if self.kernel is not None and capability is not None and context is not None:
            intent = OperationIntent(
                context=context,
                idempotency_key=context.idempotency_key,
                event_type="extraction.retrieval",
                payload=attempt_blob,
                stream_id=f"stream:{attempt_id}",
            )
            self.kernel.commit_intent(intent, capability=capability)
            result = OperationResult(
                operation_id=context.operation_id,
                attempt_id=context.attempt_id,
                status="SUCCESS",
                payload=attempt_blob,
                issue_codes=[],
            )
            self.kernel.commit_result(intent, result, capability=capability)

        return attempt

    def get_source_passage(
        self,
        provision_version_id: str,
        expansion_policy: ExpansionPolicy | None = None,
    ) -> EvidenceBundle:
        """Fetch exact passage with bounded context expansion (CONTRACTS §6.1)."""
        provision = self.provisions_map.get(provision_version_id)
        if not provision:
            raise KeyError(f"Provision {provision_version_id} not found in corpus snapshot")

        policy = expansion_policy or ExpansionPolicy()
        raw_text = self.blob_store.get(provision.text_blob).decode("utf-8", errors="replace")

        parents, headers, footnotes, amendments = self.expander.expand_passage(provision, policy)

        bundle_id = f"bundle:{uuid4().hex[:12]}"
        bundle = EvidenceBundle(
            bundle_id=bundle_id,
            primary_passage=raw_text,
            provision_version_id=provision.provision_version_id,
            source_version_id=provision.source_version_id,
            legal_path=provision.legal_path,
            locator=provision.locator,
            parents=parents,
            footnotes=footnotes,
            table_headers=headers,
            applicable_amendments=amendments,
            provenance={
                "corpus_snapshot_id": self.corpus_snapshot.snapshot_id,
                "role_scope": provision.role_scope,
                "affected_roles": provision.affected_roles,
                "regime": provision.regime,
            },
            applicability_qualifiers=[
                f"regime:{provision.regime}",
                f"review_state:{provision.review_state}",
            ],
        )
        self.bundles_cache[bundle_id] = bundle
        return bundle

    def resolve_locator(
        self,
        request: LocatorLookupRequest,
    ) -> EvidenceBundle:
        """Resolve exact provision version by legal path or alias without blind fallback."""
        target_path = request.legal_path.strip().lower()
        alias = request.source_alias_or_source_version_id.strip().lower()

        matches = []
        for pid, prov in self.provisions_map.items():
            prov_path = prov.legal_path.lower()
            if target_path in prov_path or prov_path in target_path:
                if alias in prov.source_version_id.lower() or alias in pid.lower():
                    matches.append(prov)

        # Also fallback search by legal_path alone if alias didn't match source_version_id
        if not matches:
            for prov in self.provisions_map.values():
                if target_path in prov.legal_path.lower():
                    matches.append(prov)

        if not matches:
            msg = (
                f"No provision found for legal path '{request.legal_path}' "
                f"and alias '{request.source_alias_or_source_version_id}'"
            )
            raise KeyError(msg)

        if len(matches) > 1:
            # Ambiguous matches: record explicit qualifier rather than choosing latest silently
            bundle = self.get_source_passage(
                matches[0].provision_version_id, request.expansion_policy
            )
            bundle.applicability_qualifiers.append("APPLICABILITY_UNRESOLVED")
            return bundle

        return self.get_source_passage(matches[0].provision_version_id, request.expansion_policy)

    def grade_evidence(
        self,
        bundle_id: str,
        question: str,
        basis: str = "REPORTING_PERIOD",
    ) -> list[EvidenceGrade]:
        """Grade evidence bundle against finding question across 5 dimensions."""
        bundle = self.bundles_cache.get(bundle_id)
        if not bundle:
            raise KeyError(f"Evidence bundle {bundle_id} not found in cache")
        return self.grader.grade_bundle(bundle, question, basis=basis)
