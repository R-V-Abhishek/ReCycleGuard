"""Read the real frozen corpus pack without discarding reviewed uncertainty."""

import json
from dataclasses import dataclass

from recycleguard.contracts.core import TemporalValue
from recycleguard.contracts.foundation import SourceBatch
from recycleguard.contracts.sources import AmendmentEdge, ApplicabilityAssertion, DeadlineEntry
from recycleguard.storage import canonical_json_bytes


def _date(value):
    if value is None:
        return None
    return TemporalValue(
        raw=value.isoformat(),
        value=value.isoformat(),
        precision="DATE",
        timezone=None,
        interpretation_status="REVIEWED",
    )


@dataclass(frozen=True)
class CorpusView:
    batch: SourceBatch
    assertions: list[ApplicabilityAssertion]
    amendments: list[AmendmentEdge]
    deadlines: list[DeadlineEntry]
    approved: bool


def load_corpus(snapshot, blobs) -> CorpusView:
    if snapshot.snapshot_kind != "CORPUS":
        raise ValueError("retrieval requires a CORPUS snapshot")
    if snapshot.membership_digest != snapshot.membership_blob.sha256:
        raise ValueError("corpus membership digest differs from its immutable blob")
    raw = json.loads(blobs.get(snapshot.membership_blob))
    # FoundationReviewer adds review metadata to the SourceBatch envelope. Its
    # exact bytes remain pinned by the snapshot; only typed batch fields are parsed here.
    fields = {key: raw[key] for key in SourceBatch.model_fields}
    batch = SourceBatch.model_validate_json(canonical_json_bytes(fields))
    assertions = [
        ApplicabilityAssertion(
            assertion_id=item.assertion_id,
            provision_version_id=item.provision_version_id,
            effective_from=_date(item.interval.start),
            effective_until=_date(item.interval.end),
            affected_roles=item.affected_roles,
            scope_note=item.scope_notes,
            review_state=item.interval.review_state,
            sources=item.interval.evidence_refs,
            applicability_scope=item.interval.applicability_scope,
            end_open_ended=item.interval.end_open_ended,
        )
        for item in batch.applicability
    ]
    assertions += [
        ApplicabilityAssertion.model_validate_json(canonical_json_bytes(a))
        for a in raw.get("temporal_assertions", [])
    ]
    amendments = [
        AmendmentEdge.model_validate_json(canonical_json_bytes(a))
        for a in raw.get("amendments", [])
    ]
    deadlines = [
        DeadlineEntry.model_validate_json(canonical_json_bytes(a))
        for a in raw.get("deadline_entries", [])
    ]
    for members, attribute in (
        (batch.provisions, "provision_version_id"),
        (batch.source_versions, "source_version_id"),
    ):
        ids = [member.model_dump()[attribute] for member in members]
        if len(ids) != len(set(ids)):
            raise ValueError("corpus contains duplicate version identifiers")
    approved = snapshot.model_dump().get("review_state") == "APPROVED"
    return CorpusView(batch, assertions, amendments, deadlines, approved)
