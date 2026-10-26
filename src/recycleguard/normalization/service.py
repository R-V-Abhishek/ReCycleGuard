"""C04 mapping with terminal dispositions, no fabricated facts and full record serialization."""

from pydantic import ValidationError

from recycleguard.contracts.core import EvidenceRef, Issue
from recycleguard.contracts.domain import (
    RECORD_ADAPTER,
    AccountBalanceObservation,
    CommercialRecord,
    Entity,
    Identifier,
    NonnegativeMass,
    ObligationBucket,
)
from recycleguard.contracts.extraction import Observation
from recycleguard.normalization.equivalence import EventEquivalenceEngine
from recycleguard.normalization.models import NormalizationBatch, ObservationDisposition
from recycleguard.normalization.units import normalize_quantity
from recycleguard.storage import canonical_json_bytes


class NormalizationService:
    def __init__(
        self, operation_id: str = "op:norm_001", *, authoritative_artifact_ids=frozenset()
    ):
        self.operation_id = operation_id
        self.equivalence_engine = EventEquivalenceEngine(
            operation_id, authoritative_artifact_ids=authoritative_artifact_ids
        )

    def normalize(self, case_id: str, observations: list[Observation], batch_id="batch:norm_001"):
        records, dispositions, issues, certificates = [], [], [], []
        if len({obs.observation_id for obs in observations}) != len(observations):
            raise ValueError("normalization requires unique observation IDs")
        for outer in observations:
            obs = outer
            try:
                # A JSON file containing supplied observations is still evidence. Rebind
                # provenance to this extraction; never trust its claimed storage locator.
                if "observation_type" in outer.parsed_fields:
                    claimed = Observation.model_validate_json(
                        canonical_json_bytes(outer.parsed_fields)
                    )
                    obs = claimed.model_copy(
                        update={
                            "observation_id": outer.observation_id,
                            "extraction_id": outer.extraction_id,
                            "artifact_revision_id": outer.artifact_revision_id,
                            "locator": outer.locator,
                            "source_capture_time": outer.source_capture_time,
                            "ingestion_time": outer.ingestion_time,
                        }
                    )
                if obs.validation_state != "VALID":
                    raise ValueError("source observation requires review")
                if obs.observation_type == "CertificateObservation":
                    certificates.append(obs)
                    continue
                record = self._record(case_id, obs)
                if any(item.record_id == record.record_id for item in records):
                    raise ValueError("duplicate record identity requires review")
                records.append(record)
                dispositions.append(
                    ObservationDisposition(
                        observation_id=outer.observation_id,
                        disposition="ACCEPTED",
                        reason="Mapped supplied facts; eligibility remains separate",
                        derived_record_ids=[record.record_id],
                    )
                )
            except (KeyError, ValidationError, ValueError) as exc:
                dispositions.append(
                    ObservationDisposition(
                        observation_id=outer.observation_id,
                        disposition="QUARANTINED",
                        reason=str(exc),
                        derived_record_ids=[],
                    )
                )
                issues.append(
                    Issue(
                        issue_id=f"issue:{outer.observation_id.split(':', 1)[1]}",
                        code="INVALID_SCHEMA",
                        severity="WARNING",
                        message=f"Normalization unresolved: {exc}",
                        field_path=None,
                        evidence_refs=[],
                        retryable=False,
                    )
                )
        resolved = self.equivalence_engine.resolve_observations(case_id, certificates)
        for event in resolved.events:
            if any(item.record_id == event.record_id for item in records):
                raise ValueError("event record identity collision")
            records.append(event)
        issues.extend(resolved.issues)
        for obs in certificates:
            events = [
                event for event in resolved.events if obs.observation_id in event.observation_refs
            ]
            supported = bool(events) and all(
                event.assertion_state == "SUPPORTED" for event in events
            )
            dispositions.append(
                ObservationDisposition(
                    observation_id=obs.observation_id,
                    disposition="ACCEPTED" if supported else "QUARANTINED",
                    reason="Corroborated event"
                    if supported
                    else "Event identity or equivalence unresolved",
                    derived_record_ids=[event.record_id for event in events],
                )
            )
        return NormalizationBatch(
            batch_id=batch_id,
            case_id=case_id,
            records=records,
            dispositions=dispositions,
            equivalences=resolved.equivalences,
            issues=issues,
            mapping_version="1.1",
        )

    def _record(self, case_id, obs):
        p = obs.parsed_fields
        common = {
            "case_id": case_id,
            "observation_refs": [obs.observation_id],
            "derived_from_record_refs": [],
            "validation_state": "REVIEW_REQUIRED",
            "created_by_operation_id": self.operation_id,
            "supersedes_revision_id": None,
        }
        evidence = EvidenceRef(
            ref_kind="OBSERVATION",
            ref_id=obs.observation_id,
            artifact_revision_id=obs.artifact_revision_id,
            locator=obs.locator,
        )
        if "record_type" in p:
            if p["case_id"] != case_id:
                raise ValueError("record belongs to another case")
            revision_key = self.operation_id.split(":", 1)[1]
            data = p | common | {"record_revision_id": f"rev:{revision_key}:{p['record_id']}"}
            # These are supplied assertions, not deterministic C08 approvals.
            if p["record_type"] == "CertificateEvent":
                data["assertion_state"] = "PENDING"
                data["supporting_observations"] = [obs.observation_id]
            elif p["record_type"] == "Allocation":
                data["state"] = "PENDING"
            return RECORD_ADAPTER.validate_json(canonical_json_bytes(data))
        if obs.observation_type == "EntityObservation":
            key = p["entity_id"]
            return Entity(
                **common,
                record_id=key,
                record_revision_id=f"rev:{self.operation_id}:{key}",
                record_type="Entity",
                entity_id=key,
                legal_name=p["legal_name"],
                roles=p["roles"],
                identifiers=[
                    Identifier(
                        kind=item["kind"],
                        value=item["value"],
                        validation_state="REVIEW_REQUIRED",
                        evidence_refs=[evidence],
                    )
                    for item in p["identifiers"]
                ],
                synthetic=True,
            )
        if obs.observation_type == "ObligationObservation":
            key = p["bucket_id"]
            quantity = normalize_quantity(p["target"], p["unit"], "METAL_MASS", metal=p["metal"])
            return ObligationBucket(
                **common,
                record_id=key,
                record_revision_id=f"rev:{self.operation_id}:{key}",
                record_type="ObligationBucket",
                bucket_id=key,
                producer_entity_id=p["producer_entity_id"],
                liability_year=p["liability_year"],
                component=p["component"],
                metal=p["metal"],
                target=NonnegativeMass.model_validate(quantity.model_dump()),
                basis="SUPPLIED_ACCOUNT",
                basis_refs=[evidence],
                profile_id=p["profile_id"],
            )
        if obs.observation_type == "CommercialObservation":
            key = p["commercial_id"]
            money = (
                None if p.get("money") is None else normalize_quantity(p["money"], "INR", "MONEY")
            )
            credit = (
                None
                if p.get("credit_quantity") is None
                else NonnegativeMass.model_validate(
                    normalize_quantity(
                        p["credit_quantity"], p["unit"], "METAL_MASS", metal=p["metal"]
                    ).model_dump()
                )
            )
            return CommercialRecord(
                **common,
                record_id=key,
                record_revision_id=f"rev:{self.operation_id}:{key}",
                record_type="CommercialRecord",
                commercial_id=key,
                record_kind=p["record_kind"],
                issuer_entity_id=p["issuer_entity_id"],
                recipient_entity_id=p["recipient_entity_id"],
                external_ref=p["external_ref"],
                event_time=obs.event_time,
                linked_credit_refs=[],
                money=money,
                credit_quantity=credit,
            )
        if obs.observation_type == "AccountBalanceObservation":
            key = p["balance_observation_id"]
            quantity = normalize_quantity(
                p["reported_supported"], p["unit"], "METAL_MASS", metal=p["metal"]
            )
            return AccountBalanceObservation(
                **common,
                record_id=key,
                record_revision_id=f"rev:{self.operation_id}:{key}",
                record_type="AccountBalanceObservation",
                balance_observation_id=key,
                producer_entity_id=p["producer_entity_id"],
                bucket_id=p["bucket_id"],
                reported_supported=NonnegativeMass.model_validate(quantity.model_dump()),
                source_capture_time=obs.source_capture_time,
                business_cutoff=obs.event_time,
                basis_refs=[evidence],
            )
        raise ValueError(f"No approved mapping for observation type {obs.observation_type}")
