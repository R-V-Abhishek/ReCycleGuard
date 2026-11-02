"""Installed application pins must inspect installed code and the build lock."""

import hashlib

import pytest

from recycleguard import investigation


def test_installed_package_hashes_actual_sources_and_packaged_lock(tmp_path, monkeypatch):
    package = tmp_path / "site-packages" / "recycleguard"
    package.mkdir(parents=True)
    module = package / "investigation.py"
    module.write_text("# installed source\n", encoding="utf-8")
    lock = package / "runtime" / "uv.lock"
    lock.parent.mkdir()
    lock.write_bytes(b"exact build lock")
    monkeypatch.setattr(investigation, "__file__", str(module))
    expected = hashlib.sha256(b"src/recycleguard/investigation.py# installed source\n")
    assert investigation.source_revision() == f"source-sha256:{expected.hexdigest()}"
    assert investigation.dependency_lock_path() == lock
    module.write_text("# changed installed source\n", encoding="utf-8")
    assert investigation.source_revision() != f"source-sha256:{expected.hexdigest()}"


def test_checkout_uses_working_lock_without_silently_falling_back(tmp_path, monkeypatch):
    package = tmp_path / "src" / "recycleguard"
    package.mkdir(parents=True)
    module = package / "investigation.py"
    module.write_text("# checkout source\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
    working = tmp_path / "uv.lock"
    working.write_bytes(b"working lock")
    monkeypatch.setattr(investigation, "__file__", str(module))
    assert investigation.dependency_lock_path() == working
    working.unlink()
    with pytest.raises(ValueError, match="lock is unavailable"):
        investigation.dependency_lock_path()
