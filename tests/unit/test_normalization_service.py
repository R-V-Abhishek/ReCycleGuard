"""Unit tests for NormalizationService and NormalizationBatch generation."""

import unittest

from recycleguard.contracts.core import Locator, TemporalValue
from recycleguard.contracts.extraction import Observation
from recycleguard.normalization.service import NormalizationService


def make_obs(
    obs_id: str,
    obs_type: str,
    parsed_fields: dict,
    event_time_str: str = "2024-09-15T11:30:00Z",
) -> Observation:
    """Helper to construct contract-valid Observation instances."""
    return Observation(
        observation_id=obs_id,
        extraction_id="ext:case_001",
        artifact_revision_id="art:doc_001",
        locator=Locator(
            kind="CSV_ROW",
            page_index_1based=None,
            printed_page_label=None,
            row_index_1based=1,
            column_name=None,
            json_pointer=None,
            text_start=None,
            text_end=None,
            table_id=None,
            cell_row=None,
            cell_column=None,
        ),
        observation_type=obs_type,
        raw_fields=parsed_fields,
        parsed_fields=parsed_fields,
        validation_state="VALID",
        extraction_method="CSV",
        field_quality={},
        event_time=TemporalValue(
            raw=event_time_str,
            value=event_time_str,
            precision="INSTANT",
            timezone=None,
            interpretation_status="PARSED",
        ),
        source_capture_time=TemporalValue(
            raw="2024-09-30T18:00:00Z",
            value="2024-09-30T18:00:00Z",
            precision="INSTANT",
            timezone=None,
            interpretation_status="REVIEWED",
        ),
        ingestion_time="2024-10-01T10:00:00Z",
    )


class TestNormalizationService(unittest.TestCase):
    """Test suite asserting end-to-end normalization service functionality."""

    def setUp(self) -> None:
        self.service = NormalizationService(operation_id="op:norm_test")

    def test_01_normalize_case_001_observations(self) -> None:
        """Normalizes case_001 observations, resolving F02 and retaining provenance."""
        observations = [
            # Entity 1: Producer
            make_obs(
                "obs:ent_01",
                "EntityObservation",
                {
                    "entity_id": "entity:prod_001",
                    "legal_name": "Apex Electronics India Pvt Ltd",
                    "roles": ["PRODUCER"],
                    "identifiers": [{"kind": "GSTIN", "value": "29AAACA1234A1Z5"}],
                },
            ),
            # Entity 2: Recycler
            make_obs(
                "obs:ent_02",
                "EntityObservation",
                {
                    "entity_id": "entity:rec_001",
                    "legal_name": "GreenTech Recyclers LLP",
                    "roles": ["RECYCLER"],
                    "identifiers": [{"kind": "GSTIN", "value": "27AAACG9876B1Z2"}],
                },
            ),
            # Obligation Bucket: 100 kg Cu
            make_obs(
                "obs:ob_01",
                "ObligationObservation",
                {
                    "bucket_id": "bucket:prod_001_cu_2024_2025",
                    "producer_entity_id": "entity:prod_001",
                    "liability_year": "2024-2025",
                    "component": "STANDARD",
                    "metal": "CU",
                    "target": "100.0000",
                    "unit": "KG",
                },
            ),
            # Certificate Observation 1 (from CSV) - 55 kg Cu
            make_obs(
                "obs:cert_01",
                "CertificateObservation",
                {
                    "certificate_id": "cert:rec_001",
                    "quantity": "55.0000",
                    "metal": "CU",
                    "event_kind": "TRANSFERRED",
                    "transfer_stage": "COMPLETED",
                    "from_entity_id": "entity:rec_001",
                    "to_entity_id": "entity:prod_001",
                },
            ),
            # Certificate Observation 2 (from JSON) - 55 kg Cu duplicate (F02)
            make_obs(
                "obs:cert_02",
                "CertificateObservation",
                {
                    "certificate_id": "cert:rec_001",
                    "quantity": "55.0000",
                    "metal": "CU",
                    "event_kind": "TRANSFERRED",
                    "transfer_stage": "COMPLETED",
                    "from_entity_id": "entity:rec_001",
                    "to_entity_id": "entity:prod_001",
                },
            ),
            # Commercial Record: 25 kg invoice (Pending transfer)
            make_obs(
                "obs:comm_01",
                "CommercialObservation",
                {
                    "commercial_id": "comm:inv_001",
                    "record_kind": "INVOICE",
                    "issuer_entity_id": "entity:rec_001",
                    "recipient_entity_id": "entity:prod_001",
                    "external_ref": "INV/2024-25/0842",
                    "money": "12500.0000",
                    "credit_quantity": "25.0000",
                },
            ),
            # Account Balance Observation: 55 kg reported on portal
            make_obs(
                "obs:bal_01",
                "AccountBalanceObservation",
                {
                    "balance_observation_id": "bal:snap_001",
                    "producer_entity_id": "entity:prod_001",
                    "bucket_id": "bucket:prod_001_cu_2024_2025",
                    "reported_supported": "55.0000",
                },
            ),
        ]

        batch = self.service.normalize("case:001", observations, batch_id="batch:test_001")

        self.assertEqual(batch.case_id, "case:001")
        self.assertEqual(batch.batch_id, "batch:test_001")

        # 1. Total records: 2 entities + 1 obligation + 1 certificate event + 1 commercial + 1 balance = 6
        self.assertEqual(len(batch.records), 6)

        record_types = [r.record_type for r in batch.records]
        self.assertEqual(record_types.count("Entity"), 2)
        self.assertEqual(record_types.count("ObligationBucket"), 1)
        self.assertEqual(record_types.count("CertificateEvent"), 1)
        self.assertEqual(record_types.count("CommercialRecord"), 1)
        self.assertEqual(record_types.count("AccountBalanceObservation"), 1)

        # 2. Check F02 deduplication on CertificateEvent
        events = [r for r in batch.records if r.record_type == "CertificateEvent"]
        self.assertEqual(len(events), 1)
        evt = events[0]
        self.assertEqual(evt.quantity.decimal, "55.0000")
        self.assertEqual(evt.quantity.metal, "CU")
        self.assertEqual(evt.assertion_state, "SUPPORTED")
        self.assertCountEqual(evt.supporting_observations, ["obs:cert_01", "obs:cert_02"])

        # 3. Check EventEquivalence record
        self.assertEqual(len(batch.equivalences), 1)
        eq = batch.equivalences[0]
        self.assertEqual(eq.certificate_id, "cert:rec_001")
        self.assertEqual(eq.resolved_event_id, evt.event_id)
        self.assertEqual(eq.matching_basis, "EXACT_COMPOUND_KEY_AND_CORROBORATION")

        # 4. Check Dispositions (every observation has an ACCEPTED disposition)
        self.assertEqual(len(batch.dispositions), len(observations))
        for disp in batch.dispositions:
            self.assertEqual(disp.disposition, "ACCEPTED")
            self.assertGreater(len(disp.derived_record_ids), 0)

        # 5. Check Provenance Lineage on all records
        for rec in batch.records:
            self.assertGreater(
                len(rec.observation_refs),
                0,
                f"Record {rec.record_id} must have non-empty observation_refs",
            )


if __name__ == "__main__":
    unittest.main()
