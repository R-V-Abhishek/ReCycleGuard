"""JSON and JSONL extractor with coverage tracking.

Owned by Sampreeth (H03 / C03).
Handles JSONL line-by-line and JSON document structures.
Emits observations and coverage items with JSON_POINTER locators.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from recycleguard.contracts.core import Issue, Locator, TemporalValue
from recycleguard.contracts.extraction import CoverageItem, Observation


def _utc_now_rfc3339() -> str:
    return datetime.now(timezone.utc).isoformat()


def extract_json(
    content_bytes: bytes,
    artifact_revision_id: str,
    extraction_id: str,
    *,
    is_jsonl: bool = False,
    capture_time: TemporalValue | None = None,
) -> tuple[list[Observation], list[CoverageItem], list[Issue]]:
    """Extract observations and coverage items from JSON or JSONL bytes."""
    observations: list[Observation] = []
    coverage_items: list[CoverageItem] = []
    issues: list[Issue] = []

    cap_time = capture_time or TemporalValue(
        raw=None,
        value=_utc_now_rfc3339()[:10],
        precision="DATE",
        timezone=None,
        interpretation_status="PARSED",
    )
    ingestion_time = _utc_now_rfc3339()

    text = content_bytes.decode("utf-8", errors="replace")

    if is_jsonl or (not text.strip().startswith("[") and not text.strip().startswith("{")):
        # JSONL format: line by line
        lines = text.splitlines()
        for idx, line in enumerate(lines, 1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue

            ptr = f"/{idx}"
            locator = Locator(
                kind="JSON_POINTER",
                page_index_1based=None,
                printed_page_label=None,
                row_index_1based=None,
                column_name=None,
                json_pointer=ptr,
                text_start=None,
                text_end=None,
                table_id=None,
                cell_row=None,
                cell_column=None,
            )

            try:
                data = json.loads(stripped)
                obs_id = f"obs:{uuid4().hex[:12]}"
                obs = Observation(
                    observation_id=obs_id,
                    extraction_id=extraction_id,
                    artifact_revision_id=artifact_revision_id,
                    locator=locator,
                    observation_type="JSON_RECORD",
                    raw_fields=data if isinstance(data, dict) else {"value": data},
                    parsed_fields=data if isinstance(data, dict) else {"value": data},
                    validation_state="VALID",
                    extraction_method="JSON",
                    field_quality={"quality": "PARSED_JSON_LINE"},
                    event_time=cap_time,
                    source_capture_time=cap_time,
                    ingestion_time=ingestion_time,
                )
                observations.append(obs)

                cov_id = f"cov:{uuid4().hex[:12]}"
                coverage_items.append(
                    CoverageItem(
                        coverage_item_id=cov_id,
                        artifact_revision_id=artifact_revision_id,
                        locator=locator,
                        disposition="PARSED",
                        reason_code="JSON_PARSED",
                        child_observation_ids=[obs_id],
                    )
                )
            except json.JSONDecodeError as exc:
                cov_id = f"cov:{uuid4().hex[:12]}"
                coverage_items.append(
                    CoverageItem(
                        coverage_item_id=cov_id,
                        artifact_revision_id=artifact_revision_id,
                        locator=locator,
                        disposition="QUARANTINED",
                        reason_code="JSON_DECODE_ERROR",
                        child_observation_ids=[],
                    )
                )
                issues.append(
                    Issue(
                        issue_id=f"issue:{uuid4().hex[:8]}",
                        code="INVALID_SCHEMA",
                        severity="WARNING",
                        message=f"JSON decode failed on line {idx}: {exc}",
                        field_path=f"line:{idx}",
                        evidence_refs=[],
                        retryable=False,
                    )
                )
    else:
        # Single JSON object or list
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                for idx, item in enumerate(parsed):
                    ptr = f"/{idx}"
                    locator = Locator(
                        kind="JSON_POINTER",
                        page_index_1based=None,
                        printed_page_label=None,
                        row_index_1based=None,
                        column_name=None,
                        json_pointer=ptr,
                        text_start=None,
                        text_end=None,
                        table_id=None,
                        cell_row=None,
                        cell_column=None,
                    )
                    obs_id = f"obs:{uuid4().hex[:12]}"
                    obs = Observation(
                        observation_id=obs_id,
                        extraction_id=extraction_id,
                        artifact_revision_id=artifact_revision_id,
                        locator=locator,
                        observation_type="JSON_RECORD",
                        raw_fields=item if isinstance(item, dict) else {"value": item},
                        parsed_fields=item if isinstance(item, dict) else {"value": item},
                        validation_state="VALID",
                        extraction_method="JSON",
                        field_quality={"quality": "PARSED_JSON_ITEM"},
                        event_time=cap_time,
                        source_capture_time=cap_time,
                        ingestion_time=ingestion_time,
                    )
                    observations.append(obs)
                    cov_id = f"cov:{uuid4().hex[:12]}"
                    coverage_items.append(
                        CoverageItem(
                            coverage_item_id=cov_id,
                            artifact_revision_id=artifact_revision_id,
                            locator=locator,
                            disposition="PARSED",
                            reason_code="JSON_PARSED",
                            child_observation_ids=[obs_id],
                        )
                    )
            elif isinstance(parsed, dict):
                ptr = "/"
                locator = Locator(
                    kind="JSON_POINTER",
                    page_index_1based=None,
                    printed_page_label=None,
                    row_index_1based=None,
                    column_name=None,
                    json_pointer=ptr,
                    text_start=None,
                    text_end=None,
                    table_id=None,
                    cell_row=None,
                    cell_column=None,
                )
                obs_id = f"obs:{uuid4().hex[:12]}"
                obs = Observation(
                    observation_id=obs_id,
                    extraction_id=extraction_id,
                    artifact_revision_id=artifact_revision_id,
                    locator=locator,
                    observation_type="JSON_OBJECT",
                    raw_fields=parsed,
                    parsed_fields=parsed,
                    validation_state="VALID",
                    extraction_method="JSON",
                    field_quality={"quality": "PARSED_JSON_OBJECT"},
                    event_time=cap_time,
                    source_capture_time=cap_time,
                    ingestion_time=ingestion_time,
                )
                observations.append(obs)
                cov_id = f"cov:{uuid4().hex[:12]}"
                coverage_items.append(
                    CoverageItem(
                        coverage_item_id=cov_id,
                        artifact_revision_id=artifact_revision_id,
                        locator=locator,
                        disposition="PARSED",
                        reason_code="JSON_PARSED",
                        child_observation_ids=[obs_id],
                    )
                )
        except json.JSONDecodeError as exc:
            locator = Locator(
                kind="JSON_POINTER",
                page_index_1based=None,
                printed_page_label=None,
                row_index_1based=None,
                column_name=None,
                json_pointer="/",
                text_start=None,
                text_end=None,
                table_id=None,
                cell_row=None,
                cell_column=None,
            )
            cov_id = f"cov:{uuid4().hex[:12]}"
            coverage_items.append(
                CoverageItem(
                    coverage_item_id=cov_id,
                    artifact_revision_id=artifact_revision_id,
                    locator=locator,
                    disposition="FAILED",
                    reason_code="JSON_DECODE_ERROR",
                    child_observation_ids=[],
                )
            )
            issues.append(
                Issue(
                    issue_id=f"issue:{uuid4().hex[:8]}",
                    code="INVALID_SCHEMA",
                    severity="BLOCKING",
                    message=f"JSON document parsing failed: {exc}",
                    field_path="/",
                    evidence_refs=[],
                    retryable=False,
                )
            )

    return observations, coverage_items, issues
