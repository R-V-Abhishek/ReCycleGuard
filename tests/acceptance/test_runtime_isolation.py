"""G11 acceptance tests: Enforce minimal investigator runtime and oracle isolation.

Pursuant to SYSTEM_DESIGN.md §11, CONTRACTS.md §10 (G11) and implementation plan.md §10:
- Denies hidden paths/labels/seeds/evaluator files via image, mounts, env, tool access, logs and UI.
- Records all attempted access violations in isolation reports.
"""

from pathlib import Path

import pytest

from recycleguard.isolation import (
    OracleAccessDeniedError,
    RuntimeIsolationEnforcer,
)


@pytest.fixture
def sandbox_env(tmp_path: Path):
    visible_root = tmp_path / "visible_dossier"
    visible_root.mkdir(parents=True, exist_ok=True)
    runtime_root = tmp_path / "runtime_workspace"
    runtime_root.mkdir(parents=True, exist_ok=True)

    # Legitimate visible files
    (visible_root / "case_manifest.json").write_text('{"case_id": "case:001"}')
    (visible_root / "records").mkdir(exist_ok=True)
    (visible_root / "records" / "entities.jsonl").write_text('{"entity_id": "e1"}')

    # Hidden / forbidden files
    hidden_dir = tmp_path / "benchmarks" / "evaluation"
    hidden_dir.mkdir(parents=True, exist_ok=True)
    (hidden_dir / "oracle_answers.json").write_text('{"truth": 100}')

    fixtures_expected = tmp_path / "tests" / "fixtures" / "expected"
    fixtures_expected.mkdir(parents=True, exist_ok=True)
    (fixtures_expected / "ground_truth.json").write_text('{"answer": 55}')

    return visible_root, runtime_root, hidden_dir, fixtures_expected


def test_g11_permitted_access(sandbox_env):
    """Permitted visible dossier assets and runtime directory access succeed."""
    visible_root, runtime_root, _, _ = sandbox_env
    enforcer = RuntimeIsolationEnforcer(visible_root, runtime_root)

    valid_file = visible_root / "case_manifest.json"
    resolved = enforcer.check_path_access(valid_file)
    assert resolved == valid_file.resolve()

    writable_runtime = runtime_root / "output.json"
    resolved_rt = enforcer.check_path_access(writable_runtime)
    assert resolved_rt == writable_runtime.resolve()
    assert len(enforcer.violations) == 0


def test_g11_deny_hidden_oracle_and_evaluator_paths(sandbox_env):
    """Attempted access to oracle, expected fixtures, or evaluation code is blocked and recorded."""
    visible_root, runtime_root, hidden_dir, fixtures_expected = sandbox_env
    enforcer = RuntimeIsolationEnforcer(visible_root, runtime_root)

    # 1. Deny benchmarks/evaluation access
    oracle_file = hidden_dir / "oracle_answers.json"
    with pytest.raises(OracleAccessDeniedError):
        enforcer.check_path_access(oracle_file, caller_actor_id="actor:investigator")

    # 2. Deny tests/fixtures/expected access
    truth_file = fixtures_expected / "ground_truth.json"
    with pytest.raises(OracleAccessDeniedError):
        enforcer.check_path_access(truth_file, caller_actor_id="actor:investigator")

    # 3. Deny arbitrary parent traversal outside sandbox
    with pytest.raises(OracleAccessDeniedError):
        enforcer.check_path_access(visible_root / ".." / "some_external_file.txt")

    assert len(enforcer.violations) == 3
    assert all(v.action_taken == "DENIED_AND_RECORDED" for v in enforcer.violations)


def test_g11_deny_symlink_traversal(sandbox_env):
    """Symlink pointing to forbidden oracle data outside visible boundary is rejected."""
    visible_root, runtime_root, hidden_dir, _ = sandbox_env
    enforcer = RuntimeIsolationEnforcer(visible_root, runtime_root)

    # Create symlink inside visible_root pointing to hidden oracle
    symlink_path = visible_root / "leak_link.json"
    oracle_file = hidden_dir / "oracle_answers.json"
    try:
        symlink_path.symlink_to(oracle_file)
    except OSError:
        pytest.skip("Symlink creation not permitted in this OS environment")

    with pytest.raises(OracleAccessDeniedError):
        enforcer.check_path_access(symlink_path, caller_actor_id="actor:investigator")

    assert any(
        v.violation_kind in {"ORACLE_ACCESS_ATTEMPT", "SYMLINK_TRAVERSAL", "FORBIDDEN_PATH"}
        for v in enforcer.violations
    )


def test_g11_environment_sanitization(sandbox_env):
    """Answer-bearing environment variables and seeds are stripped and recorded."""
    visible_root, runtime_root, _, _ = sandbox_env
    enforcer = RuntimeIsolationEnforcer(visible_root, runtime_root)

    dirty_env = {
        "PATH": "/usr/bin",
        "RECYCLEGUARD_MODE": "BENCHMARK",
        "ORACLE_ANSWER_KEY": "secret_key_123",
        "BENCHMARK_SEED_LOT": "seed_999",
        "GROUND_TRUTH_BALANCE": "55.000",
    }

    clean_env = enforcer.sanitize_environment(dirty_env, caller_actor_id="actor:investigator")

    assert "PATH" in clean_env
    assert "RECYCLEGUARD_MODE" in clean_env
    assert "ORACLE_ANSWER_KEY" not in clean_env
    assert "BENCHMARK_SEED_LOT" not in clean_env
    assert "GROUND_TRUTH_BALANCE" not in clean_env

    assert len(enforcer.violations) == 3
    assert all(v.violation_kind == "FORBIDDEN_ENV_VAR" for v in enforcer.violations)


def test_g11_mount_validation(sandbox_env):
    """Mount validation fails if forbidden benchmark or evaluation directories are mounted."""
    visible_root, runtime_root, hidden_dir, _ = sandbox_env
    enforcer = RuntimeIsolationEnforcer(visible_root, runtime_root)

    report = enforcer.validate_mounts(
        [visible_root, runtime_root, hidden_dir], caller_actor_id="actor:investigator"
    )

    assert not report.passed
    assert len(report.violations) > 0
    assert any(v.violation_kind == "EVALUATOR_CODE_MOUNT" for v in report.violations)
