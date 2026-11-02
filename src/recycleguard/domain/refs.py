"""Shared evidence-reference and issue builders for C08 modules."""

import hashlib
from dataclasses import dataclass

from recycleguard.contracts.core import ErrorCode, EvidenceRef, Issue
from recycleguard.domain.models import CheckState
from recycleguard.storage import canonical_json_bytes


@dataclass(frozen=True)
class Finding:
    """One tool verdict before it is shaped into a StructuredCheckResult target."""

    targets: tuple[str, ...]
    state: CheckState
    code: ErrorCode | None
    reason: str
    refs: tuple[str, ...] = ()
    values: tuple[tuple[str, str], ...] = ()


def record_ref(record) -> EvidenceRef:
    return EvidenceRef(
        ref_kind="RECORD", ref_id=record.record_id, artifact_revision_id=None, locator=None
    )


def make_issue(code: ErrorCode, severity: str, message: str, refs=None) -> Issue:
    token = hashlib.sha256(canonical_json_bytes([code, message])).hexdigest()[:12]
    return Issue(
        issue_id=f"issue:{code.lower()}_{token}",
        code=code,
        severity=severity,
        message=message,
        field_path=None,
        evidence_refs=list(refs or []),
        retryable=False,
    )
