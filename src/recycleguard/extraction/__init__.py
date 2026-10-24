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
    terminal_dispositions = {"PARSED", "QUARANTINED", "EXCLUDED", "FAILED", "NOT_APPLICABLE"}
    terminal_count = sum(1 for item in items if item.disposition in terminal_dispositions)
    return terminal_count == discovered_rows


__all__ = [
    "CoverageItem",
    "ExtractionResult",
    "Observation",
    "validate_row_coverage_consistency",
]
