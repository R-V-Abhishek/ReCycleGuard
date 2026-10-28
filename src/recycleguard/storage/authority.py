"""Process-local capabilities issued by trusted application composition, not model JSON.

The caller must authenticate humans before configuring their principal/session here.
This is an application boundary, not an OS sandbox or portal authorization service.
"""

from dataclasses import dataclass

from recycleguard.contracts.core import ActorRef

EVENT_ROLES = {
    "cp0.": {"SERVICE", "EVALUATOR"},
    "intake.": {"SERVICE"},
    "extraction.": {"SERVICE"},
    "normalization.": {"SERVICE"},
    "calculation.": {"SERVICE"},
    "snapshot.": {"SERVICE"},
    "profile.": {"SERVICE"},
    "review.": {"HUMAN"},
    "graph.": {"SERVICE", "MODEL_PROPOSAL"},
    "report.": {"SERVICE"},
    "export.": {"SERVICE", "HUMAN"},
    "evaluation.": {"EVALUATOR"},
}


class AuthorizationError(ValueError):
    pass


@dataclass(frozen=True)
class TrustedPrincipal:
    actor: ActorRef
    event_prefixes: frozenset[str]

    def __post_init__(self):
        if self.actor.actor_kind == "HUMAN" and self.actor.authenticated_session_ref is None:
            raise AuthorizationError("human principal requires a trusted authenticated session")
        if not self.event_prefixes or any(
            prefix not in EVENT_ROLES or self.actor.actor_kind not in EVENT_ROLES[prefix]
            for prefix in self.event_prefixes
        ):
            raise AuthorizationError("unknown or prohibited capability prefix")


class Capability:
    """Opaque handle; reconstructing this object does not recreate a valid grant."""


class LocalAuthority:
    def __init__(self, principals: dict[str, TrustedPrincipal] | None = None):
        self._principals = dict(principals or {})
        self._grants: dict[Capability, TrustedPrincipal] = {}

    def issue(self, principal_key: str) -> Capability:
        """Trusted dispatcher only. This factory must never be exposed as a model tool."""
        principal = self._principals[principal_key]
        capability = Capability()
        self._grants[capability] = principal
        return capability

    def revoke(self, capability: Capability):
        self._grants.pop(capability, None)

    def check(self, capability: Capability | None, actor: ActorRef, event_type: str):
        principal = self._grants.get(capability)
        if principal is None or principal.actor != actor:
            raise AuthorizationError("missing, revoked or mismatched trusted capability")
        if not any(event_type.startswith(prefix) for prefix in principal.event_prefixes):
            raise AuthorizationError("event is not permitted by this capability")
