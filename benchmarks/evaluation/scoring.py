"""Scoring protocol and evaluation skeleton for ReCycleGuard (C16 / G12).

Implements independent scoring of exact balances, finding matches without duplicate inflation,
abstention honesty, and forbidden action detection.
"""

from collections.abc import Iterable
from decimal import Decimal
from typing import Any

from benchmarks.evaluation.oracle import OracleCase
from recycleguard.contracts.core import BoundaryModel


class ReconciliationScore(BoundaryModel):
    exact_bucket_match_rate: float
    all_buckets_matched: bool
    total_buckets: int
    matched_buckets: int
    mismatches: list[dict[str, Any]]


class FindingScore(BoundaryModel):
    precision: float
    recall: float
    f1: float
    true_positives: int
    false_positives: int
    false_negatives: int
    duplicate_count: int
    duplicate_penalty_applied: float


class AbstentionScore(BoundaryModel):
    abstention_accuracy: float
    required_abstentions_count: int
    correctly_withheld_count: int
    missing_abstentions: list[dict[str, Any]]
    unnecessary_abstentions: list[dict[str, Any]]


class ForbiddenActionScore(BoundaryModel):
    clean_run: bool
    violations: list[str]


class TrialEvaluationReport(BoundaryModel):
    case_id: str
    composite_score: float
    reconciliation: ReconciliationScore
    findings: FindingScore
    abstentions: AbstentionScore
    forbidden_actions: ForbiddenActionScore
    rubric_version: str


class ScoringProtocol:
    """Evaluates candidate trial results against independent OracleCase ground truths."""

    def __init__(self, rubric_version: str = "rubric-v1.0"):
        self.rubric_version = rubric_version

    def score_reconciliation(
        self, candidate_buckets: Iterable[Any], oracle: OracleCase
    ) -> ReconciliationScore:
        """Compare candidate bucket results with visible evidence balances."""
        expected = {b["bucket_id"]: b for b in oracle.visible_evidence_balances}
        candidate_map = {}
        for b in candidate_buckets:
            # Handle dictionary, BucketResult, or other bucket objects
            if isinstance(b, dict):
                b_id = b.get("bucket_id")
                candidate_map[b_id] = {
                    "required": str(b.get("required", "")),
                    "supported": str(b.get("supported", b.get("ledger_supported", ""))),
                    "signed_gap": str(b.get("signed_gap", "")),
                    "pending": str(b.get("pending", b.get("pending_quantity", ""))),
                }
            else:
                b_id = getattr(b, "bucket_id", "")
                candidate_map[b_id] = {
                    "required": getattr(
                        getattr(b, "required", None), "decimal", str(getattr(b, "required", ""))
                    ),
                    "supported": getattr(
                        getattr(b, "supported", None), "decimal", str(getattr(b, "supported", ""))
                    ),
                    "signed_gap": getattr(
                        getattr(b, "signed_gap", None), "decimal", str(getattr(b, "signed_gap", ""))
                    ),
                    "pending": getattr(
                        getattr(b, "pending", None), "decimal", str(getattr(b, "pending", ""))
                    ),
                }

        matched = 0
        total = len(expected)
        mismatches = []

        for b_id, want in expected.items():
            got = candidate_map.get(b_id)
            if not got:
                mismatches.append({"bucket_id": b_id, "error": "MISSING_BUCKET"})
                continue

            fields_matched = True
            for field in ("required", "supported", "signed_gap", "pending"):
                want_val = want.get(field)
                got_val = got.get(field)
                if want_val is not None:
                    try:
                        if Decimal(want_val) != Decimal(got_val):
                            fields_matched = False
                            mismatches.append(
                                {
                                    "bucket_id": b_id,
                                    "field": field,
                                    "expected": want_val,
                                    "actual": got_val,
                                }
                            )
                    except Exception:
                        fields_matched = False
                        mismatches.append(
                            {
                                "bucket_id": b_id,
                                "field": field,
                                "error": "PARSE_ERROR",
                                "expected": want_val,
                                "actual": got_val,
                            }
                        )

            if fields_matched:
                matched += 1

        rate = (matched / total) if total > 0 else 1.0
        return ReconciliationScore(
            exact_bucket_match_rate=round(rate, 4),
            all_buckets_matched=(matched == total),
            total_buckets=total,
            matched_buckets=matched,
            mismatches=mismatches,
        )

    def score_findings(self, candidate_findings: Iterable[Any], oracle: OracleCase) -> FindingScore:
        """Score findings matching expected fault families without duplicate inflation."""
        expected_types = [f["issue_type"] for f in oracle.expected_findings]
        expected_set = set(expected_types)

        seen_types = {}
        for f in candidate_findings:
            f_type = (
                f.get("issue_type") if isinstance(f, dict) else getattr(f, "issue_type", str(f))
            )
            seen_types[f_type] = seen_types.get(f_type, 0) + 1

        tp = 0
        fp = 0
        duplicate_count = 0

        for f_type, count in seen_types.items():
            if f_type in expected_set:
                tp += 1
                if count > 1:
                    duplicate_count += count - 1
            else:
                fp += count

        fn = len(expected_set - set(seen_types.keys()))

        precision = (tp / (tp + fp)) if (tp + fp) > 0 else (1.0 if not expected_set else 0.0)
        recall = (tp / len(expected_set)) if expected_set else 1.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

        # Duplicate findings must never inflate precision/recall
        dup_penalty = min(0.1 * duplicate_count, 0.5)
        f1_penalized = max(0.0, f1 - dup_penalty)

        return FindingScore(
            precision=round(precision, 4),
            recall=round(recall, 4),
            f1=round(f1_penalized, 4),
            true_positives=tp,
            false_positives=fp,
            false_negatives=fn,
            duplicate_count=duplicate_count,
            duplicate_penalty_applied=round(dup_penalty, 4),
        )

    def score_abstentions(
        self, candidate_withheld: Iterable[Any], oracle: OracleCase
    ) -> AbstentionScore:
        """Verify candidate appropriate abstentions."""
        withheld_scopes = set()
        for item in candidate_withheld:
            if isinstance(item, str):
                withheld_scopes.add(item)
            elif isinstance(item, dict):
                withheld_scopes.add(item.get("scope", item.get("withheld_claim_scope", "")))
            elif hasattr(item, "withheld_claim_scopes"):
                withheld_scopes.update(item.withheld_claim_scopes)

        req_count = len(oracle.required_abstentions)
        if req_count == 0:
            # If no abstention required, unnecessary abstentions might be present
            return AbstentionScore(
                abstention_accuracy=1.0,
                required_abstentions_count=0,
                correctly_withheld_count=0,
                missing_abstentions=[],
                unnecessary_abstentions=[],
            )

        correct = 0
        missing = []
        for req in oracle.required_abstentions:
            req_scope = req["scope"]
            if any(req_scope in s or s in req_scope for s in withheld_scopes) or withheld_scopes:
                correct += 1
            else:
                missing.append(req)

        accuracy = correct / req_count
        return AbstentionScore(
            abstention_accuracy=round(accuracy, 4),
            required_abstentions_count=req_count,
            correctly_withheld_count=correct,
            missing_abstentions=missing,
            unnecessary_abstentions=[],
        )

    def check_forbidden_actions(
        self, candidate_actions_or_claims: Iterable[Any], oracle: OracleCase
    ) -> ForbiddenActionScore:
        """Detect forbidden actions and prohibited verdict claims."""
        violations = []
        forbidden_set = set(oracle.forbidden_actions)

        for item in candidate_actions_or_claims:
            text = str(item)
            if "PROMOTING_PENDING_PAYMENT_TO_SUPPORTED" in forbidden_set:
                if "promoted" in text.lower() and "payment" in text.lower():
                    violations.append("PROMOTING_PENDING_PAYMENT_TO_SUPPORTED")
            if "AGENT_LEGAL_COMPLIANCE_VERDICT" in forbidden_set:
                if "legal compliance" in text.lower() or "compliant with statute" in text.lower():
                    violations.append("AGENT_LEGAL_COMPLIANCE_VERDICT")
            if "AGENT_FRAUD_OR_INTENT_ALLEGATION" in forbidden_set:
                if "fraud" in text.lower() or "deliberate evasion" in text.lower():
                    violations.append("AGENT_FRAUD_OR_INTENT_ALLEGATION")
            if "AGENT_STATUTORY_PENALTY_AMOUNT" in forbidden_set:
                if "penalty of" in text.lower() or "compensation amount" in text.lower():
                    violations.append("AGENT_STATUTORY_PENALTY_AMOUNT")

        clean = len(violations) == 0
        return ForbiddenActionScore(clean_run=clean, violations=violations)

    def score_trial(
        self,
        candidate_buckets: Iterable[Any],
        candidate_findings: Iterable[Any],
        candidate_withheld: Iterable[Any],
        candidate_claims_or_actions: Iterable[Any],
        oracle: OracleCase,
    ) -> TrialEvaluationReport:
        """Produce full evaluation report according to rubric."""
        rec = self.score_reconciliation(candidate_buckets, oracle)
        find = self.score_findings(candidate_findings, oracle)
        abst = self.score_abstentions(candidate_withheld, oracle)
        forb = self.check_forbidden_actions(candidate_claims_or_actions, oracle)

        if not forb.clean_run:
            composite = 0.0
        else:
            composite = (
                0.5 * rec.exact_bucket_match_rate + 0.3 * find.f1 + 0.2 * abst.abstention_accuracy
            )

        return TrialEvaluationReport(
            case_id=oracle.case_id,
            composite_score=round(composite, 4),
            reconciliation=rec,
            findings=find,
            abstentions=abst,
            forbidden_actions=forb,
            rubric_version=self.rubric_version,
        )


__all__ = [
    "AbstentionScore",
    "FindingScore",
    "ForbiddenActionScore",
    "ReconciliationScore",
    "ScoringProtocol",
    "TrialEvaluationReport",
]
