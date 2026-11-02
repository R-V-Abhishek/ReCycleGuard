"""Generation-time validation: each recorded corruption must be visible in the rendered bytes.

A recipe that leaves no trace, or a trace the evidence cannot support, is a generator bug; the
CLI refuses to write such a dossier. Text checks read PDFs through the runtime's own extractor,
so "visible" means visible to intake, not only to a human reader.
"""

import csv
import io
import json
import re
from decimal import Decimal
from pathlib import Path

from benchmarks.generator.faults.recipes import INJECTIONS, Corrupted
from benchmarks.generator.pdf_style import wrap
from benchmarks.generator.render import Rendered
from benchmarks.generator.world import gstin
from recycleguard.extraction.pdf_extractor import extract_pdf_pages
from recycleguard.normalization.units import convert_mass_to_kg, parse_strict_decimal

LAKH = re.compile(r"\d,\d{2},\d{3}")


def _pdf(path: Path):
    observations, coverage, text, issues = extract_pdf_pages(
        path.read_bytes(), "art:check", "ext:check"
    )
    return observations, coverage, " ".join(text.split()), issues


def _jsonl(case: Path, stem: str) -> list[dict]:
    path = case / f"records/{stem}.jsonl"
    return [json.loads(x) for x in path.read_text("utf-8").splitlines()] if path.exists() else []


def _flat(text: str) -> str:
    return " ".join(text.split())


def asset_paths(case: Corrupted, out: Rendered, kinds) -> list[str]:
    paths = []
    for kind in kinds:
        if kind.startswith("records/"):
            if (out.case_dir / f"{kind}.jsonl").exists():
                paths.append(f"{kind}.jsonl")
        elif kind in out.documents:
            paths.append(out.documents[kind])
    return sorted(set(paths))


def validate(case: Corrupted, out: Rendered) -> list[str]:
    w, d = case.world, out.case_dir
    problems: list[str] = []
    ledger = list(csv.DictReader(io.StringIO((d / out.documents["ledger"]).read_text("utf-8"))))
    portal = (
        json.loads((d / out.documents["portal"]).read_text("utf-8"))["portal_transactions"]
        if "portal" in out.documents
        else []
    )
    _, memo_cov, memo_text, memo_issues = _pdf(d / out.documents["memo"])
    texts = {"memo": memo_text, "notice": _pdf(d / out.documents["notice"])[2]}
    for inv in w.invoices:
        texts[f"invoice:{inv.key}"] = _pdf(d / out.documents[f"invoice:{inv.key}"])[2]

    def need(condition, message):
        if not condition:
            problems.append(message)

    # Every S06 ledger figure, as printed, converts exactly to the world's kilograms.
    for row in ledger:
        t = next(t for t in w.transfers if t.txn_ref == row["Transaction_ID"])
        value = convert_mass_to_kg(row["Quantity"], row["UOM"])
        need(value == Decimal(t.quantity_kg), f"ledger figure {row['Quantity']} != {t.quantity_kg}")
    for plant in w.plants:
        if plant.channel == "invoice":
            # Remarks sit beside the totals column, so check each printed line on its own.
            flat = _flat(texts.get(f"invoice:{plant.target}", ""))
            lines = wrap(plant.text, "Helvetica", 7.0, 274)
            need(
                all(_flat(x) in flat for x in lines), f"invoice text not visible: {plant.text[:40]}"
            )
            continue
        where = {
            "memo": memo_text,
            "notice": texts["notice"],
            "invoice": texts.get(f"invoice:{plant.target}", ""),
            "ledger": " ".join(r["Narration"] for r in ledger),
            "portal": " ".join(r.get("remarks", "") for r in portal),
        }[plant.channel]
        need(
            _flat(plant.text) in _flat(where),
            f"{plant.channel} text not visible: {plant.text[:40]}",
        )

    for change in case.changes:
        f = change.family
        if f == "F02_OVERLAPPING_EXPORT":
            copies = [r for r in portal if r["transaction_id"] == "" and len(r["event_time"]) == 10]
            need(copies, "F02: no portal copy without id and time of day")
            allocations = _jsonl(d, "allocations")
            lots = [a["credit_lot_id"] for a in allocations]
            need(len(lots) != len(set(lots)), "F02: the copy is not allocated a second time")
        elif f == "F03_MULTISTAGE_ID_REUSE":
            refs = [r["Certificate_Ref"] for r in ledger]
            need(len(refs) != len(set(refs)), "F03: no certificate reference repeats in the ledger")
            events = _jsonl(d, "certificate_events")
            per_cert: dict[str, set] = {}
            for e in events:
                per_cert.setdefault(e["certificate_id"], set()).add(
                    (e["event_kind"], e["event_time"]["value"])
                )
            need(any(len(v) >= 3 for v in per_cert.values()), "F03: no certificate with 3 events")
        elif f == "F04_UNIT_DIMENSION_MIX":
            need({r["UOM"] for r in ledger} == {"KG", "TONNE"}, "F04: ledger lacks mixed units")
            need(any(LAKH.search(r["Quantity"]) for r in ledger), "F04: no lakh-grouped figure")
            obligations = _jsonl(d, "obligations")
            need(any(o["target"]["unit"] == "TONNE" for o in obligations), "F04: no tonne target")
            for row in ledger:
                parse_strict_decimal(row["Quantity"])
        elif f == "F05_WRONG_ENTITY_ALIAS":
            if not w.affiliates or not w.aliases:
                need(False, "F05: no affiliate or dated alias in the world")
                continue
            sister = w.affiliates[0]
            need(gstin(sister) in {r["Recipient_GSTIN"] for r in ledger}, "F05: no affiliate row")
            need(gstin(sister) != gstin(w.producer), "F05: affiliate shares the GSTIN")
            alias = w.aliases[0]
            need(
                any(alias.name in texts[k] for k in texts if k.startswith("invoice:")),
                "F05: no document uses the dated former name",
            )
        elif f == "F06_STALE_SNAPSHOT":
            cutoff = w.balances[0].cutoff
            later = [t for t in w.transfers if t.stage == "COMPLETED" and t.when > cutoff]
            need(later, "F06: no allocated transfer after the statement cut-off")
            need("balances as at" in memo_text, "F06: memo does not state the balance date")
        elif f == "F07_PAID_NO_TRANSFER":
            stages = {r["Transfer_Stage"] for r in ledger}
            need(stages & {"OTP_INITIATED", "PUBLIC_KEY_DISPATCHED"}, "F07: no intermediate stage")
            kinds = [c["record_kind"] for c in _jsonl(d, "commercial_records")]
            need("PAYMENT" in kinds, "F07: no payment record")
        elif f == "F08_PRIOR_ARREARS_DRAIN":
            allocations = _jsonl(d, "allocations")
            if change.issue_codes == ("EARLIER_LIABILITY_UNMET",):
                need(all("allocation_time" in a for a in allocations), "F08: undated allocation")
                year = {b["bucket_id"]: b["liability_year"] for b in _jsonl(d, "obligations")}
                by_lot: dict[str, list] = {}
                for a in allocations:
                    by_lot.setdefault(a["credit_lot_id"], []).append(a)
                drained = any(
                    year[x["bucket_id"]] > year[y["bucket_id"]]
                    and x["allocation_time"]["value"] < y["allocation_time"]["value"]
                    for group in by_lot.values()
                    for x in group
                    for y in group
                    if "allocation_time" in x and "allocation_time" in y
                )
                need(drained, "F08: no later-year draw dated before the earlier year's")
            else:
                need(not any("allocation_time" in a for a in allocations), "F08: dated history")
        elif f == "F09_EXPIRED_CANCELLED":
            certificates = _jsonl(d, "certificates")
            need(
                any(c["raw_status"] == "CANCELLED" for c in certificates),
                "F09: no CANCELLED status",
            )
            ended = [e for e in _jsonl(d, "certificate_events") if e["event_kind"] == "CANCELLED"]
            need(not ended, "F09: a dated cancellation event exists")
            need("Cancelled" in memo_text, "F09: register does not show the status")
        elif f == "F10_CAPABILITY_MISMATCH":
            if "CAPABILITY_MISMATCH" in change.issue_codes:
                codes = [set(x["covered_eee_codes"]) for x in _jsonl(d, "registrations")]
                need(
                    any(c == {"ITEW"} or c == {"CEEW"} for c in codes),
                    "F10: no narrow registration",
                )
            if "DIMENSION_MISMATCH" in change.issue_codes:
                buckets = {b["bucket_id"]: b["metal"] for b in _jsonl(d, "obligations")}
                need(
                    any(
                        a["quantity"]["metal"] != buckets[a["bucket_id"]]
                        for a in _jsonl(d, "allocations")
                    ),
                    "F10: no cross-metal allocation",
                )
        elif f == "F11_WRONG_PERIOD_RULE":
            need(
                "Rules, 2016" in memo_text and "2022-23" in memo_text,
                "F11: memo lacks the old rule",
            )
        elif f == "F12_UNSEEN_NOTICE_LEAD":
            need("extended up to" in texts["notice"], "F12: notice lacks the extension text")
            listed = {p.name for p in (d / "documents").iterdir()}
            known = {Path(p).name for p in out.documents.values()} | {"source_records.json"}
            need(listed <= known, "F12: the dossier carries a document that could be the order")
        elif f == "F13_WEIGHT_BASIS_CONFLICT":
            mappings = _jsonl(d, "product_mappings")
            skus: dict[str, set] = {}
            for m in mappings:
                skus.setdefault(m["sku"], set()).add(m["weight_basis"])
            need(any(len(v) > 1 for v in skus.values()), "F13: no SKU with two weight bases")
        elif f == "F14_OUT_OF_SCOPE_REGIME":
            need(any(o["metal"] == "AU" for o in _jsonl(d, "obligations")), "F14: no AU bucket")
            need("gold offset" in memo_text.lower(), "F14: memo lacks the offset claim")
        elif f == "F15_EXTRACTION_PAGE_LOSS":
            quarantined = [c for c in memo_cov if c.disposition == "QUARANTINED"]
            pages = len(memo_cov)
            if "no text layer" in change.transformation:
                need(len(quarantined) == 1, "F15: the textless page is not quarantined by intake")
            else:
                stated = out.memo_pages_stated
                need(stated is not None and pages < stated, "F15: no page is missing")
                need(f"of {stated}" in memo_text, "F15: footers do not state the full count")
                absent = [i for i in memo_issues if i.code == "INCOMPLETE_COVERAGE"]
                need(len(absent) == 1, "F15: intake does not flag the absent page")
        elif f == "F16_PROMPT_INJECTION":
            for channel in ("memo", "invoice", "ledger", "portal", "notice"):
                if channel in change.before_refs:
                    need(
                        any(
                            p.channel == channel and p.text == INJECTIONS[channel] for p in w.plants
                        ),
                        f"F16: no {channel} injection",
                    )
    return problems


__all__ = ["asset_paths", "validate"]
