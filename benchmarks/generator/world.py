"""S05 clean worlds: one typed, seeded source of truth from which every visible file is projected.

A ``World`` is hidden truth. Visible renderings (``render.py``) are projections of it, so CSV
rows, portal JSON, PDFs and JSONL records cannot disagree unless S06 corrupts them on purpose.

Identity policy (SYSTEM_DESIGN section 5.5): every legal identifier is an unmistakable project
string (``SYNTH-GSTIN-29-P0001``), never a valid-looking GSTIN/PAN/CIN. Business names carry a
"Synth" marker; e-mail and web domains use the reserved ``.example`` TLD (RFC 2606). Localities,
pincodes, GST state codes and STD codes are real Indian geography so the documents read true.
"""

import hashlib
from dataclasses import asdict, dataclass, field
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Literal

from recycleguard.normalization.units import convert_mass_to_kg, format_decimal_string

DATASET_VERSION = "s05-dev-0.1"
PROFILE_ID = "profile:producer_snapshot_v1"
FORBIDDEN_FRAGMENTS = ("clean", "fault", "f0", "gap", "leak", "oracle", "hidden", "expected")
# GST on traded EPR certificates is not settled by a reviewed source here; 18% is a stated
# generator assumption for realistic-looking totals, not a claim about tax law.
GST_RATE_ASSUMED = Decimal("18")


@dataclass(frozen=True)
class Party:
    key: str
    legal_name: str
    short_name: str
    role: Literal["PRODUCER", "RECYCLER"]
    kind: Literal["PTC", "PLC", "LLP"]
    state: str
    state_abbr: str
    gst_state_code: str
    address: tuple[str, ...]
    std_code: str
    nic_code: str
    incorporated: int
    domain: str
    eee_codes: tuple[str, ...]
    category: Literal["ITEW", "CEEW"]
    tagline: str
    signatory: str
    serial: int
    capacity_tonnes_per_year: str | None = None


@dataclass(frozen=True)
class Bucket:
    key: str
    bucket_id: str
    liability_year: str
    metal: str
    supplied_target: str
    supplied_unit: Literal["KG", "TONNE"]
    target_kg: str


@dataclass(frozen=True)
class Lot:
    key: str
    lot_id: str
    certificate_id: str
    external_ref: str
    recycler: str
    metal: str
    face_kg: str
    generated_on: str
    expires_on: str | None = None
    status: str = "TRANSFERRED"


@dataclass(frozen=True)
class Transfer:
    key: str
    event_id: str
    txn_ref: str
    lot: str
    quantity_kg: str
    when: str
    stage: Literal["COMPLETED", "INITIATED"]
    channels: tuple[str, ...]


@dataclass(frozen=True)
class AllocationW:
    key: str
    allocation_id: str
    transfer: str
    bucket: str
    quantity_kg: str
    order: int
    allocated_on: str | None = None


@dataclass(frozen=True)
class Lifecycle:
    """A credit that ended: an EXPIRED or CANCELLED event on a lot's certificate."""

    key: str
    event_id: str
    lot: str
    kind: Literal["EXPIRED", "CANCELLED"]
    when: str


@dataclass(frozen=True)
class Payment:
    """The producer's payment of one invoice; it carries the invoice's credit quantity."""

    key: str
    commercial_id: str
    invoice: str
    paid_on: str


@dataclass(frozen=True)
class Product:
    key: str
    mapping_id: str
    sku: str
    eee_code: str
    unit_weight_kg: str
    weight_basis: Literal["NET_EEE", "GROSS_PACKAGED", "COMPONENT"]


@dataclass(frozen=True)
class Sale:
    key: str
    sku: str
    units: str


@dataclass(frozen=True)
class Invoice:
    key: str
    commercial_id: str
    number: str
    recycler: str
    metal: str
    quantity_kg: str
    rate_inr_per_kg: str
    taxable_inr: str
    gst_inr: str
    total_inr: str
    issued: str
    paid_on: str
    utr: str
    transfer: str
    bucket: str


@dataclass(frozen=True)
class PortalBalance:
    key: str
    balance_id: str
    bucket: str
    reported_kg: str
    capture: str
    cutoff: str


@dataclass(frozen=True)
class World:
    dataset_version: str
    template_key: str
    seed: int
    timeline_group: str
    case_tag: str
    case_id: str
    fiscal_year: str
    period_start: str
    period_end_exclusive: str
    knowledge_cutoff: str
    producer: Party
    recyclers: tuple[Party, ...]
    buckets: tuple[Bucket, ...]
    lots: tuple[Lot, ...]
    transfers: tuple[Transfer, ...]
    allocations: tuple[AllocationW, ...]
    invoices: tuple[Invoice, ...]
    balances: tuple[PortalBalance, ...]
    memo_date: str
    notes: tuple[str, ...] = field(default_factory=tuple)
    lifecycle: tuple[Lifecycle, ...] = ()
    payments: tuple[Payment, ...] = ()
    products: tuple[Product, ...] = ()
    sales: tuple[Sale, ...] = ()

    def party(self, key: str) -> Party:
        return next(p for p in (self.producer, *self.recyclers) if p.key == key)

    def get(self, collection: str, key: str):
        return next(item for item in getattr(self, collection) if item.key == key)

    def to_json(self) -> dict:
        return asdict(self)


# --- Identity helpers -----------------------------------------------------------------------
def opaque(material: str, length: int = 10) -> str:
    """Stable hex token that never spells a label fragment (e.g. 'f0', 'cafe' is fine)."""
    salt = 0
    while True:
        token = hashlib.sha256(f"{material}|{salt}".encode()).hexdigest()[:length]
        if not any(word in token for word in FORBIDDEN_FRAGMENTS):
            return token
        salt += 1


def entity_id(tag: str, party: Party) -> str:
    return f"entity:{tag}_{party.role[0].lower()}{party.serial:02d}"


def gstin(party: Party) -> str:
    return f"SYNTH-GSTIN-{party.gst_state_code}-{party.role[0]}{party.serial:04d}"


def pan(party: Party) -> str:
    return f"SYNTH-PAN-{party.role[0]}{party.serial:04d}"


def corporate_id(party: Party) -> tuple[str, str]:
    """(label, value): CIN for companies, LLPIN for LLPs, in an obviously synthetic layout."""
    if party.kind == "LLP":
        return "LLPIN", f"SYNTH-LLPIN-{party.state_abbr}-{party.serial:04d}"
    listing = "L" if party.kind == "PLC" else "U"
    return (
        "CIN",
        f"SYNTH-CIN-{listing}{party.nic_code}-{party.state_abbr}-{party.incorporated}-"
        f"{party.kind}-{party.serial:04d}",
    )


def epr_registration(party: Party) -> str:
    code = "PRO" if party.role == "PRODUCER" else "REC"
    return f"SYNTH/EPR-EW/{code}/{party.state_abbr}/{party.serial:04d}"


def phone(party: Party) -> str:
    return f"+91 {party.std_code} 0000 {party.serial:04d}"


def email(party: Party, mailbox: str) -> str:
    return f"{mailbox}@{party.domain}"


# --- Exact arithmetic -----------------------------------------------------------------------
def kg(value: str | Decimal) -> str:
    return format_decimal_string(Decimal(value), 4)


def tonnes_to_kg(value: str) -> str:
    return kg(convert_mass_to_kg(value, "TONNE"))


def money(value: Decimal) -> str:
    return format_decimal_string(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN), 4)


def invoice_amounts(quantity_kg: str, rate: str) -> tuple[str, str, str]:
    taxable = (Decimal(quantity_kg) * Decimal(rate)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_EVEN
    )
    gst = (taxable * GST_RATE_ASSUMED / 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
    return money(taxable), money(gst), money(taxable + gst)


# --- Fictional party catalogue (real Indian industrial localities, synthetic firms) ----------
PRODUCERS: tuple[Party, ...] = (
    Party(
        key="producer",
        legal_name="Synthora Consumer Electronics Private Limited",
        short_name="Synthora",
        role="PRODUCER",
        kind="PTC",
        state="Karnataka",
        state_abbr="KA",
        gst_state_code="29",
        address=(
            "Plot No. 214, 2nd Phase, KIADB Industrial Area, Jigani",
            "Anekal Taluk, Bengaluru Urban, Karnataka - 562106",
        ),
        std_code="80",
        nic_code="26400",
        incorporated=2014,
        domain="synthora.example",
        eee_codes=("CEEW1", "CEEW2"),
        category="CEEW",
        tagline="Televisions, audio systems and smart displays",
        signatory="R. Venkatesh",
        serial=1,
    ),
    Party(
        key="producer",
        legal_name="SynthNova Appliances Limited",
        short_name="SynthNova",
        role="PRODUCER",
        kind="PLC",
        state="Uttar Pradesh",
        state_abbr="UP",
        gst_state_code="09",
        address=(
            "C-47, Sector 63, Noida, Gautam Buddh Nagar",
            "Uttar Pradesh - 201301",
        ),
        std_code="120",
        nic_code="27500",
        incorporated=2009,
        domain="synthnova.example",
        eee_codes=("CEEW3", "CEEW5"),
        category="CEEW",
        tagline="Home and kitchen electrical appliances",
        signatory="Priya Srivastava",
        serial=2,
    ),
    Party(
        key="producer",
        legal_name="Synthwave Mobility Devices Private Limited",
        short_name="Synthwave",
        role="PRODUCER",
        kind="PTC",
        state="Tamil Nadu",
        state_abbr="TN",
        gst_state_code="33",
        address=(
            "Plot No. B-12, SIPCOT Industrial Park, Oragadam",
            "Sriperumbudur Taluk, Kancheepuram District, Tamil Nadu - 602105",
        ),
        std_code="44",
        nic_code="26300",
        incorporated=2017,
        domain="synthwave.example",
        eee_codes=("ITEW15", "ITEW17"),
        category="ITEW",
        tagline="Mobile handsets and wearable devices",
        signatory="Meenakshi Iyer",
        serial=3,
    ),
    Party(
        key="producer",
        legal_name="Synthetica Home Electricals Private Limited",
        short_name="Synthetica",
        role="PRODUCER",
        kind="PTC",
        state="Maharashtra",
        state_abbr="MH",
        gst_state_code="27",
        address=(
            "Gat No. 118, MIDC Chakan Phase II, Khed Taluka",
            "Pune, Maharashtra - 410501",
        ),
        std_code="20",
        nic_code="27500",
        incorporated=2012,
        domain="synthetica.example",
        eee_codes=("CEEW4", "CEEW6"),
        category="CEEW",
        tagline="Air conditioners, fans and water heaters",
        signatory="Anil Kulkarni",
        serial=4,
    ),
    Party(
        key="producer",
        legal_name="SynthByte Computing Systems Private Limited",
        short_name="SynthByte",
        role="PRODUCER",
        kind="PTC",
        state="Haryana",
        state_abbr="HR",
        gst_state_code="06",
        address=(
            "Plot No. 88, Sector 8, IMT Manesar",
            "Gurugram, Haryana - 122052",
        ),
        std_code="124",
        nic_code="26200",
        incorporated=2011,
        domain="synthbyte.example",
        eee_codes=("ITEW2", "ITEW3"),
        category="ITEW",
        tagline="Laptops, desktops and computer peripherals",
        signatory="Rohit Malhotra",
        serial=5,
    ),
    Party(
        key="producer",
        legal_name="Synthelion Display Technologies Limited",
        short_name="Synthelion",
        role="PRODUCER",
        kind="PLC",
        state="Telangana",
        state_abbr="TG",
        gst_state_code="36",
        address=(
            "Survey No. 72, Phase V, IDA Cherlapally",
            "Medchal-Malkajgiri District, Telangana - 500051",
        ),
        std_code="40",
        nic_code="26400",
        incorporated=2015,
        domain="synthelion.example",
        eee_codes=("CEEW1", "ITEW6"),
        category="CEEW",
        tagline="LED panels, monitors and signage displays",
        signatory="K. Lakshmi Prasad",
        serial=6,
    ),
)

RECYCLERS: tuple[Party, ...] = (
    Party(
        key="recycler_a",
        legal_name="SynthCycle Metals Recovery LLP",
        short_name="SynthCycle",
        role="RECYCLER",
        kind="LLP",
        state="Karnataka",
        state_abbr="KA",
        gst_state_code="29",
        address=(
            "Plot No. 31, KIADB Industrial Area, Sompura 2nd Stage",
            "Nelamangala Taluk, Bengaluru Rural, Karnataka - 562111",
        ),
        std_code="80",
        nic_code="38300",
        incorporated=2016,
        domain="synthcycle.example",
        eee_codes=("ITEW", "CEEW"),
        category="ITEW",
        tagline="Authorised e-waste recycler and material recovery facility",
        signatory="S. Fathima",
        serial=1,
        capacity_tonnes_per_year="12000",
    ),
    Party(
        key="recycler_b",
        legal_name="Synthgreen E-Waste Processors Private Limited",
        short_name="Synthgreen",
        role="RECYCLER",
        kind="PTC",
        state="Tamil Nadu",
        state_abbr="TN",
        gst_state_code="33",
        address=(
            "Plot No. A-9/2, SIPCOT Industrial Growth Centre, Oragadam",
            "Kancheepuram District, Tamil Nadu - 602105",
        ),
        std_code="44",
        nic_code="38300",
        incorporated=2013,
        domain="synthgreen.example",
        eee_codes=("ITEW", "CEEW"),
        category="ITEW",
        tagline="E-waste dismantling, recycling and precious metal recovery",
        signatory="V. Senthil Kumar",
        serial=2,
        capacity_tonnes_per_year="18000",
    ),
    Party(
        key="recycler_c",
        legal_name="SynthLoop Recyclers Private Limited",
        short_name="SynthLoop",
        role="RECYCLER",
        kind="PTC",
        state="Maharashtra",
        state_abbr="MH",
        gst_state_code="27",
        address=(
            "Plot No. W-58, MIDC Taloja, Panvel Taluka",
            "Raigad District, Maharashtra - 410208",
        ),
        std_code="22",
        nic_code="38300",
        incorporated=2018,
        domain="synthloop.example",
        eee_codes=("ITEW", "CEEW"),
        category="ITEW",
        tagline="Registered recycler - copper, aluminium and ferrous recovery",
        signatory="Arjun Deshpande",
        serial=3,
        capacity_tonnes_per_year="9600",
    ),
    Party(
        key="recycler_d",
        legal_name="SynthRe Urban Mining LLP",
        short_name="SynthRe",
        role="RECYCLER",
        kind="LLP",
        state="Gujarat",
        state_abbr="GJ",
        gst_state_code="24",
        address=(
            "Plot No. 415, Phase II, GIDC Vapi",
            "Valsad District, Gujarat - 396195",
        ),
        std_code="260",
        nic_code="38300",
        incorporated=2019,
        domain="synthre.example",
        eee_codes=("ITEW", "CEEW"),
        category="ITEW",
        tagline="Urban mining and non-ferrous metal refining",
        signatory="Hetal Patel",
        serial=4,
        capacity_tonnes_per_year="7200",
    ),
    Party(
        key="recycler_e",
        legal_name="Synthterra Resource Recovery Private Limited",
        short_name="Synthterra",
        role="RECYCLER",
        kind="PTC",
        state="Uttarakhand",
        state_abbr="UK",
        gst_state_code="05",
        address=(
            "Plot No. 27, Sector 6A, IIE SIDCUL",
            "Haridwar, Uttarakhand - 249403",
        ),
        std_code="1334",
        nic_code="38300",
        incorporated=2015,
        domain="synthterra.example",
        eee_codes=("ITEW", "CEEW"),
        category="ITEW",
        tagline="E-waste recycling and secondary aluminium recovery",
        signatory="Deepak Negi",
        serial=5,
        capacity_tonnes_per_year="15000",
    ),
)

# CPCB 2024 price band for e-waste EPR certificates (30% floor to 100% of the environmental
# compensation rate), per category, INR per kg. See benchmarks/generator/README.md.
PRICE_BAND_INR_PER_KG = {
    "CEEW": (Decimal("22"), Decimal("74")),
    "ITEW": (Decimal("34"), Decimal("112")),
}


__all__ = [
    "DATASET_VERSION",
    "PROFILE_ID",
    "PRODUCERS",
    "RECYCLERS",
    "PRICE_BAND_INR_PER_KG",
    "Party",
    "Bucket",
    "Lot",
    "Transfer",
    "AllocationW",
    "Invoice",
    "Lifecycle",
    "Payment",
    "PortalBalance",
    "Product",
    "Sale",
    "World",
    "corporate_id",
    "email",
    "entity_id",
    "epr_registration",
    "gstin",
    "invoice_amounts",
    "kg",
    "opaque",
    "pan",
    "phone",
    "tonnes_to_kg",
]
