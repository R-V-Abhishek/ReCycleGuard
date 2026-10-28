"""Trusted local composition. Request JSON never supplies actors or capabilities."""

from contextlib import contextmanager
from uuid import uuid4

from recycleguard.case_service import CaseService
from recycleguard.contracts.core import ActorRef, CommandContext
from recycleguard.local_session import authenticate_reviewer
from recycleguard.profiles import ProfileStore
from recycleguard.snapshots import SnapshotStore
from recycleguard.storage import ArtifactCatalog, AuditKernel, BlobStore
from recycleguard.storage.authority import LocalAuthority, TrustedPrincipal


def command_context(actor: ActorRef) -> CommandContext:
    key = uuid4().hex
    return CommandContext(
        contract_version="1.1",
        command_id=f"command:{key}",
        operation_id=f"operation:{key}",
        attempt_id=f"attempt:{key}",
        idempotency_key=key,
        actor=actor,
        case_version_id=None,
        run_id=None,
        turn_id=None,
        correlation_id=f"correlation:{key}",
        parent_operation_id=None,
    )


@contextmanager
def local_application(settings, reviewer_password: str | None = None):
    reviewer = (
        None
        if reviewer_password is None
        else authenticate_reviewer(settings.data_root, reviewer_password)
    )
    actor = reviewer or ActorRef(
        actor_id="service:local_c05", actor_kind="SERVICE", authenticated_session_ref=None
    )
    prefixes = (
        frozenset({"review."})
        if reviewer is not None
        else frozenset(
            {
                "snapshot.",
                "profile.",
                "intake.",
                "extraction.",
                "normalization.",
                "calculation.",
                "report.",
                "graph.",
            }
        )
    )
    authority = LocalAuthority({"dispatcher": TrustedPrincipal(actor, prefixes)})
    capability = authority.issue("dispatcher")
    blobs = BlobStore(settings.data_root)
    database = settings.data_root / "application.sqlite"
    kernel = AuditKernel(database, blobs, authority=authority)
    try:
        catalog = ArtifactCatalog(database, blobs, kernel=kernel)
        service = CaseService(SnapshotStore(kernel, catalog), ProfileStore(kernel, catalog))
        yield service, command_context(actor), capability
    finally:
        authority.revoke(capability)
        kernel.close()


@contextmanager
def local_review_application(settings, password: str):
    """Authenticated human review with a separate server-owned publication grant."""
    human = authenticate_reviewer(settings.data_root, password)
    actor = ActorRef(
        actor_id="service:local_c05", actor_kind="SERVICE", authenticated_session_ref=None
    )
    authority = LocalAuthority(
        {
            "service": TrustedPrincipal(actor, frozenset({"snapshot.", "profile."})),
            "human": TrustedPrincipal(human, frozenset({"review."})),
        }
    )
    service_cap, human_cap = authority.issue("service"), authority.issue("human")
    blobs = BlobStore(settings.data_root)
    database = settings.data_root / "application.sqlite"
    kernel = AuditKernel(database, blobs, authority=authority)
    try:
        catalog = ArtifactCatalog(database, blobs, kernel=kernel)
        cases = CaseService(SnapshotStore(kernel, catalog), ProfileStore(kernel, catalog))
        yield cases, command_context(human), human_cap, actor, service_cap
    finally:
        authority.revoke(service_cap)
        authority.revoke(human_cap)
        kernel.close()
