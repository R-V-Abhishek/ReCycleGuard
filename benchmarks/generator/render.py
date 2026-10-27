"""Project a clean ``World`` into a visible dossier that goes through normal intake.

Everything visible is derived from the world here: records (validated by the contract models),
the ERP ledger CSV, the portal JSON, tax invoices, the inter-office memo, provenance files and
the ``CaseManifest``. The visible-to-world map is returned to the caller and is written only to
the hidden root, never into the case directory.
"""

import csv
import hashlib
import io
import json
import random
import shutil
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from pathlib import Path

from benchmarks.generator.documents import (
    DATE_STYLES,
    Letterhead,
    Memo,
    MemoTable,
    build_memo_pdf,
    indian_date,
    indian_group,
    rupees_in_words,
)
from benchmarks.generator.invariants import check_world
from benchmarks.generator.invoice_builder import B2BInvoiceData, InvoiceItem, build_b2b_invoice_pdf
from benchmarks.generator.pdf_style import WATERMARK, choose_style, wrap
from benchmarks.generator.world import (
    GST_RATE_ASSUMED,
    PROFILE_ID,
    World,
    corporate_id,
    email,
    entity_id,
    epr_registration,
    gstin,
    opaque,
    pan,
    phone,
)
from recycleguard.contracts import Locator, TemporalValue
from recycleguard.contracts.domain import RECORD_ADAPTER
from recycleguard.contracts.dossier import CaseManifest

METAL_NAMES = {"CU": "Copper", "AL": "Aluminium", "FE": "Iron/Steel", "AU": "Gold"}
LEDGER_HEADER = (
    "Transaction_ID",
    "Certificate_Ref",
    "Transfer_Date",
    "Issuer_GSTIN",
    "Recipient_GSTIN",
    "Metal",
    "Quantity_KG",
    "Transfer_Stage",
)
RECORD_FILES = {
    "Entity": "entities",
    "Registration": "registrations",
    "ObligationBucket": "obligations",
    "Certificate": "certificates",
    "CertificateEvent": "certificate_events",
    "Allocation": "allocations",
    "CommercialRecord": "commercial_records",
    "AccountBalanceObservation": "account_balances",
}
LOGICAL_TYPES = {
    **{stem: kind for kind, stem in RECORD_FILES.items()},
    "certificate_observations": "Observation",
    "observations": "Observation",
    "artifacts": "ArtifactRevision",
    "receipts": "AssetReceipt",
}
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


@dataclass
class Rendered:
    case_dir: Path
    visible_map: list[dict] = field(default_factory=list)
    styles: dict[str, dict] = field(default_factory=dict)


def temporal(value, precision="INSTANT", status="REVIEWED"):
    return TemporalValue(
        raw=value, value=value, precision=precision, timezone="UTC", interpretation_status=status
    ).model_dump(mode="json")


def locator(kind, **coordinates):
    return Locator.model_validate(
        {**dict.fromkeys(Locator.model_fields), "kind": kind, **coordinates}
    ).model_dump(mode="json")


def mass(value, metal, unit="KG"):
    return {"decimal": value, "unit": unit, "dimension": "METAL_MASS", "metal": metal}


def ref(kind, ref_id, revision=None, loc=None):
    return {"ref_kind": kind, "ref_id": ref_id, "artifact_revision_id": revision, "locator": loc}


def _lines(text: str) -> bytes:
    return text.replace("\r\n", "\n").encode("utf-8")


def _json_bytes(payload) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n").encode()


def _jsonl_bytes(rows) -> bytes:
    return "".join(json.dumps(r, sort_keys=True, ensure_ascii=True) + "\n" for r in rows).encode()


class _Case:
    def __init__(self, world: World, visible_root: Path):
        self.w, self.tag = world, world.case_tag
        self.case_dir = visible_root / f"case_{self.tag}"
        self.records: dict[str, list[dict]] = {name: [] for name in RECORD_FILES.values()}
        self.source_rows: dict[str, dict] = {}
        self.cert_observations: list[dict] = []
        self.out = Rendered(self.case_dir)
        self._obs = 0
        self._rev = 0
        self.stamp = world.knowledge_cutoff
        self.ids = {p.key: entity_id(self.tag, p) for p in (world.producer, *world.recyclers)}
        self.doc_name = {
            kind: f"{kind}_{opaque(f'{self.tag}|{kind}', 8)}"
            for kind in ("ledger", "portal", "memo")
        }

    # -- identities ----------------------------------------------------------------------
    def obs_id(self) -> str:
        self._obs += 1
        return f"obs:{self.tag}_{self._obs:03d}"

    def envelope(self, record_id, record_type, observation_refs, derived=()):
        self._rev += 1
        return {
            "record_id": record_id,
            "record_revision_id": f"rev:{self.tag}_{self._rev:03d}",
            "record_type": record_type,
            "case_id": self.w.case_id,
            "observation_refs": list(observation_refs),
            "derived_from_record_refs": list(derived),
            "validation_state": "VALID",
            "created_by_operation_id": f"op:{self.tag}_generate",
            "supersedes_revision_id": None,
        }

    def add(self, payload: dict, world_key: str):
        record = RECORD_ADAPTER.validate_json(json.dumps(payload)).model_dump(mode="json")
        stem = RECORD_FILES[record["record_type"]]
        self.records[stem].append(record)
        self.out.visible_map.append(
            {
                "visible": f"records/{stem}.jsonl",
                "locator": f"/{len(self.records[stem]) - 1}",
                "world_key": world_key,
            }
        )
        return record

    def sourced(self, record_id, record_type, body, world_key, derived=()):
        """A record whose provenance is a synthetic source row in source_records.json."""
        observation = self.obs_id()
        record = self.add(
            self.envelope(record_id, record_type, [observation], derived) | body, world_key
        )
        self.source_rows[observation] = {k: v for k, v in record.items() if k not in ENVELOPE}
        return record

    # -- records -------------------------------------------------------------------------
    def entities(self):
        for party in (self.w.producer, *self.w.recyclers):
            label, corp = corporate_id(party)
            identifiers = [("GSTIN", gstin(party)), ("PAN", pan(party))]
            identifiers.append(("CIN" if label == "CIN" else "OTHER", corp))
            self.sourced(
                self.ids[party.key],
                "Entity",
                {
                    "entity_id": self.ids[party.key],
                    "legal_name": party.legal_name,
                    "roles": [party.role],
                    "identifiers": [
                        {"kind": k, "value": v, "validation_state": "VALID", "evidence_refs": []}
                        for k, v in identifiers
                    ],
                    "synthetic": True,
                    "aliases": [],
                },
                party.key,
            )
            capacity = None
            if party.capacity_tonnes_per_year:
                capacity = {
                    "decimal": f"{party.capacity_tonnes_per_year}.0000",
                    "unit": "TONNE",
                    "dimension": "EQUIPMENT_MASS",
                    "metal": None,
                }
            self.sourced(
                f"reg:{self.tag}_{party.role[0].lower()}{party.serial:02d}",
                "Registration",
                {
                    "entity_id": self.ids[party.key],
                    "registration_ref": epr_registration(party),
                    "validity": {
                        "start": "2023-04-01",
                        "end": "2028-03-31",
                        "end_open_ended": False,
                        "review_state": "APPROVED",
                        "applicability_scope": "GENERAL",
                        "evidence_refs": [],
                    },
                    "covered_eee_codes": list(
                        self.w.producer.eee_codes if party.role == "PRODUCER" else party.eee_codes
                    ),
                    "status_assertion": "ACTIVE",
                    "evidence_as_of": temporal("2024-04-01", "DATE"),
                    "capacity": capacity,
                },
                party.key,
            )

    def obligations(self):
        for b in self.w.buckets:
            self.sourced(
                b.bucket_id,
                "ObligationBucket",
                {
                    "bucket_id": b.bucket_id,
                    "producer_entity_id": self.ids["producer"],
                    "liability_year": b.liability_year,
                    "component": "STANDARD",
                    "metal": b.metal,
                    "target": mass(b.supplied_target, b.metal, b.supplied_unit),
                    "basis": "SUPPLIED_ACCOUNT",
                    "basis_refs": [ref("OBSERVATION", f"obs:{self.tag}_{self._obs + 1:03d}")],
                    "profile_id": PROFILE_ID,
                    "adjustments": [],
                },
                b.key,
            )

    def ledger(self):
        """ERP export of every transfer; a portal export of transfers flagged PORTAL."""
        rows, portal = [], []
        ordered = sorted(self.w.transfers, key=lambda t: (t.when, t.key))
        for t in ordered:
            lot = self.w.get("lots", t.lot)
            rows.append(
                {
                    "Transaction_ID": t.txn_ref,
                    "Certificate_Ref": lot.external_ref,
                    "Transfer_Date": t.when[:10],
                    "Issuer_GSTIN": gstin(self.w.party(lot.recycler)),
                    "Recipient_GSTIN": gstin(self.w.producer),
                    "Metal": lot.metal,
                    "Quantity_KG": t.quantity_kg,
                    "Transfer_Stage": t.stage,
                }
            )
            self.out.visible_map.append(
                {
                    "visible": f"documents/{self.doc_name['ledger']}.csv",
                    "locator": f"row:{len(rows)}",
                    "world_key": t.key,
                }
            )
            if "PORTAL" in t.channels:
                portal.append(
                    {
                        "transaction_id": t.txn_ref,
                        "certificate_ref": lot.external_ref,
                        "quantity": t.quantity_kg,
                        "metal": lot.metal,
                        "status": t.stage,
                        "event_time": t.when,
                    }
                )
        buffer = io.StringIO(newline="")
        writer = csv.DictWriter(buffer, fieldnames=LEDGER_HEADER, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
        self.files[f"documents/{self.doc_name['ledger']}.csv"] = buffer.getvalue().encode()
        self.ledger_rows = {r["Transaction_ID"]: (i, r) for i, r in enumerate(rows, 1)}
        self.portal_rows = {}
        if portal:
            name = f"documents/{self.doc_name['portal']}.json"
            self.files[name] = _json_bytes({"portal_transactions": portal})
            for i, row in enumerate(portal):
                self.portal_rows[row["transaction_id"]] = (i, row)
                self.out.visible_map.append(
                    {
                        "visible": name,
                        "locator": f"/portal_transactions/{i}",
                        "world_key": next(
                            t.key for t in self.w.transfers if t.txn_ref == row["transaction_id"]
                        ),
                    }
                )

    def certificate_observation(self, t, channel):
        lot = self.w.get("lots", t.lot)
        recycler = self.ids[lot.recycler]
        parsed = {
            "certificate_id": lot.certificate_id,
            "credit_lot_id": lot.lot_id,
            "event_kind": "TRANSFERRED",
            "external_event_ref": t.txn_ref,
            "from_entity_id": recycler,
            "to_entity_id": self.ids["producer"],
            "metal": lot.metal,
            "quantity": t.quantity_kg,
            "unit": "KG",
            "transfer_stage": t.stage,
        }
        if channel == "LEDGER":
            index, raw = self.ledger_rows[t.txn_ref]
            loc = locator("CSV_ROW", row_index_1based=index)
            event_time, artifact, method = (
                temporal(raw["Transfer_Date"], "DATE", "PARSED"),
                "ledger",
                "CSV",
            )
        else:
            index, raw = self.portal_rows[t.txn_ref]
            loc = locator("JSON_POINTER", json_pointer=f"/portal_transactions/{index}")
            event_time, artifact, method = temporal(t.when, status="PARSED"), "portal", "JSON"
        observation = f"obs:{self.tag}_c{len(self.cert_observations) + 1:02d}"
        self.cert_observations.append(
            {
                "observation_id": observation,
                "extraction_id": f"ext:{self.tag}_{artifact}",
                "artifact_revision_id": f"art:{self.tag}_{artifact}",
                "locator": loc,
                "observation_type": "CertificateObservation",
                "raw_fields": dict(raw),
                "parsed_fields": parsed,
                "validation_state": "VALID",
                "extraction_method": method,
                "field_quality": {
                    name: {
                        "raw_score": None,
                        "score_scale": "NOT_MEASURED",
                        "engine": "synthetic_fixture",
                        "validation_checks": ["source_locator_resolved"],
                        "review_state": "DRAFT",
                    }
                    for name in ("certificate_ref", "quantity")
                },
                "event_time": event_time,
                "source_capture_time": temporal(
                    self.w.balances[0].capture if artifact == "portal" else self.stamp
                ),
                "ingestion_time": self.stamp,
            }
        )
        self.out.visible_map.append(
            {
                "visible": "records/certificate_observations.jsonl",
                "locator": f"/{len(self.cert_observations) - 1}",
                "world_key": t.key,
            }
        )
        return observation

    def certificates_and_events(self):
        completed = [t for t in self.w.transfers if t.stage == "COMPLETED"]
        for lot in self.w.lots:
            mine = [t for t in completed if t.lot == lot.key]
            if not mine:
                continue  # The producer never receives a certificate that was not transferred.
            observations = {
                t.key: [self.certificate_observation(t, c) for c in t.channels] for t in mine
            }
            self.sourced(
                lot.certificate_id,
                "Certificate",
                {
                    "certificate_id": lot.certificate_id,
                    "external_certificate_ref": lot.external_ref,
                    "issuer_entity_id": self.ids[lot.recycler],
                    "metal": lot.metal,
                    "face_quantity": mass(lot.face_kg, lot.metal),
                    "identity_evidence": [
                        ref("OBSERVATION", o) for obs in observations.values() for o in obs
                    ],
                    "generation_time": temporal(lot.generated_on, "DATE"),
                    "expiry_time": None,
                    "raw_status": "TRANSFERRED",
                },
                lot.key,
            )
            for t in mine:
                obs = observations[t.key]
                self.add(
                    self.envelope(t.event_id, "CertificateEvent", obs)
                    | {
                        "event_id": t.event_id,
                        "certificate_id": lot.certificate_id,
                        "credit_lot_id": lot.lot_id,
                        "event_kind": "TRANSFERRED",
                        "event_time": temporal(t.when),
                        "quantity": mass(t.quantity_kg, lot.metal),
                        "assertion_state": "SUPPORTED",
                        "supporting_observations": obs,
                        "external_event_ref": t.txn_ref,
                        "from_entity_id": self.ids[lot.recycler],
                        "to_entity_id": self.ids["producer"],
                        "transfer_stage": "COMPLETED",
                    },
                    t.key,
                )

    def allocations(self):
        for a in sorted(self.w.allocations, key=lambda a: a.order):
            t = self.w.get("transfers", a.transfer)
            lot = self.w.get("lots", t.lot)
            bucket = self.w.get("buckets", a.bucket)
            self.sourced(
                a.allocation_id,
                "Allocation",
                {
                    "allocation_id": a.allocation_id,
                    "credit_lot_id": lot.lot_id,
                    "event_id": t.event_id,
                    "bucket_id": bucket.bucket_id,
                    "quantity": mass(a.quantity_kg, lot.metal),
                    "basis_refs": [ref("RECORD", t.event_id)],
                    "state": "SUPPORTED",
                    "profile_id": PROFILE_ID,
                },
                a.key,
                derived=[t.event_id],
            )

    def commercial(self):
        for inv in self.w.invoices:
            t = self.w.get("transfers", inv.transfer)
            self.sourced(
                inv.commercial_id,
                "CommercialRecord",
                {
                    "commercial_id": inv.commercial_id,
                    "record_kind": "INVOICE",
                    "issuer_entity_id": self.ids[inv.recycler],
                    "recipient_entity_id": self.ids["producer"],
                    "external_ref": inv.number,
                    "event_time": temporal(inv.issued),
                    # Only a transfer the producer can see can be linked from its books.
                    "linked_credit_refs": [t.event_id] if t.stage == "COMPLETED" else [],
                    "money": {
                        "decimal": inv.total_inr,
                        "unit": "INR",
                        "dimension": "MONEY",
                        "metal": None,
                    },
                    "credit_quantity": mass(inv.quantity_kg, inv.metal),
                },
                inv.key,
            )

    def balances(self):
        for bal in self.w.balances:
            bucket = self.w.get("buckets", bal.bucket)
            self.sourced(
                bal.balance_id,
                "AccountBalanceObservation",
                {
                    "balance_observation_id": bal.balance_id,
                    "producer_entity_id": self.ids["producer"],
                    "bucket_id": bucket.bucket_id,
                    "reported_supported": mass(bal.reported_kg, bucket.metal),
                    "reported_pending": None,
                    "source_capture_time": temporal(bal.capture),
                    "business_cutoff": temporal(bal.cutoff),
                    "basis_refs": [],
                },
                bal.key,
            )

    # -- documents -----------------------------------------------------------------------
    def style_rng(self, name: str) -> random.Random:
        return random.Random(f"{self.w.seed}|{name}")

    def invoice_pdfs(self):
        buyer = self.w.producer
        for inv in self.w.invoices:
            seller = self.w.party(inv.recycler)
            t = self.w.get("transfers", inv.transfer)
            lot = self.w.get("lots", t.lot)
            rng = self.style_rng(inv.key)
            style = choose_style(rng, body_sizes=(9.0,))
            scale = rng.choice((0.94, 0.97, 1.0, 1.03))
            date_style = rng.choice(("dash", "slash", "dot", "tally"))
            intra = seller.gst_state_code == buyer.gst_state_code
            half = GST_RATE_ASSUMED / 2
            tax_label = (
                f"CGST {half:g}% + SGST {half:g}%" if intra else f"IGST {GST_RATE_ASSUMED:g}%"
            )
            words = wrap(
                f"Amount in words: {rupees_in_words(inv.total_inr)}", "Helvetica", 7.0, 274
            )
            data = B2BInvoiceData(
                invoice_number=inv.number,
                invoice_date=indian_date(inv.issued, date_style),
                payment_terms=rng.choice(
                    ("100% Advance (NEFT/RTGS)", "Advance against PI", "Payment before transfer")
                ),
                seller_name=seller.legal_name,
                seller_tagline=seller.address[0],
                seller_address=seller.address[1],
                seller_contact=f"Tel: {phone(seller)}  |  E-mail: {email(seller, 'accounts')}",
                seller_gstin=gstin(seller),
                seller_reg_no=f"EPR Regn: {epr_registration(seller)}",
                buyer_name=buyer.legal_name,
                buyer_gstin=f"{gstin(buyer)}  |  State Code: {buyer.gst_state_code}",
                buyer_address=buyer.address[0],
                buyer_contact=buyer.address[1],
                buyer_state="",
                ship_to_facility=f"{seller.short_name} Recycling Facility - Unit {seller.serial}",
                ship_to_address=seller.address[0],
                ship_to_eee_code=f"EEE category of producer: {buyer.category}",
                ship_to_place=f"Place of Supply: {buyer.state} ({buyer.gst_state_code})",
                items=[
                    InvoiceItem(
                        description=f"EPR certificate - {METAL_NAMES[inv.metal]} ({inv.metal})",
                        subtext=f"Cert. {lot.external_ref}",
                        quantity=indian_group(inv.quantity_kg, 4),
                        unit="KG",
                        unit_price=f"{Decimal(inv.rate_inr_per_kg):.2f}",
                        total=indian_group(inv.taxable_inr),
                    )
                ],
                subtotal=indian_group(inv.taxable_inr),
                discount="0.00",
                subtotal_less_discount=indian_group(inv.taxable_inr),
                tax_rate=tax_label,
                total_tax=indian_group(inv.gst_inr),
                shipping_handling="0.00",
                total_amount=indian_group(inv.total_inr),
                amount_paid=indian_group(inv.total_inr),
                balance_due="0.00",
                payment_remarks=[
                    *words,
                    f"NEFT UTR {inv.utr} dated {indian_date(inv.paid_on, date_style)}",
                    f"Bank A/c XXXXXXXX{seller.serial:02d}{rng.randint(10, 99)} | IFSC "
                    f"SYNT000{seller.serial:04d}",
                    "",
                    "EPR credit is transferred on the EPR portal only after",
                    "receipt of payment and producer OTP confirmation.",
                    "",
                    "Declaration: We declare that this invoice shows the actual",
                    "price of the goods described and that all particulars are",
                    "true and correct.",
                ],
                footer_lines=[
                    f"Subject to {seller.address[1].split(',')[-2].strip()} jurisdiction. "
                    "This is a computer-generated invoice and does not require a signature.",
                ],
            )
            name = f"documents/invoice_{opaque(f'{self.tag}|{inv.key}', 8)}.pdf"
            target = self.case_dir / name
            theme = build_b2b_invoice_pdf(
                target, data, seed=rng.randint(0, 10**6), style=style, type_scale=scale
            )
            self.files[name] = target.read_bytes()
            self.out.styles[name] = {
                "theme": theme.name,
                "style": asdict(style),
                "type_scale": scale,
            }
            self.out.visible_map.append(
                {"visible": name, "locator": "page:1", "world_key": inv.key}
            )

    def memo_pdf(self):
        w, p = self.w, self.w.producer
        rng = self.style_rng("memo")
        style = choose_style(rng, body_sizes=(9.5, 10.0, 10.5))
        ds = rng.choice(DATE_STYLES)

        def short(key):
            return w.party(key).short_name

        label, corp = corporate_id(p)
        buckets = MemoTable(
            columns=("Liability year", "Metal", "Target as supplied", "Unit"),
            rows=tuple(
                (
                    f"{b.liability_year[:4]}-{b.liability_year[-2:]}",
                    f"{METAL_NAMES[b.metal]} ({b.metal})",
                    indian_group(b.supplied_target, 4),
                    b.supplied_unit,
                )
                for b in sorted(w.buckets, key=lambda b: (b.liability_year, b.metal))
            ),
            widths=(0.22, 0.30, 0.30, 0.18),
            numeric=(False, False, True, False),
            caption="Table 1: EPR obligation targets (as supplied)",
        )
        transfers = sorted(w.transfers, key=lambda t: t.when)
        txns = MemoTable(
            columns=("Txn. ref", "Recycler", "Date", "Metal", "Qty (kg)", "Stage"),
            rows=tuple(
                (
                    t.txn_ref,
                    short(w.get("lots", t.lot).recycler),
                    indian_date(t.when, ds)
                    if ds in ("dot", "slash", "dash")
                    else indian_date(t.when, "dot"),
                    w.get("lots", t.lot).metal,
                    indian_group(t.quantity_kg, 4),
                    t.stage,
                )
                for t in transfers
            ),
            widths=(0.24, 0.17, 0.15, 0.09, 0.19, 0.16),
            numeric=(False, False, False, False, True, False),
            caption="Table 2: EPR certificate transfers recorded in the ERP ledger",
        )
        invoices = MemoTable(
            columns=("Invoice no.", "Recycler", "Qty (kg)", "Amount (Rs.)", "Paid on"),
            rows=tuple(
                (
                    i.number,
                    short(i.recycler),
                    indian_group(i.quantity_kg, 4),
                    indian_group(i.total_inr),
                    indian_date(i.paid_on, "dot"),
                )
                for i in sorted(w.invoices, key=lambda i: i.issued)
            ),
            widths=(0.24, 0.18, 0.19, 0.22, 0.17),
            numeric=(False, False, True, True, False),
            caption="Table 3: Tax invoices received and payments released",
        )
        portal_lines = []
        for bal in w.balances:
            b = w.get("buckets", bal.bucket)
            portal_lines.append(
                f"{indian_group(bal.reported_kg, 4)} kg of {METAL_NAMES[b.metal].lower()} "
                f"against the {b.liability_year} liability"
            )
        capture = indian_date(w.balances[0].capture, "dot")
        prev = f"{p.short_name[:3].upper()}/EPR/2024-25/{rng.randint(11, 39):03d}"
        has_portal = any("PORTAL" in t.channels for t in w.transfers)
        memo = Memo(
            letterhead=Letterhead(
                name=p.legal_name,
                tagline=p.tagline,
                registered_office=", ".join(p.address),
                corporate_label=label,
                corporate_id=corp,
                gstin=gstin(p),
                telephone=phone(p),
                email=email(p, "epr.cell"),
                website=f"www.{p.domain}",
            ),
            heading=rng.choice(
                (
                    "INTER-OFFICE MEMORANDUM",
                    "INTER OFFICE MEMO",
                    "OFFICE MEMORANDUM",
                    "INTERNAL MEMORANDUM",
                )
            ),
            ref_no=f"{p.short_name[:3].upper()}/EPR/2024-25/{rng.randint(40, 96):03d}",
            date_text=indian_date(w.memo_date, ds),
            to=rng.choice(
                (
                    "Chief Financial Officer",
                    "Head - Finance & Accounts",
                    "General Manager (Finance)",
                )
            ),
            sender=rng.choice(
                (
                    "Manager - EPR Compliance Cell",
                    "Head - Sustainability & EPR",
                    "Deputy Manager (EPR Compliance)",
                )
            ),
            subject=(
                "EPR certificate transfers and portal account position for FY 2024-25 under "
                "the E-Waste (Management) Rules, 2022"
            ),
            reference=f"Our memo No. {prev} regarding preparation of the annual EPR return",
            blocks=(
                "With reference to the above, the EPR obligation targets supplied for the "
                "Company's account are given below for record.",
                buckets,
                "The certificate transfers recorded in the ERP ledger for the period "
                "01.04.2024 to 31.03.2025 are listed below. Quantities are kilograms of metal.",
                txns,
                "The tax invoices received from the recyclers and the payments released "
                "against them are tabulated below for verification.",
                invoices,
                f"The account statement downloaded from the EPR portal on {capture} shows "
                + "; and ".join(portal_lines)
                + ".",
                "Finance is requested to reconcile the above with the books of account and "
                "confirm, so that the annual return can be finalised before the due date.",
                "This issues with the approval of the competent authority.",
            ),
            signatory=p.signatory,
            designation="Manager - EPR Compliance",
            department=f"{p.short_name} EPR Compliance Cell",
            enclosures=tuple(
                x
                for x in (
                    "ERP ledger export (CSV)",
                    "EPR portal transaction extract (JSON)" if has_portal else None,
                    f"Tax invoices ({len(w.invoices)} nos.)",
                )
                if x
            ),
            copy_to=("Company Secretary", "Head - Internal Audit", "Office copy"),
            classification=rng.choice((None, "INTERNAL", "FOR INTERNAL CIRCULATION ONLY")),
            labels=rng.choice(
                (("To", "From", "Subject", "Reference"), ("To", "From", "Sub", "Ref"))
            ),
            letterhead_align=rng.choice(("centre", "left")),
        )
        name = f"documents/{self.doc_name['memo']}.pdf"
        target = self.case_dir / name
        build_memo_pdf(target, memo, style)
        self.files[name] = target.read_bytes()
        self.out.styles[name] = {"style": asdict(style), "heading": memo.heading}
        self.out.visible_map.append({"visible": name, "locator": "page:1", "world_key": "summary"})

    # -- provenance and manifest ----------------------------------------------------------
    def provenance(self):
        self.files["documents/source_records.json"] = _json_bytes(
            {"synthetic": True, "source_rows": self.source_rows}
        )
        observations = [
            {
                "observation_id": obs,
                "extraction_id": f"ext:{self.tag}_source_records",
                "artifact_revision_id": f"art:{self.tag}_source_records",
                "locator": locator("JSON_POINTER", json_pointer=f"/source_rows/{obs}"),
                "observation_type": "SyntheticSourceRow",
                "raw_fields": payload,
                "parsed_fields": payload,
                "validation_state": "VALID",
                "extraction_method": "JSON",
                "field_quality": {},
                "event_time": {
                    "raw": None,
                    "value": None,
                    "precision": "UNKNOWN",
                    "timezone": None,
                    "interpretation_status": "UNKNOWN",
                },
                "source_capture_time": temporal(self.stamp, status="PARSED"),
                "ingestion_time": self.stamp,
            }
            for obs, payload in self.source_rows.items()
        ]
        self.files["records/observations.jsonl"] = _jsonl_bytes(observations)
        self.files["records/certificate_observations.jsonl"] = _jsonl_bytes(self.cert_observations)
        for stem, rows in self.records.items():
            if rows:
                self.files[f"records/{stem}.jsonl"] = _jsonl_bytes(rows)

        artifacts, receipts = [], []
        for name in sorted(n for n in self.files if n.startswith("documents/")):
            body = self.files[name]
            stem = Path(name).stem
            kind = stem.split("_")[0]
            # Ledger/portal revisions are the ones certificate observations already cite.
            revision = {
                "ledger": f"art:{self.tag}_ledger",
                "portal": f"art:{self.tag}_portal",
                "source": f"art:{self.tag}_source_records",
            }.get(kind, f"art:{self.tag}_{stem}")
            doc_type, establishes, not_establish = {
                "ledger": (
                    "ERP_CSV",
                    ["CERTIFICATE_IDENTITY", "TRANSFER_STAGE"],
                    ["PAYMENT", "PHYSICAL_MOVEMENT", "LIABILITY_ALLOCATION"],
                ),
                "portal": (
                    "PORTAL_SNAPSHOT",
                    ["CERTIFICATE_IDENTITY", "TRANSFER_STAGE"],
                    ["PAYMENT", "PHYSICAL_MOVEMENT", "LIABILITY_ALLOCATION"],
                ),
                "invoice": (
                    "GST_INVOICE",
                    ["PAYMENT"],
                    ["LIABILITY_ALLOCATION", "TRANSFER_STAGE", "PHYSICAL_MOVEMENT"],
                ),
                "memo": (
                    "OTHER",
                    ["CONTEXT_ONLY"],
                    ["LIABILITY_ALLOCATION", "TRANSFER_STAGE", "PAYMENT"],
                ),
                "source": (
                    "OTHER",
                    ["LIABILITY_ALLOCATION", "REPORTED_ACCOUNT_POSITION", "IDENTITY"],
                    ["PHYSICAL_MOVEMENT", "FILING_RECEIPT"],
                ),
            }[kind]
            media = {".pdf": "application/pdf", ".csv": "text/csv"}.get(
                Path(name).suffix, "application/json"
            )
            artifacts.append(
                {
                    "artifact_id": revision.replace("art:", "artifact:"),
                    "artifact_revision_id": revision,
                    "blob": {
                        "sha256": hashlib.sha256(body).hexdigest(),
                        "byte_length": len(body),
                        "media_type": media,
                    },
                    "original_filename": Path(name).name,
                    "source_kind": "SYNTHETIC_RECORD",
                    "doc_type": doc_type,
                    "establishes": establishes,
                    "does_not_establish": not_establish,
                    "source_url": None,
                    "fetch_attempt_id": None,
                    "captured_at": temporal(self.stamp, status="PARSED"),
                    "ingested_at": self.stamp,
                    "access_policy_id": "policy:synthetic_fixture",
                    "rights_decision_id": "rights:synthetic_fixture",
                    "synthetic": True,
                    "derived_from": [],
                }
            )
            receipts.append(
                {
                    "receipt_id": revision.replace("art:", "receipt:"),
                    "batch_id": f"batch:{self.tag}",
                    "declared_asset_id": revision.replace("art:", "asset:"),
                    "supplied_path_or_url": name,
                    "intake_status": "RECEIVED",
                    "artifact_revision_id": revision,
                    "reason": "Synthetic fixture receipt; no live intake ran",
                    "received_at": self.stamp,
                }
            )
        self.files["records/artifacts.jsonl"] = _jsonl_bytes(artifacts)
        self.files["records/receipts.jsonl"] = _jsonl_bytes(receipts)

    def manifest(self):
        assets = []
        for name in sorted(self.files, key=lambda n: (not n.startswith("records/"), n)):
            body = self.files[name]
            path = Path(name)
            if path.suffix == ".jsonl":
                media, logical = "application/x-ndjson", LOGICAL_TYPES[path.stem]
            elif path.suffix == ".csv":
                media, logical = "text/csv", "DocumentExport"
            elif path.suffix == ".pdf":
                media = "application/pdf"
                logical = "DocumentInvoice" if path.stem.startswith("invoice") else "DocumentMemo"
            else:
                media, logical = "application/json", "SourceDocument"
            assets.append(
                {
                    "relative_path": name,
                    "media_type": media,
                    "body_digest": hashlib.sha256(body).hexdigest(),
                    "byte_length": len(body),
                    "logical_record_type": logical,
                    "source_capture_time": temporal(self.stamp),
                    "visibility": "VISIBLE",
                }
            )
        manifest = {
            "schema_version": "1.0",
            "case_id": self.w.case_id,
            "synthetic": True,
            "watermark": WATERMARK,
            "producer_entity_id": self.ids["producer"],
            "fiscal_year": self.w.fiscal_year,
            "period_start": self.w.period_start,
            "period_end_exclusive": self.w.period_end_exclusive,
            "quarter": "ANNUAL",
            "allowed_eee_codes": list(self.w.producer.eee_codes),
            "allowed_metals": sorted({b.metal for b in self.w.buckets}),
            "calculation_profile_id": PROFILE_ID,
            "assets": assets,
            "optional_table_dispositions": [
                {
                    "table": "product_mappings",
                    "disposition": "ABSENT",
                    "reason": "Supplied metal obligation profile v1",
                },
                {
                    "table": "sales",
                    "disposition": "ABSENT",
                    "reason": "Target derived from supplied account baseline",
                },
                {
                    "table": "return_drafts",
                    "disposition": "ABSENT",
                    "reason": "Annual return not yet drafted",
                },
            ],
            "status": "DRAFT",
            "business_cutoff": temporal("2025-04-01T00:00:00Z", status="PARSED"),
            "knowledge_cutoff": self.stamp,
            "adapter_versions": {"ledger_csv": "1.0", "pdf_text": "1.0", "structured_json": "1.0"},
            # Identical in every case so the expectations never hint at a case's shape.
            "evidence_expectations": [
                "supplied obligation",
                "supported allocation",
                "dated account comparison",
                "ledger and portal exports may describe the same transfer",
                "financial evidence does not establish allocation",
            ],
        }
        validated = CaseManifest.model_validate_json(json.dumps(manifest))
        return _json_bytes(validated.model_dump(mode="json"))

    def render(self) -> Rendered:
        check_world(self.w)
        if self.case_dir.exists():
            shutil.rmtree(self.case_dir)
        self.case_dir.mkdir(parents=True)
        self.files: dict[str, bytes] = {}
        self.entities()
        self.obligations()
        self.ledger()
        self.certificates_and_events()
        self.allocations()
        self.commercial()
        self.balances()
        self.invoice_pdfs()
        self.memo_pdf()
        self.provenance()
        manifest = self.manifest()
        for name, body in self.files.items():
            target = self.case_dir / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(body)
        (self.case_dir / "case_manifest.json").write_bytes(manifest)
        return self.out


def render_case(world: World, visible_root: Path | str) -> Rendered:
    return _Case(world, Path(visible_root)).render()


__all__ = ["Rendered", "render_case"]
