"""C08 universe: server-side construction, supersession and the membership digest."""

import pytest

from recycleguard.contracts.domain import Allocation, ObligationBucket
from recycleguard.domain import UniverseError, universe_from_membership, universe_from_records
from tests.support.c08 import SNAPSHOT, allocation, bucket, clean_case


def test_digest_is_order_independent_and_tracks_membership():
    records = clean_case()
    forward = universe_from_records(SNAPSHOT, records)
    backward = universe_from_records(SNAPSHOT, list(reversed(records)))
    assert forward.digest == backward.digest
    extra = universe_from_records(SNAPSHOT, records + [allocation("alloc:9", quantity="1.0000")])
    assert extra.digest != forward.digest


def test_duplicate_revision_ids_are_an_integrity_failure():
    with pytest.raises(UniverseError) as caught:
        universe_from_records(SNAPSHOT, [bucket(), bucket()])
    assert caught.value.code == "INTEGRITY_FAILED"


def test_two_active_revisions_of_one_record_are_ambiguous_and_untrusted():
    records = [bucket(revision="rev:one"), bucket(revision="rev:two")]
    universe = universe_from_records(SNAPSHOT, records)
    assert universe.active(ObligationBucket) == []
    assert universe.ambiguous_ids == {"bucket:a"}


def test_supersession_by_revision_and_by_allocation_id():
    older = allocation("alloc:1", revision="rev:v1")
    newer = allocation("alloc:1", revision="rev:v2", supersedes_revision="rev:v1")
    universe = universe_from_records(SNAPSHOT, [older, newer])
    assert [a.record_revision_id for a in universe.active(Allocation)] == ["rev:v2"]
    renamed = allocation("alloc:2", supersedes_allocation="alloc:1")
    universe = universe_from_records(SNAPSHOT, [allocation("alloc:1"), renamed])
    assert [a.record_id for a in universe.active(Allocation)] == ["alloc:2"]


def test_membership_blob_is_strictly_validated():
    records = [bucket(), allocation()]
    membership = {"normalization": {"records": [r.model_dump(mode="json") for r in records]}}
    loaded = universe_from_membership(SNAPSHOT, membership)
    assert loaded.digest == universe_from_records(SNAPSHOT, records).digest
    with pytest.raises(UniverseError):
        universe_from_membership(SNAPSHOT, {"originals": []})
    bad = {"normalization": {"records": [{"record_type": "Allocation"}]}}
    with pytest.raises(UniverseError) as caught:
        universe_from_membership(SNAPSHOT, bad)
    assert caught.value.code == "INVALID_SCHEMA"


def test_universe_cannot_span_cases():
    other = bucket("bucket:b").model_copy(update={"case_id": "case:other"})
    with pytest.raises(UniverseError):
        universe_from_records(SNAPSHOT, [bucket(), other])
