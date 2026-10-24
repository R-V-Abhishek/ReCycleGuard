import json

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from recycleguard.cli import app
from recycleguard.config import Settings

runner = CliRunner()


@pytest.mark.parametrize("mode", ["runtime", "evaluation"])
def test_test_adapters_fail_closed(mode):
    with pytest.raises(ValidationError):
        Settings(mode=mode, enable_test_adapters=True)


def test_unknown_setting_rejected():
    with pytest.raises(ValidationError):
        Settings(benchmark_truth_root="/secret")


def test_doctor_has_no_side_effects(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0, result.output
    report = json.loads(result.output)
    assert report["model_gateway"] == "UNAVAILABLE"
    assert report["sqlite_fts5"] is True
    assert list(tmp_path.iterdir()) == []


def test_env_guard(monkeypatch):
    monkeypatch.setenv("RECYCLEGUARD_MODE", "evaluation")
    monkeypatch.setenv("RECYCLEGUARD_ENABLE_TEST_ADAPTERS", "true")
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 1
    assert "test adapters are allowed only in test mode" in result.output


def test_cli_version_and_help():
    assert "protocol 1.1" in runner.invoke(app, ["--version"]).output
    assert "doctor" in runner.invoke(app, ["--help"]).output


def test_cli_validate(tmp_path):
    p = tmp_path / "quantity.json"
    p.write_text('{"decimal":"25","unit":"KG","dimension":"METAL_MASS","metal":"CU"}')
    assert runner.invoke(app, ["validate", "quantity", str(p)]).exit_code == 0
    p.write_text('{"decimal":25}')
    assert runner.invoke(app, ["validate", "quantity", str(p)]).exit_code == 1
