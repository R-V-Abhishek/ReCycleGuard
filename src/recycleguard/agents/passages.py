"""The passages a Retriever may look at, and the check that a claim quotes what it was shown.

Everything here is deterministic. A passage is the prose of one observation; ids, codes and
numbers are structured data the engine already reads. Text the Retriever was shown is the only
text a quote may come from, and quotes are dropped from the record once verified.
"""

from recycleguard.agents.models import Claim, DroppedClaim, VerifiedClaim
from recycleguard.contracts.extraction import Observation

MAX_UNIT_CHARS = 1200
MIN_TEXT_WORDS = 4
HEAD_CHARS = 100
MAX_LISTED = 40


class AgentCallError(Exception):
    """A model call ended without a usable reply; that agent stops, the run does not."""

    def __init__(self, reason: str = "INVALID_OUTPUT"):
        super().__init__(reason)
        self.reason = reason


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

    Prose means a string field of at least MIN_TEXT_WORDS words.
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


def shown_text(units: dict[str, str], observation_id: str) -> str:
    """What a read returns for one passage: its text, cut at MAX_UNIT_CHARS."""
    return units[observation_id][:MAX_UNIT_CHARS]


def list_view(units: dict[str, str]) -> dict:
    """The table of contents a Retriever sees: id, length and first words. No full text."""
    ids = sorted(units)
    return {
        "count": len(ids),
        "not_listed": max(0, len(ids) - MAX_LISTED),
        "passages": [
            {
                "observation_id": ref,
                "chars": len(units[ref]),
                "first_words": units[ref][:HEAD_CHARS].replace("\n", " "),
            }
            for ref in ids[:MAX_LISTED]
        ],
    }


def read_view(units: dict[str, str], observation_ids: list[str]) -> dict:
    return {
        "passages": [
            {
                "observation_id": ref,
                "text": shown_text(units, ref),
                "truncated": len(units[ref]) > MAX_UNIT_CHARS,
            }
            for ref in observation_ids
        ]
    }


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
