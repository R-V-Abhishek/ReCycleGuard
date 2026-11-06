"""Ablation switches off deterministic findings for an evaluation, and nothing else."""

from recycleguard.contracts.results import FindingRecord
from recycleguard.reporting.calculation_findings import ablate


def finding(family):
    return FindingRecord.model_construct(issue_type=family, finding_id=f"finding:{family}")


FINDINGS = [finding("F09_EXPIRED_CANCELLED"), finding("F11_WRONG_PERIOD_RULE")]
CONTRADICTED = {"F02_OVERLAPPING_EXPORT", "F10_CAPABILITY_MISMATCH"}


def test_an_ablated_family_loses_its_finding_and_can_no_longer_contradict_the_model():
    kept, contradicted = ablate(
        FINDINGS, CONTRADICTED, ["F09_EXPIRED_CANCELLED", "F02_OVERLAPPING_EXPORT"]
    )
    assert [f.issue_type for f in kept] == ["F11_WRONG_PERIOD_RULE"]
    assert contradicted == {"F10_CAPABILITY_MISMATCH"}


def test_no_ablation_changes_nothing():
    kept, contradicted = ablate(FINDINGS, CONTRADICTED, [])
    assert kept == FINDINGS and contradicted == CONTRADICTED
