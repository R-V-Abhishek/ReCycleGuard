"""Storage primitives — V01 prototype and V02 production kernel."""

from recycleguard.contracts.audit import AuditEvent, OperationIntent, OperationResult

from .audit_kernel import AuditKernel
from .authority import AuthorizationError, Capability, LocalAuthority, TrustedPrincipal
from .blob_store import BlobIntegrityError, BlobRef, BlobStore, canonical_json_bytes
from .catalog import ArtifactCatalog, CatalogError

# V01 prototype — kept for CP0 integration tests and downstream fixtures.
from .commit_boundary import AuditContext, CommitBoundary

__all__ = [
    # V01 prototype
    "AuditContext",
    "AuditEvent",
    "BlobRef",
    "CommitBoundary",
    "OperationIntent",
    "OperationResult",
    # V02 production kernel
    "AuditKernel",
    "AuthorizationError",
    "Capability",
    "LocalAuthority",
    "TrustedPrincipal",
    "ArtifactCatalog",
    "CatalogError",
    # Shared
    "BlobIntegrityError",
    "BlobStore",
    "canonical_json_bytes",
]
