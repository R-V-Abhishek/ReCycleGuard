"""S06 development set: committed bytes, uniform surface, leakage and the hidden fault record."""

import csv
import hashlib
import io
import json
import re
from pathlib import Path
from typing import get_args

from benchmarks.generator import generate
from benchmarks.generator.faults import recipes as r
from benchmarks.generator.hidden import write_hidden
from benchmarks.generator.pdf_style import WATERMARK
from benchmarks.generator.render import S06_LEDGER_HEADER, render_case
from benchmarks.generator.s04_cases import build_s04_worlds
from benchmarks.generator.s05_cases import build_worlds
from benchmarks.generator.s06_cases import DATASET_VERSION, build_s06_cases
from recycleguard.contracts.results import FaultFamily
from recycleguard.extraction.pdf_extractor import extract_pdf_pages

VISIBLE = Path(__file__).resolve().parents[1] / "fixtures" / "visible"
CASES = build_s06_cases()


def _case(c) -> Path:
    return VISIBLE / f"case_{c.world.case_tag}"


def _pdf_text(path: Path) -> tuple[list, str]:
    _, coverage, text, _ = extract_pdf_pages(path.read_bytes(), "art:check", "ext:check")
    return coverage, text


def _identifiers(d: Path) -> list[str]:
    text = "\n".join(
        p.read_text("utf-8").lower() for p in d.rglob("*") if p.suffix in {".jsonl", ".json"}
    )
    ids = re.findall(r"\"[a-z_]*(?:_id|_ref|_tag)\":\s*\"([^\"]*)\"", text)
    return ids + [p.name.lower() for p in d.rglob("*")]


def test_regeneration_is_byte_identical_to_the_committed_cases(tmp_path):
    for case in CASES:
        out = render_case(case.world, tmp_path)
        assert generate._differences(out.case_dir, _case(case)) == [], case.world.template_key


def test_sets_have_distinct_versions_and_tags():
    assert {c.world.dataset_version for c in CASES} == {DATASET_VERSION}
    tags = [w.case_tag for w in (*build_worlds(), *build_s04_worlds())]
    tags += [c.world.case_tag for c in CASES]
    assert len(tags) == len(set(tags)) == 6 + 6 + 21
    assert all(c.world.case_tag == c.clean.case_tag for c in CASES)  # paired by tag


def test_every_dossier_has_the_same_surface():
    """Columns, fields, annexures and the notice note never reveal which case is faulty."""
    for case in CASES:
        d = _case(case)
        ledger = next((d / "documents").glob("ledger_*.csv")).read_text("utf-8")
        assert tuple(next(csv.reader(io.StringIO(ledger)))) == S06_LEDGER_HEADER
        assert len(list((d / "documents").glob("notice_*.pdf"))) == 1
        for portal in (d / "documents").glob("portal_*.json"):
            rows = json.loads(portal.read_text("utf-8"))["portal_transactions"]
            assert all("remarks" in row for row in rows)
        events = [
            json.loads(x) for x in (d / "records/certificate_events.jsonl").read_text().splitlines()
        ]
        certificates = {e["certificate_id"] for e in events}
        generated = {e["certificate_id"] for e in events if e["event_kind"] == "GENERATED"}
        assert generated == certificates
        coverage, text = _pdf_text(next((d / "documents").glob("memo_*.pdf")))
        stated = int(text.split("Page 1 of ", 1)[1].split()[0])
        assert stated >= 3  # body, then Annexure A and Annexure B on their own pages
        lost = any(c.disposition == "QUARANTINED" for c in coverage) or len(coverage) < stated
        assert "Annexure A" in text or lost


def test_visible_files_leak_no_generation_truth():
    families = set(get_args(FaultFamily))
    hidden = {
        "fault",
        "corrupt",
        "oracle",
        "hidden",
        "template",
        "seed",
        "recipe",
        "s06-dev",
        *(f.lower() for f in families),
        *(f.split("_", 1)[0].lower() + "_" for f in families),
        *(recipe.key for recipe in r.RECIPES.values()),
    }
    for case in CASES:
        d = _case(case)
        text = "\n".join(
            p.read_text("utf-8")
            for p in sorted(d.rglob("*"))
            if p.suffix in {".jsonl", ".csv", ".json"}
        )
        text += "\n".join(_pdf_text(p)[1] for p in sorted(d.rglob("*.pdf")))
        lowered = text.lower()
        for term in hidden | {case.world.timeline_group}:
            assert term.lower() not in lowered, (case.world.template_key, term)
        # Template keys are ordinary words ("alias", "notice"), so they may appear in prose, status
        # values and the shared surface; they must never shape this dossier's own identifiers.
        key = case.world.template_key
        own = " ".join(_identifiers(d))
        shared = all(key in " ".join(_identifiers(_case(other))) for other in CASES)
        assert shared or key not in own, key
        for change in case.changes:
            assert change.transformation.lower() not in lowered
        names = " ".join(p.name.lower() for p in d.rglob("*"))
        assert not any(t in names for t in ("clean", "fault", "f0", "f1", "inject", "stale"))


def test_every_pdf_page_with_text_carries_the_watermark():
    for case in CASES:
        for pdf in sorted(_case(case).rglob("*.pdf")):
            _, coverage, _, _ = extract_pdf_pages(pdf.read_bytes(), "art:check", "ext:check")
            observations, _, text, _ = extract_pdf_pages(pdf.read_bytes(), "art:check", "ext:check")
            for obs in observations:
                assert WATERMARK in obs.parsed_fields["text"], pdf.name
            assert len(observations) + sum(c.disposition == "QUARANTINED" for c in coverage) >= 1


def test_hidden_record_carries_corruptions_expectations_and_clean_counterparts(tmp_path):
    rendered = [render_case(c.world, tmp_path / "visible") for c in CASES]
    root = write_hidden(tmp_path / "hidden", [c.world for c in CASES], rendered, cases=list(CASES))
    manifest = json.loads((root / "generation_manifest.json").read_text())
    assert manifest["split_policy"] == "DEV_ONLY_S06"
    assert manifest["oracle_blob"] is None
    assert manifest["corruption_manifest_reason"] is None
    for case in CASES:
        tag, case_id = case.world.case_tag, case.world.case_id
        for kind, blob in (
            ("corruption", "corruption_manifest_blob"),
            ("expected", "expected_effects_blob"),
        ):
            body = (root / kind / f"{tag}.json").read_bytes()
            assert manifest[blob][case_id] == hashlib.sha256(body).hexdigest()
        assert (root / "clean" / f"case_{tag}" / "case_manifest.json").is_file()
        assert manifest["fault_families"][case_id] == case.families
        records = json.loads((root / "corruption" / f"{tag}.json").read_text())
        assert [x["fault_family"] for x in records] == [c.family for c in case.changes]
    # The hidden root never lands inside the visible root, and nothing hidden is committed.
    assert ".gitignore" and "benchmarks/hidden/" in (VISIBLE.parents[2] / ".gitignore").read_text()
