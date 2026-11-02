"""CLI package verification uses frozen bytes without the source application DB."""

import json

import pytest
from typer.testing import CliRunner

from recycleguard.cli import app
from tests.integration.test_a05_baseline import approved_foundation as approved_foundation
from tests.integration.test_a06_workflow import workflow as workflow
from tests.support.workflow import assess, plan


@pytest.mark.parametrize(
    "args",
    [
        ["audit", "export", "--run-id", "run:missing", "--kind", "TYPO"],
        ["replay", "--bundle-id", "bundle:missing", "--mode", "TYPO"],
    ],
)
def test_unknown_cli_modes_fail_before_creating_application(args, tmp_path, monkeypatch):
    root = tmp_path / "must-not-exist"
    monkeypatch.setenv("RECYCLEGUARD_DATA_ROOT", str(root))
    result = CliRunner().invoke(app, args)
    assert result.exit_code != 0
    assert "must be" in result.output
    assert not root.exists()


def test_cli_exports_and_replays_standalone_package(workflow, tmp_path, monkeypatch):
    with workflow([plan(), assess()]) as env:
        env.drive(env.start())
        run_id, source = env.spec.run_id, env.settings.data_root
    runner = CliRunner()
    monkeypatch.setenv("RECYCLEGUARD_DATA_ROOT", str(source))
    package = tmp_path / "package"
    exported = runner.invoke(app, ["audit", "export", "--run-id", run_id, "--output", str(package)])
    assert exported.exit_code == 0, exported.output
    assert json.loads(exported.output)["audit_event_ids"]
    # The offline commands must not construct or read an application database.
    absent = tmp_path / "absent-application"
    monkeypatch.setenv("RECYCLEGUARD_DATA_ROOT", str(absent))
    verified = runner.invoke(app, ["audit", "verify-package", str(package)])
    assert verified.exit_code == 0, verified.output
    assert json.loads(verified.output)["verdict"] == "PASS"
    replayed = runner.invoke(app, ["replay-package", str(package)])
    assert replayed.exit_code == 0, replayed.output
    assert json.loads(replayed.output)["output"]["reconstructed_state_refs"]
    assert not absent.exists()
