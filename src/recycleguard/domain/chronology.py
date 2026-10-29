"""Order and timing from evidence only: coarse or overlapping times are ties, never guesses."""

from calendar import monthrange
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta

from recycleguard.contracts.core import TemporalValue

Span = tuple[datetime, datetime]
_POINT = timedelta(microseconds=1)


def span(value: TemporalValue | None) -> Span | None:
    """Half-open [lo, hi) interval a reviewed/parsed time can actually denote; None if unusable."""
    if value is None or value.value is None:
        return None
    if value.interpretation_status not in {"PARSED", "REVIEWED"}:
        return None
    text = value.value
    if value.precision == "INSTANT":
        point = datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)
        return point, point + _POINT
    if value.precision == "DATE":
        lo = datetime.fromisoformat(text).replace(tzinfo=UTC)
        return lo, lo + timedelta(days=1)
    if value.precision == "MONTH":
        lo = datetime.fromisoformat(text + "-01").replace(tzinfo=UTC)
        return lo, lo + timedelta(days=monthrange(lo.year, lo.month)[1])
    if value.precision == "YEAR":
        lo = datetime.fromisoformat(text + "-01-01").replace(tzinfo=UTC)
        return lo, datetime(lo.year + 1, 1, 1, tzinfo=UTC)
    return None


def span_before(left: Span | None, right: Span | None) -> bool | None:
    """True if left is entirely before right, False if entirely after, None if they overlap."""
    if left is None or right is None:
        return None
    if left[1] <= right[0]:
        return True
    if right[1] <= left[0]:
        return False
    return None


class Chronology:
    """Allocation order: explicit caller order wins, else reviewed allocation_time, else unknown."""

    def __init__(
        self,
        explicit: Mapping[str, int] | None,
        times: Mapping[str, TemporalValue | None],
    ):
        self._explicit = dict(explicit or {})
        self._spans = {key: span(value) for key, value in times.items()}

    def known(self, allocation_id: str) -> bool:
        return allocation_id in self._explicit or self._spans.get(allocation_id) is not None

    def before(self, left: str, right: str) -> bool | None:
        """True if `left` was allocated strictly before `right`; None if order is not evidenced."""
        if left in self._explicit and right in self._explicit:
            a, b = self._explicit[left], self._explicit[right]
            return None if a == b else a < b
        return span_before(self._spans.get(left), self._spans.get(right))
