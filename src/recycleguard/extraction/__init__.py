"""Extraction and coverage support.

Owned by Sampreeth (C03 / H01 / H03).
"""

from recycleguard.contracts.extraction import (
    CoverageItem,
    ExtractionResult,
    Observation,
)


def validate_row_coverage_consistency(discovered_rows: int, items: list[CoverageItem]) -> bool:
    """For row-based sources, terminal row dispositions must sum to discovered rows."""
    if discovered_rows < 0:
        return False
    if any(item.locator.kind != "CSV_ROW" for item in items):
        return False
    if len({item.artifact_revision_id for item in items}) > 1:
        return False
    rows = [item.locator.row_index_1based for item in items]
    return len(rows) == discovered_rows and set(rows) == set(range(1, discovered_rows + 1))


__all__ = [
    "CoverageItem",
    "ExtractionResult",
    "Observation",
    "validate_row_coverage_consistency",
]
