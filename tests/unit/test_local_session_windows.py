"""Native Windows credential ACL checks; no permission or authentication mocks."""

import json
import os
import subprocess
from pathlib import Path

import pytest

from recycleguard.local_session import _windows_acl, authenticate_reviewer, initialize_reviewer
from recycleguard.storage.authority import AuthorizationError

pytestmark = pytest.mark.skipif(os.name != "nt", reason="requires native Windows NTFS ACLs")
PASSWORD = "windows-native-test-password"


def powershell(path, script):
    environment = os.environ.copy()
    environment["RECYCLEGUARD_CREDENTIAL_PATH"] = str(path.absolute())
    executable = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    environment["PSModulePath"] = str(executable.parent / "Modules")
    return subprocess.run(
        [str(executable), "-NoProfile", "-NonInteractive", "-Command", script],
        env=environment,
        check=True,
        capture_output=True,
        text=True,
        timeout=15,
    ).stdout


def test_windows_atomic_security_descriptor(tmp_path):
    """Inspect the native descriptor independently of the application's CHECK script."""
    path = tmp_path / "empty-credential.json"
    _windows_acl(path, create=True)
    security = json.loads(
        powershell(
            path,
            r"""
        $ErrorActionPreference = 'Stop'
        $acl = [System.IO.File]::GetAccessControl($env:RECYCLEGUARD_CREDENTIAL_PATH)
        $sid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User
        $rules = @($acl.GetAccessRules($true, $true,
            [System.Security.Principal.SecurityIdentifier]))
        $access = @($rules | ForEach-Object {
            @{ identity = $_.IdentityReference.Value; inherited = $_.IsInherited;
               rights = [string]$_.FileSystemRights; access = [string]$_.AccessControlType }
        })
        @{ owner = $acl.GetOwner([System.Security.Principal.SecurityIdentifier]).Value;
           current = $sid.Value; protected = $acl.AreAccessRulesProtected;
           sddl = $acl.Sddl; rules = $access } | ConvertTo-Json -Depth 5 -Compress
    """,
        )
    )
    assert security["owner"] == security["current"], security
    assert security["protected"] is True, security
    assert security["rules"] == [
        {
            "identity": security["current"],
            "inherited": False,
            "rights": "FullControl",
            "access": "Allow",
        }
    ], security
    assert path.read_bytes() == b""
    _windows_acl(path)


def test_windows_private_acl_authentication_and_literal_paths(tmp_path):
    root = tmp_path / "quoted' [private] & literal"
    initialize_reviewer(root, "human:windows_test", PASSWORD)
    path = root / "reviewer.json"
    security = json.loads(
        powershell(
            path,
            r"""
        $ErrorActionPreference = 'Stop'
        $acl = [System.IO.File]::GetAccessControl($env:RECYCLEGUARD_CREDENTIAL_PATH)
        $sid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User
        $rules = @($acl.GetAccessRules($true, $true,
            [System.Security.Principal.SecurityIdentifier]))
        @{ owner = $acl.GetOwner([System.Security.Principal.SecurityIdentifier]).Value;
           current = $sid.Value; protected = $acl.AreAccessRulesProtected;
           count = $rules.Count; granted = $rules[0].IdentityReference.Value } |
            ConvertTo-Json -Compress
    """,
        )
    )
    assert security["owner"] == security["current"] == security["granted"]
    assert security["protected"] is True and security["count"] == 1
    first = authenticate_reviewer(root, PASSWORD)
    second = authenticate_reviewer(root, PASSWORD)
    assert first.actor_id == "human:windows_test"
    assert first.authenticated_session_ref != second.authenticated_session_ref
    assert PASSWORD not in path.read_text()
    with pytest.raises(AuthorizationError, match="authentication failed"):
        authenticate_reviewer(root, "wrong-password")
    before = path.read_bytes()
    with pytest.raises(FileExistsError):
        initialize_reviewer(root, "human:other", PASSWORD)
    assert path.read_bytes() == before


def test_windows_foreign_read_grant_is_rejected(tmp_path):
    initialize_reviewer(tmp_path, "human:windows_test", PASSWORD)
    powershell(
        tmp_path / "reviewer.json",
        r"""
        $ErrorActionPreference = 'Stop'
        $path = $env:RECYCLEGUARD_CREDENTIAL_PATH
        $acl = [System.IO.File]::GetAccessControl($path)
        $everyone = [System.Security.Principal.SecurityIdentifier]::new('S-1-1-0')
        $rule = [System.Security.AccessControl.FileSystemAccessRule]::new(
            $everyone, [System.Security.AccessControl.FileSystemRights]::Read,
            [System.Security.AccessControl.AccessControlType]::Allow)
        $acl.AddAccessRule($rule)
        [System.IO.File]::SetAccessControl($path, $acl)
    """,
    )
    with pytest.raises(AuthorizationError, match="current-user-only ACL"):
        authenticate_reviewer(tmp_path, PASSWORD)


def test_windows_reenabled_acl_inheritance_is_rejected(tmp_path):
    initialize_reviewer(tmp_path, "human:windows_test", PASSWORD)
    powershell(
        tmp_path / "reviewer.json",
        r"""
        $ErrorActionPreference = 'Stop'
        $path = $env:RECYCLEGUARD_CREDENTIAL_PATH
        $acl = [System.IO.File]::GetAccessControl($path)
        $acl.SetAccessRuleProtection($false, $false)
        [System.IO.File]::SetAccessControl($path, $acl)
    """,
    )
    with pytest.raises(AuthorizationError, match="current-user-only ACL"):
        authenticate_reviewer(tmp_path, PASSWORD)


def test_windows_hard_link_credentials_are_rejected(tmp_path):
    initialize_reviewer(tmp_path, "human:windows_test", PASSWORD)
    (tmp_path / "alias.json").hardlink_to(tmp_path / "reviewer.json")
    with pytest.raises(AuthorizationError, match="unlinked regular file"):
        authenticate_reviewer(tmp_path, PASSWORD)


def test_windows_symlink_credentials_are_rejected(tmp_path):
    root = tmp_path / "credentials"
    initialize_reviewer(root, "human:windows_test", PASSWORD)
    original = root / "reviewer.json"
    moved = root / "original.json"
    original.rename(moved)
    try:
        original.symlink_to(moved)
    except OSError as exc:
        if exc.winerror == 1314:
            pytest.skip("Windows account lacks the OS privilege to create symbolic links")
        raise
    with pytest.raises(AuthorizationError, match="unlinked regular file"):
        authenticate_reviewer(root, PASSWORD)
