"""Normalization service implementing C04 Normalization & Equivalence.

Transforms raw observations into validated domain records, resolves event
equivalence, and packages a complete NormalizationBatch.
"""

from pathlib import Path
from typing import Any

from recycleguard.contracts.core import ID, Issue, TemporalValue
from recycleguard.contracts.domain import (
    AccountBalanceObservation,
    Allocation,
    Certificate,
    CertificateEvent,
    CommercialRecord,
    Entity,
    Identifier,
    NonnegativeMass,
    NormalizedRecord,
    ObligationBucket,
    Registration,
    ReviewedInterval,
)
from recycleguard.contracts.extraction import Observation
from recycleguard.normalization.equivalence import EventEquivalenceEngine
from recycleguard.normalization.models import (
    EventEquivalence,
    NormalizationBatch,
    ObservationDisposition,
)
from recycleguard.normalization.units import normalize_quantity


class NormalizationService:
    """Service that orchestrates data normalization and equivalence."""

    def __init__(self, operation_id: str = "op:norm_001"):
        self.operation_id = operation_id
        self.equivalence_engine = EventEquivalenceEngine(operation_id=operation_id)

    def normalize(
        self,
        case_id: str,
        observations: list[Observation],
        batch_id: str = "batch:norm_001",
    ) -> NormalizationBatch:
        """Normalize a collection of raw observations into a NormalizationBatch."""
        dispositions: list[ObservationDisposition] = []
        records: list[NormalizedRecord] = []
        issues: list[Issue] = []

        cert_observations: list[Observation] = []

        # 1. Process entity, obligation, registration, commercial, account observations
        for obs in observations:
            obs_type = obs.observation_type
            parsed = obs.parsed_fields
            derived_ids: list[str] = []

            if obs_type == "CertificateObservation":
                cert_observations.append(obs)
                # Disposition will be recorded after equivalence resolution
                continue

            elif obs_type == "EntityObservation":
                ent_id = str(parsed.get("entity_id") or "entity:unknown")
                legal_name = str(parsed.get("legal_name") or "")
                roles = parsed.get("roles") or ["PRODUCER"]
                raw_ids = parsed.get("identifiers") or []
                identifiers = [
                    Identifier(
                        kind=i["kind"],
                        value=i["value"],
                        validation_state="VALID",
                        evidence_refs=[],
                    )
                    for i in raw_ids
                ]
                ent = Entity(
                    record_id=ent_id,
                    record_revision_id=f"rev:{ent_id}",
                    record_type="Entity",
                    case_id=case_id,
                    observation_refs=[obs.observation_id],
                    derived_from_record_refs=[],
                    validation_state="VALID",
                    created_by_operation_id=self.operation_id,
                    supersedes_revision_id=None,
                    entity_id=ent_id,
                    legal_name=legal_name,
                    roles=roles,  # type: ignore
                    identifiers=identifiers,
                    synthetic=True,
                )
                records.append(ent)
                derived_ids.append(ent_id)

            elif obs_type == "ObligationObservation":
                b_id = str(parsed.get("bucket_id") or "bucket:unknown")
                metal = str(parsed.get("metal") or "CU")
                target_qty = normalize_quantity(
                    parsed.get("target") or "0.0000",
                    parsed.get("unit") or "KG",
                    "METAL_MASS",
                    metal=metal,  # type: ignore
                )
                ob = ObligationBucket(
                    record_id=b_id,
                    record_revision_id=f"rev:{b_id}",
                    record_type="ObligationBucket",
                    case_id=case_id,
                    observation_refs=[obs.observation_id],
                    derived_from_record_refs=[],
                    validation_state="VALID",
                    created_by_operation_id=self.operation_id,
                    supersedes_revision_id=None,
                    bucket_id=b_id,
                    producer_entity_id=str(parsed.get("producer_entity_id") or ""),
                    liability_year=str(parsed.get("liability_year") or "2024-2025"),
                    component=str(parsed.get("component") or "STANDARD"),
                    metal=metal,  # type: ignore
                    target=NonnegativeMass(
                        decimal=target_qty.decimal,
                        unit="KG",
                        dimension="METAL_MASS",
                        metal=metal,  # type: ignore
                    ),
                    basis="SUPPLIED_ACCOUNT",
                    basis_refs=[],
                    profile_id=str(parsed.get("profile_id") or "profile:producer_snapshot_v1"),
                )
                records.append(ob)
                derived_ids.append(b_id)

            elif obs_type == "CommercialObservation":
                comm_id = str(parsed.get("commercial_id") or "comm:unknown")
                money_val = parsed.get("money")
                credit_qty_val = parsed.get("credit_quantity")

                norm_money = (
                    normalize_quantity(money_val, "INR", "MONEY")
                    if money_val
                    else None
                )
                norm_credit_qty = (
                    NonnegativeMass(
                        decimal=normalize_quantity(credit_qty_val, "KG", "METAL_MASS", metal="CU").decimal,
                        unit="KG",
                        dimension="METAL_MASS",
                        metal="CU",
                    )
                    if credit_qty_val
                    else None
                )

                cr = CommercialRecord(
                    record_id=comm_id,
                    record_revision_id=f"rev:{comm_id}",
                    record_type="CommercialRecord",
                    case_id=case_id,
                    observation_refs=[obs.observation_id],
                    derived_from_record_refs=[],
                    validation_state="VALID",
                    created_by_operation_id=self.operation_id,
                    supersedes_revision_id=None,
                    commercial_id=comm_id,
                    record_kind=str(parsed.get("record_kind") or "INVOICE"),  # type: ignore
                    issuer_entity_id=str(parsed.get("issuer_entity_id") or ""),
                    recipient_entity_id=str(parsed.get("recipient_entity_id") or ""),
                    external_ref=str(parsed.get("external_ref") or "REF-001"),
                    event_time=obs.event_time,
                    linked_credit_refs=[],
                    money=norm_money,
                    credit_quantity=norm_credit_qty,
                )
                records.append(cr)
                derived_ids.append(comm_id)

            elif obs_type == "AccountBalanceObservation":
                bal_id = str(parsed.get("balance_observation_id") or "bal:unknown")
                rep_supp = normalize_quantity(
                    parsed.get("reported_supported") or "0.0000",
                    "KG",
                    "METAL_MASS",
                    metal="CU",
                )
                ab = AccountBalanceObservation(
                    record_id=bal_id,
                    record_revision_id=f"rev:{bal_id}",
                    record_type="AccountBalanceObservation",
                    case_id=case_id,
                    observation_refs=[obs.observation_id],
                    derived_from_record_refs=[],
                    validation_state="VALID",
                    created_by_operation_id=self.operation_id,
                    supersedes_revision_id=None,
                    balance_observation_id=bal_id,
                    producer_entity_id=str(parsed.get("producer_entity_id") or ""),
                    bucket_id=str(parsed.get("bucket_id") or ""),
                    reported_supported=NonnegativeMass(
                        decimal=rep_supp.decimal,
                        unit="KG",
                        dimension="METAL_MASS",
                        metal="CU",
                    ),
                    source_capture_time=obs.source_capture_time,
                    business_cutoff=obs.source_capture_time,
                    basis_refs=[],
                )
                records.append(ab)
                derived_ids.append(bal_id)

            dispositions.append(
                ObservationDisposition(
                    observation_id=obs.observation_id,
                    disposition="ACCEPTED",
                    reason="Normalized into domain record",
                    derived_record_ids=derived_ids,
                )
            )

        # 2. Resolve Certificate Observations via Equivalence Engine
        resolved = self.equivalence_engine.resolve_observations(case_id, cert_observations)
        records.extend(resolved.events)
        issues.extend(resolved.issues)

        # Record dispositions for certificate observations
        obs_to_event: dict[str, list[str]] = {}
        for evt in resolved.events:
            for obs_ref in evt.observation_refs:
                obs_to_event.setdefault(obs_ref, []).append(evt.record_id)

        for obs in cert_observations:
            derived_evts = obs_to_event.get(obs.observation_id, [])
            dispositions.append(
                ObservationDisposition(
                    observation_id=obs.observation_id,
                    disposition="ACCEPTED" if derived_evts else "QUARANTINED",
                    reason="Resolved via event equivalence" if derived_evts else "Unresolved certificate observation",
                    derived_record_ids=derived_evts,
                )
            )

        return NormalizationBatch(
            batch_id=batch_id,
            case_id=case_id,
            records=records,
            dispositions=dispositions,
            equivalences=resolved.equivalences,
            issues=issues,
            mapping_version="1.0",
        )
