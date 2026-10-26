"""Conservative event equivalence: exact keys, explicit corroboration, retained provenance."""

import hashlib
from dataclasses import dataclass, field

from recycleguard.contracts.core import Issue
from recycleguard.contracts.domain import CertificateEvent, NonnegativeMass
from recycleguard.contracts.extraction import Observation
from recycleguard.normalization.models import EventEquivalence
from recycleguard.normalization.units import NumericSafetyError, normalize_quantity
from recycleguard.storage import canonical_json_bytes


@dataclass(frozen=True)
class EventCompoundKey:
    certificate_id: str
    credit_lot_id: str | None
    metal: str
    quantity_kg: str
    from_entity_id: str | None
    to_entity_id: str | None
    event_kind: str
    transfer_stage: str | None
    event_time: str | None
    time_precision: str
    timezone: str | None


@dataclass
class EquivalenceResolutionResult:
    events: list[CertificateEvent] = field(default_factory=list)
    equivalences: list[EventEquivalence] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)


class EventEquivalenceEngine:
    def __init__(
        self, operation_id: str = "op:norm_001", *, authoritative_artifact_ids=frozenset()
    ):
        self.operation_id = operation_id
        self.authoritative_artifact_ids = authoritative_artifact_ids

    def extract_compound_key(self, obs: Observation) -> EventCompoundKey:
        parsed = obs.parsed_fields
        quantity = normalize_quantity(
            parsed["quantity"], parsed["unit"], "METAL_MASS", metal=parsed["metal"]
        )
        return EventCompoundKey(
            certificate_id=parsed["certificate_id"],
            credit_lot_id=parsed.get("credit_lot_id"),
            metal=quantity.metal,
            quantity_kg=quantity.decimal,
            from_entity_id=parsed.get("from_entity_id"),
            to_entity_id=parsed.get("to_entity_id"),
            event_kind=parsed["event_kind"],
            transfer_stage=parsed.get("transfer_stage"),
            event_time=obs.event_time.value,
            time_precision=obs.event_time.precision,
            timezone=obs.event_time.timezone,
        )

    def resolve_observations(self, case_id: str, observations: list[Observation]):
        result = EquivalenceResolutionResult()
        groups = {}
        external_keys = {}
        for obs in observations:
            try:
                key = self.extract_compound_key(obs)
            except (KeyError, ValueError, NumericSafetyError) as exc:
                result.issues.append(
                    Issue(
                        issue_id=f"issue:{obs.observation_id.split(':', 1)[1]}",
                        code="UNCONFIRMED_IDENTIFIER",
                        severity="WARNING",
                        message=f"Event unresolved: {exc}",
                        field_path=None,
                        evidence_refs=[],
                        retryable=False,
                    )
                )
                continue
            external = obs.parsed_fields.get("external_event_ref")
            # Unknown fields or coarse source time must never establish automated equivalence.
            complete = all(
                (
                    key.certificate_id,
                    key.credit_lot_id,
                    key.from_entity_id,
                    key.to_entity_id,
                    key.event_kind,
                    key.event_time,
                    key.timezone,
                )
            )
            precise = key.time_precision == "INSTANT"
            # Evidence content cannot assign its own authority or human review status.
            corroborated = bool(
                external and obs.artifact_revision_id in self.authoritative_artifact_ids
            )
            token = (
                (key, external) if complete and precise and corroborated else (obs.observation_id,)
            )
            groups.setdefault(token, []).append((key, obs, complete and precise and corroborated))
            if external:
                external_keys.setdefault((key.certificate_id, external), set()).add(key)

        for matched in groups.values():
            key, first, supported = matched[0]
            obs_ids = [item[1].observation_id for item in matched]
            external = first.parsed_fields.get("external_event_ref")
            conflict = bool(external and len(external_keys[(key.certificate_id, external)]) > 1)
            completed = key.event_kind != "TRANSFERRED" or key.transfer_stage == "COMPLETED"
            state = (
                "CONFLICTING" if conflict else "SUPPORTED" if supported and completed else "PENDING"
            )
            event_id = (
                "evt:"
                + hashlib.sha256(
                    canonical_json_bytes([case_id, self.operation_id, obs_ids])
                ).hexdigest()[:24]
            )
            event = CertificateEvent(
                record_id=event_id,
                record_revision_id=f"rev:{event_id.split(':')[1]}",
                record_type="CertificateEvent",
                case_id=case_id,
                observation_refs=obs_ids,
                derived_from_record_refs=[],
                validation_state="VALID" if state == "SUPPORTED" else "REVIEW_REQUIRED",
                created_by_operation_id=self.operation_id,
                supersedes_revision_id=None,
                event_id=event_id,
                certificate_id=key.certificate_id,
                credit_lot_id=key.credit_lot_id,
                event_kind=key.event_kind,
                event_time=first.event_time,
                quantity=NonnegativeMass(
                    decimal=key.quantity_kg, unit="KG", dimension="METAL_MASS", metal=key.metal
                ),
                assertion_state=state,
                supporting_observations=obs_ids,
                external_event_ref=external,
                from_entity_id=key.from_entity_id,
                to_entity_id=key.to_entity_id,
                transfer_stage=key.transfer_stage,
            )
            result.events.append(event)
            if len(matched) > 1:
                result.equivalences.append(
                    EventEquivalence(
                        equivalence_id=f"equiv:{event_id.split(':')[1]}",
                        certificate_id=key.certificate_id,
                        resolved_event_id=event_id,
                        observation_ids=obs_ids,
                        matching_basis="AUTHORITATIVE_EVENT_ID"
                        if external
                        else "EXACT_COMPOUND_KEY_AND_CORROBORATION",
                        assertion_state=state,
                        review_state="DRAFT",
                    )
                )
        return result
