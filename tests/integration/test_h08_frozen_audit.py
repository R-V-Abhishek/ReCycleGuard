"""H08 verifies real approved bytes and ledger state, not expected constants."""

import json
import shutil
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from recycleguard.application import local_application
from recycleguard.config import Settings
from recycleguard.contracts.artifacts import ProfileRef, SnapshotRef
from recycleguard.indexing.builder import IndexBuilder
from recycleguard.indexing.corpus import load_corpus
from recycleguard.knowledge.corpus_audit import audit_frozen_corpus_profile
from tests.integration.test_a05_baseline import approved_foundation as approved_foundation


@pytest.fixture
def frozen_audit(tmp_path, approved_foundation):
    root = tmp_path / "data"
    shutil.copytree(approved_foundation, root, ignore=shutil.ignore_patterns("reviewer.json"))

    @contextmanager
    def create():
        with local_application(Settings(data_root=root)) as (cases, context, capability):
            corpus = cases.snapshots.catalog.get_snapshot("snapshot:corpus_approved")
            case = cases.snapshots.catalog.get_snapshot("snapshot:case_approved")
            membership = json.loads(cases.kernel.blob_store.get(case.membership_blob))
            profile_ref = ProfileRef.model_validate(membership["profile"])
            profile = cases.profiles.get(profile_ref, require_approved=True)
            manifest, index = IndexBuilder(
                root, cases.kernel.blob_store, kernel=cases.kernel
            ).build_index(corpus, context=context, capability=capability)
            path = index.db_path
            index.close()
            arguments = dict(
                corpus_snapshot=corpus,
                profile=profile,
                index_manifest=manifest,
                blobs=cases.kernel.blob_store,
                index_path=path,
                expected_corpus=SnapshotRef(
                    snapshot_id=corpus.snapshot_id, membership_digest=corpus.membership_digest
                ),
                expected_profile=profile_ref,
                expected_index=manifest.pin(),
                kernel=cases.kernel,
                runtime_metadata={"mode": "LOCAL_GATEWAY_EXPLORATION_NOT_EVALUATED"},
            )
            yield SimpleNamespace(cases=cases, args=arguments)

    return create


def test_actual_frozen_corpus_profile_and_ledger_are_verified(frozen_audit):
    with frozen_audit() as env:
        manifest = audit_frozen_corpus_profile(**env.args)
        assert manifest.verification_status == "VERIFIED_INTEGRITY"
        assert manifest.profile.review_state == "APPROVED"
        assert manifest.verified_audit_streams
        assert "application_hash_chains" in manifest.verified_checks
        assert manifest.runtime_metadata == env.args["runtime_metadata"]
        assert "TEST_DOUBLE" not in manifest.model_dump_json()
        sources = load_corpus(env.args["corpus_snapshot"], env.args["blobs"]).batch.source_versions
        assert [s.review_state for s in manifest.sources] == [s.review_state for s in sources]
        assert sorted(s.total_pages for s in manifest.sources) == [13, 38]
        assert sorted(page for s in manifest.sources for page in s.active_physical_pages) == [
            9,
            24,
            27,
        ]
        assert any(item.kind == "DISABLED_PURCHASE_CEILING" for item in manifest.limitations)


@pytest.mark.parametrize("reference", ["expected_corpus", "expected_profile", "expected_index"])
def test_mismatched_exact_pins_are_rejected(frozen_audit, reference):
    with frozen_audit() as env:
        args = env.args.copy()
        field = "membership_digest" if reference == "expected_corpus" else "digest"
        args[reference] = args[reference].model_copy(update={field: "0" * 64})
        with pytest.raises(ValueError, match="expected pin"):
            audit_frozen_corpus_profile(**args)


def test_changed_index_cache_is_rejected(frozen_audit):
    with frozen_audit() as env:
        with env.args["index_path"].open("ab") as output:
            output.write(b"tamper")
        with pytest.raises(ValueError, match="index bytes"):
            audit_frozen_corpus_profile(**env.args)


@pytest.mark.parametrize("kind", ["original", "provision"])
def test_tampered_original_or_provision_blob_is_rejected(frozen_audit, kind):
    with frozen_audit() as env:
        view = load_corpus(env.args["corpus_snapshot"], env.args["blobs"])
        blob = (
            view.batch.artifact_revisions[0].blob
            if kind == "original"
            else view.batch.provisions[0].text_blob
        )
        path = env.args["blobs"].objects / blob.sha256[:2] / blob.sha256
        path.write_bytes(b"corrupted immutable bytes")
        with pytest.raises(ValueError):
            audit_frozen_corpus_profile(**env.args)


def test_profile_content_without_new_canonical_digest_is_rejected(frozen_audit):
    with frozen_audit() as env:
        args = env.args | {
            "profile": env.args["profile"].model_copy(update={"allowed_metals": ["CU"]})
        }
        with pytest.raises(ValueError, match="digest"):
            audit_frozen_corpus_profile(**args)


def test_application_audit_hash_corruption_is_rejected(frozen_audit):
    with frozen_audit() as env:
        connection = env.cases.kernel.connection
        row = connection.execute("SELECT event_id,event_json FROM audit_events LIMIT 1").fetchone()
        changed = json.loads(row["event_json"])
        changed["event_hash"] = "0" * 64
        connection.execute(
            "UPDATE audit_events SET event_json=? WHERE event_id=?",
            (json.dumps(changed), row["event_id"]),
        )
        with pytest.raises(ValueError, match="hash chain"):
            audit_frozen_corpus_profile(**env.args)


def test_unpublished_manifest_cannot_borrow_other_valid_audit_streams(frozen_audit):
    with frozen_audit() as env:
        manifest = env.args["index_manifest"].model_copy(
            update={"build_code_revision": "unpublished"}
        )
        args = env.args | {"index_manifest": manifest, "expected_index": manifest.pin()}
        with pytest.raises(ValueError, match="no successful publication"):
            audit_frozen_corpus_profile(**args)
