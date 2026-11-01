"""Evaluator-only checks binding independently authored agent review annotations.

This module does not manufacture a human attestation. A reviewer supplies exact
allocation dispositions and a case-specific note after inspecting the originals.
Arithmetic is recomputed from original source rows, not world or production tools.
"""

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path


def _mass(value):
    if value["dimension"] != "METAL_MASS" or value["unit"] not in {"KG", "TONNE"}:
        raise ValueError("review requires an explicit metal-mass dimension")
    return Decimal(value["decimal"]) * (1000 if value["unit"] == "TONNE" else 1)


def review_case(
    visible_dir: Path,
    reference_path: Path,
    *,
    allocation_states: dict[str, str],
    expected_families: set[str],
    note: str,
    scope: str,
    reviewer_ref: str,
) -> dict:
    """Validate original-backed arithmetic using explicitly supplied review choices."""
    if not note.strip() or not reviewer_ref.startswith("agent:"):
        raise ValueError("a case-specific agent review annotation is required")
    reference_bytes = reference_path.read_bytes()
    reference = json.loads(reference_bytes)
    manifest = json.loads((visible_dir / "case_manifest.json").read_bytes())
    rows = json.loads((visible_dir / "documents/source_records.json").read_bytes())["source_rows"]
    if reference["case_id"] != manifest["case_id"]:
        raise ValueError("case identity mismatch")
    digest_lines = [
        f"{path.relative_to(visible_dir).as_posix()}\t{hashlib.sha256(path.read_bytes()).hexdigest()}"
        for path in sorted(visible_dir.rglob("*"))
        if path.is_file()
    ]
    input_digest = hashlib.sha256("\n".join(digest_lines).encode()).hexdigest()
    if input_digest != reference["visible_input_digest"]:
        raise ValueError("reference no longer binds inspected originals")
    allocations = {r["allocation_id"]: r for r in rows.values() if "allocation_id" in r}
    if set(allocations) != set(allocation_states):
        raise ValueError("review choices do not cover every original allocation")
    for decision in reference["allocations"]:
        original = rows[decision["source_observation"]]
        if decision["state"] != allocation_states[original["allocation_id"]]:
            raise ValueError("reference disagrees with independent reviewed disposition")
        if Decimal(decision["quantity"]) != _mass(original["quantity"]):
            raise ValueError("reference allocation quantity differs from original")
    buckets = {r["bucket_id"]: r for r in rows.values() if "target" in r and "liability_year" in r}
    statements = {r["bucket_id"]: r for r in rows.values() if "balance_observation_id" in r}
    invoices = [
        r
        for r in rows.values()
        if r.get("record_kind") == "INVOICE"
        and not r["linked_credit_refs"]
        and r["credit_quantity"] is not None
    ]
    numeric_checks = []
    for result in reference["balances"]:
        bucket = buckets[result["bucket_id"]]
        if bucket["adjustments"]:
            raise ValueError("reference review needs explicit nonempty adjustment inspection")
        mine = [r for r in allocations.values() if r["bucket_id"] == result["bucket_id"]]
        required = _mass(bucket["target"])
        supported = sum(
            (
                _mass(r["quantity"])
                for r in mine
                if allocation_states[r["allocation_id"]] == "INCLUDED"
            ),
            Decimal(0),
        )
        pending = sum(
            (
                _mass(r["quantity"])
                for r in mine
                if allocation_states[r["allocation_id"]] == "PENDING"
            ),
            Decimal(0),
        )
        compatible = [b for b in buckets.values() if b["metal"] == bucket["metal"]]
        commercial = [r for r in invoices if r["credit_quantity"]["metal"] == bucket["metal"]]
        if commercial and len(compatible) != 1:
            raise ValueError("unlinked commercial claim cannot be assigned to a liability year")
        pending += sum((_mass(r["credit_quantity"]) for r in commercial), Decimal(0))
        portal = _mass(statements[result["bucket_id"]]["reported_supported"])
        expected = dict(
            required=required,
            supported=supported,
            pending=pending,
            signed_gap=required - supported,
            shortfall=max(required - supported, Decimal(0)),
            surplus=max(supported - required, Decimal(0)),
            portal_reported=portal,
            delta=portal - supported,
        )
        if any(Decimal(result[field]) != amount for field, amount in expected.items()):
            raise ValueError("independent original-backed arithmetic disagrees")
        numeric_checks.append(
            {"bucket_id": result["bucket_id"], "fields_checked": list(expected), "status": "PASS"}
        )
    actual = {finding["issue_type"] for finding in reference["findings"]}
    if actual != expected_families:
        raise ValueError("findings disagree with independently inspected recipe evidence")
    scopes = {item["scope"] for item in reference["abstentions"]}
    required_scopes = {
        "F02_OVERLAPPING_EXPORT": "pending_untransferred_credits",
        "F06_STALE_SNAPSHOT": "stale_portal_statement",
        "F07_PAID_NO_TRANSFER": "pending_untransferred_credits",
        "F08_PRIOR_ARREARS_DRAIN": "earlier_liability_priority",
        "F09_EXPIRED_CANCELLED": "undated_history",
        "F11_WRONG_PERIOD_RULE": "rule_version_applied",
        "F12_UNSEEN_NOTICE_LEAD": "deadline_extension",
        "F13_WEIGHT_BASIS_CONFLICT": "weight_basis_selection",
        "F14_OUT_OF_SCOPE_REGIME": "gold_offset_credits",
        "F15_EXTRACTION_PAGE_LOSS": "lost_document_page",
    }
    for family, expected_scope in required_scopes.items():
        if family in expected_families and expected_scope not in scopes:
            raise ValueError("reference omits required evidence-limited abstention")
    return {
        "case_id": manifest["case_id"],
        "visible_input_digest": input_digest,
        "reference_sha256": hashlib.sha256(reference_bytes).hexdigest(),
        "reviewer_ref": reviewer_ref,
        "reviewer_kind": "CODING_AGENT",
        "human_review_performed": False,
        "review_scope": scope,
        "recorded_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "status": "AGENT_REVIEWED_WITH_LIMITATIONS",
        "case_specific_observation": note,
        "allocation_dispositions_reviewed": allocation_states,
        "numeric_checks": numeric_checks,
        "finding_families_reviewed": sorted(actual),
        "abstention_scopes_reviewed": sorted(scopes),
        "source_locators": [
            f"documents/source_records.json#/source_rows/{identifier}" for identifier in rows
        ],
        "original_files_bound": reference["evidence_inventory"],
        "limitations": [
            "Independent coding-agent inspection and original-backed arithmetic; not human review.",
            "PDF inspection used extracted text and page-count clues; not expert legal review.",
            "Supplied allocation quantities retain all UNKNOWN lifecycle/priority qualifications.",
            "Pending ambiguous claims are exposure categories, not additive economic credit.",
            "No held-out model trial or performance scoring was performed "
            "during oracle validation.",
        ],
    }
