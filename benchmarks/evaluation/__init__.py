"""Evaluator-only reference material. Excluded from the application wheel."""

from benchmarks.evaluation.oracle import OracleBuilder, OracleCase, write_oracle_records
from benchmarks.evaluation.scoring import (
    AbstentionScore,
    FindingScore,
    ForbiddenActionScore,
    ReconciliationScore,
    ScoringProtocol,
    TrialEvaluationReport,
)
from benchmarks.evaluation.validation import (
    HeldOutAccessRecord,
    OracleSeal,
    OracleValidation,
    load_oracle_records,
    record_heldout_access,
    seal_oracles,
    validate_oracle,
    validate_oracle_against_world,
)

__all__ = [
    "AbstentionScore",
    "FindingScore",
    "ForbiddenActionScore",
    "HeldOutAccessRecord",
    "OracleBuilder",
    "OracleCase",
    "OracleSeal",
    "OracleValidation",
    "ReconciliationScore",
    "ScoringProtocol",
    "TrialEvaluationReport",
    "load_oracle_records",
    "record_heldout_access",
    "seal_oracles",
    "validate_oracle",
    "validate_oracle_against_world",
    "write_oracle_records",
]
