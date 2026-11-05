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
    kind: Literal[
        "OLD_RULE_PERIOD",
        "UNVERIFIED_EXTENSION",
        "UNSUPPORTED_REFURBISHMENT_OFFSET",
        "INSTRUCTION_TEXT",
    ]
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


# Directive wording addressed to an automated reader rather than to a person. Matching text is
# evidence about the document; it is never quoted into a report and never followed.
_INSTRUCTION = re.compile(
    r"\bsystem\s+(?:instruction|prompt)s?\b"
    r"|\b(?:ignore|disregard)\s+(?:all\s+|any\s+)?(?:previous|prior|earlier|above)\b"
    r"|\bautomated\s+(?:review(?:er)?s?|verification|compliance|tools?|systems?|agents?)\b"
    r"|\byou\s+are\s+now\b"
    r"|\b(?:assistant|ai|model)\s*:\s*override\b",
    re.IGNORECASE,
)


def _strings(value) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [text for item in value.values() for text in _strings(item)]
    if isinstance(value, list):
        return [text for item in value for text in _strings(item)]
    return []


def addresses_automated_reader(observation: Observation) -> bool:
    text = " ".join(_strings(observation.raw_fields) + _strings(observation.parsed_fields))
    return _INSTRUCTION.search(text) is not None


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
    observations: list[Observation], reporting_period: str, case_periods=()
) -> list[RegulatoryClaimFinding]:
    """Inspect supplied, approved-case observations; references retain exact original locators.

    This detects claims requiring investigation, never certifies the legal authority
    of a dossier assertion. Callers retain responsibility for case-membership approval.
    A cited period the case itself holds an obligation for (``case_periods``, such as an
    earlier liability year) is that period's own record, not a wrong-period rule citation.
    """
    findings = []
    target = _period(reporting_period)
    own = {target} | {_period(period) for period in case_periods}
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
            and cited not in own
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
        if addresses_automated_reader(observation):
            kinds.append(
                (
                    "INSTRUCTION_TEXT",
                    "UNKNOWN",
                    "text addressed to automated tools",
                    (
                        "Document text addresses automated tools; it was treated as evidence "
                        "only and changed no permission or control."
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
