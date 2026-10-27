"""C06 Index builder and integrity manifest generator.

Owned by Sampreeth (H05).
Implements CONTRACTS §6.1:
build_index(corpus_snapshot_id, retrieval_configuration_id) -> IndexManifest.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

from recycleguard.contracts.audit import OperationIntent, OperationResult
from recycleguard.contracts.foundation import SourceBatch
from recycleguard.contracts.retrieval import IndexManifest, LexicalConfiguration
from recycleguard.contracts.snapshots import SnapshotPublication
from recycleguard.indexing.chunker import ProvisionChunker
from recycleguard.indexing.fts_index import FTS5Index
from recycleguard.storage.blob_store import canonical_json_bytes

if TYPE_CHECKING:
    from recycleguard.contracts.core import CommandContext
    from recycleguard.extraction.vlm_parser import VLMPdfParser
    from recycleguard.storage.audit_kernel import AuditKernel
    from recycleguard.storage.authority import Capability
    from recycleguard.storage.blob_store import BlobStore
    from recycleguard.storage.catalog import ArtifactCatalog


class IndexBuilder:
    """Builds frozen SQLite FTS5 lexical index and integrity manifest."""

    def __init__(
        self,
        data_root: Path | str,
        blob_store: BlobStore,
        *,
        catalog: ArtifactCatalog | None = None,
        kernel: AuditKernel | None = None,
        vlm_parser: VLMPdfParser | None = None,
    ):
        self.data_root = Path(data_root)
        self.blob_store = blob_store
        self.catalog = catalog
        self.kernel = kernel
        self.vlm_parser = vlm_parser
        self.chunker = ProvisionChunker(vlm_parser=vlm_parser)

    def build_index(
        self,
        corpus_snapshot: SnapshotPublication,
        retrieval_configuration_id: str = "config:lexical_fts5_v1",
        *,
        context: CommandContext | None = None,
        capability: Capability | None = None,
    ) -> tuple[IndexManifest, FTS5Index]:
        """Build frozen index from corpus snapshot and return manifest with index handle."""
        index_id = f"index:fts5_{uuid4().hex[:12]}"
        index_dir = self.data_root / "indexes" / index_id.replace(":", "_")
        index_dir.mkdir(parents=True, exist_ok=True)
        db_path = index_dir / "index.sqlite"

        # 1. Load corpus snapshot membership
        raw_membership = self.blob_store.get(corpus_snapshot.membership_blob)
        membership_dict = json.loads(raw_membership.decode("utf-8"))
        source_batch = SourceBatch.model_validate(membership_dict)

        # 2. Chunk provisions
        all_chunks = []
        for prov in source_batch.provisions:
            chunks = self.chunker.chunk_provision(prov, self.blob_store)
            all_chunks.extend(chunks)

        # 3. Build FTS5 index
        lex_cfg = LexicalConfiguration()
        fts_index = FTS5Index(db_path, config=lex_cfg)
        fts_index.insert_chunks(all_chunks)

        # 4. Compute digests
        # Eligible members digest: sha256 of sorted provision entries
        eligible_entries = sorted(
            [
                {
                    "provision_version_id": p.provision_version_id,
                    "legal_path": p.legal_path,
                    "regime": p.regime,
                    "text_sha256": p.text_blob.sha256,
                }
                for p in source_batch.provisions
                if p.review_state in {"APPROVED", "DRAFT"}
            ],
            key=lambda x: x["provision_version_id"],
        )
        eligible_digest = hashlib.sha256(canonical_json_bytes(eligible_entries)).hexdigest()

        # Database file integrity digest
        db_bytes = db_path.read_bytes()
        integrity_digest = hashlib.sha256(db_bytes).hexdigest()

        # 5. Create IndexManifest
        manifest = IndexManifest(
            index_id=index_id,
            corpus_snapshot_id=corpus_snapshot.snapshot_id,
            eligible_members_digest=eligible_digest,
            extraction_versions={
                "provision_chunker": "1.0",
                "pdf_extractor": "1.0",
                "sqlite_fts5": "fts5-unicode61",
            },
            lexical_configuration=lex_cfg,
            dense_configuration_or_null=None,
            build_code_revision="git:cp2_h05_release",
            index_files=[str(db_path.name)],
            integrity_digest=integrity_digest,
            total_chunks=len(all_chunks),
        )

        # 6. Save manifest to disk
        manifest_path = index_dir / "index_manifest.json"
        manifest_path.write_text(manifest.model_dump_json(indent=2))

        # 7. Audited persistence if kernel and capability are supplied
        if self.kernel is not None and capability is not None and context is not None:
            manifest_blob = self.blob_store.put(
                canonical_json_bytes(manifest.model_dump(mode="json")), "application/json"
            )
            intent = OperationIntent(
                context=context,
                idempotency_key=context.idempotency_key,
                event_type="extraction.index",
                payload=manifest_blob,
                stream_id=f"stream:{index_id}",
            )
            self.kernel.commit_intent(intent, capability=capability)

            result = OperationResult(
                operation_id=context.operation_id,
                attempt_id=context.attempt_id,
                status="SUCCESS",
                payload=manifest_blob,
                issue_codes=[],
            )
            self.kernel.commit_result(intent, result, capability=capability)

        return manifest, fts_index
