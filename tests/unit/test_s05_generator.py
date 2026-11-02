"""S05 clean-world generator: determinism, contracts, invariants, watermark, leakage, diversity."""

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pdfplumber
import pytest

from benchmarks.generator import generate
from benchmarks.generator.documents import indian_date, indian_group, rupees_in_words
from benchmarks.generator.hidden import reference_balances
from benchmarks.generator.invariants import (
    REAL_CIN,
    REAL_GSTIN,
    REAL_PAN,
    WorldInvariantError,
    check_world,
)
from benchmarks.generator.pdf_style import WATERMARK
from benchmarks.generator.render import render_case
from benchmarks.generator.s05_cases import build_worlds
from benchmarks.generator.starter_world import build_case_001
from recycleguard.contracts.domain import RECORD_ADAPTER
from recycleguard.contracts.dossier import CaseManifest

VISIBLE = Path(__file__).resolve().parents[1] / "fixtures" / "visible"
WORLDS = build_worlds()
CASES = [VISIBLE / f"case_{w.case_tag}" for w in WORLDS]
RECORD_FILES = {
    "entities",
    "registrations",
    "obligations",
    "certificates",
    "certificate_events",
    "allocations",
    "commercial_records",
    "account_balances",
}


def _pdf_text(path: Path) -> str:
    with pdfplumber.open(path) as doc:
        return "\n".join(page.extract_text() or "" for page in doc.pages)


def _visible_text(case: Path) -> str:
    parts = []
    for path in sorted(case.rglob("*")):
        if path.is_file():
            parts.append(path.relative_to(case).as_posix())
            parts.append(_pdf_text(path) if path.suffix == ".pdf" else path.read_text("utf-8"))
    return "\n".join(parts)


def test_regeneration_is_byte_identical_to_the_committed_cases(tmp_path):
    for world, case in zip(WORLDS, CASES, strict=True):
        out = render_case(world, tmp_path)
        assert generate._differences(out.case_dir, case) == [], case.name


def test_manifests_validate_and_declare_exactly_the_files_on_disk():
    for case in CASES:
        manifest = CaseManifest.model_validate_json((case / "case_manifest.json").read_bytes())
        declared = {a.relative_path: a for a in manifest.assets}
        on_disk = {
            p.relative_to(case).as_posix()
            for p in case.rglob("*")
            if p.is_file() and p.name != "case_manifest.json"
        }
        assert set(declared) == on_disk
        for rel, asset in declared.items():
            body = (case / rel).read_bytes()
            assert (hashlib.sha256(body).hexdigest(), len(body)) == (
                asset.body_digest,
                asset.byte_length,
            )
        assert manifest.case_id == f"case:{case.name.split('_', 1)[1]}"


def test_world_invariants_hold_and_violations_are_caught():
    for world in WORLDS:
        check_world(world)
    world = next(w for w in WORLDS if len(w.allocations) > 1)
    inflated = replace(world.allocations[0], quantity_kg="999999.0000")
    with pytest.raises(WorldInvariantError):
        check_world(replace(world, allocations=(inflated, *world.allocations[1:])))
    with pytest.raises(WorldInvariantError):
        check_world(replace(world, producer=replace(world.producer, domain="real-company.in")))


def test_records_are_contract_valid_and_carry_no_binary_floats():
    def reject(value):
        raise AssertionError(f"binary float or nonfinite value: {value}")

    for case in CASES:
        for path in (case / "records").glob("*.jsonl"):
            for line in path.read_text("utf-8").splitlines():
                row = json.loads(line, parse_float=reject, parse_constant=reject)
                if path.stem in RECORD_FILES:
                    assert RECORD_ADAPTER.validate_json(line).record_id == row["record_id"]
            assert path.read_bytes().endswith(b"\n") and b"\r" not in path.read_bytes()


def test_every_pdf_has_a_true_watermark_and_clean_extractable_text():
    for world, case in zip(WORLDS, CASES, strict=True):
        pdfs = sorted((case / "documents").glob("*.pdf"))
        assert len(pdfs) == len(world.invoices) + 1
        for pdf in pdfs:
            raw = pdf.read_bytes()
            assert b"/Subtype /Watermark" in raw and b"/GSwm gs" in raw  # vector layer
            text = _pdf_text(pdf)
            assert WATERMARK in text.splitlines()  # extractable footer, its own line
            assert not text.splitlines()[0].startswith("SYNTHETIC")  # no top banner
        for invoice in world.invoices:
            texts = [_pdf_text(p) for p in pdfs if p.name.startswith("invoice")]
            match = [t for t in texts if invoice.number in t]
            assert len(match) == 1 and "TAX INVOICE" in match[0]
            # Watermark strokes are paths, so figures extract intact.
            assert indian_group(invoice.quantity_kg, 4) + " KG" in match[0]


def test_identities_are_unmistakably_synthetic():
    for case in CASES:
        text = _visible_text(case)
        assert not REAL_GSTIN.search(text) and not REAL_PAN.search(text)
        assert not REAL_CIN.search(text)
        for line in (case / "records/entities.jsonl").read_text("utf-8").splitlines():
            entity = json.loads(line)
            assert "synth" in entity["legal_name"].lower() and entity["synthetic"] is True
            assert all(i["value"].startswith("SYNTH") for i in entity["identifiers"])


def test_visible_files_leak_no_generation_truth():
    hidden_terms = {"clean", "fault", "oracle", "hidden", "template", "seed", "s05-dev"}
    for world in WORLDS:
        hidden_terms |= {world.template_key, world.timeline_group}
    for case in CASES:
        lowered = _visible_text(case).lower()
        for term in hidden_terms:
            assert term.lower() not in lowered, (case.name, term)
        for path in case.rglob("*"):
            assert not any(w in path.name for w in ("f0", "gap", "expected", "answer"))
    gitignore = (VISIBLE.parents[2] / ".gitignore").read_text("utf-8")
    assert "benchmarks/hidden/" in gitignore.splitlines()


def test_cases_are_diverse_in_parties_shapes_and_document_styles(tmp_path):
    assert len({w.producer.legal_name for w in WORLDS}) == 6
    assert len({w.timeline_group for w in WORLDS}) == 6
    assert len({w.template_key for w in WORLDS}) == 6
    styles = [s for w in WORLDS for s in render_case(w, tmp_path).styles.values()]
    papers = {s["style"]["paper_name"] for s in styles}
    inks = {s["style"]["ink_name"] for s in styles}
    families = {s["style"]["family"] for s in styles}
    sizes = {s["style"]["body_size"] for s in styles}
    assert len(papers) >= 4 and len(inks) >= 4 and families == {"sans", "serif"}
    assert len(sizes) >= 2


def test_reference_arithmetic_covers_each_shape():
    refs = {w.template_key: reference_balances(w)["buckets"] for w in WORLDS}
    assert refs["exact_coverage"][0]["signed_gap"] == "0.0000"
    assert refs["overlap_and_paid_pending"][0]["pending"] != "0.0000"
    assert refs["surplus"][0]["signed_gap"].startswith("-")
    assert {b["metal"] for b in refs["two_metals"]} == {"AL", "CU"}
    assert {b["liability_year"] for b in refs["historical_shared_lot"]} == {
        "2023-2024",
        "2024-2025",
    }
    tonne = next(w for w in WORLDS if w.template_key == "tonne_two_recyclers")
    assert tonne.buckets[0].supplied_unit == "TONNE" and len(tonne.recyclers) == 2
    for rows in refs.values():
        for row in rows:
            assert row["delta_portal_minus_supported"] == "0.0000"  # clean worlds agree


def test_indian_number_money_and_date_conventions():
    assert indian_group("12345678.5") == "1,23,45,678.50"
    assert indian_group("999.5", 4) == "999.5000"
    assert rupees_in_words("360513.60") == (
        "Indian Rupees Three Lakh Sixty Thousand Five Hundred Thirteen and Sixty Paise Only"
    )
    assert rupees_in_words("12000000") == "Indian Rupees One Crore Twenty Lakh Only"
    assert indian_date("2025-04-03", "ordinal") == "3rd April, 2025"
    assert indian_date("2024-08-17", "tally") == "17-Aug-2024"


def test_legacy_invoice_layout_stays_byte_identical_for_case_001(tmp_path):
    build_case_001(tmp_path)
    produced = tmp_path / "visible/case_001/documents/doc_invoice_payment.pdf"
    assert (
        produced.read_bytes()
        == (VISIBLE / "case_001/documents/doc_invoice_payment.pdf").read_bytes()
    )


def test_cli_writes_hidden_record_outside_the_visible_root(tmp_path):
    visible, hidden = tmp_path / "visible", tmp_path / "hidden"
    assert generate.main(["--visible-root", str(visible), "--hidden-root", str(hidden)]) == 0
    assert (
        generate.main(["--visible-root", str(visible), "--hidden-root", str(hidden), "--check"])
        == 0
    )
    record = hidden / WORLDS[0].dataset_version
    manifest = json.loads((record / "generation_manifest.json").read_text("utf-8"))
    assert manifest["case_ids"] == [w.case_id for w in WORLDS]
    assert manifest["split_policy"] == "DEV_ONLY_S05" and manifest["oracle_blob"] is None
    for kind in ("world", "visible_map", "reference"):
        assert len(list((record / kind).glob("*.json"))) == 6
    assert not any(p.name.endswith("generation_manifest.json") for p in visible.rglob("*"))
    with pytest.raises(SystemExit):
        generate.main(["--visible-root", str(tmp_path), "--hidden-root", str(hidden)])
