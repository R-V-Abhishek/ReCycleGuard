"""CSV row-level extractor and coverage tracker.

Owned by Sampreeth (H03 / C03).
Guarantees:
- Every data row (1-based, excluding header) receives a terminal disposition.
- Discovered rows match sum of terminal dispositions (PARSED, QUARANTINED, FAILED).
- Generates Observation records with raw_fields, parsed_fields, and CSV_ROW locators.
"""

import csv
import io
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from recycleguard.contracts.core import Issue, Locator, TemporalValue
from recycleguard.contracts.extraction import CoverageItem, Observation


def _utc_now_rfc3339() -> str:
    return datetime.now(UTC).isoformat()


def extract_csv(
    content_bytes: bytes,
    artifact_revision_id: str,
    extraction_id: str,
    *,
    capture_time: TemporalValue | None = None,
) -> tuple[list[Observation], list[CoverageItem], list[Issue]]:
    """Extract observations and coverage items from CSV bytes."""
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
    stream = io.StringIO(text)
    reader = csv.reader(stream)

    try:
        header = next(reader)
    except StopIteration:
        # Empty file
        return observations, coverage_items, issues

    header = [h.strip() for h in header]
    expected_cols = len(header)

    row_index = 0
    for row in reader:
        row_index += 1  # 1-based data row
        locator = Locator(
            kind="CSV_ROW",
            page_index_1based=None,
            printed_page_label=None,
            row_index_1based=row_index,
            column_name=None,
            json_pointer=None,
            text_start=None,
            text_end=None,
            table_id=None,
            cell_row=None,
            cell_column=None,
        )

        # Check for malformed row (e.g. column count mismatch)
        if len(row) != expected_cols:
            cov_id = f"cov:{uuid4().hex[:12]}"
            coverage_items.append(
                CoverageItem(
                    coverage_item_id=cov_id,
                    artifact_revision_id=artifact_revision_id,
                    locator=locator,
                    disposition="QUARANTINED",
                    reason_code="CSV_COLUMN_COUNT_MISMATCH",
                    child_observation_ids=[],
                )
            )
            issues.append(
                Issue(
                    issue_id=f"issue:{uuid4().hex[:8]}",
                    code="INCOMPLETE_COVERAGE",
                    severity="WARNING",
                    message=(
                        f"Row {row_index} column count {len(row)} does not match "
                        f"header {expected_cols}"
                    ),
                    field_path=f"row:{row_index}",
                    evidence_refs=[],
                    retryable=False,
                )
            )
            continue

        # Build raw and parsed fields
        raw_fields: dict[str, Any] = {}
        parsed_fields: dict[str, Any] = {}
        for col_name, val in zip(header, row, strict=False):
            raw_fields[col_name] = val
            clean_val = val.strip()
            # Parsing a CSV cell never changes its decimal or identifier representation.
            parsed_fields[col_name] = clean_val

        obs_id = f"obs:{uuid4().hex[:12]}"
        obs = Observation(
            observation_id=obs_id,
            extraction_id=extraction_id,
            artifact_revision_id=artifact_revision_id,
            locator=locator,
            observation_type="CSV_RECORD",
            raw_fields=raw_fields,
            parsed_fields=parsed_fields,
            validation_state="VALID",
            extraction_method="CSV",
            field_quality={"quality": "PARSED_CSV_ROW"},
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
                reason_code="CSV_ROW_PARSED",
                child_observation_ids=[obs_id],
            )
        )

    return observations, coverage_items, issues
