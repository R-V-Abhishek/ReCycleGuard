"""Regulatory knowledge, provision review, and calculation profile support.

Owned by Sampreeth (H04 / C06 / C07).
"""

from recycleguard.knowledge.profile_v1 import (
    build_v1_calculation_profile,
    build_v1_profile_definition,
)
from recycleguard.knowledge.provisions import (
    R02_ARTIFACT_REV_ID,
    R02_RULE_6_4_TEXT,
    R02_RULE_15_1_3_TEXT,
    R08_ARTIFACT_REV_ID,
    R08_SECTION_C_TEXT,
    get_reviewed_provisions,
    register_reviewed_sources,
)

__all__ = [
    "R02_ARTIFACT_REV_ID",
    "R02_RULE_6_4_TEXT",
    "R02_RULE_15_1_3_TEXT",
    "R08_ARTIFACT_REV_ID",
    "R08_SECTION_C_TEXT",
    "build_v1_calculation_profile",
    "build_v1_profile_definition",
    "get_reviewed_provisions",
    "register_reviewed_sources",
]
