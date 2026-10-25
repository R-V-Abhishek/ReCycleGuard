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
from pathlib import Path
from uuid import uuid4

from recycleguard.contracts.core import ActorRef, BoundaryModel
from recycleguard.storage.authority import AuthorizationError


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
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(record.model_dump(mode="json"), stream)


def authenticate_reviewer(root: Path, password: str) -> ActorRef:
    path = root / "reviewer.json"
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "r", encoding="utf-8") as stream:
        metadata = os.fstat(stream.fileno())
        if (
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
