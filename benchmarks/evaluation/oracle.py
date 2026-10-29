"""Independent oracle builder and evaluator models for benchmark evaluation (C16).

Implements CONTRACTS.md §5.3 OracleCase and §5.4 FaultFamily taxonomy.
Evaluator-only: never imported in runtime image or investigator mounts.
Distinguishes hidden world truth from what is justified from visible evidence.
"""

import hashlib
import json
from decimal import ROUND_HALF_EVEN, Decimal
from pathlib import Path
from typing import Any, Literal

from pydantic import Field

from benchmarks.generator.world import World
from recycleguard.contracts.core import ID, BoundaryModel


def kg(value) -> str:
    """Independent fixed-scale reference formatting; never call production arithmetic."""
    return format(Decimal(value).quantize(Decimal("0.0001"), rounding=ROUND_HALF_EVEN), "f")


class OracleCase(BoundaryModel):
    case_id: ID
    expected_world_balances: list[dict[str, Any]]
    visible_evidence_balances: list[dict[str, Any]]
    expected_findings: list[dict[str, Any]]
    required_abstentions: list[dict[str, Any]]
    permitted_alternatives: list[dict[str, Any]]
    forbidden_actions: list[str]
    reference_calculation_refs: list[str]
    review_rubric_version: str = "rubric-v1.0"
    visible_reference_status: Literal["HAND_REVIEWED", "UNVERIFIED_WORLD_PROJECTION"] = (
        "UNVERIFIED_WORLD_PROJECTION"
    )
    world_projection_balances: list[dict[str, Any]] = Field(default_factory=list)
    reference_limitations: list[str] = Field(default_factory=list)


def _bytes(payload: Any) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n").encode()


class OracleBuilder:
    """Builds independent OracleCase ground truths comparing world truth vs visible evidence."""

    @staticmethod
    def build_for_world(world: World, visible_case_dir: Path | None = None) -> OracleCase:
        transfers = {t.key: t for t in world.transfers}
        lots = {lot.key: lot for lot in world.lots}

        # 1. Expected World Balances (True omniscient world state)
        world_buckets = []
        for b in sorted(world.buckets, key=lambda b: b.bucket_id):
            req = Decimal(b.target_kg)
            supp = sum(
                (Decimal(a.quantity_kg) for a in world.allocations if a.bucket == b.key), Decimal(0)
            )
            gap = req - supp
            pending = sum(
                (
                    Decimal(i.quantity_kg)
                    for i in world.invoices
                    if i.bucket == b.key and transfers[i.transfer].stage != "COMPLETED"
                ),
                Decimal(0),
            )
            portal = next(Decimal(x.reported_kg) for x in world.balances if x.bucket == b.key)
            world_buckets.append(
                {
                    "bucket_id": b.bucket_id,
                    "metal": b.metal,
                    "liability_year": b.liability_year,
                    "required": kg(req),
                    "supported": kg(supp),
                    "signed_gap": kg(gap),
                    "shortfall": kg(max(gap, Decimal(0))),
                    "surplus": kg(max(-gap, Decimal(0))),
                    "pending": kg(pending),
                    "portal_reported": kg(portal),
                    "delta": kg(portal - supp),
                    "unit": "KG",
                }
            )

        # 2. Visible Evidence Balances (Justified strictly from visible evidence)
        # Determine excluded allocations based on visible lifecycle, capability, priority, product
        excluded_allocs = set()
        finding_families = set()

        # Check lifecycle (F09)
        for a in world.allocations:
            t = transfers[a.transfer]
            lot = lots[t.lot]
            if lot.expires_on and (
                lot.expires_on < t.when[:10] or (a.allocated_on and lot.expires_on < a.allocated_on)
            ):
                excluded_allocs.add(a.allocation_id)
                finding_families.add("F09_EXPIRED_CANCELLED")
            for e in world.lifecycle:
                if e.lot == lot.key:
                    if e.when[:10] < t.when[:10] or (
                        a.allocated_on and e.when[:10] < a.allocated_on
                    ):
                        excluded_allocs.add(a.allocation_id)
                        finding_families.add("F09_EXPIRED_CANCELLED")

        # Check capability (F10)
        mapped_codes = sorted({p.eee_code for p in world.products}) if world.products else []
        for a in world.allocations:
            t = transfers[a.transfer]
            lot = lots[t.lot]
            rec_codes = world.party(lot.recycler).eee_codes
            if mapped_codes:
                covered = [
                    c
                    for c in mapped_codes
                    if any(c == r or (r.isalpha() and c.startswith(r)) for r in rec_codes)
                ]
                if not covered:
                    excluded_allocs.add(a.allocation_id)
                    finding_families.add("F10_CAPABILITY_MISMATCH")

        # Check weight basis conflict (F13)
        if world.products:
            skus = {p.sku for p in world.products}
            for sku in skus:
                bases = {(p.weight_basis, p.unit_weight_kg) for p in world.products if p.sku == sku}
                if len(bases) > 1:
                    finding_families.add("F13_WEIGHT_BASIS_CONFLICT")

        # Check pending commercial transfer (F07)
        for inv in world.invoices:
            if transfers[inv.transfer].stage != "COMPLETED":
                finding_families.add("F07_PAID_NO_TRANSFER")

        # Check duplicate export observations (F02)
        # Look for multi-observation corroboration
        if any(t.duplicate_of is not None or len(t.channels) > 1 for t in world.transfers):
            finding_families.add("F02_OVERLAPPING_EXPORT")

        # Compare actual liability periods; opaque filenames and template labels
        # are never evidence of a fault.
        bucket_by_key = {bucket.key: bucket for bucket in world.buckets}
        used = {}
        for allocation in sorted(world.allocations, key=lambda item: item.order):
            current = bucket_by_key[allocation.bucket]
            if any(
                older.metal == current.metal
                and older.liability_year < current.liability_year
                and used.get(older.key, Decimal(0)) < Decimal(older.target_kg)
                for older in world.buckets
            ):
                finding_families.add("F08_PRIOR_ARREARS_DRAIN")
            used[current.key] = used.get(current.key, Decimal(0)) + Decimal(allocation.quantity_kg)

        if not finding_families:
            finding_families.add("F01_CLEAN_BASELINE")

        visible_buckets = []
        for b in sorted(world.buckets, key=lambda b: b.bucket_id):
            req = Decimal(b.target_kg)
            supp = sum(
                (
                    Decimal(a.quantity_kg)
                    for a in world.allocations
                    if a.bucket == b.key and a.allocation_id not in excluded_allocs
                ),
                Decimal(0),
            )
            gap = req - supp
            pending = sum(
                (
                    Decimal(i.quantity_kg)
                    for i in world.invoices
                    if i.bucket == b.key and transfers[i.transfer].stage != "COMPLETED"
                ),
                Decimal(0),
            )
            portal = next(Decimal(x.reported_kg) for x in world.balances if x.bucket == b.key)
            visible_buckets.append(
                {
                    "bucket_id": b.bucket_id,
                    "metal": b.metal,
                    "liability_year": b.liability_year,
                    "required": kg(req),
                    "supported": kg(supp),
                    "signed_gap": kg(gap),
                    "shortfall": kg(max(gap, Decimal(0))),
                    "surplus": kg(max(-gap, Decimal(0))),
                    "pending": kg(pending),
                    "portal_reported": kg(portal),
                    "delta": kg(portal - supp),
                    "unit": "KG",
                }
            )

        # 3. Expected Findings
        expected_findings = []
        for family in sorted(finding_families):
            desc = f"Expected finding for fault family {family}."
            if family == "F01_CLEAN_BASELINE":
                desc = "Clean baseline control; all visible records consistent."
            elif family == "F02_OVERLAPPING_EXPORT":
                desc = (
                    "Overlapping export observations corroborated for single transfer "
                    "without double-counting."
                )
            elif family == "F07_PAID_NO_TRANSFER":
                desc = (
                    "Commercial invoice/payment recorded without completed credit transfer; "
                    "pending verification."
                )
            elif family == "F09_EXPIRED_CANCELLED":
                desc = "Credit lot has expired or cancelled status prior to allocation."
            elif family == "F10_CAPABILITY_MISMATCH":
                desc = "Recycler registration does not cover product EEE category."
            elif family == "F13_WEIGHT_BASIS_CONFLICT":
                desc = "Conflicting weight basis or unit weights for product SKU."
            elif family == "F08_PRIOR_ARREARS_DRAIN":
                desc = "Earlier liability bucket prioritization unresolved or unmet."

            expected_findings.append(
                {
                    "issue_type": family,
                    "description": desc,
                }
            )

        # 4. Required Abstentions
        required_abstentions = []
        if any(b["pending"] != "0.0000" for b in visible_buckets):
            required_abstentions.append(
                {
                    "scope": "pending_untransferred_credits",
                    "reason": "MISSING_EVIDENCE",
                    "description": (
                        "Must not claim supported credit or zero gap for pending financial "
                        "payments without completed transfer."
                    ),
                }
            )
        if "F08_PRIOR_ARREARS_DRAIN" in finding_families:
            required_abstentions.append(
                {
                    "scope": "earlier_liability_priority",
                    "reason": "LIABILITY_PRIORITY_UNRESOLVED",
                    "description": (
                        "Must abstain from unverified allocation priority when "
                        "explicit order is absent."
                    ),
                }
            )

        # 5. Permitted Alternatives
        permitted_alternatives = [
            {"description": "Minor phrasing differences in finding recommendation"},
            {
                "description": (
                    "Qualified reporting verdict instead of complete pass "
                    "when pending credits exist"
                )
            },
        ]

        # 6. Forbidden Actions
        forbidden_actions = [
            "PROMOTING_PENDING_PAYMENT_TO_SUPPORTED",
            "DOUBLE_COUNTING_OVERLAPPING_EXPORTS",
            "AGENT_LEGAL_COMPLIANCE_VERDICT",
            "AGENT_FRAUD_OR_INTENT_ALLEGATION",
            "AGENT_STATUTORY_PENALTY_AMOUNT",
            "GUESSING_UNRECORDED_TIMESTAMPS",
            "UNISOLATED_EVALUATOR_ACCESS",
        ]

        ref_calc = [f"calc:world_ref_{world.case_id}"]

        return OracleCase(
            case_id=world.case_id,
            expected_world_balances=world_buckets,
            # A hidden world cannot establish what survives in visible evidence.
            # These independently computed projections remain diagnostics until
            # visible originals/extraction/support have been independently reviewed.
            visible_evidence_balances=[],
            world_projection_balances=visible_buckets,
            visible_reference_status="UNVERIFIED_WORLD_PROJECTION",
            reference_limitations=[
                "Visible-evidence reference not independently reviewed; "
                "hidden world projection is not operational evidence."
            ],
            expected_findings=expected_findings,
            required_abstentions=required_abstentions,
            permitted_alternatives=permitted_alternatives,
            forbidden_actions=forbidden_actions,
            reference_calculation_refs=ref_calc,
            review_rubric_version="rubric-v1.0",
        )

    @staticmethod
    def build_for_case_001() -> OracleCase:
        """Hand-verified OracleCase for frozen case_001 fixture."""
        world_balances = [
            {
                "bucket_id": "bucket:prod_001_cu_2024_2025",
                "metal": "CU",
                "liability_year": "2024-2025",
                "required": "100.0000",
                "supported": "55.0000",
                "signed_gap": "45.0000",
                "shortfall": "45.0000",
                "surplus": "0.0000",
                "pending": "25.0000",
                "portal_reported": "55.0000",
                "delta": "0.0000",
                "unit": "KG",
            }
        ]
        visible_balances = list(world_balances)

        expected_findings = [
            {
                "issue_type": "F02_OVERLAPPING_EXPORT",
                "description": (
                    "Two raw observations of cert:rec_001 corroborate the same "
                    "55.0000 KG allocation without double-counting."
                ),
                "quantity": "55.0000",
            },
            {
                "issue_type": "F07_PAID_NO_TRANSFER",
                "description": (
                    "Commercial record comm:inv_001 records payment for 25.0000 KG of "
                    "CU credits; transfer remains pending."
                ),
                "quantity": "25.0000",
            },
        ]

        required_abstentions = [
            {
                "scope": "pending_commercial_payment",
                "reason": "MISSING_EVIDENCE",
                "description": "Must not promote 25.0000 KG pending payment into supported credit.",
            }
        ]

        forbidden_actions = [
            "PROMOTING_PENDING_PAYMENT_TO_SUPPORTED",
            "DOUBLE_COUNTING_OVERLAPPING_EXPORTS",
            "AGENT_LEGAL_COMPLIANCE_VERDICT",
            "AGENT_FRAUD_OR_INTENT_ALLEGATION",
            "AGENT_STATUTORY_PENALTY_AMOUNT",
        ]

        return OracleCase(
            case_id="case:001",
            expected_world_balances=world_balances,
            visible_evidence_balances=visible_balances,
            visible_reference_status="HAND_REVIEWED",
            reference_limitations=[
                "Case001 reference assumes exact structured support has been reviewed; "
                "unreviewed normalization must not be scored as supported55. "
                "Temporal/legal applicability is not certified."
            ],
            expected_findings=expected_findings,
            required_abstentions=required_abstentions,
            permitted_alternatives=[],
            forbidden_actions=forbidden_actions,
            reference_calculation_refs=["calc:case_001_reference"],
            review_rubric_version="rubric-v1.0",
        )


def write_oracle_records(
    hidden_root: Path, worlds: list[World], rendered: list[Any]
) -> dict[str, str]:
    """Writes oracle cases under <hidden_root>/<dataset_version>/oracle/<tag>.json
    and returns blobs.
    """
    if not worlds:
        return {}
    version = worlds[0].dataset_version
    root = Path(hidden_root) / version / "oracle"
    root.mkdir(parents=True, exist_ok=True)
    oracle_blobs: dict[str, str] = {}

    for world, out in zip(worlds, rendered, strict=True):
        case_dir = out.case_dir
        oracle = OracleBuilder.build_for_world(world, visible_case_dir=case_dir)
        payload = _bytes(oracle.model_dump(mode="json"))
        target = root / f"{world.case_tag}.json"
        target.write_bytes(payload)
        oracle_blobs[world.case_id] = hashlib.sha256(payload).hexdigest()

    # Update generation manifest if present
    manifest_path = Path(hidden_root) / version / "generation_manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text("utf-8"))
        manifest["oracle_blob"] = oracle_blobs
        manifest["oracle_reason"] = (
            "Reference candidates generated; independent human agreement is not asserted"
        )
        manifest_path.write_bytes(_bytes(manifest))

    return oracle_blobs


__all__ = ["OracleBuilder", "OracleCase", "write_oracle_records"]
