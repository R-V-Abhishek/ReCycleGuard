"""Frozen corpus/profile integrity verification and explicitly unverified metadata helpers.

Integrity verification establishes exact persisted inputs and audit lineage, not legal
correctness, redistribution permission, temporal applicability, or model quality.
"""

import hashlib
import io
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import Field

from recycleguard.contracts.artifacts import (
    ArtifactRevision,
    FrozenSnapshot,
    ProfileRef,
    SnapshotRef,
)
from recycleguard.contracts.core import BoundaryModel, Digest
from recycleguard.contracts.profiles import CalculationProfile
from recycleguard.contracts.retrieval import IndexManifest
from recycleguard.contracts.workflow import ConfigurationPin
from recycleguard.indexing.corpus import load_corpus
from recycleguard.storage import AuditKernel, BlobStore, canonical_json_bytes

# ──────────────────────────────────────────────────────────────────────────────
# Audit record models
# ──────────────────────────────────────────────────────────────────────────────


class SourceAuditRecord(BoundaryModel):
    """Pinned digest and locator record for a single active corpus source."""

    artifact_revision_id: str
    source_alias: str
    document_title: str
    source_kind: str
    source_url: str
    sha256_digest: Digest
    total_pages: int
    active_physical_pages: list[int]
    active_provision_ids: list[str]
    access_policy_id: str
    rights_decision_id: str
    copyright_owner: str
    statutory_exception: str
    redistribution_allowed: bool | None
    review_state: Literal["DRAFT", "APPROVED", "REJECTED"] | None
    review_note: str


class IndexAuditRecord(BoundaryModel):
    """Pinned index manifest digest for the active lexical index."""

    index_id: str
    corpus_snapshot_id: str
    corpus_membership_digest: Digest | None
    index_integrity_digest: Digest
    tokenizer: str
    bm25_k1: float
    bm25_b: float
    total_chunks: int
    build_code_revision: str


class ProfileAuditRecord(BoundaryModel):
    """Pinned digest and policy summary for the active calculation profile."""

    profile_id: str
    profile_version: str
    profile_digest: Digest
    review_state: Literal["DRAFT", "APPROVED", "REJECTED"]
    supported_regime: str
    target_basis: str
    allowed_metals: list[str]
    category_scope: list[str]
    priority_check: str
    purchase_ceiling_state: str
    purchase_ceiling_note: str
    unsupported_features: list[str]
    source_dependency_digests: list[dict[str, str]]


class AuditLimitation(BoundaryModel):
    """Explicit recorded limitation for handoff documentation."""

    limitation_id: str
    kind: Literal[
        "UNREVIEWED_PROVISION",
        "MISSING_EXTENSION_ORDER",
        "DISABLED_PURCHASE_CEILING",
        "NOTICE_LEAD_NO_ORDER",
        "REDISTRIBUTION_RESTRICTED",
        "TEMPORAL_APPLICABILITY_UNRESOLVED",
        "SEMANTIC_GRADE_UNRESOLVED",
        "UNSUPPORTED_FEATURE",
    ]
    scope: str
    description: str
    effect_on_retrieval: str


class CorpusProfileAuditManifest(BoundaryModel):
    """Typed audit outcome; only VERIFIED_INTEGRITY has inspected frozen bytes."""

    verification_status: Literal["UNVERIFIED_METADATA", "VERIFIED_INTEGRITY"] = (
        "UNVERIFIED_METADATA"
    )
    runtime_metadata: dict[str, str] = Field(default_factory=dict)
    verified_checks: list[str] = Field(default_factory=list)
    verified_audit_streams: list[str] = Field(default_factory=list)
    manifest_id: str = "manifest:h08_corpus_profile_audit_v1"
    generated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    owner: str = "Sampreeth (H08)"
    task_ref: str = "H08"
    checkpoint_ref: str = "checkpoint-3"
    sources: list[SourceAuditRecord]
    index: IndexAuditRecord | None = None
    profile: ProfileAuditRecord
    limitations: list[AuditLimitation]
    retrieval_engine_note: str = (
        "Metadata helper only; no runtime, model, retrieval grades or review decisions verified."
    )


# ──────────────────────────────────────────────────────────────────────────────
# Static corpus constants (from provisions.py / profile_v1.py)
# ──────────────────────────────────────────────────────────────────────────────

_R02_REV_ID = "artifact_rev:r02_rules_2022_official_pdf"
_R08_REV_ID = "artifact_rev:cpcb_faq_20240123_pdf"

_SOURCE_DIGESTS: dict[str, str] = {
    _R02_REV_ID: ("d03f8744bc79d67a94b06e1020537e93d15572b0cf1d575cb32b76c89f30a5fb"),
    _R08_REV_ID: ("30f56238fb7db53dd82f69d198be9a92e31d98ea5b21d2724eb7397641a80d16"),
}

_SOURCE_PAGES: dict[str, int] = {_R02_REV_ID: 38, _R08_REV_ID: 13}

_ACTIVE_PAGES: dict[str, list[int]] = {
    _R02_REV_ID: [24, 27],
    _R08_REV_ID: [9],
}

_ACTIVE_PROVISIONS: dict[str, list[str]] = {
    _R02_REV_ID: [
        "provision:r02_rule6_sub4",
        "provision:r02_rule15_sub1_sub3",
    ],
    _R08_REV_ID: ["provision:r08_sec_c_recycler_capability"],
}


# ──────────────────────────────────────────────────────────────────────────────
# Audit functions
# ──────────────────────────────────────────────────────────────────────────────


def audit_corpus_sources() -> list[SourceAuditRecord]:
    """Return pinned source audit records for the two active corpus sources.

    Does NOT require live PDF bytes; the digests are the pinned originals.
    Call register_reviewed_sources() separately to verify actual file bytes.
    """
    return [
        SourceAuditRecord(
            artifact_revision_id=_R02_REV_ID,
            source_alias="R02",
            document_title=(
                "E-Waste (Management) Rules 2022 — Official Gazette, "
                "Ministry of Environment, Forest and Climate Change"
            ),
            source_kind="GAZETTE",
            source_url=("https://eprewaste.cpcb.gov.in/assets/PDF/e-waste_rules_2022.pdf"),
            sha256_digest=_SOURCE_DIGESTS[_R02_REV_ID],
            total_pages=_SOURCE_PAGES[_R02_REV_ID],
            active_physical_pages=_ACTIVE_PAGES[_R02_REV_ID],
            active_provision_ids=_ACTIVE_PROVISIONS[_R02_REV_ID],
            access_policy_id="policy:local_source_review",
            rights_decision_id="decision:review_required",
            copyright_owner="Unverified expected metadata",
            statutory_exception="No rights determination performed",
            redistribution_allowed=None,
            review_state=None,
            review_note="UNVERIFIED_METADATA: no frozen bytes or review decisions inspected",
        ),
        SourceAuditRecord(
            artifact_revision_id=_R08_REV_ID,
            source_alias="R08",
            document_title=(
                "CPCB FAQ on E-Waste (Management) Rules 2022 — Guidance for Producers, January 2024"
            ),
            source_kind="OFFICIAL_GUIDANCE",
            source_url=("https://eprewaste.cpcb.gov.in/assets/PDF/faqewaste.pdf"),
            sha256_digest=_SOURCE_DIGESTS[_R08_REV_ID],
            total_pages=_SOURCE_PAGES[_R08_REV_ID],
            active_physical_pages=_ACTIVE_PAGES[_R08_REV_ID],
            active_provision_ids=_ACTIVE_PROVISIONS[_R08_REV_ID],
            access_policy_id="policy:local_source_review",
            rights_decision_id="decision:review_required",
            copyright_owner="Unverified expected metadata",
            statutory_exception="No rights determination performed",
            redistribution_allowed=None,
            review_state=None,
            review_note="UNVERIFIED_METADATA: no frozen bytes or review decisions inspected",
        ),
    ]


def audit_profile(profile_payload: dict) -> ProfileAuditRecord:
    """Derive a ProfileAuditRecord from a serialised CalculationProfile payload.

    Args:
        profile_payload: ``CalculationProfile.model_dump(mode="json")``.

    Returns:
        Pinned ProfileAuditRecord capturing digest, policy state and limitations.
    """
    dep_digests = [
        {
            "artifact_revision_id": dep["artifact_revision_id"],
            "blob_digest": dep["blob_digest"],
        }
        for dep in profile_payload.get("source_dependencies", [])
    ]
    return ProfileAuditRecord(
        profile_id=profile_payload["profile_id"],
        profile_version=profile_payload["profile_version"],
        profile_digest=profile_payload["digest"],
        review_state=profile_payload["review_state"],
        supported_regime=profile_payload["supported_regime"],
        target_basis=profile_payload["target_basis"],
        allowed_metals=profile_payload["allowed_metals"],
        category_scope=profile_payload["category_scope"],
        priority_check=profile_payload["allocation_policy"]["priority_check"],
        purchase_ceiling_state=profile_payload["purchase_ceiling_policy"]["state"],
        purchase_ceiling_note=(
            "Recorded profile policy state: "
            + profile_payload["purchase_ceiling_policy"]["state"]
            + "; this summary does not independently approve policy authority."
        ),
        unsupported_features=profile_payload["unsupported_features"],
        source_dependency_digests=dep_digests,
    )


def build_audit_limitations() -> list[AuditLimitation]:
    """Questions for a future real audit, not claims about an inspected runtime."""
    questions = [
        ("UNREVIEWED_PROVISION", "Source/provision review", "Review states require frozen inputs."),
        ("MISSING_EXTENSION_ORDER", "Deadline authority", "Issued order coverage is unverified."),
        (
            "DISABLED_PURCHASE_CEILING",
            "Profile policy",
            "Use the supplied profile's actual ceiling state.",
        ),
        ("NOTICE_LEAD_NO_ORDER", "Notice leads", "A lead is not an issued extension order."),
        (
            "REDISTRIBUTION_RESTRICTED",
            "Source rights",
            "Rights require recorded decisions; no legal permission is inferred.",
        ),
        (
            "TEMPORAL_APPLICABILITY_UNRESOLVED",
            "Applicability",
            "No temporal grades were executed by this metadata helper.",
        ),
        (
            "SEMANTIC_GRADE_UNRESOLVED",
            "Model/retrieval",
            "Runtime model and semantic grades are not supplied or verified.",
        ),
        (
            "UNSUPPORTED_FEATURE",
            "Calculation scope",
            "Read unsupported features from the supplied profile.",
        ),
    ]
    return [
        AuditLimitation(
            limitation_id=f"limit:h08_metadata_{number}",
            kind=kind,
            scope=scope,
            description=description,
            effect_on_retrieval="UNVERIFIED_METADATA; not a runtime verification result.",
        )
        for number, (kind, scope, description) in enumerate(questions, 1)
    ]


def build_index_audit_record(manifest_payload: dict) -> IndexAuditRecord:
    """Derive an IndexAuditRecord from a serialised IndexManifest payload."""
    lex = manifest_payload.get("lexical_configuration", {})
    return IndexAuditRecord(
        index_id=manifest_payload["index_id"],
        corpus_snapshot_id=manifest_payload["corpus_snapshot_id"],
        corpus_membership_digest=manifest_payload.get("corpus_membership_digest"),
        index_integrity_digest=manifest_payload["integrity_digest"],
        tokenizer=lex.get("tokenizer", "unicode61"),
        bm25_k1=lex.get("bm25_k1", 1.2),
        bm25_b=lex.get("bm25_b", 0.75),
        total_chunks=manifest_payload.get("total_chunks", 0),
        build_code_revision=manifest_payload.get("build_code_revision", "unknown"),
    )


def build_corpus_profile_audit_manifest(
    *,
    profile_payload: dict,
    index_manifest_payload: dict | None = None,
) -> CorpusProfileAuditManifest:
    """Assemble a complete H08 audit manifest.

    Args:
        profile_payload: ``CalculationProfile.model_dump(mode="json")``.
        index_manifest_payload: Optional ``IndexManifest.model_dump(mode="json")``.
            Omit when auditing in isolation (no live index required).

    Returns:
        CorpusProfileAuditManifest ready for documentation and handoff.
    """
    sources = audit_corpus_sources()
    profile = audit_profile(profile_payload)
    limitations = build_audit_limitations()
    index = build_index_audit_record(index_manifest_payload) if index_manifest_payload else None
    return CorpusProfileAuditManifest(
        sources=sources,
        index=index,
        profile=profile,
        limitations=limitations,
    )


def verify_source_digest(artifact_revision_id: str, pdf_bytes: bytes) -> bool:
    """Verify that supplied PDF bytes match the pinned SHA-256 digest.

    Returns True if the digest matches; False if it differs.
    Raises KeyError if the revision ID is unknown.
    """
    expected = _SOURCE_DIGESTS[artifact_revision_id]
    actual = hashlib.sha256(pdf_bytes).hexdigest()
    return actual == expected


def _verify_kernel_chains(kernel, blobs) -> list[str]:
    """Verify every stream in the supplied application ledger, including child services."""
    streams = [
        row[0]
        for row in kernel.connection.execute(
            "SELECT DISTINCT stream_id FROM audit_events ORDER BY stream_id"
        )
    ]
    if not streams:
        raise ValueError("corpus audit requires persisted application audit events")
    for stream in streams:
        previous = None
        events = kernel.list_stream_events(stream)
        for sequence, event in enumerate(events, 1):
            actual = hashlib.sha256(
                canonical_json_bytes(event.model_dump(mode="json", exclude={"event_hash"}))
            ).hexdigest()
            if (
                event.stream_id != stream
                or event.sequence != sequence
                or event.previous_event_hash != previous
                or event.event_hash != actual
            ):
                raise ValueError("application audit hash chain mismatch")
            for reference in [event.payload_blob, *event.input_refs, *event.output_refs]:
                blobs.get(reference)
            previous = actual
        if kernel.stream_head(stream) != (len(events), previous):
            raise ValueError("application audit indexed head mismatch")
    return streams


def audit_frozen_corpus_profile(
    *,
    corpus_snapshot: FrozenSnapshot,
    profile: CalculationProfile,
    index_manifest: IndexManifest,
    blobs: BlobStore,
    index_path: Path,
    expected_corpus: SnapshotRef,
    expected_profile: ProfileRef,
    expected_index: ConfigurationPin,
    kernel: AuditKernel,
    runtime_metadata: dict[str, str],
) -> CorpusProfileAuditManifest:
    """Verify exact frozen inputs. Fail closed on missing bytes, pins or audit corruption.

    The supplied kernel must be the same application ledger that published the
    snapshot/profile and index. Runtime metadata is caller supplied and retained as
    such; this function performs no C10 inference or legal/semantic evaluation.
    """
    corpus_snapshot = FrozenSnapshot.model_validate_json(corpus_snapshot.model_dump_json())
    profile = CalculationProfile.model_validate_json(profile.model_dump_json())
    index_manifest = IndexManifest.model_validate_json(index_manifest.model_dump_json())
    if (
        SnapshotRef(
            snapshot_id=corpus_snapshot.snapshot_id,
            membership_digest=corpus_snapshot.membership_digest,
        )
        != expected_corpus
    ):
        raise ValueError("corpus snapshot differs from expected pin")
    if (
        ProfileRef(
            profile_id=profile.profile_id,
            profile_version=profile.profile_version,
            digest=profile.digest,
        )
        != expected_profile
    ):
        raise ValueError("profile differs from expected pin")
    if index_manifest.pin() != expected_index:
        raise ValueError("index manifest differs from expected pin")
    if (
        index_manifest.corpus_snapshot_id != corpus_snapshot.snapshot_id
        or index_manifest.corpus_membership_digest != corpus_snapshot.membership_digest
    ):
        raise ValueError("index is not bound to exact corpus membership")
    snapshot_row = kernel.connection.execute(
        "SELECT snapshot_json FROM frozen_snapshots WHERE snapshot_id=?",
        (corpus_snapshot.snapshot_id,),
    ).fetchone()
    profile_row = kernel.connection.execute(
        "SELECT profile_json FROM profile_revisions WHERE profile_id=? AND profile_version=?",
        (profile.profile_id, profile.profile_version),
    ).fetchone()
    if (
        snapshot_row is None
        or FrozenSnapshot.model_validate_json(snapshot_row[0]) != corpus_snapshot
    ):
        raise ValueError("frozen corpus differs from persisted catalog revision")
    if profile_row is None or CalculationProfile.model_validate_json(profile_row[0]) != profile:
        raise ValueError("profile differs from persisted catalog revision")
    streams = _verify_kernel_chains(kernel, blobs)
    index_events = [
        event
        for stream in streams
        for event in kernel.list_stream_events(stream)
        if event.event_type == "extraction.index.result"
        and event.payload_blob.sha256 == expected_index.digest
    ]
    if not index_events or not any(
        kernel.get_result(event.operation_id) is not None
        and kernel.get_result(event.operation_id).status == "SUCCESS"
        and kernel.get_result(event.operation_id).payload == event.payload_blob
        for event in index_events
    ):
        raise ValueError("index manifest has no successful publication in application ledger")
    view = load_corpus(corpus_snapshot, blobs)
    blobs.get(corpus_snapshot.coverage_blob)
    artifacts = {a.artifact_revision_id: a for a in view.batch.artifact_revisions}
    source_versions = {s.source_version_id: s for s in view.batch.source_versions}
    leads = {s.source_lead_id: s for s in view.batch.leads}
    for artifact in artifacts.values():
        row = kernel.connection.execute(
            "SELECT revision_json FROM artifact_revisions WHERE artifact_revision_id=?",
            (artifact.artifact_revision_id,),
        ).fetchone()
        if row is None or ArtifactRevision.model_validate_json(row[0]) != artifact:
            raise ValueError("corpus original differs from persisted artifact revision")
        blobs.get(artifact.blob)
    for provision in view.batch.provisions:
        if provision.source_version_id not in source_versions:
            raise ValueError("provision references a source absent from corpus")
        blobs.get(provision.text_blob)
    for dependency in profile.source_dependencies:
        artifact = artifacts.get(dependency.artifact_revision_id)
        if artifact is None or artifact.blob.sha256 != dependency.blob_digest:
            raise ValueError("profile source dependency differs from frozen corpus")
        blobs.get(artifact.blob)
    pinned = {dependency.artifact_revision_id for dependency in profile.source_dependencies}
    policy_refs = list(profile.applicability_assertion_refs)
    policy_refs += [ref for rule in profile.eligibility_rules for ref in rule.source_refs]
    ceiling = profile.purchase_ceiling_policy
    policy_refs += ceiling.source_refs + ceiling.applicability_refs
    if any(ref.artifact_revision_id not in pinned for ref in policy_refs):
        raise ValueError("profile policy evidence is not bound to a source dependency")
    members = [
        p.model_dump(mode="json")
        for p in sorted(view.batch.provisions, key=lambda p: p.provision_version_id)
    ]
    if (
        hashlib.sha256(canonical_json_bytes(members)).hexdigest()
        != index_manifest.eligible_members_digest
    ):
        raise ValueError("index provision membership differs from frozen corpus")
    if index_manifest.index_blob is None:
        raise ValueError("index manifest has no immutable index bytes")
    original_index = blobs.get(index_manifest.index_blob)
    if (
        hashlib.sha256(original_index).hexdigest() != index_manifest.integrity_digest
        or Path(index_path).read_bytes() != original_index
    ):
        raise ValueError("index bytes differ from immutable manifest")

    import pdfplumber

    sources = []
    limitations = []
    for source in view.batch.source_versions:
        artifact = artifacts[source.artifact_revision_id]
        lead = leads[source.source_lead_id]
        provisions = [
            p for p in view.batch.provisions if p.source_version_id == source.source_version_id
        ]
        with pdfplumber.open(io.BytesIO(blobs.get(artifact.blob))) as pdf:
            page_count = len(pdf.pages)
        pages = sorted(
            {
                p.locator.page_index_1based
                for p in provisions
                if p.locator.page_index_1based is not None
            }
        )
        if any(page < 1 or page > page_count for page in pages):
            raise ValueError("provision locator is outside original PDF")
        rights = lead.rights_and_license
        sources.append(
            SourceAuditRecord(
                artifact_revision_id=artifact.artifact_revision_id,
                source_alias=", ".join(lead.aliases),
                document_title=source.title,
                source_kind=artifact.source_kind,
                source_url=artifact.source_url or lead.official_url,
                sha256_digest=artifact.blob.sha256,
                total_pages=page_count,
                active_physical_pages=pages,
                active_provision_ids=[p.provision_version_id for p in provisions],
                access_policy_id=artifact.access_policy_id,
                rights_decision_id=artifact.rights_decision_id,
                copyright_owner=rights.copyright_owner,
                statutory_exception=rights.statutory_exception_sec52 or "Not recorded",
                redistribution_allowed=rights.redistribution_allowed,
                review_state=source.review_state,
                review_note="Recorded source state; no legal certification.",
            )
        )
        if not rights.redistribution_allowed or rights.asset_rights_seed != "ALLOW":
            limitations.append(
                AuditLimitation(
                    limitation_id=f"limit:rights_{source.source_version_id}",
                    kind="REDISTRIBUTION_RESTRICTED",
                    scope=source.source_version_id,
                    description=f"Recorded rights state: {rights.asset_rights_seed}.",
                    effect_on_retrieval="Integrity grants no additional use/export permission.",
                )
            )
        for provision in provisions:
            if provision.review_state != "APPROVED":
                limitations.append(
                    AuditLimitation(
                        limitation_id=f"limit:review_{provision.provision_version_id}",
                        kind="UNREVIEWED_PROVISION",
                        scope=provision.provision_version_id,
                        description=f"Recorded review state: {provision.review_state}.",
                        effect_on_retrieval="Review uncertainty is retained.",
                    )
                )
    for assertion in view.assertions:
        if assertion.review_state != "APPROVED" or assertion.effective_from is None:
            limitations.append(
                AuditLimitation(
                    limitation_id=f"limit:temporal_{assertion.assertion_id}",
                    kind="TEMPORAL_APPLICABILITY_UNRESOLVED",
                    scope=assertion.assertion_id,
                    description="Temporal authority/interval is not fully reviewed.",
                    effect_on_retrieval="Integrity does not establish temporal applicability.",
                )
            )
    if ceiling.state != "APPROVED":
        limitations.append(
            AuditLimitation(
                limitation_id="limit:ceiling",
                kind="DISABLED_PURCHASE_CEILING",
                scope=profile.profile_id,
                description=f"Recorded policy state: {ceiling.state}.",
                effect_on_retrieval="Purchase ceiling is not enabled by this audit.",
            )
        )
    for deadline in view.deadlines:
        if deadline.extended_due is not None and (
            deadline.unverified_notice or not deadline.extension_order_refs
        ):
            limitations.append(
                AuditLimitation(
                    limitation_id=f"limit:deadline_{deadline.deadline_id}",
                    kind="MISSING_EXTENSION_ORDER",
                    scope=deadline.deadline_id,
                    description="Extension order evidence is missing or the notice is unverified.",
                    effect_on_retrieval="The extension is not verified by this integrity audit.",
                )
            )
    if profile.unsupported_features:
        limitations.append(
            AuditLimitation(
                limitation_id="limit:unsupported",
                kind="UNSUPPORTED_FEATURE",
                scope=profile.profile_id,
                description=", ".join(profile.unsupported_features),
                effect_on_retrieval="Unsupported profile features remain outside calculations.",
            )
        )
    limitations.append(
        AuditLimitation(
            limitation_id="limit:semantic",
            kind="SEMANTIC_GRADE_UNRESOLVED",
            scope="runtime metadata",
            description="Caller-supplied runtime metadata; no model/semantic evaluation executed.",
            effect_on_retrieval="No model quality or semantic support is established.",
        )
    )
    return CorpusProfileAuditManifest(
        verification_status="VERIFIED_INTEGRITY",
        runtime_metadata=runtime_metadata,
        sources=sources,
        profile=audit_profile(profile.model_dump(mode="json")),
        index=build_index_audit_record(index_manifest.model_dump(mode="json")),
        limitations=limitations,
        verified_checks=[
            "exact_pins",
            "persisted_catalog",
            "corpus_source_provision_bytes",
            "profile_canonical_digest_dependencies",
            "immutable_index_bytes",
            "application_hash_chains",
        ],
        verified_audit_streams=streams,
        retrieval_engine_note="Index integrity verified; retrieval/semantic grades not executed.",
    )
