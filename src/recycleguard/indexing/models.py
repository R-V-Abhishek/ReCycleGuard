"""Data models for C06 chunking and index construction.

Owned by Sampreeth (H05).
"""

from typing import Any, Literal

from pydantic import Field

from recycleguard.contracts.core import BoundaryModel, Locator
from recycleguard.contracts.sources import Role

ChunkDisposition = Literal["INDEXED", "EXCLUDED", "UNINDEXABLE"]
ChunkType = Literal["PROVISION_CLAUSE", "TABLE_ROW", "PAGE_SECTION", "TABLE_CELL"]


class IndexedChunk(BoundaryModel):
    """Segmented unit of regulatory or table text with stable locator (CONTRACTS §6.1)."""

    chunk_id: str
    provision_version_id: str
    source_version_id: str
    legal_path: str
    title: str | None = None
    text: str
    locator: Locator
    parent_provision_id: str | None = None
    role_scope: str = "GENERAL"
    affected_roles: list[Role] = Field(default_factory=list)
    regime: str = "E_WASTE_2022"
    disposition: ChunkDisposition = "INDEXED"
    chunk_type: ChunkType = "PROVISION_CLAUSE"
    char_start: int | None = None
    char_end: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
