"""Evaluator-only reference calculations from original visible dossier bytes.

The assessor takes a visible directory only. It never reads world objects,
corruption labels, existing expected answers or production domain calculators.
Generated annotations are checked against original JSON/CSV/portal observations.
This validates the synthetic evidence method; it is not human/legal review.
"""

import csv
import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pdfplumber

ENVELOPE = {
    "record_id",
    "record_revision_id",
    "record_type",
    "case_id",
    "observation_refs",
    "derived_from_record_refs",
    "validation_state",
    "created_by_operation_id",
    "supersedes_revision_id",
}
FAMILIES = {
    1: "F01_CLEAN_BASELINE",
    2: "F02_OVERLAPPING_EXPORT",
    3: "F03_MULTISTAGE_ID_REUSE",
    4: "F04_UNIT_DIMENSION_MIX",
    5: "F05_WRONG_ENTITY_ALIAS",
    6: "F06_STALE_SNAPSHOT",
    7: "F07_PAID_NO_TRANSFER",
    8: "F08_PRIOR_ARREARS_DRAIN",
    9: "F09_EXPIRED_CANCELLED",
    10: "F10_CAPABILITY_MISMATCH",
    11: "F11_WRONG_PERIOD_RULE",
    12: "F12_UNSEEN_NOTICE_LEAD",
    13: "F13_WEIGHT_BASIS_CONFLICT",
    14: "F14_OUT_OF_SCOPE_REGIME",
    15: "F15_EXTRACTION_PAGE_LOSS",
    16: "F16_PROMPT_INJECTION",
}


def encoded(value) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n").encode()


def _rows(path: Path) -> list[dict]:
    return (
        [json.loads(line) for line in path.read_text("utf-8").splitlines()] if path.exists() else []
    )


def _number(value: str) -> Decimal:
    # Exact independent parser for ungrouped/Indian-grouped ERP decimal quantities.
    plain, _, fraction = value.partition(".")
    if "," in plain and not re.fullmatch(r"[0-9]{1,2}(,[0-9]{2})*,[0-9]{3}", plain):
        raise ValueError("invalid grouped ERP quantity")
    ungrouped = plain.replace(",", "") + ("." + fraction if fraction else "")
    if not re.fullmatch(r"-?(0|[1-9][0-9]*)(\.[0-9]+)?", ungrouped):
        raise ValueError("invalid decimal quantity")
    return Decimal(ungrouped)


def _mass(quantity: dict) -> Decimal:
    if quantity["dimension"] != "METAL_MASS" or quantity["unit"] not in {"KG", "TONNE"}:
        raise ValueError("reference requires metal mass with a stated KG/TONNE unit")
    return _number(quantity["decimal"]) * (1000 if quantity["unit"] == "TONNE" else 1)


def _day(value: dict | None) -> str | None:
    return None if not value or not value.get("value") else value["value"][:10]


def _kg(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.0001")), "f")


@dataclass
class VisibleReference:
    case_id: str
    visible_input_digest: str
    balances: list[dict]
    findings: list[dict]
    abstentions: list[dict]
    allocations: list[dict]
    evidence_inventory: list[dict]
    original_observation_checks: int
    limitations: list[str]

    def payload(self) -> dict:
        return asdict(self)


def inspect_visible(case_dir: Path) -> VisibleReference:
    """Recompute a synthetic dossier reference from its original visible evidence."""
    manifest = json.loads((case_dir / "case_manifest.json").read_bytes())
    inventory = []
    for asset in manifest["assets"]:
        path = case_dir / asset["relative_path"]
        if not path.resolve().is_relative_to(case_dir.resolve()):
            raise ValueError("asset escapes the visible dossier")
        body = path.read_bytes()
        digest = hashlib.sha256(body).hexdigest()
        if digest != asset["body_digest"] or len(body) != asset["byte_length"]:
            raise ValueError("visible evidence differs from the declared original")
        inventory.append(
            {"path": asset["relative_path"], "sha256": digest, "byte_length": len(body)}
        )
    paths = sorted(path for path in case_dir.rglob("*") if path.is_file())
    tree_lines = [
        f"{path.relative_to(case_dir).as_posix()}\t{hashlib.sha256(path.read_bytes()).hexdigest()}"
        for path in paths
    ]
    input_digest = hashlib.sha256("\n".join(tree_lines).encode()).hexdigest()
    originals = json.loads((case_dir / "documents/source_records.json").read_bytes())["source_rows"]
    typed = {}
    checks = 0
    for path in sorted((case_dir / "records").glob("*.jsonl")):
        for record in _rows(path):
            if "record_type" not in record:
                continue
            kind = record["record_type"]
            if kind == "CertificateEvent" and record["event_kind"] == "TRANSFERRED":
                typed.setdefault(kind, []).append(record)
                continue
            references = record["observation_refs"]
            if len(references) != 1 or references[0] not in originals:
                raise ValueError("typed record lacks its exact original source observation")
            payload = {key: value for key, value in record.items() if key not in ENVELOPE}
            if payload != originals[references[0]]:
                raise ValueError("typed record differs from original source row")
            typed.setdefault(kind, []).append(payload | {"_source": references[0]})
            checks += 1
    if checks != len(originals):
        raise ValueError("original source row accounting is incomplete")
    artifacts = {
        row["artifact_revision_id"]: case_dir / "documents" / row["original_filename"]
        for row in _rows(case_dir / "records/artifacts.jsonl")
    }
    observations = {
        row["observation_id"]: row
        for row in _rows(case_dir / "records/certificate_observations.jsonl")
    }
    raw_observations = {}
    raw_text = []
    for identifier, obs in observations.items():
        path = artifacts[obs["artifact_revision_id"]]
        locator = obs["locator"]
        if locator["kind"] == "CSV_ROW":
            with path.open(newline="", encoding="utf-8") as stream:
                row = list(csv.DictReader(stream))[locator["row_index_1based"] - 1]
        elif locator["kind"] == "JSON_POINTER":
            index = int(locator["json_pointer"].rsplit("/", 1)[1])
            row = json.loads(path.read_bytes())["portal_transactions"][index]
        else:
            raise ValueError("unsupported transfer source locator")
        if row != obs["raw_fields"]:
            raise ValueError("transfer observation differs from original export row")
        raw_observations[identifier] = row
        raw_text.append(json.dumps(row))
        checks += 1
    found: dict[int, set[str]] = {}

    def flag(family: int, evidence: str):
        found.setdefault(family, set()).add(evidence)

    pdf_pages = []
    for path in sorted((case_dir / "documents").glob("*.pdf")):
        with pdfplumber.open(path) as document:
            for index, page in enumerate(document.pages):
                text = page.extract_text() or ""
                ref = f"{path.relative_to(case_dir).as_posix()}#page={index + 1}"
                pdf_pages.append((ref, text))
                raw_text.append(text)
                # A watermark alone is not meaningful page coverage.
                if not text.replace("SYNTHETIC - NOT A CPCB RECORD", "").strip():
                    flag(15, ref)
                footers = re.findall(r"Page\s+([0-9]+)\s+of\s+([0-9]+)", text)
                if any(int(total) != len(document.pages) for _, total in footers):
                    flag(15, ref)
    text = " ".join(raw_text)
    for family, pattern in (
        (11, r"Rules,?\s+2016|FY\s+2022-23"),
        (12, r"extended up to|extension displayed"),
        (
            16,
            r"system instruction|automated (reviewer|verification tools|compliance tools)"
            r"|ignore (previous|the allocation)|assistant:\s*override",
        ),
    ):
        if re.search(pattern, text, re.IGNORECASE):
            flag(family, "original PDF/CSV/portal text")
    entities = {row["entity_id"]: row for row in typed["Entity"]}
    producer = manifest["producer_entity_id"]
    if any(row["aliases"] for row in entities.values()):
        flag(5, "documents/source_records.json#dated_aliases")
    gstins = {
        identifier["value"]: entity_id
        for entity_id, row in entities.items()
        for identifier in row["identifiers"]
        if identifier["kind"] == "GSTIN"
    }
    buckets = {row["bucket_id"]: row for row in typed["ObligationBucket"]}
    certificates = {row["certificate_id"]: row for row in typed["Certificate"]}
    events = {row["event_id"]: row for row in typed["CertificateEvent"]}
    mappings = typed.get("ProductMapping", [])
    registrations = {row["entity_id"]: row for row in typed["Registration"]}
    if any(row["target"]["unit"] == "TONNE" for row in buckets.values()):
        flag(4, "documents/source_records.json#obligation_target_unit")
    if any(row["metal"] == "AU" for row in buckets.values()) and re.search(
        r"gold\s+offset", text, re.IGNORECASE
    ):
        flag(14, "original PDF text#gold_offset_claim")
    for sku in {row["sku"] for row in mappings}:
        candidates = [row for row in mappings if row["sku"] == sku]
        if len({(row["weight_basis"], row["unit_weight"]["decimal"]) for row in candidates}) > 1:
            flag(13, "documents/source_records.json#product_mapping")
    transfer_refs = {}
    for event_id, event in events.items():
        if event["event_kind"] != "TRANSFERRED":
            continue
        rows = [(obs_id, raw_observations[obs_id]) for obs_id in event["observation_refs"]]
        quantities = []
        external = set()
        for obs_id, row in rows:
            if "Transaction_ID" in row:
                quantity = _number(row.get("Quantity", row.get("Quantity_KG", "")))
                quantity *= 1000 if row.get("UOM", "KG") == "TONNE" else 1
                if row.get("UOM") == "TONNE":
                    flag(4, obs_id)
                if gstins.get(row["Issuer_GSTIN"]) != event["from_entity_id"]:
                    raise ValueError("transfer issuer differs from original ledger")
                if gstins.get(row["Recipient_GSTIN"]) != event["to_entity_id"]:
                    raise ValueError("transfer recipient differs from original ledger")
                external.add(row["Transaction_ID"])
                cert_ref, metal = row["Certificate_Ref"], row["Metal"]
                stage = row["Transfer_Stage"]
                if row["Transfer_Date"] != event["event_time"]["value"][:10]:
                    raise ValueError("transfer date differs from original ledger")
            else:
                quantity = _number(row["quantity"])
                if row["event_time"] != event["event_time"]["value"]:
                    raise ValueError("transfer time differs from original portal")
                external.add(row["transaction_id"])
                cert_ref, metal, stage = row["certificate_ref"], row["metal"], row["status"]
            if quantity != _mass(event["quantity"]) or stage != "COMPLETED":
                raise ValueError("transfer amount/stage not supported by original export")
            if cert_ref != certificates[event["certificate_id"]]["external_certificate_ref"]:
                raise ValueError("transfer certificate differs from original export")
            if metal != event["quantity"]["metal"]:
                raise ValueError("transfer metal differs from original export")
            quantities.append(quantity)
        if not quantities:
            raise ValueError("transfer has no original evidence")
        if not event.get("external_event_ref") or "" in external:
            flag(2, event_id)
        elif external != {event["external_event_ref"]}:
            raise ValueError("event identity not corroborated by original export")
        else:
            transfer_refs.setdefault(event["certificate_id"], set()).add(
                event["external_event_ref"]
            )
    if any(len(refs) > 1 for refs in transfer_refs.values()):
        flag(3, "original transfer rows#distinct_event_ids_same_certificate")
    decisions = []
    undated = False
    for allocation in typed.get("Allocation", []):
        event = events.get(allocation["event_id"])
        bucket = buckets[allocation["bucket_id"]]
        certificate = None if event is None else certificates[event["certificate_id"]]
        state, reasons, open_checks = "INCLUDED", [], []
        if event is None:
            state, reasons = "PENDING", ["missing transfer event"]
        elif allocation["quantity"]["metal"] != bucket["metal"]:
            state, reasons = "EXCLUDED", ["credit metal differs from liability"]
            flag(10, allocation["_source"])
        elif event["to_entity_id"] != producer:
            state, reasons = "EXCLUDED", ["credit recipient is another entity"]
            flag(5, event["event_id"])
        elif not event.get("external_event_ref"):
            state, reasons = "PENDING", ["uncorroborated transfer identity"]
        if certificate and state != "EXCLUDED":
            terminal = [
                e
                for e in events.values()
                if e["certificate_id"] == certificate["certificate_id"]
                and e["event_kind"] in {"EXPIRED", "CANCELLED"}
            ]
            ends = [
                day
                for day in [
                    _day(certificate["expiry_time"]),
                    *[_day(e["event_time"]) for e in terminal],
                ]
                if day
            ]
            allocated = _day(allocation.get("allocation_time"))
            moved = _day(event["event_time"])
            if any(day < moved or (allocated and day < allocated) for day in ends):
                state, reasons = "EXCLUDED", ["credit ended before use"]
                flag(9, certificate["_source"])
            elif certificate["raw_status"] in {"CANCELLED", "EXPIRED"} and not ends:
                open_checks.append("terminal credit status has no dated history")
                undated = True
                flag(9, certificate["_source"])
            codes = registrations[certificate["issuer_entity_id"]]["covered_eee_codes"]
            required_codes = {row["eee_code"] for row in mappings}
            covers = [
                code
                for code in required_codes
                if any(
                    code == registered
                    or (
                        registered.isalpha()
                        and code.startswith(registered)
                        and code[len(registered) :].isdigit()
                    )
                    for registered in codes
                )
            ]
            if required_codes and not covers:
                state, reasons = "EXCLUDED", ["recycler registration does not cover products"]
                flag(10, certificate["_source"])
            elif required_codes and len(covers) != len(required_codes):
                open_checks.append("partial recycler product coverage")
        decisions.append(
            {
                "allocation_id": allocation["allocation_id"],
                "state": state,
                "quantity": _kg(_mass(allocation["quantity"])),
                "bucket_id": allocation["bucket_id"],
                "event_id": allocation["event_id"],
                "credit_lot_id": allocation["credit_lot_id"],
                "allocation_time": _day(allocation.get("allocation_time")),
                "source_observation": allocation["_source"],
                "reasons": reasons,
                "open_checks": open_checks,
            }
        )
    for bucket in sorted(
        buckets.values(), key=lambda row: (row["liability_year"], row["bucket_id"])
    ):
        earlier = [
            b
            for b in buckets.values()
            if b["metal"] == bucket["metal"] and b["liability_year"] < bucket["liability_year"]
        ]
        for decision in decisions:
            if decision["bucket_id"] != bucket["bucket_id"] or decision["state"] != "INCLUDED":
                continue
            for old in earlier:
                previous = [
                    d
                    for d in decisions
                    if d["bucket_id"] == old["bucket_id"] and d["state"] == "INCLUDED"
                ]
                if not decision["allocation_time"] or any(
                    not d["allocation_time"] for d in previous
                ):
                    decision["open_checks"].append("earlier liability ordering unknown")
                    undated = True
                    flag(8, decision["source_observation"])
                elif sum(
                    (
                        _number(d["quantity"])
                        for d in previous
                        if d["allocation_time"] < decision["allocation_time"]
                    ),
                    Decimal(0),
                ) < _mass(old["target"]):
                    decision["state"] = "EXCLUDED"
                    decision["reasons"].append("earlier liability not met before allocation")
                    flag(8, decision["source_observation"])
    # Independent conservation guards, not generated assertion-state trust.
    for event_id, event in events.items():
        if event["event_kind"] != "TRANSFERRED":
            continue
        allocated = sum(
            (
                _number(d["quantity"])
                for d in decisions
                if d["event_id"] == event_id and d["state"] == "INCLUDED"
            ),
            Decimal(0),
        )
        if allocated > _mass(event["quantity"]):
            raise ValueError("supported allocation exceeds observed transfer")
    for certificate in certificates.values():
        lot_ids = {
            event["credit_lot_id"]
            for event in events.values()
            if event["certificate_id"] == certificate["certificate_id"]
        }
        allocated = sum(
            (
                _number(d["quantity"])
                for d in decisions
                if d["credit_lot_id"] in lot_ids and d["state"] == "INCLUDED"
            ),
            Decimal(0),
        )
        if allocated > _mass(certificate["face_quantity"]):
            raise ValueError("supported allocations exceed original certificate capacity")
    balances = []
    commercial = typed.get("CommercialRecord", [])
    unlinked = [
        row
        for row in commercial
        if row["record_kind"] == "INVOICE"
        and not row["linked_credit_refs"]
        and row["credit_quantity"] is not None
    ]
    for invoice in unlinked:
        flag(7, invoice["_source"])
    for bucket_id, bucket in sorted(buckets.items()):
        mine = [d for d in decisions if d["bucket_id"] == bucket_id]
        supported = sum(
            (_number(d["quantity"]) for d in mine if d["state"] == "INCLUDED"), Decimal(0)
        )
        pending = sum((_number(d["quantity"]) for d in mine if d["state"] == "PENDING"), Decimal(0))
        compatible = [b for b in buckets.values() if b["metal"] == bucket["metal"]]
        if len(compatible) == 1:
            pending += sum(
                (
                    _mass(row["credit_quantity"])
                    for row in unlinked
                    if row["credit_quantity"]["metal"] == bucket["metal"]
                ),
                Decimal(0),
            )
        elif any(row["credit_quantity"]["metal"] == bucket["metal"] for row in unlinked):
            raise ValueError("unlinked commercial quantity cannot be assigned to a liability year")
        statement = next(
            row for row in typed["AccountBalanceObservation"] if row["bucket_id"] == bucket_id
        )
        cutoff = statement["business_cutoff"]["value"]
        for decision in mine:
            event = events[decision["event_id"]]
            if event["event_time"]["value"] > cutoff:
                flag(6, statement["_source"])
        required, portal = _mass(bucket["target"]), _mass(statement["reported_supported"])
        gap = required - supported
        balances.append(
            dict(
                bucket_id=bucket_id,
                metal=bucket["metal"],
                liability_year=bucket["liability_year"],
                unit="KG",
                required=_kg(required),
                supported=_kg(supported),
                signed_gap=_kg(gap),
                shortfall=_kg(max(gap, Decimal(0))),
                surplus=_kg(max(-gap, Decimal(0))),
                pending=_kg(pending),
                portal_reported=_kg(portal),
                delta=_kg(portal - supported),
            )
        )
    if not found:
        flag(1, "all original records checked within stated synthetic scope")
    abstentions = []

    def abstain(scope, reason, description):
        abstentions.append(dict(scope=scope, reason=reason, description=description))

    if any(_number(balance["pending"]) > 0 for balance in balances):
        abstain(
            "pending_untransferred_credits",
            "MISSING_EVIDENCE",
            "Pending claims do not establish supported allocation.",
        )
    if 8 in found:
        abstain(
            "earlier_liability_priority",
            "INCOMPLETE_HISTORY" if undated else "RULE_CONFLICT",
            "Do not assert correct priority with incomplete or refuting evidence.",
        )
    if undated:
        abstain("undated_history", "INCOMPLETE_HISTORY", "Do not invent missing dates or order.")
    if 13 in found:
        abstain(
            "weight_basis_selection",
            "RULE_CONFLICT",
            "Do not average conflicting net/gross weights or recompute the supplied target.",
        )
    for family, scope, reason, description in (
        (
            6,
            "stale_portal_statement",
            "TEMPORAL_UNCERTAINTY",
            "An earlier statement is not current fulfilment evidence.",
        ),
        (
            11,
            "rule_version_applied",
            "RULE_CONFLICT",
            "Do not verify using a superseded rule/year.",
        ),
        (
            12,
            "deadline_extension",
            "MISSING_AUTHORITY",
            "An unofficial note does not establish a signed extension.",
        ),
        (
            14,
            "gold_offset_credits",
            "UNSUPPORTED_FEATURE",
            "Do not deduct out-of-scope gold offsets.",
        ),
        (
            15,
            "lost_document_page",
            "MISSING_EVIDENCE",
            "An unread or missing page does not establish zero activity.",
        ),
    ):
        if family in found:
            abstain(scope, reason, description)
    findings = [
        dict(issue_type=FAMILIES[number], evidence_refs=sorted(refs))
        for number, refs in sorted(found.items())
    ]
    return VisibleReference(
        manifest["case_id"],
        input_digest,
        balances,
        findings,
        abstentions,
        decisions,
        inventory,
        checks,
        [
            "Automated independent review of synthetic originals; no human/legal approval.",
            "Source-supported quantity retains UNKNOWN lifecycle/priority checks; "
            "it is not verified lawful fulfilment.",
            "Pending overlapping-export quantities are ambiguous claim exposure, "
            "not additional economic credit.",
            "Textless PDF pages are flagged; no OCR or hidden text reconstruction is attempted.",
        ],
    )


def validate_directory(
    visible_root: Path, output_root: Path, oracle_root: Path | None = None
) -> dict:
    """Write evaluator-only reference artifacts and an input-bound validation seal.

    The output root must stay outside all visible dossiers. This independently
    recomputed artifact intentionally does not assert human review or model scores.
    """
    if output_root.resolve().is_relative_to(visible_root.resolve()):
        raise ValueError("reference answers must stay outside the visible input root")
    output_root.mkdir(parents=True, exist_ok=True)
    entries, records, reviews, comparisons = [], {}, {}, []
    for case_dir in sorted(visible_root.glob("case_*")):
        if not case_dir.is_dir():
            continue
        reference = inspect_visible(case_dir)
        body = encoded(reference.payload())
        digest = hashlib.sha256(body).hexdigest()
        path = output_root / f"{case_dir.name}.json"
        path.write_bytes(body)
        if oracle_root is not None:
            from benchmarks.evaluation.oracle import OracleCase

            candidate = OracleCase.model_validate_json(
                (oracle_root / f"{case_dir.name}.json").read_bytes()
            )
            revised, review, comparison = bind_oracle_reference(candidate, reference)
            records[revised.case_id], reviews[revised.case_id] = revised, review
            comparisons.append(comparison)
            (output_root / f"oracle_{case_dir.name}.json").write_bytes(
                encoded(revised.model_dump(mode="json"))
            )
        entries.append(
            dict(
                case_id=reference.case_id,
                visible_input_digest=reference.visible_input_digest,
                reference_digest=digest,
                original_observation_checks=reference.original_observation_checks,
            )
        )
    if not entries:
        raise ValueError("no visible dossiers found")
    if records:
        from benchmarks.evaluation.validation import seal_oracles

        seal = seal_oracles(
            records, dataset_version="pilot-0.1", reviewed_case_ids=records, review_records=reviews
        )
        (output_root / "oracle-reference-seal.json").write_bytes(
            encoded(seal.model_dump(mode="json"))
        )
        (output_root / "review-records.json").write_bytes(
            encoded(
                {case_id: review.model_dump(mode="json") for case_id, review in reviews.items()}
            )
        )
        (output_root / "projection-comparison.json").write_bytes(encoded(comparisons))
    summary = dict(
        status="INDEPENDENT_REFERENCE_VALIDATED",
        case_count=len(entries),
        hand_reviewed_case_count=0,
        cases=entries,
        reference_implementation_digest=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        limitation="Automated evaluator validation; no human/legal approval or model evaluation.",
    )
    summary["aggregate_digest"] = hashlib.sha256(encoded(summary)).hexdigest()
    (output_root / "visible-reference-seal.json").write_bytes(encoded(summary))
    return summary


def main():
    import typer

    def run(visible_root: Path, output_root: Path, oracle_root: Path | None = None):
        summary = validate_directory(visible_root, output_root, oracle_root)
        print(json.dumps({key: value for key, value in summary.items() if key != "cases"}))

    typer.run(run)


def bind_oracle_reference(oracle, reference: VisibleReference):
    """Bind independently computed visible answers to a candidate evaluator oracle.

    Old expected answers are used only for a discrepancy ledger after original
    evidence assessment, never as inputs to that assessment.
    """
    from benchmarks.evaluation.validation import (
        VisibleReferenceReview,
        oracle_digest,
        validate_oracle,
    )

    if oracle.case_id != reference.case_id:
        raise ValueError("candidate oracle and visible reference identify different cases")
    reference_digest = hashlib.sha256(encoded(reference.payload())).hexdigest()
    revised = oracle.model_copy(
        update={
            "visible_evidence_balances": reference.balances,
            "visible_reference_status": "INDEPENDENT_REFERENCE_VALIDATED",
            "expected_findings": reference.findings,
            "required_abstentions": reference.abstentions,
            "reference_calculation_refs": [f"calc:visible_reference_{reference_digest}"],
            "reference_limitations": reference.limitations,
        }
    )
    validation = validate_oracle(revised)
    if not validation.valid:
        raise ValueError("independently computed visible oracle failed structural validation")
    old_findings = {row["issue_type"] for row in oracle.expected_findings}
    new_findings = {row["issue_type"] for row in reference.findings}
    old_abstentions = {(row["scope"], row["reason"]) for row in oracle.required_abstentions}
    new_abstentions = {(row["scope"], row["reason"]) for row in reference.abstentions}
    comparison = dict(
        case_id=reference.case_id,
        balance_projection_agreement=reference.balances == oracle.world_projection_balances,
        finding_families_agree=old_findings == new_findings,
        added_abstentions=sorted(new_abstentions - old_abstentions),
        removed_abstentions=sorted(old_abstentions - new_abstentions),
    )
    review = VisibleReferenceReview(
        reviewer_ref="evaluator:independent_visible_reference_v1",
        oracle_digest=oracle_digest(revised),
        visible_input_digest=reference.visible_input_digest,
        evidence_refs=[
            f"{entry['path']}#sha256={entry['sha256']}" for entry in reference.evidence_inventory
        ],
        reference_calculation_refs=revised.reference_calculation_refs,
        recorded_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    )
    return revised, review, comparison


if __name__ == "__main__":
    main()
