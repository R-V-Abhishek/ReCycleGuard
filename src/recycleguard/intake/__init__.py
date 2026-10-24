"""Intake and source acquisition support.

Owned by Sampreeth (C01 / H01 / H02).
"""

import json
from pathlib import Path

from pydantic import ValidationError

from recycleguard.contracts.sources import SourceLead


def load_source_leads(manifest_path: str | Path) -> list[SourceLead]:
    """Load and validate all SourceLead entries from a JSONL manifest."""
    path = Path(manifest_path)
    if not path.is_file():
        raise FileNotFoundError(f"source leads manifest not found: {path}")

    leads: list[SourceLead] = []
    with path.open("r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            try:
                data = json.loads(stripped)
                lead = SourceLead.model_validate(data)
                leads.append(lead)
            except (json.JSONDecodeError, ValidationError) as exc:
                raise ValueError(f"invalid SourceLead at line {line_num}: {exc}") from exc

    return leads


def validate_lead_manifest(leads: list[SourceLead]) -> tuple[bool, list[str]]:
    """Validate cross-entry invariants for source leads."""
    issues: list[str] = []
    seen_ids: set[str] = set()

    for lead in leads:
        if lead.source_lead_id in seen_ids:
            issues.append(f"duplicate source_lead_id: {lead.source_lead_id}")
        seen_ids.add(lead.source_lead_id)

        # Gazette seeds must have REVIEW_REQUIRED asset rights seed
        if lead.source_class == "GAZETTE_RULE":
            if lead.rights_and_license.asset_rights_seed != "REVIEW_REQUIRED":
                issues.append(
                    f"{lead.source_lead_id}: Gazette rule must have "
                    "REVIEW_REQUIRED asset rights seed"
                )
            if lead.rights_and_license.redistribution_allowed:
                issues.append(
                    f"{lead.source_lead_id}: Gazette rule cannot automatically seed "
                    "redistribution_allowed=True"
                )

    return (len(issues) == 0, issues)


__all__ = ["SourceLead", "load_source_leads", "validate_lead_manifest"]
