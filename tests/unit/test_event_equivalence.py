"""Unit tests for Gate G04 Lifecycle: F02 deduplication and F03 multi-stage ID reuse."""

import unittest

from recycleguard.contracts.core import Locator, TemporalValue
from recycleguard.contracts.extraction import Observation
from recycleguard.normalization.equivalence import EventEquivalenceEngine


def make_test_observation(
    obs_id: str,
    cert_id: str,
    qty: str,
    metal: str = "CU",
    event_kind: str = "TRANSFERRED",
    stage: str = "COMPLETED",
    event_time_str: str = "2024-09-15T11:30:00Z",
    from_ent: str = "entity:rec_001",
    to_ent: str = "entity:prod_001",
) -> Observation:
    """Helper to synthesize a contract-valid Observation."""
    return Observation(
        observation_id=obs_id,
        extraction_id="ext:test_001",
        artifact_revision_id="art:test_001",
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
        observation_type="CertificateObservation",
        raw_fields={"cert": cert_id, "qty": qty},
        parsed_fields={
            "certificate_id": cert_id,
            "quantity": qty,
            "metal": metal,
            "event_kind": event_kind,
            "external_event_ref": f"TXN-{cert_id}-{event_time_str}",
            "credit_lot_id": "lot:test",
            "unit": "KG",
            "transfer_stage": stage,
            "from_entity_id": from_ent,
            "to_entity_id": to_ent,
        },
        validation_state="VALID",
        extraction_method="CSV",
        field_quality={},
        event_time=TemporalValue(
            raw=event_time_str,
            value=event_time_str,
            precision="INSTANT",
            timezone="UTC",
            interpretation_status="PARSED",
        ),
        source_capture_time=TemporalValue(
            raw="2024-09-30T18:00:00Z",
            value="2024-09-30T18:00:00Z",
            precision="INSTANT",
            timezone="UTC",
            interpretation_status="REVIEWED",
        ),
        ingestion_time="2024-10-01T10:00:00Z",
    )


class TestEventEquivalence(unittest.TestCase):
    """Test suite asserting Gate G04 Lifecycle and Equivalence compliance."""

    def setUp(self) -> None:
        self.engine = EventEquivalenceEngine(
            operation_id="op:test_norm", authoritative_artifact_ids=frozenset({"art:test_001"})
        )

    def test_01_f02_duplicate_observations_collapse_to_supported_event(self) -> None:
        """Two duplicate observations of cert:rec_001 collapse into 1 supported event (F02)."""
        obs1 = make_test_observation("obs:csv_01", "cert:rec_001", "55.0000")
        obs2 = make_test_observation("obs:json_01", "cert:rec_001", "55.0000")

        res = self.engine.resolve_observations("case:001", [obs1, obs2])

        # Exactly 1 resolved event
        self.assertEqual(len(res.events), 1)
        evt = res.events[0]
        self.assertEqual(evt.certificate_id, "cert:rec_001")
        self.assertEqual(evt.quantity.decimal, "55.0000")
        self.assertEqual(evt.quantity.metal, "CU")
        self.assertEqual(evt.assertion_state, "SUPPORTED")

        # Provenance: both observation IDs retained
        self.assertCountEqual(evt.supporting_observations, ["obs:csv_01", "obs:json_01"])
        self.assertCountEqual(evt.observation_refs, ["obs:csv_01", "obs:json_01"])

        # Exactly 1 equivalence assertion record
        self.assertEqual(len(res.equivalences), 1)
        eq = res.equivalences[0]
        self.assertEqual(eq.certificate_id, "cert:rec_001")
        self.assertEqual(eq.resolved_event_id, evt.event_id)
        self.assertEqual(eq.matching_basis, "AUTHORITATIVE_EVENT_ID")
        self.assertEqual(eq.assertion_state, "SUPPORTED")

    def test_02_f02_conflicting_quantities_remain_conflicting(self) -> None:
        """Observations with mismatched quantities for same certificate flag as CONFLICTING."""
        obs1 = make_test_observation("obs:01", "cert:rec_002", "55.0000")
        obs2 = make_test_observation("obs:02", "cert:rec_002", "60.0000")

        res = self.engine.resolve_observations("case:001", [obs1, obs2])

        # Both events emitted with CONFLICTING state
        self.assertEqual(len(res.events), 2)
        for evt in res.events:
            self.assertEqual(evt.assertion_state, "CONFLICTING")

    def test_03_f03_multistage_legitimate_reuse_preserved(self) -> None:
        """Distinct lifecycle stages sharing a certificate ID are preserved separately (F03)."""
        # Stage 1: Certificate generated at t1
        obs_gen = make_test_observation(
            "obs:gen",
            "cert:rec_003",
            "100.0000",
            event_kind="GENERATED",
            stage="COMPLETED",
            event_time_str="2024-08-01T10:00:00Z",
            from_ent="entity:rec_001",
            to_ent=None,
        )
        # Stage 2: Certificate transferred at t2
        obs_trans = make_test_observation(
            "obs:trans",
            "cert:rec_003",
            "55.0000",
            event_kind="TRANSFERRED",
            stage="COMPLETED",
            event_time_str="2024-09-15T11:30:00Z",
            from_ent="entity:rec_001",
            to_ent="entity:prod_001",
        )

        res = self.engine.resolve_observations("case:001", [obs_gen, obs_trans])

        # Must NOT collapse into 1 event! Both must exist
        self.assertEqual(len(res.events), 2)
        event_kinds = {e.event_kind for e in res.events}
        self.assertSetEqual(event_kinds, {"GENERATED", "TRANSFERRED"})

        # No false F02 equivalence emitted
        self.assertEqual(len(res.equivalences), 0)


if __name__ == "__main__":
    unittest.main()
