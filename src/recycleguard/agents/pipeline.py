"""Reader then Analyst, as a pure function of observations, facts and two model calls."""

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass

from pydantic import JsonValue

from recycleguard.agents.analyst import allowed_refs, analyst_body, require_claim_support
from recycleguard.agents.models import (
    AnalystProposal,
    ReaderCoverage,
    ReaderProposal,
    VerifiedClaim,
)
from recycleguard.agents.reader import AgentCallError, run_reader
from recycleguard.contracts.core import EvidenceRef
from recycleguard.contracts.extraction import Observation
from recycleguard.contracts.workflow import FindingProposal


@dataclass
class AgentOutcome:
    """What the agents produced. Proposals still go through the finding gate."""

    proposals: list[FindingProposal]
    unsupported: list[FindingProposal]
    refs: dict[str, EvidenceRef]
    verified: list[VerifiedClaim]
    coverage: ReaderCoverage | None
    analyst_calls: int
    analyst_stopped_because: str | None


def run_agents(
    observations: list[Observation],
    *,
    facts: Mapping[str, JsonValue],
    calculation_ids: Iterable[str],
    decided_families: Iterable[str],
    families: Iterable[str],
    read: Callable[[dict], ReaderProposal],
    analyse: Callable[[dict], AnalystProposal],
    max_reader_chunks: int,
    reader_context: Mapping[str, JsonValue] | None = None,
    use_reader: bool = True,
) -> AgentOutcome:
    """Run the Reader (unless ablated) and one Analyst call.

    A failed Reader call keeps the claims verified so far. A failed Analyst call yields no
    proposals; the deterministic findings are unaffected either way.
    """
    verified: list[VerifiedClaim] = []
    coverage = None
    if use_reader:
        verified, coverage = run_reader(observations, read, max_reader_chunks, reader_context)
    calculation_ids = list(calculation_ids)
    body = analyst_body(facts, calculation_ids, verified, decided_families, families)
    refs = allowed_refs(observations, verified, calculation_ids)
    try:
        reply = analyse(body)
        proposals, unsupported = require_claim_support(reply.findings, verified)
        stopped = None
    except AgentCallError as exc:
        proposals, unsupported, stopped = [], [], exc.reason
    return AgentOutcome(proposals, unsupported, refs, verified, coverage, 1, stopped)
