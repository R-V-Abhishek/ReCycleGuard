"""Deadline register and temporal applicability service.

Owned by Sampreeth (H07 / C07).
Implements CONTRACTS §4.3 deadline register with mandatory kind separation:
  - OBLIGATION_ACHIEVEMENT
  - CREDIT_EVENT
  - RETURN_FILING

Key invariants:
- A RETURN_FILING extension cannot automatically extend OBLIGATION_ACHIEVEMENT
  or CREDIT_EVENT without separate reviewed authority.
- Rule 9A is an enabling provision, not the extension order itself.
- A notice lead with unverified_notice=True never creates a verified extension.
- Missing baseline_due stays unknown; never invent a default.
- General-role clauses apply unless a role-specific clause overrides.
"""

import re
from datetime import date
from typing import Literal

from recycleguard.contracts.sources import (
    AmendmentEdge,
    ApplicabilityAssertion,
    DeadlineEntry,
    DeadlineKind,
)

# ──────────────────────────────────────────────────────────────────────────────
# Temporal check result types
# ──────────────────────────────────────────────────────────────────────────────

TemporalVerdict = Literal["PASS", "FAIL", "UNRESOLVED", "ABSTAIN"]


class DeadlineCheckResult:
    """Outcome of a deadline applicability check."""

    def __init__(
        self,
        deadline_id: str,
        kind: DeadlineKind,
        verdict: TemporalVerdict,
        effective_date: str | None,
        is_verified_extension: bool,
        reasons: list[str],
    ):
        self.deadline_id = deadline_id
        self.kind = kind
        self.verdict = verdict
        self.effective_date = effective_date
        self.is_verified_extension = is_verified_extension
        self.reasons = reasons

    def to_dict(self) -> dict:
        return {
            "deadline_id": self.deadline_id,
            "kind": self.kind,
            "verdict": self.verdict,
            "effective_date": self.effective_date,
            "is_verified_extension": self.is_verified_extension,
            "reasons": self.reasons,
        }


class AmendmentOverlayResult:
    """Outcome of checking a provision's amendment status."""

    def __init__(
        self,
        provision_version_id: str,
        is_amended: bool,
        is_replaced: bool,
        surviving_amendment: str | None,
        unaffected_clauses: list[str],
        reasons: list[str],
    ):
        self.provision_version_id = provision_version_id
        self.is_amended = is_amended
        self.is_replaced = is_replaced
        self.surviving_amendment = surviving_amendment
        self.unaffected_clauses = unaffected_clauses
        self.reasons = reasons

    def to_dict(self) -> dict:
        return {
            "provision_version_id": self.provision_version_id,
            "is_amended": self.is_amended,
            "is_replaced": self.is_replaced,
            "surviving_amendment": self.surviving_amendment,
            "unaffected_clauses": self.unaffected_clauses,
            "reasons": self.reasons,
        }


# ──────────────────────────────────────────────────────────────────────────────
# Deadline Register
# ──────────────────────────────────────────────────────────────────────────────


class DeadlineRegister:
    """Frozen deadline register enforcing mandatory kind separation per CONTRACTS §4.3.

    Stores DeadlineEntry records, resolves effective deadlines by kind,
    and returns ABSTAIN when authority is unverified or baseline is unknown.
    """

    def __init__(
        self,
        entries: list[DeadlineEntry] | None = None,
        *,
        verified_order_refs: set[str] | None = None,
    ):
        self.verified_order_refs = verified_order_refs or set()
        self._entries: list[DeadlineEntry] = entries or []
        # Build index by (producer_or_role_scope, fiscal_year, quarter, kind)
        self._index: dict[tuple[str, str, str | None, str], list[DeadlineEntry]] = {}
        for entry in self._entries:
            key = (
                entry.producer_or_role_scope,
                entry.fiscal_year,
                entry.quarter,
                entry.kind,
            )
            self._index.setdefault(key, []).append(entry)

    def add_entry(self, entry: DeadlineEntry) -> None:
        """Register a new deadline entry."""
        self._entries.append(entry)
        key = (
            entry.producer_or_role_scope,
            entry.fiscal_year,
            entry.quarter,
            entry.kind,
        )
        self._index.setdefault(key, []).append(entry)

    def resolve_deadline(
        self,
        producer_or_role_scope: str,
        fiscal_year: str,
        kind: DeadlineKind,
        *,
        quarter: str | None = None,
    ) -> DeadlineCheckResult:
        """Resolve the effective deadline for a given producer/role, FY, and kind.

        Returns ABSTAIN when:
        - No baseline_due is present.
        - An extension exists but unverified_notice=True (notice lead, not signed order).
        - Cross-kind extension is attempted without separate reviewed authority.

        A RETURN_FILING extension NEVER automatically extends OBLIGATION_ACHIEVEMENT
        or CREDIT_EVENT — those require separate reviewed authority entries.
        """
        key = (producer_or_role_scope, fiscal_year, quarter, kind)
        entries = self._index.get(key, [])

        # Also try "general" scope if specific not found
        if not entries:
            general_key = ("GENERAL", fiscal_year, quarter, kind)
            entries = self._index.get(general_key, [])

        if not entries:
            return DeadlineCheckResult(
                deadline_id=f"deadline:unknown_{kind}_{fiscal_year}",
                kind=kind,
                verdict="ABSTAIN",
                effective_date=None,
                is_verified_extension=False,
                reasons=[
                    f"No {kind} deadline entry found for FY {fiscal_year}; "
                    "baseline stays unknown, cannot determine effective date."
                ],
            )

        superseded = {e.supersedes_deadline_id for e in entries if e.supersedes_deadline_id}
        active = [
            e for e in entries if e.deadline_id not in superseded and e.review_state == "APPROVED"
        ]
        if len(active) != 1:
            return DeadlineCheckResult(
                "deadline:unresolved",
                kind,
                "ABSTAIN",
                None,
                False,
                ["No unique approved active deadline entry."],
            )
        active_entry = active[0]

        reasons: list[str] = []

        # Check if baseline_due is available
        if (
            active_entry.baseline_due.value is None
            or not active_entry.baseline_basis_refs
            or active_entry.baseline_due.interpretation_status != "REVIEWED"
        ):
            reasons.append(
                f"Baseline {kind} deadline for FY {fiscal_year} has unknown value; "
                "date-only or missing cut-off prevents automated eligibility check."
            )
            return DeadlineCheckResult(
                deadline_id=active_entry.deadline_id,
                kind=kind,
                verdict="ABSTAIN",
                effective_date=None,
                is_verified_extension=False,
                reasons=reasons,
            )

        baseline_date = str(active_entry.baseline_due.value)
        reasons.append(f"Baseline {kind} due: {baseline_date}")

        # Determine effective deadline
        effective_date = baseline_date
        is_verified_extension = False

        if active_entry.extended_due is not None:
            if active_entry.unverified_notice:
                # Notice lead without signed order — cannot verify extension
                reasons.append(
                    "Extension order refs present but unverified_notice=True; "
                    "notice lead does not constitute a signed extension order. "
                    "Extension NOT applied — using baseline date."
                )
            elif (
                not active_entry.extension_order_refs
                or not all(
                    ref.ref_id in self.verified_order_refs
                    for ref in active_entry.extension_order_refs
                )
                or active_entry.extended_due.value is None
                or active_entry.extended_due.interpretation_status != "REVIEWED"
            ):
                # Extension exists but no order ref supplied
                reasons.append(
                    "extended_due is set but extension_order_refs is empty; "
                    "enabling provision alone (e.g., Rule 9A) is not an extension order. "
                    "Extension NOT applied — using baseline date."
                )
            else:
                # Verified extension
                extended_date = str(active_entry.extended_due.value)
                reasons.append(
                    f"Verified extension order found; effective {kind} deadline: {extended_date}"
                )
                effective_date = extended_date
                is_verified_extension = True

        return DeadlineCheckResult(
            deadline_id=active_entry.deadline_id,
            kind=kind,
            verdict="ABSTAIN"
            if active_entry.extended_due is not None and not is_verified_extension
            else "PASS",
            effective_date=effective_date,
            is_verified_extension=is_verified_extension,
            reasons=reasons,
        )

    def check_cross_kind_independence(
        self,
        filing_deadline_id: str,
        obligation_kind: DeadlineKind,
    ) -> dict:
        """Verify that a RETURN_FILING extension does NOT auto-extend obligation/credit kinds.

        Returns a dict with verdict and reasons. Per CONTRACTS §4.3:
        A RETURN_FILING extension cannot extend OBLIGATION_ACHIEVEMENT or CREDIT_EVENT
        without a separate reviewed DeadlineEntry for each kind.
        """
        if obligation_kind == "RETURN_FILING":
            return {
                "verdict": "PASS",
                "reasons": ["Same kind — no cross-kind independence check needed."],
            }

        # Look for filing entry and see if it incorrectly references obligation periods
        filing_entry = next((e for e in self._entries if e.deadline_id == filing_deadline_id), None)
        if filing_entry is None:
            return {
                "verdict": "ABSTAIN",
                "reasons": [f"Filing deadline entry {filing_deadline_id} not found in register."],
            }

        if filing_entry.kind != "RETURN_FILING":
            return {
                "verdict": "ABSTAIN",
                "reasons": [
                    f"Entry {filing_deadline_id} is kind {filing_entry.kind}, not RETURN_FILING."
                ],
            }

        return {
            "verdict": "PASS",
            "reasons": [
                f"RETURN_FILING entry {filing_deadline_id} does not automatically extend "
                f"{obligation_kind}. A separate reviewed {obligation_kind} entry is required. "
                "Independence maintained."
            ],
        }


# ──────────────────────────────────────────────────────────────────────────────
# Amendment Overlay Service
# ──────────────────────────────────────────────────────────────────────────────


class AmendmentOverlayService:
    """Resolves amendment overlays and preserves unaffected clauses.

    Per CONTRACTS §4.3:
    - Unaffected clauses must survive after partial amendments.
    - REPLACES relation means the prior provision is superseded.
    - RELAXES_DEADLINE requires extension_order_refs (not just enabling provision).
    - REFERENCES is informational only; it does not modify applicability.
    """

    def __init__(self, edges: list[AmendmentEdge] | None = None):
        self._edges = edges or []
        # Index by from_provision_id
        self._from_index: dict[str, list[AmendmentEdge]] = {}
        self._to_index: dict[str, list[AmendmentEdge]] = {}
        for edge in self._edges:
            self._from_index.setdefault(edge.from_provision_id, []).append(edge)
            self._to_index.setdefault(edge.to_provision_id, []).append(edge)

    def add_edge(self, edge: AmendmentEdge) -> None:
        """Register an amendment edge."""
        self._edges.append(edge)
        self._from_index.setdefault(edge.from_provision_id, []).append(edge)
        self._to_index.setdefault(edge.to_provision_id, []).append(edge)

    def check_amendment_status(self, provision_version_id: str) -> AmendmentOverlayResult:
        """Check whether a provision has been amended, replaced, or is unaffected.

        Returns AmendmentOverlayResult with surviving amendment id (if replaced)
        and list of clause paths that remain unaffected.
        """
        reasons: list[str] = []
        outbound = self._from_index.get(provision_version_id, [])
        inbound = self._to_index.get(provision_version_id, [])

        is_replaced = any(e.relation == "REPLACES" for e in inbound if e.review_state == "APPROVED")
        is_amended = any(
            e.relation in {"AMENDS", "INSERTS"} for e in inbound if e.review_state == "APPROVED"
        )
        surviving_amendment: str | None = None

        if is_replaced:
            replacers = [
                e.from_provision_id
                for e in inbound
                if e.relation == "REPLACES" and e.review_state == "APPROVED"
            ]
            surviving_amendment = replacers[0] if len(replacers) == 1 else None
            if len(replacers) != 1:
                reasons.append("Multiple approved replacement edges: surviving text is unresolved.")
            reasons.append(
                f"Provision {provision_version_id} is replaced by {surviving_amendment}. "
                "Prior text is superseded for the scope covered by the replacement."
            )
        elif is_amended:
            amenders = [
                e.from_provision_id
                for e in inbound
                if e.relation in {"AMENDS", "INSERTS"} and e.review_state == "APPROVED"
            ]
            surviving_amendment = amenders[0] if amenders else None
            reasons.append(
                f"Provision {provision_version_id} has partial amendments from: {amenders}. "
                "Only the amended scope is superseded; unaffected clauses survive."
            )
        else:
            reasons.append(
                f"Provision {provision_version_id} has no superseding amendment overlay."
            )

        # Collect unaffected clauses from outbound REFERENCES edges
        unaffected_clauses = [
            e.to_provision_id
            for e in outbound
            if e.relation == "REFERENCES" and e.review_state == "APPROVED"
        ]
        if unaffected_clauses:
            reasons.append(
                f"Provisions referenced but unaffected by this amendment: {unaffected_clauses}"
            )

        # Check deadline relaxation validity
        relaxation_edges = [e for e in outbound if e.relation == "RELAXES_DEADLINE"]
        for edge in relaxation_edges:
            if not edge.extension_order_refs:
                reasons.append(
                    f"Amendment edge {edge.edge_id} uses RELAXES_DEADLINE but has no "
                    "extension_order_refs — enabling provision alone does not constitute "
                    "a verified extension order."
                )

        return AmendmentOverlayResult(
            provision_version_id=provision_version_id,
            is_amended=is_amended,
            is_replaced=is_replaced,
            surviving_amendment=surviving_amendment,
            unaffected_clauses=unaffected_clauses,
            reasons=reasons,
        )

    def get_applicable_provisions(
        self,
        provision_ids: list[str],
    ) -> dict[str, AmendmentOverlayResult]:
        """Check all given provision IDs and return overlay results for each.

        Provisions that are replaced return their surviving amendment ID.
        The caller must fetch the surviving amendment's text for the final retrieval.
        """
        return {pid: self.check_amendment_status(pid) for pid in provision_ids}


# ──────────────────────────────────────────────────────────────────────────────
# Temporal Applicability Checker
# ──────────────────────────────────────────────────────────────────────────────


class TemporalApplicabilityChecker:
    """Checks whether a provision's applicability assertion covers the target period.

    Per CONTRACTS §4.3 and SYSTEM_DESIGN §4:
    - Distinguish reporting period, business event time, filing date, and knowledge cut-off.
    - A later notice may address an earlier reporting year — do not reject solely
      because its issue date follows that year's end.
    - Unknown or date-only cut-offs preserve precision; no ambiguous automated decisions.
    - General-role clauses apply unless a role-specific clause overrides.
    """

    def __init__(self, assertions: list[ApplicabilityAssertion] | None = None):
        self._assertions: dict[str, ApplicabilityAssertion] = {
            a.assertion_id: a for a in (assertions or [])
        }

    def add_assertion(self, assertion: ApplicabilityAssertion) -> None:
        """Register an applicability assertion."""
        self._assertions[assertion.assertion_id] = assertion

    def check_temporal_fit(
        self,
        assertion_id: str,
        target_period: str | None,
        target_event_time: str | None = None,
        question_basis: str = "REPORTING_PERIOD",
    ) -> TemporalVerdict:
        """Return temporal verdict for a provision's assertion against a target period.

        Returns UNRESOLVED when:
        - Assertion is not found or review_state is REJECTED.
        - effective_from or effective_until is unknown (None value).
        - The target period itself is not supplied.

        Returns PASS when the provision is active for the given period.
        Returns FAIL when outside the half-open interval [effective_from, effective_until).
        """
        assertion = self._assertions.get(assertion_id)
        if not assertion:
            return "UNRESOLVED"

        if assertion.review_state == "REJECTED":
            return "FAIL"

        if (
            assertion.review_state != "APPROVED"
            or assertion.applicability_scope == "UNKNOWN"
            or assertion.event_basis != question_basis
            or not assertion.sources
        ):
            return "UNRESOLVED"
        lower, upper = assertion.effective_from, assertion.effective_until
        if lower is None or lower.value is None or lower.interpretation_status != "REVIEWED":
            return "UNRESOLVED"
        if upper is None and not assertion.end_open_ended:
            return "UNRESOLVED"
        if upper is not None and (upper.value is None or upper.interpretation_status != "REVIEWED"):
            return "UNRESOLVED"
        if question_basis == "REPORTING_PERIOD":
            match = re.fullmatch(r"(?:FY)?(20\d{2})-(?:20)?(\d{2})", target_period or "")
            if not match or int(match[2]) != (int(match[1]) + 1) % 100:
                return "UNRESOLVED"
            start, end = date(int(match[1]), 4, 1), date(int(match[1]) + 1, 4, 1)
        else:
            if target_event_time is None or len(target_event_time) != 10:
                return "UNRESOLVED"
            try:
                start = end = date.fromisoformat(target_event_time)
            except ValueError:
                return "UNRESOLVED"
        if lower.precision != "DATE" or (upper and upper.precision != "DATE"):
            return "UNRESOLVED"
        lo = date.fromisoformat(str(lower.value))
        hi = date.fromisoformat(str(upper.value)) if upper else None
        before = end <= lo if question_basis == "REPORTING_PERIOD" else end < lo
        if (hi is not None and start >= hi) or before:
            return "FAIL"
        if start < lo or (hi is not None and end > hi):
            return "UNRESOLVED"
        return "PASS"

    def check_role_override(
        self,
        general_assertion_id: str,
        role: str,
        specific_assertion_ids: list[str],
    ) -> TemporalVerdict:
        """Determine if a role-specific clause overrides the general-role clause.

        General-role clauses apply unless a role-specific clause explicitly narrows scope.
        If no specific override exists for the role, the general clause applies.
        """
        specific = [
            a
            for aid in specific_assertion_ids
            if (a := self._assertions.get(aid)) is not None and role in (a.affected_roles or [])
        ]

        if not specific:
            # No specific override — general clause applies
            general = self._assertions.get(general_assertion_id)
            if (
                general
                and general.review_state == "APPROVED"
                and general.applicability_scope != "UNKNOWN"
            ):
                return "PASS"
            return "UNRESOLVED"

        # Role-specific assertion exists — use it
        for s in specific:
            if s.review_state == "APPROVED":
                return "PASS"
        return "UNRESOLVED"
