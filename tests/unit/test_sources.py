"""Unit tests for source leads loading, validation, and metadata integrity."""

from pathlib import Path

from recycleguard.intake import load_source_leads, validate_lead_manifest

MANIFEST_PATH = Path(__file__).resolve().parents[2] / "configs/sources/source_leads.jsonl"


def test_source_leads_manifest_loads_and_validates():
    assert MANIFEST_PATH.is_file()
    leads = load_source_leads(MANIFEST_PATH)
    assert len(leads) == 29

    is_valid, issues = validate_lead_manifest(leads)
    assert is_valid, f"Validation issues: {issues}"


def test_priority_p0_leads_present():
    leads = load_source_leads(MANIFEST_PATH)
    lead_ids = {lead.source_lead_id for lead in leads}

    expected_p0 = {
        "source_lead:r02",
        "source_lead:r03",
        "source_lead:r04",
        "source_lead:r05",
        "source_lead:r06",
        "source_lead:r07",
        "source_lead:r08",
        "source_lead:r09",
        "source_lead:r10",
        "source_lead:r11",
    }
    missing = expected_p0 - lead_ids
    assert not missing, f"Missing P0 leads: {missing}"


def test_aliases_preserve_legacy_prefixes():
    leads = load_source_leads(MANIFEST_PATH)
    lead_map = {lead.source_lead_id: lead for lead in leads}

    assert "domain:R02" in lead_map["source_lead:r02"].aliases
    assert "cpcb:R02" in lead_map["source_lead:r02"].aliases
    assert "domain:R08" in lead_map["source_lead:r08"].aliases
    assert "cpcb:R08" in lead_map["source_lead:r08"].aliases


def test_gazette_asset_rights_seed():
    leads = load_source_leads(MANIFEST_PATH)
    gazette_leads = [lead for lead in leads if lead.source_class == "GAZETTE_RULE"]
    assert len(gazette_leads) >= 5

    for lead in gazette_leads:
        assert lead.rights_and_license.asset_rights_seed == "REVIEW_REQUIRED"
        assert lead.rights_and_license.redistribution_allowed is False
        assert "Section 52" in (lead.rights_and_license.statutory_exception_sec52 or "")


def test_official_urls_valid_syntax():
    leads = load_source_leads(MANIFEST_PATH)
    for lead in leads:
        assert lead.official_url.startswith(("http://", "https://"))
        assert len(lead.official_url) > 10
