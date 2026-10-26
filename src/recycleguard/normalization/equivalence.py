"""Event equivalence engine (Gate G04 Lifecycle & Equivalence).

Implements F02 (Overlapping Export deduplication) and F03 (Multi-stage ID reuse)
conforming to CONTRACTS §3.4 and §5.4.
"""

from dataclasses import dataclass, field

from recycleguard.contracts.core import Issue
from recycleguard.contracts.domain import CertificateEvent, NonnegativeMass
from recycleguard.contracts.extraction import Observation
from recycleguard.normalization.models import EventEquivalence
from recycleguard.normalization.units import normalize_quantity


@dataclass(frozen=True)
class EventCompoundKey:
    """Canonical compound key for matching certificate events."""

    certificate_id: str
    metal: str
    quantity_kg: str
    from_entity_id: str | None
    to_entity_id: str | None
    event_kind: str
    transfer_stage: str | None
    event_date: str | None


@dataclass
class EquivalenceResolutionResult:
    """Outcome of resolving a collection of certificate observations."""

    events: list[CertificateEvent] = field(default_factory=list)
    equivalences: list[EventEquivalence] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)


class EventEquivalenceEngine:
    """Engine that evaluates certificate observations for equivalence or conflict."""

    def __init__(self, operation_id: str = "op:norm_001"):
        self.operation_id = operation_id

    def extract_compound_key(self, obs: Observation) -> EventCompoundKey:
        """Derive the compound key from an observation's parsed and raw fields."""
        parsed = obs.parsed_fields

        cert_id = str(parsed.get("certificate_id") or "")
        metal = str(parsed.get("metal") or "")
        raw_qty = parsed.get("quantity") or "0.0000"

        # Standardize quantity to canonical 4-decimal string
        norm_qty = normalize_quantity(raw_qty, "KG", "METAL_MASS", metal=metal)  # type: ignore

        from_ent = parsed.get("from_entity_id") or parsed.get("issuer_entity_id")
        to_ent = parsed.get("to_entity_id") or parsed.get("recipient_entity_id")
        event_kind = str(parsed.get("event_kind") or "TRANSFERRED")
        stage = parsed.get("transfer_stage")

        # Temporal anchor
        t_val = obs.event_time.value or obs.event_time.raw or ""
        event_date = t_val[:10] if len(t_val) >= 10 else t_val

        return EventCompoundKey(
            certificate_id=cert_id,
            metal=metal,
            quantity_kg=norm_qty.decimal,
            from_entity_id=str(from_ent) if from_ent else None,
            to_entity_id=str(to_ent) if to_ent else None,
            event_kind=event_kind,
            transfer_stage=str(stage) if stage else None,
            event_date=event_date,
        )

    def resolve_observations(
        self,
        case_id: str,
        observations: list[Observation],
    ) -> EquivalenceResolutionResult:
        """Group and resolve certificate observations into deduplicated events."""
        result = EquivalenceResolutionResult()

        # Group observations by certificate_id first
        by_cert: dict[str, list[Observation]] = {}
        for obs in observations:
            parsed = obs.parsed_fields
            cert_id = str(parsed.get("certificate_id") or "")
            if not cert_id:
                continue
            by_cert.setdefault(cert_id, []).append(obs)

        event_counter = 1
        equiv_counter = 1

        for cert_id, obs_list in by_cert.items():
            # Sub-group by compound key
            by_key: dict[EventCompoundKey, list[Observation]] = {}
            for obs in obs_list:
                key = self.extract_compound_key(obs)
                by_key.setdefault(key, []).append(obs)

            # Check if there are conflicting observations for the same certificate
            # (e.g. same cert, same date, but different quantities -> Conflict)
            quantities_seen = {
                k.quantity_kg for k in by_key.keys() if k.event_kind == "TRANSFERRED"
            }
            has_conflicting_quantity = len(quantities_seen) > 1

            for key, matched_obs in by_key.items():
                event_id = f"evt:trans_{event_counter:03d}"
                event_counter += 1

                obs_ids = [o.observation_id for o in matched_obs]
                is_duplicate_export = len(matched_obs) > 1

                # Determine assertion state
                if has_conflicting_quantity:
                    assertion_state = "CONFLICTING"
                elif key.transfer_stage == "COMPLETED" or key.event_kind in {
                    "GENERATED",
                    "TRANSFERRED",
                }:
                    assertion_state = "SUPPORTED"
                else:
                    assertion_state = "PENDING"

                # Build NonnegativeMass quantity
                mass_qty = NonnegativeMass(
                    decimal=key.quantity_kg,
                    unit="KG",
                    dimension="METAL_MASS",
                    metal=key.metal,  # type: ignore
                )

                # Event time from first observation
                event_time = matched_obs[0].event_time

                # Create CertificateEvent
                evt = CertificateEvent(
                    record_id=event_id,
                    record_revision_id=f"rev:{event_id}",
                    record_type="CertificateEvent",
                    case_id=case_id,
                    observation_refs=obs_ids,
                    derived_from_record_refs=[],
                    validation_state="VALID",
                    created_by_operation_id=self.operation_id,
                    supersedes_revision_id=None,
                    event_id=event_id,
                    certificate_id=cert_id,
                    credit_lot_id=f"lot:{cert_id.split(':')[-1]}",
                    event_kind=key.event_kind,  # type: ignore
                    event_time=event_time,
                    quantity=mass_qty,
                    assertion_state=assertion_state,
                    supporting_observations=obs_ids,
                    from_entity_id=key.from_entity_id,
                    to_entity_id=key.to_entity_id,
                    transfer_stage=key.transfer_stage,  # type: ignore
                )
                result.events.append(evt)

                # Record EventEquivalence record if duplicated (F02)
                if is_duplicate_export:
                    eq = EventEquivalence(
                        equivalence_id=f"equiv:{equiv_counter:03d}",
                        certificate_id=cert_id,
                        resolved_event_id=event_id,
                        observation_ids=obs_ids,
                        matching_basis="EXACT_COMPOUND_KEY_AND_CORROBORATION",
                        assertion_state=assertion_state,
                        review_state="APPROVED" if assertion_state == "SUPPORTED" else "DRAFT",
                    )
                    equiv_counter += 1
                    result.equivalences.append(eq)

        return result
