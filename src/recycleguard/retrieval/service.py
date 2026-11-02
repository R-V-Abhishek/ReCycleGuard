"""Frozen lexical retrieval with exact source locators and durable audit records."""

import hashlib

from recycleguard.contracts.audit import OperationIntent, OperationResult
from recycleguard.contracts.core import EvidenceRef
from recycleguard.contracts.retrieval import (
    CandidateDisposition,
    EvidenceBundle,
    ExpansionPolicy,
    RetrievalAttempt,
)
from recycleguard.indexing.corpus import load_corpus
from recycleguard.knowledge.deadline_register import TemporalApplicabilityChecker
from recycleguard.retrieval.expansion import ContextExpander
from recycleguard.retrieval.grader import EvidenceGrader
from recycleguard.storage import canonical_json_bytes
from recycleguard.storage.authority import AuthorizationError


class RetrievalService:
    def __init__(self, index, corpus_snapshot, blob_store, *, manifest=None, kernel=None):
        self.index, self.corpus_snapshot, self.blob_store = index, corpus_snapshot, blob_store
        self.manifest, self.kernel = manifest or index.manifest, kernel
        self.view = load_corpus(corpus_snapshot, blob_store)
        self.provisions_map = {p.provision_version_id: p for p in self.view.batch.provisions}
        self.sources_map = {s.source_version_id: s for s in self.view.batch.source_versions}
        self.leads_map = {s.source_lead_id: s for s in self.view.batch.leads}
        self.expander = ContextExpander(blob_store, self.provisions_map)
        self.grader = EvidenceGrader()
        self.temporal = TemporalApplicabilityChecker(self.view.assertions)
        self.bundles_cache = {}
        if self.manifest is None:
            raise ValueError("retrieval requires an exact index manifest")
        if (
            self.manifest.corpus_snapshot_id != corpus_snapshot.snapshot_id
            or self.manifest.corpus_membership_digest != corpus_snapshot.membership_digest
        ):
            raise ValueError("index is not bound to the supplied frozen corpus")
        if hashlib.sha256(index.db_path.read_bytes()).hexdigest() != self.manifest.integrity_digest:
            raise ValueError("index integrity differs from manifest")

    def _grade(self, chunk, request):
        source = self.sources_map.get(chunk.source_version_id)
        lead = self.leads_map.get(source.source_lead_id) if source else None
        provision = self.provisions_map[chunk.provision_version_id]
        refs = [
            EvidenceRef(
                ref_kind="PROVISION",
                ref_id=provision.provision_version_id,
                artifact_revision_id=source.artifact_revision_id if source else None,
                locator=chunk.locator,
            )
        ]
        return self.grader.grade_candidate(
            chunk,
            request.query,
            target_period=request.target_reporting_period,
            source_class=lead.source_class if lead else None,
            source_reviewed=bool(
                source
                and source.review_state == "APPROVED"
                and provision.review_state == "APPROVED"
                and self.view.approved
            ),
            complete=bool(
                source
                and source.completeness == "COMPLETE_TEXT"
                and not provision.parent_provision_id
            ),
            temporal_fit=self.temporal.check_temporal_fit(
                provision.applicability_assertion_id,
                request.target_reporting_period,
                question_basis=request.question_basis,
            ),
            evidence_refs=refs,
        )

    def search_rules(self, request, *, context=None, capability=None):
        if (
            request.corpus_snapshot_id != self.corpus_snapshot.snapshot_id
            or request.index_id != self.manifest.index_id
        ):
            raise ValueError("request corpus/index pins differ from active frozen inputs")
        if request.expected_index_digest not in {None, self.manifest.integrity_digest}:
            raise ValueError("request index digest mismatch")
        if request.expected_corpus_membership_digest not in {
            None,
            self.corpus_snapshot.membership_digest,
        }:
            raise ValueError("request corpus membership digest mismatch")
        intent = None
        request_blob = self.blob_store.put(
            canonical_json_bytes(request.model_dump(mode="json")), "application/json"
        )
        if self.kernel is not None:
            if context is None or capability is None or context.actor.actor_kind != "SERVICE":
                raise AuthorizationError(
                    "audited retrieval requires trusted SERVICE context and capability"
                )
            self.kernel.authority.check(capability, context.actor, "extraction.retrieval")
            intent = OperationIntent(
                context=context,
                idempotency_key=context.idempotency_key,
                event_type="extraction.retrieval",
                payload=request_blob,
                stream_id=f"stream:{context.run_id or self.corpus_snapshot.snapshot_id}",
            )
            self.kernel.commit_intent(intent, capability=capability)
            previous = self.kernel.get_result(context.operation_id)
            if previous is not None:
                return RetrievalAttempt.model_validate_json(self.blob_store.get(previous.payload))
        if (
            hashlib.sha256(self.index.db_path.read_bytes()).hexdigest()
            != self.manifest.integrity_digest
        ):
            raise ValueError("index integrity differs from manifest")
        candidates = self.index.search(request.query, limit=max(1, self.manifest.total_chunks))
        scores = {chunk.chunk_id: (chunk, score) for chunk, score in candidates}
        dispositions, selected, excluded, engine, grades = [], [], [], [], []
        eligible_candidates = [
            chunk
            for chunk, _ in candidates
            if (not request.regimes or chunk.regime in request.regimes)
            and (
                not request.roles
                or chunk.role_scope == "GENERAL"
                or set(request.roles).intersection(chunk.affected_roles)
            )
        ]
        ranks = {chunk.chunk_id: rank for rank, chunk in enumerate(eligible_candidates, 1)}
        for chunk in self.index.all_chunks():
            rank = None
            reason, disposition = "No lexical match", "NOT_SCORED"
            score = scores[chunk.chunk_id][1] if chunk.chunk_id in scores else None
            if chunk.disposition != "INDEXED":
                disposition, reason = "FILTERED_OUT", f"Corpus disposition {chunk.disposition}"
            elif request.regimes and chunk.regime not in request.regimes:
                disposition, reason = "FILTERED_OUT", "Regime filter"
            elif (
                request.roles
                and not set(request.roles).intersection(chunk.affected_roles)
                and chunk.role_scope != "GENERAL"
            ):
                disposition, reason = "FILTERED_OUT", "Role filter"
            elif score is not None:
                rank = ranks[chunk.chunk_id]
                if rank > request.top_k:
                    disposition, reason = "OUTSIDE_ENGINE_WINDOW", "Outside requested top-k"
                else:
                    grade = self._grade(chunk, request)
                    grades.append(grade)
                    rejected = "FAIL" in (grade.authority, grade.temporal_fit)
                    disposition = "REJECTED_SUPPORT" if rejected else "SCORED"
                    reason = (
                        "Rejected authority/applicability"
                        if rejected
                        else "Lexical context; support remains explicitly graded"
                    )
                    if not rejected:
                        selected.append(chunk.chunk_id)
                        engine.append(
                            {
                                "chunk_id": chunk.chunk_id,
                                "provision_version_id": chunk.provision_version_id,
                                "legal_path": chunk.legal_path,
                                "text": chunk.text,
                                "score": score,
                                "rank": rank,
                            }
                        )
            dispositions.append(
                CandidateDisposition(
                    candidate_ref=chunk.chunk_id,
                    disposition=disposition,
                    reason=reason,
                    score=score,
                    rank=rank if score is not None else None,
                )
            )
            if chunk.chunk_id not in selected:
                excluded.append(chunk.chunk_id)
        attempt = RetrievalAttempt(
            attempt_id=f"retrieval:{request_blob.sha256[:24]}",
            request=request,
            eligibility_set_reference=self.corpus_snapshot.snapshot_id,
            candidate_dispositions=dispositions,
            engine_candidates=sorted(engine, key=lambda item: item["rank"]),
            graph_expansion_edges=[],
            grading_assessments=grades,
            selected_refs=selected,
            excluded_refs=excluded,
            execution_versions={
                "retrieval_engine": "cp3-frozen-1",
                "grader": self.grader.assessment_version,
            },
        )
        body = self.blob_store.put(
            canonical_json_bytes(attempt.model_dump(mode="json")), "application/json"
        )
        attempt = attempt.model_copy(update={"full_result_blob": body})
        if intent is not None:
            payload = self.blob_store.put(
                canonical_json_bytes(attempt.model_dump(mode="json")), "application/json"
            )
            self.kernel.commit_result(
                intent,
                OperationResult(
                    operation_id=context.operation_id,
                    attempt_id=context.attempt_id,
                    status="SUCCESS",
                    payload=payload,
                    output_refs=[body],
                ),
                capability=capability,
            )
        return attempt

    def get_source_passage(self, provision_version_id, expansion_policy=None):
        provision = self.provisions_map[provision_version_id]
        source = self.sources_map.get(provision.source_version_id)
        lead = self.leads_map.get(source.source_lead_id) if source else None
        text = self.blob_store.get(provision.text_blob).decode("utf-8")
        policy = expansion_policy or ExpansionPolicy()
        parents, headers, footnotes, amendments = self.expander.expand_passage(provision, policy)
        bundle_digest = hashlib.sha256(
            canonical_json_bytes(
                [
                    provision_version_id,
                    policy.model_dump(mode="json"),
                    self.corpus_snapshot.membership_digest,
                ]
            )
        ).hexdigest()[:24]
        bundle = EvidenceBundle(
            bundle_id=f"bundle:{bundle_digest}",
            primary_passage=text,
            provision_version_id=provision_version_id,
            source_version_id=provision.source_version_id,
            legal_path=provision.legal_path,
            locator=provision.locator,
            parents=parents,
            table_headers=headers,
            footnotes=footnotes,
            applicable_amendments=amendments,
            provenance={
                "corpus_snapshot_id": self.corpus_snapshot.snapshot_id,
                "artifact_revision_id": source.artifact_revision_id if source else None,
                "authority": "PASS"
                if self.view.approved
                and source
                and source.review_state == "APPROVED"
                and lead
                and lead.source_class in {"STATUTE", "GAZETTE_RULE", "ORDER"}
                else "UNRESOLVED",
                "complete_source": bool(source and source.completeness == "COMPLETE_TEXT"),
            },
            applicability_qualifiers=[
                "APPLICABILITY_UNRESOLVED",
                "Direct support and amendment completeness require assessment.",
            ],
        )
        self.bundles_cache[bundle.bundle_id] = bundle
        return bundle

    def resolve_locator(self, request):
        if request.corpus_snapshot_id != self.corpus_snapshot.snapshot_id:
            raise ValueError("locator lookup corpus mismatch")
        alias = request.source_alias_or_source_version_id.casefold()
        sourceids = {
            s.source_version_id
            for s in self.sources_map.values()
            if s.source_version_id.casefold() == alias
            or (
                s.source_lead_id in self.leads_map
                and alias in {a.casefold() for a in self.leads_map[s.source_lead_id].aliases}
            )
        }
        path = request.legal_path.strip().casefold()
        matches = [
            p
            for p in self.provisions_map.values()
            if p.source_version_id in sourceids
            and (
                p.legal_path.strip().casefold() == path
                or p.legal_path.split(",", 1)[0].strip().casefold() == path
            )
        ]
        if len(matches) != 1:
            raise KeyError(
                f"Exact source/locator resolution requires one match; found {len(matches)}"
            )
        return self.get_source_passage(matches[0].provision_version_id, request.expansion_policy)

    def grade_evidence(self, bundle_id, question, basis="REPORTING_PERIOD"):
        return self.grader.grade_bundle(self.bundles_cache[bundle_id], question, basis=basis)
