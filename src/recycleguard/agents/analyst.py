"""The Analyst: judges computed facts against verified claim kinds. It never sees prose."""

from collections.abc import Iterable, Mapping

from pydantic import JsonValue

from recycleguard.agents.models import CLAIM_FAMILY, VerifiedClaim
from recycleguard.contracts.core import EvidenceRef
from recycleguard.contracts.extraction import Observation
from recycleguard.contracts.workflow import FindingProposal

TEXT_FAMILIES = frozenset(CLAIM_FAMILY.values())


def analyst_body(
    facts: Mapping[str, JsonValue],
    verified: Iterable[VerifiedClaim],
    decided_families: Iterable[str],
    families: Iterable[str],
) -> dict:
    """The only content the Analyst call receives.

    `facts` holds computed figures and codes only. The claims are kind and observation id; the
    passage they came from is not passed on.
    """
    return {
        "facts": dict(facts),
        "verified_claims": [
            {
                "kind": claim.kind,
                "family": CLAIM_FAMILY[claim.kind],
                "observation_id": claim.observation_id,
            }
            for claim in verified
        ],
        "already_decided_families": sorted(set(decided_families)),
        "allowed_families": sorted(set(families)),
    }


def allowed_refs(
    observations: Iterable[Observation],
    verified: Iterable[VerifiedClaim],
    calculation_ids: Iterable[str],
) -> dict[str, EvidenceRef]:
    """What the Analyst may cite: verified-claim observations and this run's calculations."""
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
            ref_kind="CALCULATION",
            ref_id=calculation_id,
            artifact_revision_id=None,
            locator=None,
        )
    return refs


def require_claim_support(
    proposals: Iterable[FindingProposal], verified: Iterable[VerifiedClaim]
) -> tuple[list[FindingProposal], list[FindingProposal]]:
    """A text-derived family needs a verified claim of its kind on a cited observation.

    Returns (kept, unsupported). Families computed from records, such as F02 or F10, pass
    through to the gate, which checks them against the deterministic universe.
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
