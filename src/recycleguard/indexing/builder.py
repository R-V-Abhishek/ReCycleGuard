"""Pinned, auditable construction of a readonly lexical index over frozen originals."""

import hashlib
import os
import tempfile
from pathlib import Path

from recycleguard.contracts.audit import OperationIntent, OperationResult
from recycleguard.contracts.retrieval import IndexManifest, LexicalConfiguration
from recycleguard.indexing.chunker import ProvisionChunker
from recycleguard.indexing.corpus import load_corpus
from recycleguard.indexing.fts_index import FTS5Index
from recycleguard.storage import canonical_json_bytes
from recycleguard.storage.authority import AuthorizationError


class IndexBuilder:
    def __init__(self, data_root, blob_store, *, catalog=None, kernel=None, vlm_parser=None):
        self.data_root, self.blob_store = Path(data_root), blob_store
        self.catalog, self.kernel = catalog, kernel
        self.chunker = ProvisionChunker(vlm_parser=vlm_parser)

    def _open(self, manifest):
        path = self.data_root / "indexes" / manifest.index_id.replace(":", "_") / "index.sqlite"
        if manifest.index_blob is None:
            raise ValueError("index manifest lacks immutable database reference")
        original = self.blob_store.get(manifest.index_blob)
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(original)
        if hashlib.sha256(path.read_bytes()).hexdigest() != manifest.integrity_digest:
            raise ValueError("frozen index bytes differ from the manifest")
        self.blob_store.get(manifest.index_blob)
        index = FTS5Index(path, config=manifest.lexical_configuration, readonly=True)
        index.manifest = manifest
        return manifest, index

    def build_index(
        self,
        corpus_snapshot,
        retrieval_configuration_id="config:lexical_fts5_v1",
        *,
        context=None,
        capability=None,
    ):
        intent = None
        request = {
            "snapshot_id": corpus_snapshot.snapshot_id,
            "membership_digest": corpus_snapshot.membership_digest,
            "retrieval_configuration_id": retrieval_configuration_id,
            "chunker_version": "cp3-reviewed-2",
        }
        if self.kernel is not None:
            if context is None or capability is None:
                raise AuthorizationError(
                    "audited index construction requires context and capability"
                )
            if context.actor.actor_kind != "SERVICE":
                raise AuthorizationError("index construction requires a trusted SERVICE")
            self.kernel.authority.check(capability, context.actor, "extraction.index")
            intent = OperationIntent(
                context=context,
                idempotency_key=context.idempotency_key,
                event_type="extraction.index",
                payload=self.blob_store.put(canonical_json_bytes(request), "application/json"),
                stream_id=f"stream:{context.run_id or corpus_snapshot.snapshot_id}",
            )
            self.kernel.commit_intent(intent, capability=capability)
            previous = self.kernel.get_result(context.operation_id)
            if previous is not None:
                manifest = IndexManifest.model_validate_json(self.blob_store.get(previous.payload))
                return self._open(manifest)
        view = load_corpus(corpus_snapshot, self.blob_store)
        sources = {source.source_version_id: source for source in view.batch.source_versions}
        chunks = [
            chunk
            for provision in view.batch.provisions
            for chunk in self.chunker.chunk_provision(provision, self.blob_store)
        ]
        for position, chunk in enumerate(chunks):
            source = sources.get(chunk.source_version_id)
            eligible = (
                view.approved
                and source is not None
                and source.review_state == "APPROVED"
                and source.completeness == "COMPLETE_TEXT"
            )
            if chunk.disposition == "INDEXED" and not eligible:
                chunks[position] = chunk.model_copy(update={"disposition": "EXCLUDED"})
        digest = hashlib.sha256(canonical_json_bytes(request)).hexdigest()
        index_id = f"index:fts5_{digest[:24]}"
        directory = self.data_root / "indexes" / index_id.replace(":", "_")
        directory.mkdir(parents=True, exist_ok=True)
        descriptor, name = tempfile.mkstemp(suffix=".sqlite", dir=directory)
        os.close(descriptor)
        temporary = Path(name)
        configuration = LexicalConfiguration()
        try:
            index = FTS5Index(temporary, config=configuration)
            try:
                index.insert_chunks(chunks)
            finally:
                index.close()
            raw = temporary.read_bytes()
            database_blob = self.blob_store.put(raw, "application/vnd.sqlite3")
            destination = directory / "index.sqlite"
            if destination.exists():
                if destination.read_bytes() != raw:
                    raise ValueError("existing frozen index differs; refusing to overwrite")
            else:
                os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
        members = [
            p.model_dump(mode="json")
            for p in sorted(view.batch.provisions, key=lambda p: p.provision_version_id)
        ]
        manifest = IndexManifest(
            index_id=index_id,
            corpus_snapshot_id=corpus_snapshot.snapshot_id,
            eligible_members_digest=hashlib.sha256(canonical_json_bytes(members)).hexdigest(),
            extraction_versions={"provision_chunker": "cp3-reviewed-2", "sqlite_fts5": "unicode61"},
            lexical_configuration=configuration,
            dense_configuration_or_null=None,
            build_code_revision="cp3-reviewed-2",
            index_files=["index.sqlite"],
            integrity_digest=database_blob.sha256,
            total_chunks=len(chunks),
            corpus_membership_digest=corpus_snapshot.membership_digest,
            index_blob=database_blob,
            retrieval_configuration_id=retrieval_configuration_id,
        )
        manifest_blob = self.blob_store.put(
            canonical_json_bytes(manifest.model_dump(mode="json")), "application/json"
        )
        (directory / "index_manifest.json").write_bytes(self.blob_store.get(manifest_blob))
        if intent is not None:
            self.kernel.commit_result(
                intent,
                OperationResult(
                    operation_id=context.operation_id,
                    attempt_id=context.attempt_id,
                    status="SUCCESS",
                    payload=manifest_blob,
                    output_refs=[database_blob],
                ),
                capability=capability,
            )
        return self._open(manifest)
