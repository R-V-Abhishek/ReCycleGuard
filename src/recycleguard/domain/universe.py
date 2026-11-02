"""C08 candidate-input universe, computed server-side from the pinned case snapshot.

Callers never supply record lists; they can only name the snapshot to analyze.
"""

import hashlib
from collections import Counter
from dataclasses import dataclass

from recycleguard.contracts.domain import RECORD_ADAPTER, Record
from recycleguard.storage import canonical_json_bytes


class UniverseError(ValueError):
    """Integrity failure while building the input universe."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Universe:
    snapshot_id: str
    case_id: str | None
    records: tuple[Record, ...]
    superseded: frozenset[str]
    ambiguous_ids: frozenset[str]
    digest: str

    def active(self, kind: type) -> list:
        """Active revisions of one record class; superseded and ambiguous ones are excluded."""
        return [
            r
            for r in self.records
            if r.record_type == kind.__name__
            and r.record_revision_id not in self.superseded
            and r.record_id not in self.ambiguous_ids
        ]

    def members(self) -> list[dict[str, str]]:
        return [
            {
                "record_type": r.record_type,
                "record_id": r.record_id,
                "record_revision_id": r.record_revision_id,
            }
            for r in self.records
        ]


def _superseded_revisions(records: list[Record]) -> frozenset[str]:
    gone: set[str] = set()
    for newer in records:
        if newer.supersedes_revision_id is not None:
            gone.add(newer.supersedes_revision_id)
        if newer.record_type == "Allocation" and newer.supersedes_allocation_id is not None:
            for older in records:
                if (
                    older.record_type == "Allocation"
                    and older.allocation_id == newer.supersedes_allocation_id
                    and older.record_revision_id != newer.record_revision_id
                ):
                    gone.add(older.record_revision_id)
    return frozenset(gone)


def universe_from_records(snapshot_id: str, records: list[Record]) -> Universe:
    revisions = Counter(r.record_revision_id for r in records)
    duplicated = sorted(rev for rev, count in revisions.items() if count > 1)
    if duplicated:
        raise UniverseError("INTEGRITY_FAILED", f"duplicate record revision IDs: {duplicated}")
    cases = {r.case_id for r in records}
    if len(cases) > 1:
        raise UniverseError("INTEGRITY_FAILED", "universe spans more than one case")
    ordered = sorted(records, key=lambda r: (r.record_type, r.record_id, r.record_revision_id))
    superseded = _superseded_revisions(ordered)
    live = Counter(r.record_id for r in ordered if r.record_revision_id not in superseded)
    ambiguous = frozenset(record_id for record_id, count in live.items() if count > 1)
    digest = hashlib.sha256(
        canonical_json_bytes([r.model_dump(mode="json") for r in ordered])
    ).hexdigest()
    return Universe(
        snapshot_id=snapshot_id,
        case_id=next(iter(cases), None),
        records=tuple(ordered),
        superseded=superseded,
        ambiguous_ids=ambiguous,
        digest=digest,
    )


def universe_from_membership(snapshot_id: str, membership: dict) -> Universe:
    """Strictly validate the normalized records of a CASE snapshot membership blob."""
    try:
        raw = membership["normalization"]["records"]
    except (KeyError, TypeError) as exc:
        raise UniverseError("INVALID_SCHEMA", "case membership has no normalized records") from exc
    try:
        records = [RECORD_ADAPTER.validate_json(canonical_json_bytes(item)) for item in raw]
    except ValueError as exc:
        raise UniverseError("INVALID_SCHEMA", f"normalized record is invalid: {exc}") from exc
    return universe_from_records(snapshot_id, records)
