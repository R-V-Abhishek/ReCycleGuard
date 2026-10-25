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
        frozenset({"review."}) if reviewer is not None else frozenset({"snapshot.", "profile."})
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
