"""Local operator bootstrap and password reauthentication for trusted CLI review.

The credential file belongs to the OS user who owns this data root. This is a local
application trust boundary, not multi-user isolation or official signatory authority.
"""

import hashlib
import hmac
import json
import os
import secrets
import stat
import subprocess
from pathlib import Path
from uuid import uuid4

from recycleguard.contracts.core import ActorRef, BoundaryModel
from recycleguard.storage.authority import AuthorizationError

_WINDOWS_CREATE = r"""
$ErrorActionPreference = 'Stop'
$path = $env:RECYCLEGUARD_CREDENTIAL_PATH
$owner = [System.Security.Principal.WindowsIdentity]::GetCurrent().User
$acl = [System.Security.AccessControl.FileSecurity]::new()
$acl.SetOwner($owner)
$acl.SetAccessRuleProtection($true, $false)
$rule = [System.Security.AccessControl.FileSystemAccessRule]::new(
    $owner, [System.Security.AccessControl.FileSystemRights]::FullControl,
    [System.Security.AccessControl.AccessControlType]::Allow)
$acl.AddAccessRule($rule)
# CreateNew with a security descriptor makes the empty file private atomically.
# ACL changes after ordinary creation would not revoke previously opened handles.
$stream = [System.IO.FileStream]::new(
    $path, [System.IO.FileMode]::CreateNew,
    [System.Security.AccessControl.FileSystemRights]::FullControl,
    [System.IO.FileShare]::None, 4096, [System.IO.FileOptions]::None, $acl)
$stream.Dispose()
"""

_WINDOWS_CHECK = r"""
$ErrorActionPreference = 'Stop'
$path = $env:RECYCLEGUARD_CREDENTIAL_PATH
$owner = [System.Security.Principal.WindowsIdentity]::GetCurrent().User
$item = Get-Item -LiteralPath $path -Force
if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
    throw 'Credential reparse points are prohibited'
}
$acl = Get-Acl -LiteralPath $path
if ($acl.GetOwner([System.Security.Principal.SecurityIdentifier]).Value -ne $owner.Value) {
    throw 'Credential owner is not the current user'
}
if (-not $acl.AreAccessRulesProtected) { throw 'Credential ACL inheritance is enabled' }
$rules = @($acl.GetAccessRules($true, $true, [System.Security.Principal.SecurityIdentifier]))
if ($rules.Count -ne 1) { throw 'Credential ACL must contain only the current user' }
$rule = $rules[0]
if ($rule.IdentityReference.Value -ne $owner.Value -or $rule.IsInherited -or
    $rule.AccessControlType -ne [System.Security.AccessControl.AccessControlType]::Allow -or
    $rule.FileSystemRights -ne [System.Security.AccessControl.FileSystemRights]::FullControl) {
    throw 'Credential ACL requires current-user-only full control'
}
"""


def _windows_acl(path: Path, *, create: bool = False):
    """Trusted static OS ACL operation; neither scripts nor credentials come from requests."""
    try:
        executable = (
            Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
        )
        environment = os.environ.copy()
        environment["RECYCLEGUARD_CREDENTIAL_PATH"] = str(path.absolute())
        completed = subprocess.run(
            [
                str(executable),
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                _WINDOWS_CREATE if create else _WINDOWS_CHECK,
            ],
            env=environment,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (KeyError, OSError, subprocess.TimeoutExpired) as exc:
        raise AuthorizationError("Windows credential ACL operation is unavailable") from exc
    if completed.returncode != 0:
        raise AuthorizationError("Windows reviewer credentials require a current-user-only ACL")


def _windows_regular_file(path: Path):
    metadata = path.lstat()
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT
        or metadata.st_nlink != 1
    ):
        raise AuthorizationError("reviewer credentials require an unlinked regular file")
    return metadata


class ReviewerCredential(BoundaryModel):
    actor: ActorRef
    salt: str
    password_hash: str


def _derive(password: str, salt: str) -> str:
    return hashlib.scrypt(
        password.encode("utf-8"), salt=bytes.fromhex(salt), n=16384, r=8, p=1, dklen=32
    ).hex()


def initialize_reviewer(root: Path, actor_id: str, password: str):
    """Explicit first-owner enrollment. Existing credentials are never overwritten."""
    actor = ActorRef(actor_id=actor_id, actor_kind="HUMAN", authenticated_session_ref=None)
    if len(password) < 12:
        raise ValueError("reviewer password must contain at least 12 characters")
    salt = secrets.token_hex(16)
    record = ReviewerCredential(actor=actor, salt=salt, password_hash=_derive(password, salt))
    root.mkdir(parents=True, exist_ok=True)
    path = root / "reviewer.json"
    if os.name == "nt":
        if path.exists() or path.is_symlink():
            raise FileExistsError(path)
        _windows_acl(path, create=True)
        before = _windows_regular_file(path)
        _windows_acl(path)
        descriptor = os.open(path, os.O_WRONLY | os.O_NOINHERIT)
        if not os.path.samestat(before, os.fstat(descriptor)):
            os.close(descriptor)
            raise AuthorizationError("credential file changed during creation")
    else:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(record.model_dump(mode="json"), stream)


def authenticate_reviewer(root: Path, password: str) -> ActorRef:
    path = root / "reviewer.json"
    if os.name == "nt":
        before = _windows_regular_file(path)
        _windows_acl(path)
        descriptor = os.open(path, os.O_RDONLY | os.O_NOINHERIT)
    elif os.name == "posix":
        before = None
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    else:
        raise AuthorizationError("trusted local review requires POSIX permissions or Windows ACLs")
    with os.fdopen(descriptor, "r", encoding="utf-8") as stream:
        metadata = os.fstat(stream.fileno())
        if os.name == "nt":
            if not os.path.samestat(before, metadata) or not os.path.samestat(
                metadata, _windows_regular_file(path)
            ):
                raise AuthorizationError("credential file changed during authentication")
            _windows_acl(path)
        elif (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or stat.S_IMODE(metadata.st_mode) & 0o077
        ):
            raise AuthorizationError("reviewer credentials require an owner-only regular file")
        record = ReviewerCredential.model_validate_json(stream.read())
    if (
        record.actor.actor_kind != "HUMAN"
        or record.actor.authenticated_session_ref is not None
        or not hmac.compare_digest(_derive(password, record.salt), record.password_hash)
    ):
        raise AuthorizationError("reviewer authentication failed")
    return record.actor.model_copy(update={"authenticated_session_ref": f"session:{uuid4().hex}"})
