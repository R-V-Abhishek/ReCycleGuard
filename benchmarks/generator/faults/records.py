"""Evaluator-only records of what a fault recipe did (CONTRACTS section 5.3 field names).

These models live under ``benchmarks/`` on purpose: the runtime never imports them, so a
corruption record or an expected effect cannot reach the investigator's registry, logs or cache.
``ExpectedEffects`` is a draft input for V04's ``OracleCase``; it is not an oracle.
"""

from pydantic import BaseModel, ConfigDict

from recycleguard.contracts.core import ErrorCode
from recycleguard.contracts.results import AbstentionReason, FaultFamily


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CorruptionRecord(_Strict):
    corruption_id: str
    case_id: str
    fault_family: FaultFamily
    affected_visible_asset_refs: list[str]
    transformation: str
    before_refs: list[str]  # world object keys in the clean counterpart
    after_refs: list[str]  # world object keys in the visible (corrupted) world
    intended_evidence_effect: str


class ExpectedEffects(_Strict):
    case_id: str
    fault_families: list[FaultFamily]
    expected_issue_codes: list[ErrorCode]
    required_abstentions: list[AbstentionReason]
    forbidden_actions: list[str]
    permitted_alternatives: list[str]
    clean_reference_buckets: list[dict]  # world truth of the clean counterpart
    visible_reference_buckets: list[dict]  # what the visible evidence justifies
    basis: str = "Draft input for the V04 OracleCase; generator arithmetic, not an oracle"


__all__ = ["CorruptionRecord", "ExpectedEffects"]
