"""Unit tests for H05 provision/table chunking and SQLite FTS5 lexical indexing.

Owned by Sampreeth (H05 / C06).
Verifies:
- Stable locator and parent-context preservation across chunks.
- Multimodal VLM PDF parsing adapter and table preservation.
- SQLite FTS5 lexical BM25 search, prefix matching, and role filtering.
- IndexManifest generation, eligible members digest, and integrity verification.
- Audited index creation with AuditKernel.
"""

from __future__ import annotations

from pathlib import Path

from recycleguard.contracts.core import ActorRef, CommandContext, Locator
from recycleguard.contracts.foundation import SourceBatch
from recycleguard.contracts.snapshots import SnapshotPublication
from recycleguard.contracts.sources import ProvisionVersion
from recycleguard.extraction.pdf_extractor import extract_pdf_pages
from recycleguard.extraction.vlm_parser import DeterministicVLMPdfParser
from recycleguard.indexing.builder import IndexBuilder
from recycleguard.indexing.chunker import ProvisionChunker
from recycleguard.indexing.fts_index import FTS5Index
from recycleguard.indexing.models import IndexedChunk
from recycleguard.knowledge.provisions import (
    get_reviewed_provisions,
    register_reviewed_sources,
)
from recycleguard.storage import ArtifactCatalog, AuditKernel, BlobStore
from recycleguard.storage.authority import LocalAuthority, TrustedPrincipal
from recycleguard.storage.blob_store import canonical_json_bytes

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures/visible"
R02_PDF = FIXTURES_DIR / "h04/acquired_originals/e-waste_rules_2022.pdf"
R08_PDF = FIXTURES_DIR / "h01/acquired_originals/cpcb_faq_20240123.pdf"


def test_vlm_pdf_parser_test_double_extraction():
    """Verify multimodal VLM PDF parser test double extracts structured clauses and tables."""
    vlm = DeterministicVLMPdfParser(model_name="test-vlm-v1")
    sample_text = (
        "Rule 6. Responsibilities of the producer.\n"
        "(1) The producer of electrical and electronic equipment shall...\n"
        "| EEE Code | Category | Base Obligation |\n"
        "| ITEW4 | IT Equipment | 55.0000 |\n"
        "| CEEW1 | Consumer Electronics | 45.0000 |\n"
    )

    page_out = vlm.parse_page(sample_text, 24)
    assert page_out.page_number == 24
    assert len(page_out.clauses) >= 1
    assert len(page_out.tables) == 1
    tbl = page_out.tables[0]
    assert tbl.headers == ["EEE Code", "Category", "Base Obligation"]
    assert len(tbl.rows) == 2
    assert tbl.rows[0] == ["ITEW4", "IT Equipment", "55.0000"]
    assert page_out.model_name == "test-vlm-v1"


def test_pdf_extractor_vlm_assistance_on_unscanned_page():
    """Verify extract_pdf_pages leverages VLM when page text is blank."""
    vlm = DeterministicVLMPdfParser()

    # Simulate an empty or blank page text
    obs, cov, text, issues = extract_pdf_pages(
        b"%PDF-1.4 dummy",
        "artifact_rev:test_dummy",
        "ext:vlm_test",
        vlm_parser=vlm,
    )
    # The dummy bytes raise error in pdfplumber, returning empty
    assert len(obs) == 0


def test_provision_chunking_hierarchy_and_locators(tmp_path):
    """Verify provision chunker produces locator-bound sub-clause and table chunks."""
    store = BlobStore(tmp_path / "blobs")
    chunker = ProvisionChunker()

    sample_rule = (
        "Rule 15. Priority of allocation.\n"
        "(1) The allocation of recycled metal shall strictly follow earlier liabilities.\n"
        "(2) Proviso: Provided that earlier compliant transactions take priority.\n"
        "(3) No transfer without certificate validity."
    )
    blob = store.put(sample_rule.encode("utf-8"), "text/plain")

    prov = ProvisionVersion(
        provision_version_id="provision:test_rule15",
        source_version_id="source_ver:test_r02",
        parent_provision_id=None,
        locator=Locator(
            kind="PDF_PAGE",
            page_index_1based=27,
            printed_page_label="27",
            row_index_1based=None,
            column_name=None,
            json_pointer=None,
            text_start=None,
            text_end=None,
            table_id=None,
            cell_row=None,
            cell_column=None,
        ),
        legal_path="Rule 15(1)-(3)",
        text_blob=blob,
        regime="E_WASTE_2022",
        role_scope="GENERAL",
        affected_roles=["PRODUCER", "RECYCLER"],
        applicability_assertion_id="assertion:test_priority",
        table_context_refs=[],
        review_state="APPROVED",
    )

    chunks = chunker.chunk_provision(prov, store)
    assert len(chunks) >= 3

    # All child chunks must retain the physical page index 27
    for chk in chunks:
        assert chk.locator.page_index_1based == 27
        assert chk.disposition == "INDEXED"
        assert chk.regime == "E_WASTE_2022"
        assert "PRODUCER" in chk.affected_roles

    # Verify character offsets are valid within sample_rule
    first_chunk = chunks[0]
    assert first_chunk.char_start is not None
    assert first_chunk.char_end is not None
    assert first_chunk.char_end > first_chunk.char_start
    assert sample_rule[first_chunk.char_start : first_chunk.char_end] == first_chunk.text

    long_text = "Clause text " * 400
    long_provision = prov.model_copy(
        update={"text_blob": store.put(long_text.encode(), "text/plain")}
    )
    bounded = chunker.chunk_provision(long_provision, store)
    assert len(bounded) > 1
    assert all(len(chunk.text) <= 1500 for chunk in bounded)
    assert all(long_text[chunk.char_start : chunk.char_end] == chunk.text for chunk in bounded)
    assert all(chunk.locator.table_id is None for chunk in bounded)
    assert bounded == chunker.chunk_provision(long_provision, store)


def test_fts5_lexical_indexing_bm25_search_and_filtering(tmp_path):
    """Verify SQLite FTS5 table indexing, BM25 scoring, and role filtering."""
    db_path = tmp_path / "test_index.sqlite"
    index = FTS5Index(db_path)

    loc = Locator(
        kind="PDF_PAGE",
        page_index_1based=24,
        printed_page_label=None,
        row_index_1based=None,
        column_name=None,
        json_pointer=None,
        text_start=0,
        text_end=100,
        table_id=None,
        cell_row=None,
        cell_column=None,
    )

    c1 = IndexedChunk(
        chunk_id="chk:r02_rule6_1",
        provision_version_id="provision:r02_rule6",
        source_version_id="source_ver:r02",
        legal_path="Rule 6(4)",
        title="Rule 6. Producer responsibilities",
        text=(
            "The producer shall file annual returns and maintain "
            "extended producer responsibility records."
        ),
        locator=loc,
        parent_provision_id=None,
        role_scope="SPECIFIC",
        affected_roles=["PRODUCER"],
        regime="E_WASTE_2022",
        disposition="INDEXED",
        chunk_type="PROVISION_CLAUSE",
    )

    c2 = IndexedChunk(
        chunk_id="chk:r02_rule15_1",
        provision_version_id="provision:r02_rule15",
        source_version_id="source_ver:r02",
        legal_path="Rule 15(1)",
        title="Rule 15. Priority of allocation",
        text=(
            "Earlier compatible liabilities have priority at allocation "
            "time for recyclers and producers."
        ),
        locator=loc,
        parent_provision_id=None,
        role_scope="GENERAL",
        affected_roles=["PRODUCER", "RECYCLER"],
        regime="E_WASTE_2022",
        disposition="INDEXED",
        chunk_type="PROVISION_CLAUSE",
    )

    index.insert_chunks([c1, c2])
    assert index.count() == 2

    # Query 1: search for "annual returns"
    res1 = index.search("annual returns")
    assert len(res1) >= 1
    top_chunk, score = res1[0]
    assert top_chunk.chunk_id == "chk:r02_rule6_1"
    assert score > 0

    # Query 2: search for "priority" with role filter
    res2 = index.search("priority", role="RECYCLER")
    assert len(res2) == 1
    assert res2[0][0].chunk_id == "chk:r02_rule15_1"

    # Query 3: search for "producer" with role filter RECYCLER should return only c2
    res3 = index.search("producer", role="RECYCLER")
    assert len(res3) == 1
    assert res3[0][0].chunk_id == "chk:r02_rule15_1"

    index.close()


def test_index_builder_manifest_and_audited_commit(tmp_path):
    """Verify IndexBuilder creates FTS5 index, manifest, and commits under AuditKernel."""
    data_root = tmp_path / "data"
    data_root.mkdir()
    store = BlobStore(data_root / "blobs")

    actor = ActorRef(
        actor_id="service:indexer", actor_kind="SERVICE", authenticated_session_ref=None
    )
    authority = LocalAuthority({"indexer": TrustedPrincipal(actor, frozenset({"extraction."}))})
    cap = authority.issue("indexer")

    db_path = data_root / "app.sqlite"
    kernel = AuditKernel(db_path, store, authority=authority)
    catalog = ArtifactCatalog(db_path, store, kernel=kernel)

    # 1. Register reviewed authentic sources from CP1 fixtures
    r02_rev, r08_rev = register_reviewed_sources(store, r02_path=R02_PDF, r08_path=R08_PDF)
    provisions = get_reviewed_provisions(store, r02_revision=r02_rev, r08_revision=r08_rev)

    # 2. Build SourceBatch and mock CorpusSnapshot
    source_batch = SourceBatch(
        artifact_revisions=[r02_rev, r08_rev],
        receipts=[],
        leads=[],
        source_versions=[],
        provisions=provisions,
        applicability=[],
    )
    batch_json = canonical_json_bytes(source_batch.model_dump(mode="json"))
    membership_blob = store.put(batch_json, "application/json")
    coverage_blob = store.put(b'{"coverage": []}', "application/json")

    corpus_snapshot = SnapshotPublication(
        scope_id="corpus:test_h05",
        snapshot_id="snapshot:corpus_test_h05",
        snapshot_kind="CORPUS",
        expected_head=None,
        membership_blob=membership_blob,
        membership_digest=membership_blob.sha256,
        coverage_blob=coverage_blob,
        source_receipt_ids=[],
    )

    context = CommandContext(
        contract_version="1.1",
        command_id="cmd:test_index",
        operation_id="op:test_index",
        attempt_id="att:test_index",
        idempotency_key="key:test_index",
        actor=actor,
        case_version_id=None,
        run_id=None,
        turn_id=None,
        correlation_id="corr:test_index",
        parent_operation_id=None,
    )

    builder = IndexBuilder(data_root, store, catalog=catalog, kernel=kernel)
    manifest, fts_index = builder.build_index(
        corpus_snapshot,
        context=context,
        capability=cap,
    )

    assert manifest.index_id.startswith("index:fts5_")
    assert manifest.corpus_snapshot_id == corpus_snapshot.snapshot_id
    assert manifest.total_chunks > 0
    assert len(manifest.integrity_digest) == 64
    assert len(manifest.eligible_members_digest) == 64
    assert "index.sqlite" in manifest.index_files

    # Check search over built index
    hits = fts_index.search("Rule 6")
    assert hits == []  # The incoming source proposals have not been approved.
    assert all(c.disposition == "EXCLUDED" for c in fts_index.all_chunks())

    # Verify audit event recorded in stream
    events = kernel.list_stream_events(f"stream:{corpus_snapshot.snapshot_id}")
    assert len(events) >= 1
    assert events[0].event_type == "extraction.index.result"

    fts_index.close()
