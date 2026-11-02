"""Hand-calculated CP0 reference, independent of the generator and runtime tools.

Prepared during A02 integration; Vedantha's independent acknowledgement is pending.
Fractions avoid sharing the future production calculator's Decimal implementation.
"""

from fractions import Fraction


def reference_amounts() -> dict[str, str]:
    target, allocated, paid_pending = Fraction(100), Fraction(55), Fraction(25)
    assert target - allocated == 45
    # Financial payment does not increase supported credit; only a later supported allocation can.
    return {
        "required_target": f"{int(target)}.0000",
        "ledger_supported": f"{int(allocated)}.0000",
        "signed_gap": f"{int(target - allocated)}.0000",
        "pending_quantity": f"{int(paid_pending)}.0000",
        "portal_reported": "55.0000",
        "delta_portal_vs_ledger": "0.0000",
    }
