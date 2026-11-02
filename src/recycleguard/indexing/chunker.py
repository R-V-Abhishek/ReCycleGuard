"""Segment provisions and tables into stable indexed chunks.

Owned by Sampreeth (H05).
Follows CONTRACTS §6.1 and SYSTEM_DESIGN §4:
- Chunks provisions by sub-rule, paragraph, proviso, and table rows.
- Preserves parent-child hierarchy and exact physical page/row locators.
- Emits explicit dispositions (INDEXED, EXCLUDED, UNINDEXABLE).
- Indexes reviewed extraction output; optional OCR/VLM belongs before corpus review.
"""

import hashlib
import re

from recycleguard.contracts.sources import ProvisionVersion
from recycleguard.extraction.vlm_parser import VLMPdfParser
from recycleguard.indexing.models import IndexedChunk
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
        if max_chunk_chars < 1 or not 0 <= chunk_overlap < max_chunk_chars:
            raise ValueError("chunk overlap must be nonnegative and smaller than chunk size")
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
        text = text_bytes.decode("utf-8")

        content_id = hashlib.sha256((provision.provision_version_id + text).encode()).hexdigest()[
            :24
        ]
        if not text.strip():
            # Unindexable empty provision
            return [
                IndexedChunk(
                    chunk_id=f"chk:{content_id}",
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
            and provision.review_state == "APPROVED"
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

        spans = []
        cursor = 0
        for segment in segments:
            start = text.index(segment, cursor)
            cursor = start + len(segment)
            for offset in range(0, len(segment), self.max_chunk_chars - self.chunk_overlap):
                end = min(offset + self.max_chunk_chars, len(segment))
                spans.append((start + offset, start + end))
                if end == len(segment):
                    break
        chunks: list[IndexedChunk] = []
        for idx, (start_offset, end_offset) in enumerate(spans, 1):
            segment = text[start_offset:end_offset]
            is_table_row = "|" in segment and segment.count("|") >= 2
            chunk_type = "TABLE_ROW" if is_table_row else "PROVISION_CLAUSE"
            chunk_locator = provision.locator.model_copy(
                update={
                    "text_start": start_offset,
                    "text_end": end_offset,
                }
            )

            # Extract heading if present (e.g. "(1)", "Rule 6", etc.)
            first_line = segment.split("\n", 1)[0].strip()
            title = first_line[:80] if len(first_line) <= 80 else None

            # Generate stable deterministic chunk ID from provision and index
            chunk_id = f"chk:{content_id}_s{idx}"

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
                    metadata={"segment_index": idx, "total_segments": len(spans)},
                )
            )

        # OCR/VLM extraction belongs before reviewed corpus publication. Indexing
        # never synthesizes unreviewed table observations from legal source text.
        return chunks
