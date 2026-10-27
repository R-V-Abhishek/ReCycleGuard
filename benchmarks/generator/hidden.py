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

SPLIT_POLICY = "DEV_ONLY_S05"
GENERATOR_DIR = Path(__file__).resolve().parent


def _bytes(payload) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n").encode()


def reference_balances(world: World) -> dict:
    """Independent world arithmetic: required - supported = signed gap; pending is separate."""
    transfers = {t.key: t for t in world.transfers}
    rows = []
    for b in sorted(world.buckets, key=lambda b: b.bucket_id):
        required = Decimal(b.target_kg)
        supported = sum(
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
    return {
        "case_id": world.case_id,
        "buckets": rows,
        "allocation_order": {a.allocation_id: a.order for a in world.allocations},
        "basis": "generator world arithmetic; not an OracleCase",
    }


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
        "corruption_manifest_reason": "S05 renders clean worlds only; faults arrive in S06",
        "oracle_blob": None,
        "oracle_reason": "OracleCase is built independently by V04 from these records",
        "reference_blob": blobs["reference"],
        "visible_map_blob": blobs["visible_map"],
        "split_policy": SPLIT_POLICY,
        "rights_manifest_ref": "rights:synthetic_fixture",
        "timeline_groups": {w.case_id: w.timeline_group for w in worlds},
        "templates": {w.case_id: w.template_key for w in worlds},
    }
    (root / "generation_manifest.json").write_bytes(_bytes(manifest))
    return root


__all__ = ["SPLIT_POLICY", "generator_revision", "reference_balances", "write_hidden"]
