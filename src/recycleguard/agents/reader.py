"""The quarantined Reader: sees document text, returns only verified claim kinds.

Everything around the model call is deterministic. The text selector decides what is read,
the chunker bounds each call, and the verifier drops any claim whose observation was not shown
or whose quote is not in that observation's text. Quotes are not kept.
"""

from collections.abc import Callable

from recycleguard.agents.models import (
    Claim,
    DroppedClaim,
    ReaderCoverage,
    ReaderProposal,
    VerifiedClaim,
)
from recycleguard.contracts.extraction import Observation

MAX_UNIT_CHARS = 1200
MAX_CHUNK_CHARS = 3600
MIN_TEXT_WORDS = 4


class AgentCallError(Exception):
    """A model call failed or its reply stayed invalid after the runner's retry."""


def _strings(value) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [text for key in sorted(value) for text in _strings(value[key])]
    if isinstance(value, list):
        return [text for item in value for text in _strings(item)]
    return []


def text_units(observations: list[Observation]) -> list[tuple[str, str]]:
    """(observation_id, text) of every observation holding prose, in a stable order.

    Prose means a string field of at least MIN_TEXT_WORDS words. Identifiers, codes and
    numbers are structured data the deterministic engine already reads.
    """
    units = []
    for observation in sorted(observations, key=lambda item: item.observation_id):
        prose = [
            text.strip()
            for text in _strings(observation.raw_fields)
            if len(text.split()) >= MIN_TEXT_WORDS
        ]
        if prose:
            units.append((observation.observation_id, "\n".join(prose)))
    return units


def chunk_units(
    units: list[tuple[str, str]], max_chunks: int
) -> tuple[list[list[tuple[str, str]]], int, int]:
    """Pack units into chunks of at most MAX_CHUNK_CHARS. Returns (chunks, read, truncated).

    A unit over MAX_UNIT_CHARS is cut and counted as truncated. Units that do not fit in
    max_chunks are not read; the caller reports them through the coverage.
    """
    chunks: list[list[tuple[str, str]]] = []
    current: list[tuple[str, str]] = []
    size = 0
    read = truncated = 0
    for observation_id, text in units:
        if len(text) > MAX_UNIT_CHARS:
            text, truncated = text[:MAX_UNIT_CHARS], truncated + 1
        if current and size + len(text) > MAX_CHUNK_CHARS:
            chunks.append(current)
            current, size = [], 0
        if len(chunks) >= max_chunks:
            break
        current.append((observation_id, text))
        size += len(text)
        read += 1
    if current and len(chunks) < max_chunks:
        chunks.append(current)
    return chunks, read, truncated


def verify_claims(
    claims: list[Claim], shown: dict[str, str]
) -> tuple[list[VerifiedClaim], list[DroppedClaim]]:
    """Keep a claim only when its observation was shown and the quote occurs there verbatim."""
    verified: dict[tuple[str, str], VerifiedClaim] = {}
    dropped = []
    for claim in claims:
        text = shown.get(claim.observation_id)
        if text is None:
            reason = "OBSERVATION_NOT_SHOWN"
        elif claim.quote not in text:
            reason = "QUOTE_NOT_IN_TEXT"
        else:
            verified.setdefault(
                (claim.kind, claim.observation_id),
                VerifiedClaim(kind=claim.kind, observation_id=claim.observation_id),
            )
            continue
        dropped.append(
            DroppedClaim(kind=claim.kind, observation_id=claim.observation_id, reason=reason)
        )
    return list(verified.values()), dropped


def reader_body(chunk: list[tuple[str, str]]) -> dict:
    """The only content a Reader call receives."""
    return {"passages": [{"observation_id": ref, "text": text} for ref, text in chunk]}


def run_reader(
    observations: list[Observation],
    call: Callable[[dict], ReaderProposal],
    max_chunks: int,
) -> tuple[list[VerifiedClaim], ReaderCoverage]:
    """Read the prose of a case in at most max_chunks calls.

    `call` returns a validated ReaderProposal or raises AgentCallError. An invalid reply ends
    reading with the claims verified so far; nothing is retried here.
    """
    units = text_units(observations)
    chunks, read, truncated = chunk_units(units, max_chunks)
    verified: dict[tuple[str, str], VerifiedClaim] = {}
    dropped: list[DroppedClaim] = []
    proposed = calls = 0
    stopped = "CHUNK_CAP" if read < len(units) else None
    for chunk in chunks:
        calls += 1
        try:
            reply = call(reader_body(chunk))
        except AgentCallError:
            stopped = "INVALID_OUTPUT"
            break
        proposed += len(reply.claims)
        good, bad = verify_claims(reply.claims, dict(chunk))
        verified.update({(item.kind, item.observation_id): item for item in good})
        dropped.extend(bad)
    return list(verified.values()), ReaderCoverage(
        units_total=len(units),
        units_read=read,
        units_truncated=truncated,
        chunks=len(chunks),
        calls=calls,
        claims_proposed=proposed,
        claims_verified=len(verified),
        claims_dropped=dropped,
        stopped_because=stopped,
    )
