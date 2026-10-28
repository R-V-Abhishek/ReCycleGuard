"""Hidden generation record (CONTRACTS section 5.3 names), written only under the hidden root.

Layout under ``<hidden_root>/<dataset_version>/``:
  generation_manifest.json      GenerationManifest fields; blob refs are SHA-256 of the files
  world/<case_tag>.json         the full clean world (template key, seed, timeline group)
  visible_map/<case_tag>.json   visible asset + locator -> world object key
  reference/<case_tag>.json     world-level reference balances per bucket and allocation order

``reference`` is generator arithmetic over the world, not an ``OracleCase``; V04 builds the
oracle independently. The format is a proposal pending V04 agreement (S05 sign-off gate).
"""

import hashlib
import json
import subprocess
from decimal import Decimal
from pathlib import Path

from benchmarks.generator.render import Rendered
from benchmarks.generator.world import World, kg

SPLIT_POLICY = "DEV_ONLY_S05"  # the S05 set; later sets derive theirs from the dataset version
GENERATOR_DIR = Path(__file__).resolve().parent


def _bytes(payload) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n").encode()


def _covers(registered: str, code: str) -> bool:
    """A registered category ("CEEW") covers its numbered items ("CEEW1"); other codes are exact."""
    return code == registered or (
        registered.isalpha() and code.startswith(registered) and code[len(registered) :].isdigit()
    )


def _lifecycle(world: World, a, transfer, lot) -> tuple[str, str | None]:
    """An end date before the transfer or the allocation voids the credit; no date is no end."""
    ends = [] if lot.expires_on is None else [("CREDIT_EXPIRED", lot.expires_on)]
    ends += [
        ("CREDIT_EXPIRED" if e.kind == "EXPIRED" else "CREDIT_CANCELLED", e.when[:10])
        for e in world.lifecycle
        if e.lot == lot.key
    ]
    state = "PASS"
    for code, day in sorted(ends, key=lambda end: end[1]):
        if day < transfer.when[:10] or (a.allocated_on is not None and day < a.allocated_on):
            return "FAIL", code
        if a.allocated_on is None:
            state = "UNKNOWN"  # ended after the transfer; without an allocation date it is open
    return state, None


def _capability(world: World, lot) -> str:
    """Evaluated only when product mappings exist (registrations always do in these dossiers)."""
    mapped = sorted({p.eee_code for p in world.products})
    if not mapped:
        return "NOT_EVALUATED"
    registered = world.party(lot.recycler).eee_codes
    covered = [c for c in mapped if any(_covers(r, c) for r in registered)]
    return "PASS" if len(covered) == len(mapped) else "FAIL" if not covered else "UNKNOWN"


def allocation_outcomes(world: World) -> dict[str, dict]:
    """Independent per-allocation validity: lifecycle, capability, then earlier-liability."""
    transfers = {t.key: t for t in world.transfers}
    lots = {lot.key: lot for lot in world.lots}
    buckets = {b.key: b for b in world.buckets}
    outcomes: dict[str, dict] = {}
    for a in world.allocations:
        t = transfers[a.transfer]
        lifecycle, code = _lifecycle(world, a, t, lots[t.lot])
        capability = _capability(world, lots[t.lot])
        if capability == "FAIL":
            code = code or "CAPABILITY_MISMATCH"
        outcomes[a.allocation_id] = {
            "lifecycle": lifecycle,
            "capability": capability,
            "priority": "NOT_EVALUATED",
            "excluded": "FAIL" in (lifecycle, capability),
            "code": code,
            "_alloc": a,
        }
    # Oldest liability first, so a later bucket sees earlier buckets' final decisions.
    for later in sorted(world.buckets, key=lambda b: (b.liability_year, b.bucket_id)):
        earlier = [
            b
            for b in world.buckets
            if b.metal == later.metal and b.liability_year < later.liability_year
        ]
        if not earlier:
            continue
        for row in outcomes.values():
            a = row["_alloc"]
            if buckets[a.bucket] is not later or row["excluded"]:
                continue
            states = []
            for b in earlier:
                paid = [
                    o["_alloc"]
                    for o in outcomes.values()
                    if o["_alloc"].bucket == b.key and not o["excluded"]
                ]
                if a.allocated_on is None or any(p.allocated_on is None for p in paid):
                    states.append("UNKNOWN")
                    continue
                before = sum(
                    (Decimal(p.quantity_kg) for p in paid if p.allocated_on < a.allocated_on),
                    Decimal(0),
                )
                states.append("PASS" if before >= Decimal(b.target_kg) else "FAIL")
            row["priority"] = (
                "FAIL" if "FAIL" in states else "UNKNOWN" if "UNKNOWN" in states else "PASS"
            )
            if row["priority"] == "FAIL":
                row["excluded"], row["code"] = True, "EARLIER_LIABILITY_UNMET"
    return outcomes


def product_outcomes(world: World) -> dict:
    """F13: one SKU with two weight bases (or weights) in force together is a conflict."""
    conflicts = {}
    for sku in sorted({p.sku for p in world.products}):
        shapes = {(p.weight_basis, p.unit_weight_kg) for p in world.products if p.sku == sku}
        conflicts[sku] = "FAIL" if len(shapes) > 1 else "PASS"
    out = {"weight_basis": conflicts}
    if world.sales:
        out["sales"] = "FAIL" if any(conflicts[s.sku] == "FAIL" for s in world.sales) else "PASS"
    return out


def reference_balances(world: World) -> dict:
    """Independent world arithmetic: required - supported = signed gap; pending is separate."""
    transfers = {t.key: t for t in world.transfers}
    outcomes = allocation_outcomes(world)
    kept = {k for k, o in outcomes.items() if not o["excluded"]}
    rows = []
    for b in sorted(world.buckets, key=lambda b: b.bucket_id):
        required = Decimal(b.target_kg)
        supported = sum(
            (
                Decimal(a.quantity_kg)
                for a in world.allocations
                if a.bucket == b.key and a.allocation_id in kept
            ),
            Decimal(0),
        )
        reported = sum(
            (Decimal(a.quantity_kg) for a in world.allocations if a.bucket == b.key), Decimal(0)
        )
        pending = sum(
            (
                Decimal(i.quantity_kg)
                for i in world.invoices
                if i.bucket == b.key and transfers[i.transfer].stage != "COMPLETED"
            ),
            Decimal(0),
        )
        portal = next(Decimal(x.reported_kg) for x in world.balances if x.bucket == b.key)
        if portal != reported:
            raise ValueError("the portal reports every recorded allocation")
        gap = required - supported
        rows.append(
            {
                "bucket_id": b.bucket_id,
                "metal": b.metal,
                "liability_year": b.liability_year,
                "required": kg(required),
                "supported": kg(supported),
                "signed_gap": kg(gap),
                "shortfall": kg(max(gap, Decimal(0))),
                "surplus": kg(max(-gap, Decimal(0))),
                "pending": kg(pending),
                "portal_reported": kg(portal),
                "delta_portal_minus_supported": kg(portal - supported),
                "unit": "KG",
            }
        )
    reference = {
        "case_id": world.case_id,
        "buckets": rows,
        "allocation_order": {a.allocation_id: a.order for a in world.allocations},
        "allocation_checks": {
            k: {f: v for f, v in o.items() if f != "_alloc"} for k, o in sorted(outcomes.items())
        },
        "basis": "generator world arithmetic; not an OracleCase",
    }
    if world.products:
        reference["product_checks"] = product_outcomes(world)
    return reference


def generator_revision() -> dict:
    sources = sorted(GENERATOR_DIR.glob("*.py"))
    digest = hashlib.sha256()
    for path in sources:
        digest.update(path.name.encode() + b"\0" + path.read_bytes().replace(b"\r\n", b"\n"))
    try:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=GENERATOR_DIR,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        head = None
    return {"git_head": head, "module_digest": digest.hexdigest()}


def write_hidden(hidden_root: Path, worlds: list[World], rendered: list[Rendered]) -> Path:
    if not worlds:
        raise ValueError("nothing to record")
    version = worlds[0].dataset_version
    root = Path(hidden_root) / version
    blobs: dict[str, dict[str, str]] = {"world": {}, "visible_map": {}, "reference": {}}
    for world, out in zip(worlds, rendered, strict=True):
        files = {
            "world": {**world.to_json(), "document_styles": out.styles},
            "visible_map": {"case_id": world.case_id, "entries": out.visible_map},
            "reference": reference_balances(world),
        }
        for kind, payload in files.items():
            body = _bytes(payload)
            target = root / kind / f"{world.case_tag}.json"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(body)
            blobs[kind][world.case_id] = hashlib.sha256(body).hexdigest()
    manifest = {
        "dataset_version": version,
        "generator_revision": generator_revision(),
        "seed": {w.case_id: w.seed for w in worlds},
        "profile_digest": None,
        "profile_digest_reason": (
            "Profile is pinned by the reviewed CP1 profile at run time; generation does not "
            "resolve or approve a profile."
        ),
        "case_ids": [w.case_id for w in worlds],
        "world_blob": blobs["world"],
        "visible_asset_manifest_blob": {
            w.case_id: hashlib.sha256(
                (out.case_dir / "case_manifest.json").read_bytes()
            ).hexdigest()
            for w, out in zip(worlds, rendered, strict=True)
        },
        "corruption_manifest_blob": None,
        "corruption_manifest_reason": (
            "S05 renders clean worlds only; faults arrive in S06"
            if version.startswith("s05")
            else "S04 worlds carry hand-built lifecycle, commercial, capability and product "
            "effects, listed in each world's notes and reference; S06 supplies fault recipes"
        ),
        "oracle_blob": None,
        "oracle_reason": "OracleCase is built independently by V04 from these records",
        "reference_blob": blobs["reference"],
        "visible_map_blob": blobs["visible_map"],
        "split_policy": f"DEV_ONLY_{version.split('-')[0].upper()}",
        "rights_manifest_ref": "rights:synthetic_fixture",
        "timeline_groups": {w.case_id: w.timeline_group for w in worlds},
        "templates": {w.case_id: w.template_key for w in worlds},
    }
    (root / "generation_manifest.json").write_bytes(_bytes(manifest))
    return root


__all__ = ["SPLIT_POLICY", "generator_revision", "reference_balances", "write_hidden"]
