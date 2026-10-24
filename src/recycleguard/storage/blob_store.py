"""Content-addressed blob storage for the V01 commit-boundary prototype."""

import hashlib
import json
import os
import tempfile
from pathlib import Path

from recycleguard.contracts import BlobRef


class BlobIntegrityError(ValueError):
    """Raised when a stored blob does not match its content-addressed reference."""


def canonical_json_bytes(value: object) -> bytes:
    """Serialize JSON according to the repository hashing contract."""
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


class BlobStore:
    """Write-once SHA-256 objects with verification on every read."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.objects = self.root / "objects" / "sha256"
        self.objects.mkdir(parents=True, exist_ok=True)

    def put(self, data: bytes, media_type: str) -> BlobRef:
        digest = hashlib.sha256(data).hexdigest()
        reference = BlobRef(sha256=digest, byte_length=len(data), media_type=media_type)
        destination = self.objects / digest[:2] / digest
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            if self._read_verified(destination, reference) != data:
                raise BlobIntegrityError(f"existing blob mismatch: {digest}")
            return reference

        with tempfile.NamedTemporaryFile(
            dir=destination.parent, prefix=f".{digest}.", delete=False
        ) as temporary:
            temporary.write(data)
            temporary_path = Path(temporary.name)
        try:
            os.link(temporary_path, destination)
        except FileExistsError as exc:
            temporary_path.unlink(missing_ok=True)
            if self._read_verified(destination, reference) != data:
                raise BlobIntegrityError(f"concurrent blob mismatch: {digest}") from exc
        finally:
            temporary_path.unlink(missing_ok=True)
        return reference

    def get(self, reference: BlobRef) -> bytes:
        return self._read_verified(
            self.objects / reference.sha256[:2] / reference.sha256, reference
        )

    @staticmethod
    def _read_verified(path: Path, reference: BlobRef) -> bytes:
        if not path.is_file():
            raise FileNotFoundError(f"blob is missing: {reference.sha256}")
        data = path.read_bytes()
        if len(data) != reference.byte_length:
            raise BlobIntegrityError(f"blob length mismatch: {reference.sha256}")
        if hashlib.sha256(data).hexdigest() != reference.sha256:
            raise BlobIntegrityError(f"blob digest mismatch: {reference.sha256}")
        return data
