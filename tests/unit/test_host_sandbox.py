"""Profile text and probe logic. Real sandbox-exec denial can only be proven on macOS."""

import json

import pytest

from recycleguard.host_sandbox import (
    _attempt,
    probe_boundary,
    sandbox_command,
    sandbox_environment,
    sandbox_profile,
)


@pytest.fixture
def roots(tmp_path):
    visible, runtime = tmp_path / "visible", tmp_path / "runtime"
    visible.mkdir()
    runtime.mkdir()
    return visible, runtime


def test_profile_denies_by_default_and_names_only_the_given_paths(roots, tmp_path):
    visible, runtime = roots
    wheel = tmp_path / "venv"
    profile = sandbox_profile(visible, runtime, (wheel,), model_port=8766)
    assert "(deny default)" in profile
    assert f'(subpath "{visible.resolve().as_posix()}")' in profile
    assert f'(subpath "{wheel.as_posix()}")' in profile
    writes = profile[profile.index("(allow file-write*") : profile.index("(allow network-outbound")]
    assert runtime.resolve().as_posix() in writes and visible.resolve().as_posix() not in writes
    assert '(remote ip "localhost:8766")' in profile
    assert "(allow network*" not in profile and '(remote ip "*' not in profile


@pytest.mark.parametrize("port", [0, 70000])
def test_profile_rejects_a_bad_port(roots, port):
    with pytest.raises(ValueError, match="port"):
        sandbox_profile(*roots, (), model_port=port)


def test_profile_rejects_overlapping_roots(tmp_path):
    inner = tmp_path / "visible" / "runtime"
    inner.mkdir(parents=True)
    with pytest.raises(ValueError, match="separate"):
        sandbox_profile(tmp_path / "visible", inner, (), model_port=8766)


def test_profile_rejects_an_evaluator_mount(tmp_path):
    hidden, runtime = tmp_path / "hidden", tmp_path / "runtime"
    hidden.mkdir()
    runtime.mkdir()
    with pytest.raises(ValueError, match="forbidden"):
        sandbox_profile(hidden, runtime, (), model_port=8766)


def test_profile_rejects_a_path_that_could_break_out_of_its_quotes(roots, tmp_path):
    with pytest.raises(ValueError, match="unsupported"):
        sandbox_profile(*roots, ('/tmp/evil")(allow default',), model_port=8766)


def test_command_ignores_python_path_and_environment_inherits_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv("ORACLE_ROOT", "/secret")
    command = sandbox_command(tmp_path / "p.sb", tmp_path / "python", tmp_path / "c.py", ["--x"])
    assert command[0] == "/usr/bin/sandbox-exec" and "-I" in command and command[-1] == "--x"
    environment = sandbox_environment(tmp_path)
    assert set(environment) == {
        "PATH",
        "HOME",
        "TMPDIR",
        "PYTHONDONTWRITEBYTECODE",
        "PYTHONUNBUFFERED",
    }


def test_only_a_permission_refusal_counts_as_denied():
    def refused():
        raise PermissionError(13, "denied")

    def missing():
        raise FileNotFoundError(2, "missing")

    assert _attempt("read", "x", refused)["denied"] is True
    assert _attempt("read", "x", missing)["denied"] is False
    assert _attempt("read", "x", lambda: None)["denied"] is False


def test_unsandboxed_probe_records_evidence_and_refuses_to_continue(roots, tmp_path):
    visible, runtime = roots
    forbidden = tmp_path / "evaluator"
    forbidden.mkdir()
    (forbidden / "answers.json").write_text("{}")
    evidence = runtime / "evidence.json"
    with pytest.raises(RuntimeError, match="not denied"):
        probe_boundary([forbidden], visible, runtime, evidence)
    probes = json.loads(evidence.read_text("utf-8"))["probes"]
    assert any(p["action"] == "list" and p["denied"] is False for p in probes)


def test_probe_needs_something_to_try(roots, tmp_path):
    with pytest.raises(RuntimeError, match="forbidden host paths"):
        probe_boundary([], *roots, tmp_path / "evidence.json")
