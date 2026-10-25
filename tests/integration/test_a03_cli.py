"""Exercise real local CLI composition, password checks and durable review records."""

import json

import pytest
from typer.testing import CliRunner

from recycleguard.application import local_application
from recycleguard.cli import app
from recycleguard.config import Settings
from recycleguard.contracts.snapshots import SnapshotReview
from recycleguard.local_session import authenticate_reviewer, initialize_reviewer
from recycleguard.storage import BlobStore
from recycleguard.storage.authority import AuthorizationError
from tests.integration.test_a03_snapshots import publication

runner = CliRunner()
PASSWORD = "test-fixture-password-only"


def configure(tmp_path, monkeypatch):
    root = tmp_path / "runtime"
    monkeypatch.setenv("RECYCLEGUARD_DATA_ROOT", str(root))
    blobs = BlobStore(root)
    request = publication(blobs)
    path = tmp_path / "publish.json"
    path.write_text(request.model_dump_json(), encoding="utf-8")
    return root, request, path


def test_cli_publication_and_authenticated_review_survive_reopen(tmp_path, monkeypatch):
    root, request, path = configure(tmp_path, monkeypatch)
    result = runner.invoke(
        app, ["reviewer", "init", "human:lead"], input=f"{PASSWORD}\n{PASSWORD}\n"
    )
    assert result.exit_code == 0, result.output
    assert root.joinpath("reviewer.json").stat().st_mode & 0o077 == 0
    result = runner.invoke(app, ["snapshot", "publish", str(path)])
    assert result.exit_code == 0, result.output
    draft = json.loads(result.stdout)["output"]
    review = SnapshotReview(
        scope_id=request.scope_id,
        target_snapshot_id=draft["snapshot_id"],
        target_membership_digest=draft["membership_digest"],
        expected_head=draft["snapshot_id"],
        new_snapshot_id="snapshot:approved",
        decision="APPROVE",
        reason="Internal fixture review",
    )
    review_path = tmp_path / "review.json"
    review_path.write_text(review.model_dump_json(), encoding="utf-8")
    result = runner.invoke(app, ["snapshot", "review", str(review_path)], input=f"{PASSWORD}\n")
    assert result.exit_code == 0, result.output
    output = json.loads(result.stdout)
    assert output["output"]["review_state"] == "APPROVED"
    assert output["audit_event_ids"]
    assert PASSWORD not in result.output
    with local_application(Settings.from_environment()) as (service, _, _):
        assert service.snapshots.head(request.scope_id).snapshot_id == "snapshot:approved"
        events = service.kernel.list_stream_events(f"stream:{request.scope_id}")
        assert events[-1].actor.actor_id == "human:lead"
        assert events[-1].actor.authenticated_session_ref.startswith("session:")
        assert PASSWORD not in str(events)
        assert service.snapshots.catalog.get_snapshot(draft["snapshot_id"]).review_state == "DRAFT"


def test_wrong_password_cannot_open_review_application(tmp_path, monkeypatch):
    root, request, path = configure(tmp_path, monkeypatch)
    initialize_reviewer(root, "human:lead", PASSWORD)
    assert runner.invoke(app, ["snapshot", "publish", str(path)]).exit_code == 0
    review = SnapshotReview(
        scope_id=request.scope_id,
        target_snapshot_id=request.snapshot_id,
        target_membership_digest=request.membership_digest,
        expected_head=request.snapshot_id,
        new_snapshot_id="snapshot:approved",
        decision="APPROVE",
        reason="Fixture",
    )
    path.write_text(review.model_dump_json(), encoding="utf-8")
    result = runner.invoke(app, ["snapshot", "review", str(path)], input="wrong-password\n")
    assert result.exit_code == 1 and "authentication failed" in result.output
    with local_application(Settings.from_environment()) as (service, _, _):
        assert service.snapshots.head(request.scope_id).review_state == "DRAFT"
        assert len(service.kernel.list_stream_events(f"stream:{request.scope_id}")) == 1


def test_json_cannot_supply_actor_or_change_permissions(tmp_path, monkeypatch):
    root, request, path = configure(tmp_path, monkeypatch)
    data = request.model_dump(mode="json")
    data["actor"] = {"actor_kind": "HUMAN"}
    path.write_text(json.dumps(data), encoding="utf-8")
    result = runner.invoke(app, ["snapshot", "publish", str(path)])
    assert result.exit_code == 1 and "Extra inputs" in result.output
    assert not root.joinpath("application.sqlite").exists()


def test_reviewer_bootstrap_does_not_overwrite_and_sessions_are_distinct(tmp_path):
    initialize_reviewer(tmp_path, "human:lead", PASSWORD)
    original = tmp_path.joinpath("reviewer.json").read_bytes()
    with pytest.raises(FileExistsError):
        initialize_reviewer(tmp_path, "human:attacker", PASSWORD)
    assert tmp_path.joinpath("reviewer.json").read_bytes() == original
    first = authenticate_reviewer(tmp_path, PASSWORD)
    second = authenticate_reviewer(tmp_path, PASSWORD)
    assert first.actor_id == second.actor_id
    assert first.authenticated_session_ref != second.authenticated_session_ref
    assert PASSWORD.encode() not in original


@pytest.mark.parametrize("fault", ["permissions", "symlink"])
def test_unsafe_credential_files_are_rejected(tmp_path, fault):
    initialize_reviewer(tmp_path, "human:lead", PASSWORD)
    path = tmp_path / "reviewer.json"
    if fault == "permissions":
        path.chmod(0o644)
    else:
        target = tmp_path / "target.json"
        path.rename(target)
        path.symlink_to(target)
    with pytest.raises((AuthorizationError, OSError)):
        authenticate_reviewer(tmp_path, PASSWORD)


def test_weak_password_does_not_create_credentials(tmp_path):
    with pytest.raises(ValueError, match="12 characters"):
        initialize_reviewer(tmp_path, "human:lead", "short")
    assert not (tmp_path / "reviewer.json").exists()


def test_application_revokes_capability_on_exit(tmp_path):
    with local_application(Settings(data_root=tmp_path)) as (service, ctx, cap):
        authority = service.kernel.authority
        authority.check(cap, ctx.actor, "profile.publish")
    with pytest.raises(AuthorizationError):
        authority.check(cap, ctx.actor, "profile.publish")
