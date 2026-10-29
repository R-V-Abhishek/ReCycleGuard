"""Hidden generation record (CONTRACTS section 5.3 names), written only under the hidden root.

Layout under ``<hidden_root>/<dataset_version>/``:
  generation_manifest.json      GenerationManifest fields; blob refs are SHA-256 of the files
  world/<case_tag>.json         the full clean world (template key, seed, timeline group)
  visible_map/<case_tag>.json   visible asset + locator -> world object key
  reference/<case_tag>.json     world-level reference balances per bucket and allocation order

S06 sets add, per case:
  corruption/<case_tag>.json    list of CorruptionRecord (one per applied recipe; [] for F01)
  expected/<case_tag>.json      ExpectedEffects: clean vs visible reference, codes, abstentions
  clean_world/<case_tag>.json   the clean counterpart world before corruption
  clean/case_<case_tag>/        the clean counterpart rendered with the same tag and styles

``world`` is then the corrupted world, i.e. what the visible evidence says.

``reference`` is generator arithmetic over the world, not an ``OracleCase``; V04 builds the
oracle independently. The base format was agreed by V04 on 2026-10-28; the S06 additions above
are new files and manifest fields only, pending the same agreement.
"""

import hashlib
import json
import subprocess
from decimal import Decimal
from pathlib import Path

from benchmarks.generator.render import Rendered
from benchmarks.generator.world import World, kg, opaque, portal_counts

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
    """An end date before the transfer or the allocation voids the credit; no date is no end.

    A status that says the credit ended, with no dated event of that kind, cannot be ordered
    against the allocation: the credit is neither valid nor void on that evidence (UNKNOWN).
    """
    ends = [] if lot.expires_on is None else [("CREDIT_EXPIRED", lot.expires_on)]
    ends += [
        ("CREDIT_EXPIRED" if e.kind == "EXPIRED" else "CREDIT_CANCELLED", e.when[:10])
        for e in world.lifecycle
        if e.lot == lot.key
    ]
    status = {"EXPIRED": "CREDIT_EXPIRED", "CANCELLED": "CREDIT_CANCELLED"}.get(lot.status)
    undated = status is not None and not any(code == status for code, _ in ends)
    state = "UNKNOWN" if undated else "PASS"
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
        lot = lots[t.lot]
        # Evidence that cannot belong to the bucket at all is excluded before validity checks.
        if lot.metal != buckets[a.bucket].metal:
            outcomes[a.allocation_id] = _row(a, "EXCLUDED", "DIMENSION_MISMATCH")
            continue
        if t.recipient != "producer":
            outcomes[a.allocation_id] = _row(a, "EXCLUDED", "AMBIGUOUS_IDENTITY")
            continue
        lifecycle, code = _lifecycle(world, a, t, lot)
        capability = _capability(world, lot)
        if capability == "FAIL":
            code = code or "CAPABILITY_MISMATCH"
        excluded = "FAIL" in (lifecycle, capability)
        state = "EXCLUDED" if excluded else "INCLUDED"
        if not excluded and (t.duplicate_of is not None or t.stage != "COMPLETED"):
            # An unreconciled export is an unresolved event: observed, never supported.
            state, code = "PENDING", "AMBIGUOUS_EVENT"
        outcomes[a.allocation_id] = {
            "state": state,
            "lifecycle": lifecycle,
            "capability": capability,
            "priority": "NOT_EVALUATED",
            "excluded": excluded,
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
            if buckets[a.bucket] is not later or row["state"] != "INCLUDED":
                continue
            states = []
            for b in earlier:
                paid = [
                    o["_alloc"]
                    for o in outcomes.values()
                    if o["_alloc"].bucket == b.key and o["state"] == "INCLUDED"
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
                row["state"] = "EXCLUDED"
    return outcomes


def _row(a, state, code) -> dict:
    return {
        "state": state,
        "lifecycle": "NOT_EVALUATED",
        "capability": "NOT_EVALUATED",
        "priority": "NOT_EVALUATED",
        "excluded": state == "EXCLUDED",
        "code": code,
        "_alloc": a,
    }


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
    lots = {lot.key: lot for lot in world.lots}
    outcomes = allocation_outcomes(world)
    state = {k: o["state"] for k, o in outcomes.items()}
    rows = []
    for b in sorted(world.buckets, key=lambda b: b.bucket_id):
        required = Decimal(b.target_kg)
        mine = [a for a in world.allocations if a.bucket == b.key]
        supported = sum(
            (Decimal(a.quantity_kg) for a in mine if state[a.allocation_id] == "INCLUDED"),
            Decimal(0),
        )
        pending = sum(
            (Decimal(a.quantity_kg) for a in mine if state[a.allocation_id] == "PENDING"),
            Decimal(0),
        )
        pending += sum(
            (
                Decimal(i.quantity_kg)
                for i in world.invoices
                if i.bucket == b.key and transfers[i.transfer].stage != "COMPLETED"
            ),
            Decimal(0),
        )
        balance = next(x for x in world.balances if x.bucket == b.key)
        portal = Decimal(balance.reported_kg)
        recorded = sum(
            (
                Decimal(a.quantity_kg)
                for a in mine
                if portal_counts(
                    transfers[a.transfer], lots[transfers[a.transfer].lot], b, balance.cutoff
                )
            ),
            Decimal(0),
        )
        if portal != recorded:
            raise ValueError("the portal reports exactly the allocations it recorded")
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
    sources = sorted(GENERATOR_DIR.rglob("*.py"))
    digest = hashlib.sha256()
    for path in sources:
        name = path.relative_to(GENERATOR_DIR).as_posix()
        digest.update(name.encode() + b"\0" + path.read_bytes().replace(b"\r\n", b"\n"))
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


def fault_records(case, out: Rendered) -> tuple[list[dict], dict]:
    """CorruptionRecords and the draft expected effects of one S06 case (evaluator-only)."""
    from benchmarks.generator.faults.records import CorruptionRecord, ExpectedEffects
    from benchmarks.generator.faults.validate import asset_paths

    w = case.world
    records = [
        CorruptionRecord(
            corruption_id=f"corruption:{opaque(f'{w.case_tag}|{i}|{c.family}', 12)}",
            case_id=w.case_id,
            fault_family=c.family,
            affected_visible_asset_refs=asset_paths(case, out, c.assets),
            transformation=c.transformation,
            before_refs=list(c.before_refs),
            after_refs=list(c.after_refs),
            intended_evidence_effect=c.effect,
        ).model_dump(mode="json")
        for i, c in enumerate(case.changes)
    ]

    def union(name):
        return sorted({x for c in case.changes for x in getattr(c, name)})

    expected = ExpectedEffects(
        case_id=w.case_id,
        fault_families=case.families,
        expected_issue_codes=union("issue_codes"),
        required_abstentions=union("abstentions"),
        forbidden_actions=union("forbidden"),
        permitted_alternatives=union("permitted"),
        clean_reference_buckets=reference_balances(case.clean)["buckets"],
        visible_reference_buckets=reference_balances(w)["buckets"],
    ).model_dump(mode="json")
    return records, expected


def write_hidden(
    hidden_root: Path, worlds: list[World], rendered: list[Rendered], cases=None
) -> Path:
    """Write the hidden record; ``cases`` (S06 ``Corrupted``) adds corruption, expected effects
    and a rendered clean counterpart per case."""
    if not worlds:
        raise ValueError("nothing to record")
    version = worlds[0].dataset_version
    root = Path(hidden_root) / version
    blobs: dict[str, dict[str, str]] = {"world": {}, "visible_map": {}, "reference": {}}
    if cases is not None:
        from benchmarks.generator.render import render_case

        blobs |= {"corruption": {}, "expected": {}, "clean_world": {}}
        clean_root = root / "clean"
        for case, out in zip(cases, rendered, strict=True):
            records, expected = fault_records(case, out)
            render_case(case.clean, clean_root)
            for kind, payload in (
                ("corruption", records),
                ("expected", expected),
                ("clean_world", case.clean.to_json()),
            ):
                body = _bytes(payload)
                target = root / kind / f"{case.world.case_tag}.json"
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(body)
                blobs[kind][case.world.case_id] = hashlib.sha256(body).hexdigest()
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
        "corruption_manifest_blob": blobs.get("corruption"),
        "corruption_manifest_reason": (
            None
            if cases is not None
            else "S05 renders clean worlds only; faults arrive in S06"
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
    if cases is not None:
        manifest |= {
            "expected_effects_blob": blobs["expected"],
            "clean_world_blob": blobs["clean_world"],
            "clean_counterpart_root": "clean/",
            "fault_families": {c.world.case_id: c.families for c in cases},
        }
    (root / "generation_manifest.json").write_bytes(_bytes(manifest))
    return root


__all__ = ["SPLIT_POLICY", "generator_revision", "reference_balances", "write_hidden"]
