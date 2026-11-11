"""Boundary models of the MG2 Retriever and Classifier. See docs/checkpoints/mg2/DESIGN.md."""

from typing import Literal

from pydantic import Field

from recycleguard.contracts.core import BoundaryModel, EvidenceRef
from recycleguard.contracts.workflow import FindingProposal

# Closed list from the public family definitions (docs/design/CONTRACTS.md, FaultFamily table).
# A kind says what a passage is about. It carries no verdict and no instruction.
ClaimKind = Literal[
    "AUTOMATION_DIRECTIVE",
    "RULE_PERIOD_MISMATCH",
    "DEADLINE_EXTENSION_CLAIM",
    "UNSUPPORTED_REGIME_CLAIM",
    "PAYMENT_WITHOUT_TRANSFER",
    "EXPIRED_OR_CANCELLED_INSTRUMENT",
    "ENTITY_ALIAS_STATEMENT",
    "WEIGHT_BASIS_STATEMENT",
    "MIXED_UNIT_STATEMENT",
]

# Which family a verified claim kind can support. A text-derived family can be proposed only when
# a verified claim of one of its kinds backs it.
CLAIM_FAMILY = {
    "AUTOMATION_DIRECTIVE": "F16_PROMPT_INJECTION",
    "RULE_PERIOD_MISMATCH": "F11_WRONG_PERIOD_RULE",
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
MAX_IDS = 8

# RETRIEVER_LOOKUP (M1): Retriever, then a fixed kind-to-family lookup. No Classifier call.
# RETRIEVER_CLASSIFIER (M2): Retriever, then the Classifier with compute tools.
# CLASSIFIER_ONLY (M2-nr): the Classifier alone, with no verified claims.
AgentArchitecture = Literal["RETRIEVER_LOOKUP", "RETRIEVER_CLASSIFIER", "CLASSIFIER_ONLY"]

RetrieverTool = Literal["list_passages", "read_passages", "search_rules"]
ClassifierTool = Literal["compute_reconciliation", "trace_certificate"]
Grade = Literal["NO_RESULT_YET", "SUFFICIENT", "WEAK", "EMPTY"]
StopReason = Literal["TURN_CAP", "INVALID_OUTPUT", "BUDGET_EXHAUSTED"]


class Claim(BoundaryModel):
    """One passage the Retriever says is about a kind. The quote is a locator, not a conclusion."""

    kind: ClaimKind
    observation_id: str
    quote: str = Field(min_length=3, max_length=MAX_QUOTE)


class RetrieverStep(BoundaryModel):
    """One Retriever turn: grade the last result, then call a tool or finish. Claims accumulate."""

    grade: Grade
    reason: str = Field(max_length=240)
    action: Literal["CALL", "FINISH"]
    tool: RetrieverTool | None = None
    query: str | None = Field(default=None, max_length=160)
    observation_ids: list[str] = Field(default_factory=list, max_length=3)
    claims: list[Claim] = Field(default_factory=list, max_length=MAX_CLAIMS)


class ClassifierStep(BoundaryModel):
    """One Classifier turn: call a compute tool, or propose findings and stop."""

    action: Literal["CALL", "PROPOSE"]
    tool: ClassifierTool | None = None
    bucket_ids: list[str] = Field(default_factory=list, max_length=MAX_IDS)
    certificate_ids: list[str] = Field(default_factory=list, max_length=MAX_IDS)
    findings: list[FindingProposal] = Field(default_factory=list, max_length=MAX_PROPOSALS)


class VerifiedClaim(BoundaryModel):
    """A claim whose observation was shown and whose quote occurs there verbatim. No text."""

    kind: ClaimKind
    observation_id: str


class DroppedClaim(BoundaryModel):
    kind: str
    observation_id: str
    reason: Literal["OBSERVATION_NOT_SHOWN", "QUOTE_NOT_IN_TEXT"]


class RetrieverTurn(BoundaryModel):
    """What one turn did, for the trace: the grade it gave, the call it made and what came back."""

    turn: int
    grade: Grade
    reason: str
    action: Literal["CALL", "FINISH"]
    tool: RetrieverTool | None
    query: str | None
    observation_ids: list[str]
    refused: str | None
    result_ids: list[str]
    claims_proposed: int


class ClassifierTurn(BoundaryModel):
    action: Literal["CALL", "PROPOSE"]
    tool: ClassifierTool | None
    ids: list[str]
    refused: str | None
    findings: int


class RetrievalCoverage(BoundaryModel):
    """What the Retriever did and did not read; an unread passage is stated, never silent."""

    units_total: int
    units_read: int
    units_truncated: int
    turns: int
    tool_calls: int
    searches: int
    reformulations: int
    claims_proposed: int
    claims_verified: int
    claims_dropped: list[DroppedClaim]
    read_observation_ids: list[str]
    stopped_because: StopReason | None = None


class AgentRecord(BoundaryModel):
    """What the agents produced in one run, archived before the report is drafted.

    The proposals are still only proposals: the finding gate decides what reaches a report.
    """

    architecture: AgentArchitecture
    coverage: RetrievalCoverage | None
    retriever_turns: list[RetrieverTurn]
    classifier_turns: list[ClassifierTurn]
    verified_claims: list[VerifiedClaim]
    proposals: list[FindingProposal]
    unsupported_proposals: list[FindingProposal]
    refs: list[EvidenceRef]
    classifier_calls: int
    classifier_stopped_because: StopReason | None = None
