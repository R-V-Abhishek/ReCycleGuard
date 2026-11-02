"""Credit lots are derived, not stored: one lot per resolved certificate (SYSTEM_DESIGN §6.2)."""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal

from recycleguard.contracts.domain import Certificate, CertificateEvent
from recycleguard.domain.arith import to_kg
from recycleguard.domain.universe import Universe

LotState = Literal["SUPPORTED", "PENDING", "CONFLICTING"]


@dataclass
class Lot:
    credit_lot_id: str
    certificate_id: str | None
    metal: str | None
    capacity: Decimal | None
    state: LotState
    reason: str
    event_ids: list[str] = field(default_factory=list)


def derive_lots(universe: Universe) -> dict[str, Lot]:
    certificates = universe.active(Certificate)
    events = universe.active(CertificateEvent)
    lots: dict[str, Lot] = {}
    owners: dict[str, set[str]] = {}
    for certificate in certificates:
        mine = [e for e in events if e.certificate_id == certificate.certificate_id]
        for lot_id in {e.credit_lot_id for e in mine if e.credit_lot_id is not None}:
            owners.setdefault(lot_id, set()).add(certificate.certificate_id)
    for certificate in certificates:
        mine = [e for e in events if e.certificate_id == certificate.certificate_id]
        lot_ids = sorted({e.credit_lot_id for e in mine if e.credit_lot_id is not None})
        for lot_id in lot_ids:
            on_lot = [e for e in mine if e.credit_lot_id == lot_id]
            if len(lot_ids) > 1:
                state, reason = "CONFLICTING", "certificate has events on more than one lot"
            elif len(owners[lot_id]) > 1:
                state, reason = "CONFLICTING", "lot is claimed by more than one certificate"
            elif any(e.quantity.metal != certificate.metal for e in on_lot):
                state, reason = "CONFLICTING", "event metal differs from certificate metal"
            elif certificate.validation_state != "VALID":
                state, reason = "PENDING", "certificate identity requires review"
            elif not any(e.assertion_state == "SUPPORTED" for e in on_lot):
                state, reason = "PENDING", "no supported event establishes the lot"
            else:
                state, reason = "SUPPORTED", "one resolved certificate with a supported event"
            lots[lot_id] = Lot(
                credit_lot_id=lot_id,
                certificate_id=certificate.certificate_id,
                metal=certificate.metal,
                capacity=to_kg(certificate.face_quantity),
                state=state,
                reason=reason,
                event_ids=sorted(e.event_id for e in on_lot),
            )
    return lots
