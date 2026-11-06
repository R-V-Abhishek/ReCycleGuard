"""Boundary models of the MG2 Reader and Analyst. See docs/checkpoints/mg2/DESIGN.md."""

from typing import Literal

from pydantic import Field

from recycleguard.contracts.core import BoundaryModel
from recycleguard.contracts.workflow import FindingProposal

# Closed list from the public family definitions (docs/design/CONTRACTS.md, FaultFamily table).
# A kind says what a passage is about. It carries no verdict and no instruction.
ClaimKind = Literal[
    "AUTOMATION_DIRECTIVE",
    "RULE_OR_PERIOD_CITATION",
    "DEADLINE_EXTENSION_CLAIM",
    "UNSUPPORTED_REGIME_CLAIM",
    "PAYMENT_WITHOUT_TRANSFER",
    "EXPIRED_OR_CANCELLED_INSTRUMENT",
    "ENTITY_ALIAS_STATEMENT",
    "WEIGHT_BASIS_STATEMENT",
    "MIXED_UNIT_STATEMENT",
]

# Which family a verified claim kind can support. The Analyst may propose a text-derived family
# only when a verified claim of one of its kinds backs it.
CLAIM_FAMILY = {
    "AUTOMATION_DIRECTIVE": "F16_PROMPT_INJECTION",
    "RULE_OR_PERIOD_CITATION": "F11_WRONG_PERIOD_RULE",
    "DEADLINE_EXTENSION_CLAIM": "F12_UNSEEN_NOTICE_LEAD",
    "UNSUPPORTED_REGIME_CLAIM": "F14_OUT_OF_SCOPE_REGIME",
    "PAYMENT_WITHOUT_TRANSFER": "F07_PAID_NO_TRANSFER",
    "EXPIRED_OR_CANCELLED_INSTRUMENT": "F09_EXPIRED_CANCELLED",
    "ENTITY_ALIAS_STATEMENT": "F05_WRONG_ENTITY_ALIAS",
    "WEIGHT_BASIS_STATEMENT": "F13_WEIGHT_BASIS_CONFLICT",
    "MIXED_UNIT_STATEMENT": "F04_UNIT_DIMENSION_MIX",
}

MAX_QUOTE = 160
MAX_CLAIMS = 12
MAX_PROPOSALS = 6


class Claim(BoundaryModel):
    """One passage the Reader says is about a kind. The quote is a locator, not a conclusion."""

    kind: ClaimKind
    observation_id: str
    quote: str = Field(min_length=3, max_length=MAX_QUOTE)


class ReaderProposal(BoundaryModel):
    claims: list[Claim] = Field(max_length=MAX_CLAIMS)


class VerifiedClaim(BoundaryModel):
    """A claim whose observation was shown and whose quote occurs there verbatim. No text."""

    kind: ClaimKind
    observation_id: str


class DroppedClaim(BoundaryModel):
    kind: str
    observation_id: str
    reason: Literal["OBSERVATION_NOT_SHOWN", "QUOTE_NOT_IN_TEXT"]


class AnalystProposal(BoundaryModel):
    findings: list[FindingProposal] = Field(max_length=MAX_PROPOSALS)


ReaderStopReason = Literal["CHUNK_CAP", "INVALID_OUTPUT"]


class ReaderCoverage(BoundaryModel):
    """What the Reader did and did not read; an unread unit is stated, never silent."""

    units_total: int
    units_read: int
    units_truncated: int
    chunks: int
    calls: int
    claims_proposed: int
    claims_verified: int
    claims_dropped: list[DroppedClaim]
    stopped_because: ReaderStopReason | None = None
