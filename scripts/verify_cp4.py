"""Summarize executed CP4 regression evidence without inventing gate approval.

Consume pytest's actual JUnit output. A passing mapped test group records only
regression evidence; a human still checks the required demonstration and its
runtime boundary. This script cannot approve CP4 or promote scripted model tests
into scientific agent evaluation.
"""

import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Annotated

import typer

GATES = {
    "G01": ("Intake completeness", ["test_h02_intake", "test_h03_extraction"]),
    "G02": ("Provenance", ["test_a05_baseline", "test_v02_storage"]),
    "G03": ("Numeric safety", ["test_quantities", "test_reconciliation"]),
    "G04": ("Lifecycle", ["test_event_equivalence", "test_s04_lifecycle"]),
    "G05": ("Allocation", ["test_allocation_conservation", "test_s04_checks"]),
    "G06": ("Temporal RAG", ["test_h07_temporal", "test_h07_temporal_pipeline"]),
    "G07": ("Retrieval transparency", ["test_h06_retrieval", "test_h08_frozen_audit"]),
    "G08": ("Injection boundary", ["test_a06_workflow", "test_a07_tools"]),
    "G09": (
        "Recovery",
        ["test_v02_regressions", "test_a06_usage_recovery", "test_cp4_recovery"],
    ),
    "G10": ("Review/export", ["test_v05_review", "test_review_export", "test_v06_export_replay"]),
    "G11": ("Oracle isolation", ["test_runtime_isolation"]),
    "G12": ("Evaluation honesty", ["test_v04_oracle", "test_v09_oracle", "test_s07_pilot"]),
}

REVIEW_REQUIREMENTS = {
    "G09": "Inspect failure-window evidence and authoritative recovery, not just clean restarts.",
    "G10": "Verify actual self-contained bundle replay and denied rights through derivatives.",
    "G11": (
        "Demonstrate enforced investigator process/filesystem isolation and durable "
        "denied-access audit; helper-only checks are insufficient."
    ),
    "G12": (
        "Require independent visible-reference review, complete pilot seal and honest "
        "trial denominators; unit arithmetic alone is insufficient."
    ),
}


def summarize(junit: Path) -> dict:
    raw = junit.read_bytes()
    root = ET.fromstring(raw)
    cases = list(root.iter("testcase"))
    if not cases:
        raise ValueError("JUnit evidence contains no executed test cases")
    rows = []
    for gate, (title, modules) in GATES.items():
        matched = [
            case
            for case in cases
            if any(module in case.get("classname", "").split(".") for module in modules)
        ]
        failures = sum(case.find("failure") is not None for case in matched)
        errors = sum(case.find("error") is not None for case in matched)
        skipped = sum(case.find("skipped") is not None for case in matched)
        found = {
            module
            for module in modules
            for case in matched
            if module in case.get("classname", "").split(".")
        }
        missing = sorted(set(modules) - found)
        status = "TESTS_PASSED_REVIEW_REQUIRED"
        if failures or errors:
            status = "FAILED"
        elif missing or skipped:
            status = "INCOMPLETE_EVIDENCE"
        rows.append(
            {
                "gate": gate,
                "title": title,
                "status": status,
                "tests": len(matched),
                "failures": failures,
                "errors": errors,
                "skipped": skipped,
                "missing_modules": missing,
                "review_requirement": REVIEW_REQUIREMENTS.get(
                    gate, "Check the actual G01–G12 demonstration in SYSTEM_DESIGN.md section 10."
                ),
            }
        )
    failed_count = sum(case.find("failure") is not None for case in cases)
    error_count = sum(case.find("error") is not None for case in cases)
    return {
        "checkpoint": "CP4",
        "status": "BLOCKED" if failed_count or error_count else "REVIEW_REQUIRED",
        "failed_tests": failed_count,
        "errored_tests": error_count,
        "scope": "Executed regression evidence only; no checkpoint or model-quality approval.",
        "junit_sha256": hashlib.sha256(raw).hexdigest(),
        "executed_tests": len(cases),
        "gates": rows,
    }


def main(
    junit: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
    output: Annotated[Path, typer.Option()],
):
    """Summarize a real pytest --junitxml=PATH result without approving CP4."""
    if output.exists():
        raise typer.BadParameter("output must be a new file; preserve previous evidence")
    result = summarize(junit)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    typer.echo(f"Recorded {result['executed_tests']} tests; CP4 status: {result['status']}")


if __name__ == "__main__":
    typer.run(main)
