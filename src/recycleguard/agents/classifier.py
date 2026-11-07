"""The Classifier: decides which families the computed facts and verified claims show.

It never sees passage text, only claim kinds and ids. It may call the compute tools a few times to
read a figure or a lifecycle before it decides, and then proposes findings. Calls are run by
`execute`, an audited external call supplied by the workflow runner. The deterministic parts are
which calls are valid, which are repeats, which ids the proposals may cite, and the support filter.
"""

import hashlib
import json
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field

from pydantic import JsonValue

from recycleguard.agents.models import (
    CLAIM_FAMILY,
    ClassifierStep,
    ClassifierTurn,
    VerifiedClaim,
)
from recycleguard.agents.passages import AgentCallError
from recycleguard.agents.registry import STATUS_RULES
from recycleguard.contracts.core import EvidenceRef
from recycleguard.contracts.extraction import Observation
from recycleguard.contracts.workflow import FindingProposal

TEXT_FAMILIES = frozenset(CLAIM_FAMILY.values())
MAX_ID_ARGUMENTS = 8


@dataclass
class ClassifierToolResult:
    view: dict
    refused: str | None = None
    calculation_ids: list[str] = field(default_factory=list)


@dataclass
class ClassifierOutcome:
    proposals: list[FindingProposal]
    turns: list[ClassifierTurn]
    calculation_ids: list[str]
    calls: int
    stopped_because: str | None


def call_key(step: ClassifierStep) -> str:
    ids = step.bucket_ids if step.tool == "compute_reconciliation" else step.certificate_ids
    return hashlib.sha256(json.dumps([step.tool, sorted(ids)]).encode()).hexdigest()


def refusal_for(
    step: ClassifierStep,
    known: Mapping[str, Iterable[str]],
    called: set[str],
) -> str | None:
    """Why a requested compute call cannot run, or None. A refusal still uses one call."""
    if step.tool is None:
        return "tool is required when action is CALL"
    ids = step.bucket_ids if step.tool == "compute_reconciliation" else step.certificate_ids
    if step.tool == "trace_certificate" and not ids:
        return "certificate_ids is required for trace_certificate"
    unknown = [ref for ref in ids if ref not in set(known[step.tool])]
    if unknown:
        return "ids must be copied exactly from facts"
    return "that call was already made" if call_key(step) in called else None


def classifier_body(
    facts: Mapping[str, JsonValue],
    calculation_ids: Iterable[str],
    verified: Iterable[VerifiedClaim],
    decided_families: Iterable[str],
    families: Iterable[str],
    results: list[dict],
    calls_left: int,
) -> dict:
    """The only content a Classifier call receives. Claims are kind and id; the text is not here."""
    return {
        "facts": dict(facts),
        "calculation_ids": list(calculation_ids),
        "verified_claims": [
            {
                "kind": claim.kind,
                "family": CLAIM_FAMILY[claim.kind],
                "observation_id": claim.observation_id,
            }
            for claim in verified
        ],
        "tool_results": results,
        "already_decided_families": sorted(set(decided_families)),
        "calls_left": calls_left,
        "allowed_families": sorted(set(families)),
    }


def allowed_refs(
    observations: Iterable[Observation],
    verified: Iterable[VerifiedClaim],
    calculation_ids: Iterable[str],
) -> dict[str, EvidenceRef]:
    """What proposals may cite: verified-claim observations and this run's calculations."""
    wanted = {claim.observation_id for claim in verified}
    refs = {
        item.observation_id: EvidenceRef(
            ref_kind="OBSERVATION",
            ref_id=item.observation_id,
            artifact_revision_id=item.artifact_revision_id,
            locator=item.locator,
        )
        for item in observations
        if item.observation_id in wanted
    }
    for calculation_id in calculation_ids:
        refs[calculation_id] = EvidenceRef(
            ref_kind="CALCULATION", ref_id=calculation_id, artifact_revision_id=None, locator=None
        )
    return refs


def require_claim_support(
    proposals: Iterable[FindingProposal], verified: Iterable[VerifiedClaim]
) -> tuple[list[FindingProposal], list[FindingProposal]]:
    """A text-derived family needs a verified claim of its kind on a cited observation.

    Returns (kept, unsupported). Families computed from records, such as F02 or F10, pass through
    to the gate, which checks them against the deterministic universe.
    """
    backed = {(CLAIM_FAMILY[claim.kind], claim.observation_id) for claim in verified}
    kept, unsupported = [], []
    for proposal in proposals:
        if proposal.issue_type in TEXT_FAMILIES and not any(
            (proposal.issue_type, ref) in backed for ref in proposal.evidence_ref_ids
        ):
            unsupported.append(proposal)
        else:
            kept.append(proposal)
    return kept, unsupported


def lookup_proposals(
    verified: Iterable[VerifiedClaim], decided_families: Iterable[str]
) -> list[FindingProposal]:
    """M1: no model. One finding per family a verified claim points to, cited to its passages."""
    skip = set(decided_families)
    cited: dict[str, list[str]] = {}
    for claim in verified:
        family = CLAIM_FAMILY[claim.kind]
        if family not in skip and claim.observation_id not in cited.setdefault(family, []):
            cited[family].append(claim.observation_id)
    proposals = []
    for family, observation_ids in cited.items():
        status, reason, scopes = STATUS_RULES.get(family, ("REQUIRES_EXPERT_REVIEW", None, ()))
        proposals.append(
            FindingProposal(
                issue_type=family,
                advisory_status=status,
                basis="A passage in the cited document matches the pattern this family describes.",
                evidence_ref_ids=observation_ids[:3],
                abstention_reason=reason,
                withheld_claim_scopes=list(scopes),
                next_action_kind="INVESTIGATE",
                next_action_text="A reviewer reads the cited passage and confirms the family.",
            )
        )
    return proposals


def run_classifier(
    *,
    facts: Mapping[str, JsonValue],
    calculation_ids: Iterable[str],
    verified: list[VerifiedClaim],
    decided_families: Iterable[str],
    families: Iterable[str],
    known_ids: Mapping[str, Iterable[str]],
    step: Callable[[dict], ClassifierStep],
    execute: Callable[[ClassifierStep], ClassifierToolResult],
    max_calls: int,
) -> ClassifierOutcome:
    """At most max_calls tool calls, then one proposal turn. A failed call yields no findings."""
    calculation_ids = list(calculation_ids)
    results: list[dict] = []
    turns: list[ClassifierTurn] = []
    called: set[str] = set()
    used = model_calls = 0
    stopped = None
    proposals: list[FindingProposal] = []
    while True:
        body = classifier_body(
            facts,
            calculation_ids,
            verified,
            decided_families,
            families,
            results,
            max_calls - used,
        )
        model_calls += 1
        try:
            reply = step(body)
        except AgentCallError as exc:
            stopped = exc.reason
            break
        if reply.action == "PROPOSE":
            proposals = reply.findings
            turns.append(
                ClassifierTurn(
                    action="PROPOSE", tool=None, ids=[], refused=None, findings=len(proposals)
                )
            )
            break
        ids = reply.bucket_ids if reply.tool == "compute_reconciliation" else reply.certificate_ids
        if used >= max_calls:
            turns.append(
                ClassifierTurn(
                    action="CALL", tool=reply.tool, ids=ids, refused="CALL_CAP", findings=0
                )
            )
            stopped = "TURN_CAP"
            break
        used += 1
        refused = refusal_for(reply, known_ids, called)
        if refused is None:
            called.add(call_key(reply))
            result = execute(reply)
            refused = result.refused
            view = result.view
            calculation_ids += [c for c in result.calculation_ids if c not in calculation_ids]
        else:
            view = None
        results.append({"tool": reply.tool, "ids": ids, "refused": refused, "result": view})
        turns.append(
            ClassifierTurn(action="CALL", tool=reply.tool, ids=ids, refused=refused, findings=0)
        )
    return ClassifierOutcome(proposals, turns, calculation_ids, model_calls, stopped)
