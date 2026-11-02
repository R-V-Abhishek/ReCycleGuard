import json
import subprocess

import pytest

from benchmarks.evaluation.freeze import (
    build_freeze,
    freeze_bytes,
    freeze_digest,
    tree_digest,
    verify_freeze,
)


@pytest.fixture
def repository(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "a.py").write_text("a = 1\n")
    (tmp_path / "pkg" / "b.py").write_text("b = 2\n")
    (tmp_path / "lock.txt").write_text("lock\n")
    for command in (
        ["init", "-q"],
        ["config", "user.email", "t@example.invalid"],
        ["config", "user.name", "t"],
        ["add", "."],
        ["commit", "-q", "-m", "x"],
    ):
        subprocess.run(["git", "-C", str(tmp_path), *command], check=True)
    return tmp_path


SPEC = {
    "scope": "INCLUDES_REAL_MODEL",
    "files": ["lock.txt"],
    "trees": ["pkg"],
    "values": {"prompt_pin": "abc", "model_revision": "r1"},
}


def test_freeze_verifies_unchanged_inputs_and_is_deterministic(repository):
    freeze = build_freeze(repository, SPEC)
    assert freeze["git"]["dirty"] is False
    assert freeze_bytes(freeze) == freeze_bytes(build_freeze(repository, SPEC))
    assert verify_freeze(repository, freeze, strict_commit=True) == []
    assert len(freeze_digest(freeze)) == 64


def test_changed_file_tree_and_missing_input_are_named(repository):
    freeze = build_freeze(repository, SPEC)
    (repository / "lock.txt").write_text("other\n")
    (repository / "pkg" / "b.py").write_text("b = 3\n")
    problems = verify_freeze(repository, freeze)
    assert problems == ["changed file: lock.txt", "changed tree: pkg"]
    (repository / "lock.txt").unlink()
    assert "missing file: lock.txt" in verify_freeze(repository, freeze)


def test_added_file_changes_tree_but_caches_do_not(repository):
    before = tree_digest(repository / "pkg")
    (repository / "pkg" / "__pycache__").mkdir()
    (repository / "pkg" / "__pycache__" / "a.pyc").write_bytes(b"x")
    assert tree_digest(repository / "pkg") == before
    (repository / "pkg" / "c.py").write_text("c = 3\n")
    assert tree_digest(repository / "pkg") != before


def test_scope_must_be_declared_and_dirty_trees_are_flagged(repository):
    with pytest.raises(ValueError):
        build_freeze(repository, {**SPEC, "scope": "WHATEVER"})
    (repository / "lock.txt").write_text("changed\n")
    freeze = build_freeze(repository, SPEC)
    assert freeze["git"]["dirty"] is True
    assert "freeze was recorded from a dirty working tree" in verify_freeze(repository, freeze)


def test_strict_commit_detects_a_later_commit(repository):
    freeze = build_freeze(repository, SPEC)
    (repository / "extra.txt").write_text("e\n")
    subprocess.run(["git", "-C", str(repository), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repository), "commit", "-q", "-m", "y"], check=True)
    assert verify_freeze(repository, freeze) == []
    assert any(
        "not the frozen commit" in p for p in verify_freeze(repository, freeze, strict_commit=True)
    )
    assert json.loads(freeze_bytes(freeze))["scope"] == "INCLUDES_REAL_MODEL"
