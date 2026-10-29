"""Segment provisions and tables into stable indexed chunks.

Owned by Sampreeth (H05).
Follows CONTRACTS §6.1 and SYSTEM_DESIGN §4:
- Chunks provisions by sub-rule, paragraph, proviso, and table rows.
- Preserves parent-child hierarchy and exact physical page/row locators.
- Emits explicit dispositions (INDEXED, EXCLUDED, UNINDEXABLE).
- Integrates optional VLM multimodal table parsing when enabled.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING
from uuid import uuid4

from recycleguard.contracts.core import Locator
from recycleguard.contracts.sources import ProvisionVersion
from recycleguard.indexing.models import IndexedChunk

if TYPE_CHECKING:
    from recycleguard.extraction.vlm_parser import VLMPdfParser
    from recycleguard.storage.blob_store import BlobStore


class ProvisionChunker:
    """Deterministic segmenter for regulatory texts and tables."""

    def __init__(
        self,
        *,
        max_chunk_chars: int = 1500,
        chunk_overlap: int = 100,
        vlm_parser: VLMPdfParser | None = None,
    ):
        self.max_chunk_chars = max_chunk_chars
        self.chunk_overlap = chunk_overlap
        self.vlm_parser = vlm_parser

    def chunk_provision(
        self,
        provision: ProvisionVersion,
        blob_store: BlobStore,
    ) -> list[IndexedChunk]:
        """Segment a ProvisionVersion into stable, locator-bound chunks."""
        text_bytes = blob_store.get(provision.text_blob)
        text = text_bytes.decode("utf-8", errors="replace")

        if not text.strip():
            # Unindexable empty provision
            return [
                IndexedChunk(
                    chunk_id=f"chk:{uuid4().hex[:12]}",
                    provision_version_id=provision.provision_version_id,
                    source_version_id=provision.source_version_id,
                    legal_path=provision.legal_path,
                    title=None,
                    text="",
                    locator=provision.locator,
                    parent_provision_id=provision.parent_provision_id,
                    role_scope=provision.role_scope,
                    affected_roles=provision.affected_roles,
                    regime=provision.regime,
                    disposition="UNINDEXABLE",
                    chunk_type="PROVISION_CLAUSE",
                )
            ]

        # Check for wrong regime or unreviewed status
        disposition = (
            "INDEXED"
            if provision.regime in {"E_WASTE_2022", "E_WASTE_2016"}
            and provision.review_state in {"APPROVED", "DRAFT"}
            else "EXCLUDED"
        )

        # Detect sub-clauses using regex patterns like (1), (2), (a), (b), Provided that, etc.
        sub_clause_pattern = re.compile(
            r"(?=(?:^|\n)\s*(?:\(\d+\)|\([a-z]\)|(?:Provided\s+(?:further\s+)?that)|(?:Explanation\s*[\.:\-]))\s*)",
            re.IGNORECASE,
        )

        segments = sub_clause_pattern.split(text)
        segments = [s.strip() for s in segments if s.strip()]

        # If no regex sub-clauses found or only one huge segment, chunk by paragraphs or max_chars
        if len(segments) <= 1:
            paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
            segments = paragraphs if len(paragraphs) > 1 else [text.strip()]

        chunks: list[IndexedChunk] = []
        cursor = 0

        for idx, segment in enumerate(segments, 1):
            # Check for tabular row content
            is_table_row = "|" in segment and segment.count("|") >= 2
            chunk_type = "TABLE_ROW" if is_table_row else "PROVISION_CLAUSE"

            # Derive locator with character offsets
            start_offset = text.find(segment, cursor)
            if start_offset == -1:
                start_offset = cursor
            end_offset = start_offset + len(segment)
            cursor = end_offset

            chunk_locator = Locator(
                kind=provision.locator.kind,
                page_index_1based=provision.locator.page_index_1based,
                printed_page_label=provision.locator.printed_page_label,
                row_index_1based=idx if is_table_row else None,
                column_name=None,
                json_pointer=None,
                text_start=start_offset,
                text_end=end_offset,
                table_id=f"tbl:{provision.provision_version_id}" if is_table_row else None,
                cell_row=idx if is_table_row else None,
                cell_column=None,
            )

            # Extract heading if present (e.g. "(1)", "Rule 6", etc.)
            first_line = segment.split("\n", 1)[0].strip()
            title = first_line[:80] if len(first_line) <= 80 else None

            # Generate stable deterministic chunk ID from provision and index
            chunk_id = f"chk:{provision.provision_version_id.replace('provision:', '')}_s{idx}"

            chunks.append(
                IndexedChunk(
                    chunk_id=chunk_id,
                    provision_version_id=provision.provision_version_id,
                    source_version_id=provision.source_version_id,
                    legal_path=provision.legal_path,
                    title=title,
                    text=segment,
                    locator=chunk_locator,
                    parent_provision_id=provision.parent_provision_id,
                    role_scope=provision.role_scope,
                    affected_roles=provision.affected_roles,
                    regime=provision.regime,
                    disposition=disposition,
                    chunk_type=chunk_type,
                    char_start=start_offset,
                    char_end=end_offset,
                    metadata={"segment_index": idx, "total_segments": len(segments)},
                )
            )

        # If VLM parser is provided, also run VLM table extraction to enhance any table chunks
        if self.vlm_parser is not None and any(c.chunk_type == "TABLE_ROW" for c in chunks):
            try:
                vlm_out = self.vlm_parser.parse_page(text, provision.locator.page_index_1based or 1)
                for tbl in vlm_out.tables:
                    for r_idx, row_cells in enumerate(tbl.rows, 1):
                        row_text = " | ".join(row_cells)
                        base_id = provision.provision_version_id.replace("provision:", "")
                        vlm_chunk_id = f"chk:{base_id}_vlm_t{r_idx}"
                        vlm_locator = Locator(
                            kind="PDF_TABLE_CELL",
                            page_index_1based=provision.locator.page_index_1based,
                            printed_page_label=provision.locator.printed_page_label,
                            row_index_1based=r_idx,
                            column_name=tbl.headers[0] if tbl.headers else None,
                            json_pointer=None,
                            text_start=None,
                            text_end=None,
                            table_id=tbl.table_id,
                            cell_row=r_idx,
                            cell_column=1,
                        )
                        chunks.append(
                            IndexedChunk(
                                chunk_id=vlm_chunk_id,
                                provision_version_id=provision.provision_version_id,
                                source_version_id=provision.source_version_id,
                                legal_path=f"{provision.legal_path} > {tbl.table_id} row {r_idx}",
                                title=tbl.caption,
                                text=row_text,
                                locator=vlm_locator,
                                parent_provision_id=provision.provision_version_id,
                                role_scope=provision.role_scope,
                                affected_roles=provision.affected_roles,
                                regime=provision.regime,
                                disposition=disposition,
                                chunk_type="TABLE_ROW",
                                metadata={"vlm_parsed": True, "headers": tbl.headers},
                            )
                        )
            except Exception:
                pass

        return chunks
