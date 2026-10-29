"""Conservative checks of visible dossier claims, independent of benchmark labels."""

import hashlib
import json
import re
from typing import Literal

from pydantic import Field

from recycleguard.contracts.core import BoundaryModel, EvidenceRef
from recycleguard.contracts.extraction import Observation


class RegulatoryClaimFinding(BoundaryModel):
    finding_id: str
    kind: Literal["OLD_RULE_PERIOD", "UNVERIFIED_EXTENSION", "UNSUPPORTED_REFURBISHMENT_OFFSET"]
    outcome: Literal["FAIL", "UNKNOWN"]
    scope: str
    summary: str
    evidence_refs: list[EvidenceRef]
    cited_reporting_period: str | None = None
    cited_regime: str | None = None


class RegulatoryCheckRequest(BoundaryModel):
    claim_kind: Literal["RULE_APPLICABILITY", "DEADLINE_EXTENSION", "REFURBISHMENT_OFFSET"]
    query: str
    target_reporting_period: str
    cited_reporting_period: str | None = None
    cited_regime: str | None = None
    metal: str | None = None
    evidence_refs: list[EvidenceRef] = Field(min_length=1)


class RegulatoryCheckResult(BoundaryModel):
    outcome: Literal["FAIL", "UNKNOWN", "PASS"]
    scope: str
    reasons: list[str]
    evidence_refs: list[EvidenceRef]
    unsupported_calculation_withheld: bool = False


def _period(value: str) -> str | None:
    match = re.search(
        r"\b(?:FY\s*(20\d{2})\s*[-–/]\s*(?:20)?(\d{2})|(20\d{2})\s*[-–/]\s*(20\d{2}))\b",
        value,
        re.I,
    )
    if match is None:
        return None
    start = int(match[1] or match[3])
    end = int(match[2]) if match[1] else int(match[4]) % 100
    return f"{start}-{end:02d}" if end == (start + 1) % 100 else None


def inspect_regulatory_claims(
    observations: list[Observation], reporting_period: str
) -> list[RegulatoryClaimFinding]:
    """Inspect supplied, approved-case observations; references retain exact original locators.

    This detects claims requiring investigation, never certifies the legal authority
    of a dossier assertion. Callers retain responsibility for case-membership approval.
    """
    findings = []
    target = _period(reporting_period)
    for observation in observations:
        text = json.dumps(
            {"raw": observation.raw_fields, "parsed": observation.parsed_fields}, ensure_ascii=False
        ).lower()
        kinds = []
        cited = _period(text)
        old_rule = bool(re.search(r"(?:rules?[^\n]{0,40}2016|2016[^\n]{0,40}rules?)", text))
        if old_rule or (
            cited is not None
            and target is not None
            and cited != target
            and any(term in text for term in ("rule", "regulat", "applicab"))
        ):
            kinds.append(
                (
                    "OLD_RULE_PERIOD",
                    "FAIL",
                    "cited rule / reporting period",
                    "Dossier cites an older rule or a reporting period different from the case.",
                )
            )
        if ("extension" in text or "extended" in text) and any(
            word in text for word in ("unsigned", "unverified", "notice", "circular")
        ):
            kinds.append(
                (
                    "UNVERIFIED_EXTENSION",
                    "UNKNOWN",
                    "claimed deadline extension",
                    (
                        "An extension claim requires the reviewed issued order; "
                        "the dossier notice is insufficient."
                    ),
                )
            )
        if "refurbish" in text and any(word in text for word in ("offset", "deduct", "defer")):
            kinds.append(
                (
                    "UNSUPPORTED_REFURBISHMENT_OFFSET",
                    "UNKNOWN",
                    "refurbishment offset only",
                    (
                        "Refurbishment offset is outside the supported calculation profile; "
                        "ordinary supplied-target arithmetic remains available."
                    ),
                )
            )
        reference = EvidenceRef(
            ref_kind="OBSERVATION",
            ref_id=observation.observation_id,
            artifact_revision_id=observation.artifact_revision_id,
            locator=observation.locator,
        )
        for kind, outcome, scope, summary in kinds:
            digest = hashlib.sha256(f"{observation.observation_id}:{kind}".encode()).hexdigest()[
                :24
            ]
            findings.append(
                RegulatoryClaimFinding(
                    finding_id=f"finding:regulatory_{digest}",
                    kind=kind,
                    outcome=outcome,
                    scope=scope,
                    summary=summary,
                    evidence_refs=[reference],
                    cited_reporting_period=cited,
                    cited_regime="E_WASTE_2016" if old_rule else None,
                )
            )
    return findings


class RuleApplicabilityChecker:
    def __init__(self, retrieval):
        self.retrieval = retrieval

    def check(self, request: RegulatoryCheckRequest) -> RegulatoryCheckResult:
        if request.claim_kind == "REFURBISHMENT_OFFSET":
            return RegulatoryCheckResult(
                outcome="UNKNOWN",
                scope="refurbishment offset only",
                reasons=[
                    (
                        "No reviewed supported offset calculator is available; "
                        "supplied-target arithmetic is unaffected."
                    )
                ],
                evidence_refs=request.evidence_refs,
                unsupported_calculation_withheld=True,
            )
        wrong_period = request.cited_reporting_period is not None and _period(
            request.cited_reporting_period
        ) != _period(request.target_reporting_period)
        if request.claim_kind == "RULE_APPLICABILITY" and (
            wrong_period or request.cited_regime == "E_WASTE_2016"
        ):
            return RegulatoryCheckResult(
                outcome="FAIL",
                scope="cited rule / reporting period",
                reasons=[
                    "The cited rule or period does not establish applicability for this case."
                ],
                evidence_refs=request.evidence_refs,
            )
        return RegulatoryCheckResult(
            outcome="UNKNOWN",
            scope=request.claim_kind,
            reasons=[
                (
                    "A reviewed applicable provision and issued order, where required, "
                    "must establish this claim; dossier assertions alone do not."
                )
            ],
            evidence_refs=request.evidence_refs,
        )
