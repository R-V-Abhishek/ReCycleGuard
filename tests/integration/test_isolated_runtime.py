"""Trusted Docker launcher contracts; actual OS-boundary evidence is a separate run."""

import pytest
from typer.testing import CliRunner

from recycleguard import isolated_runtime


def test_build_context_excludes_repository_and_evaluator(tmp_path):
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "pyproject.toml").write_text("[project]\nname='fixture'\n")
    (repository / "uv.lock").write_text("version=1\n")
    dockerfile = repository / "tools/investigator-runtime/Dockerfile"
    dockerfile.parent.mkdir(parents=True)
    dockerfile.write_text("FROM fixture\n")
    (repository / "hidden.txt").write_text("must never enter the build context")
    wheel = tmp_path / "recycleguard-0.1.0-py3-none-any.whl"
    wheel.write_bytes(b"fixture wheel")
    context = isolated_runtime.prepare_build_context(repository, wheel, tmp_path / "context")
    assert sorted(
        path.relative_to(context).as_posix() for path in context.rglob("*") if path.is_file()
    ) == ["Dockerfile", "pyproject.toml", "uv.lock", f"wheels/{wheel.name}"]
    with pytest.raises(ValueError, match="must be new"):
        isolated_runtime.prepare_build_context(repository, wheel, context)


def test_launcher_has_fixed_boundary_and_rejects_mount_or_command_escape(tmp_path):
    visible, runtime = tmp_path / "visible", tmp_path / "runtime"
    visible.mkdir()
    runtime.mkdir()
    arguments = ["investigation", "status", "run:fixture"]
    command = isolated_runtime.docker_arguments("fixture-image", visible, runtime, arguments)
    assert "--read-only" in command
    assert command[command.index("--network") + 1] == "none"
    assert command[command.index("--cap-drop") + 1] == "ALL"
    assert "no-new-privileges" in command
    assert command[command.index("--user") + 1] == "10001:10001"
    assert command[-4:] == ["fixture-image", *arguments]
    assert "--env" not in command and "--volume" not in command
    with pytest.raises(ValueError, match="allowlisted"):
        isolated_runtime.docker_arguments("fixture-image", visible, runtime, ["shell", "execute"])
    with pytest.raises(ValueError, match="separate"):
        isolated_runtime.docker_arguments("fixture-image", runtime, runtime, arguments)
    with pytest.raises(ValueError, match="nonroot"):
        isolated_runtime.docker_arguments("fixture-image", visible, runtime, arguments, user_id=0)
    (visible / ".env").write_text("not allowed")
    with pytest.raises(ValueError, match="forbidden"):
        isolated_runtime.docker_arguments("fixture-image", visible, runtime, arguments)


def test_internal_entrypoint_preserves_cli_option_order(monkeypatch):
    seen = []
    monkeypatch.setattr(
        isolated_runtime, "container_entry", lambda arguments: seen.append(arguments) or 0
    )
    result = CliRunner().invoke(
        isolated_runtime.app, ["investigation", "run", "run:fixture", "--max-steps", "2"]
    )
    assert result.exit_code == 0, result.output
    assert seen == [["investigation", "run", "run:fixture", "--max-steps", "2"]]
