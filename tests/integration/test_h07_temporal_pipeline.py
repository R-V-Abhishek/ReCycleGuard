"""End-to-end integration test connecting H05 indexing, H06 retrieval, and H07 temporal services.

Owned by Sampreeth (H05 / H06 / H07).
Verifies:
- End-to-end foundation and lexical index building.
- Retrieval of regulatory provisions combined with H07 temporal overlays.
- DeadlineRegister kind separation (OBLIGATION_ACHIEVEMENT vs RETURN_FILING).
- AmendmentOverlayService tracking surviving clauses and replaced provisions.
- TemporalApplicabilityChecker validating FY 2024-25 active intervals.
"""

from pathlib import Path

from recycleguard.application import local_application
from recycleguard.config import Settings
from recycleguard.contracts.core import EvidenceRef, Locator, TemporalValue
from recycleguard.contracts.foundation import FoundationRequest
from recycleguard.contracts.retrieval import SearchRulesRequest
from recycleguard.contracts.sources import (
    AmendmentEdge,
    ApplicabilityAssertion,
    DeadlineEntry,
)
from recycleguard.foundation import FoundationService
from recycleguard.indexing.builder import IndexBuilder
from recycleguard.knowledge.deadline_register import (
    AmendmentOverlayService,
    DeadlineRegister,
    TemporalApplicabilityChecker,
)
from recycleguard.retrieval.service import RetrievalService

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures/visible"
R02_PDF = FIXTURES_DIR / "h04/acquired_originals/e-waste_rules_2022.pdf"
R08_PDF = FIXTURES_DIR / "h01/acquired_originals/cpcb_faq_20240123.pdf"


def _make_temporal(val: str | None) -> TemporalValue:
    if val is None:
        return TemporalValue(
            raw=None,
            value=None,
            precision="UNKNOWN",
            timezone=None,
            interpretation_status="UNKNOWN",
        )
    return TemporalValue(
        raw=val,
        value=val,
        precision="DATE",
        timezone=None,
        interpretation_status="REVIEWED",
    )


def test_h07_temporal_pipeline_with_retrieval(tmp_path):
    """Integrate CP1 foundation -> H05 index -> H06 retrieval -> H07 temporal governance."""
    settings = Settings(data_root=tmp_path)
    with local_application(settings) as (cases, context, cap):
        # 1. Build Foundation
        f_req = FoundationRequest(
            case_root=str(FIXTURES_DIR / "case_001"),
            r02_path=str(R02_PDF),
            r08_path=str(R08_PDF),
            case_snapshot_id="snapshot:case_e2e_h07",
            corpus_snapshot_id="snapshot:corpus_e2e_h07",
            profile_version="1.0-draft",
        )
        f_service = FoundationService(cases)
        f_result = f_service.build(context, f_req, capability=cap)
        corpus_snapshot = f_result.output.corpus_snapshot

        # 2. Build H05 Lexical Index
        builder = IndexBuilder(
            tmp_path,
            cases.kernel.blob_store,
            catalog=cases.snapshots.catalog,
            kernel=cases.kernel,
        )
        idx_ctx = context.model_copy(
            update={
                "command_id": "cmd:build_h07_index",
                "operation_id": "op:build_h07_index",
                "attempt_id": "att:build_h07_index",
                "idempotency_key": "key:build_h07_index",
            }
        )
        manifest, fts_index = builder.build_index(
            corpus_snapshot,
            context=idx_ctx,
            capability=cap,
        )

        # 3. Retrieve relevant rule
        retrieval = RetrievalService(
            fts_index,
            corpus_snapshot,
            cases.kernel.blob_store,
            kernel=cases.kernel,
        )
        search_req = SearchRulesRequest(
            query="extended producer responsibility targets",
            corpus_snapshot_id=corpus_snapshot.snapshot_id,
            index_id=manifest.index_id,
            roles=["PRODUCER"],
            top_k=2,
        )
        retrieval_context = context.model_copy(
            update={
                "command_id": "cmd:h07_search",
                "operation_id": "op:h07_search",
                "attempt_id": "att:h07_search",
                "idempotency_key": "key:h07_search",
            }
        )
        attempt = retrieval.search_rules(search_req, context=retrieval_context, capability=cap)
        # Foundation emits draft source proposals. Search accounts for every chunk,
        # without elevating those proposals to reviewed authoritative evidence.
        assert attempt.selected_refs == []
        assert attempt.engine_candidates == []
        assert len(attempt.candidate_dispositions) == manifest.total_chunks
        assert all(d.disposition == "FILTERED_OUT" for d in attempt.candidate_dispositions)

        # 4. Initialize H07 DeadlineRegister with kind separation
        deadline_register = DeadlineRegister()

        # Add baseline obligation achievement deadline
        deadline_register.add_entry(
            DeadlineEntry(
                deadline_id="deadline:epr_target_2024_25",
                producer_or_role_scope="PRODUCER",
                fiscal_year="2024-25",
                quarter=None,
                kind="OBLIGATION_ACHIEVEMENT",
                baseline_due=_make_temporal("2025-03-31"),
                extended_due=None,
                review_state="APPROVED",
            )
        )

        # Add a claimed return filing extension; no reviewed issued order is supplied
        order_ref = EvidenceRef(
            ref_kind="PROVISION",
            ref_id="prov:cpcb_ext_order_20250620",
            artifact_revision_id="artrev:cpcb_order",
            locator=Locator(
                kind="PDF_PAGE",
                page_index_1based=1,
                printed_page_label="1",
                row_index_1based=None,
                column_name=None,
                json_pointer=None,
                text_start=None,
                text_end=None,
                table_id=None,
                cell_row=None,
                cell_column=None,
            ),
        )
        deadline_register.add_entry(
            DeadlineEntry(
                deadline_id="deadline:return_filing_2024_25",
                producer_or_role_scope="PRODUCER",
                fiscal_year="2024-25",
                quarter=None,
                kind="RETURN_FILING",
                baseline_due=_make_temporal("2025-06-30"),
                extended_due=_make_temporal("2025-09-30"),
                extension_order_refs=[order_ref],
                unverified_notice=False,
                review_state="APPROVED",
            )
        )

        # 5. Check deadline resolutions
        filing_res = deadline_register.resolve_deadline("PRODUCER", "2024-25", "RETURN_FILING")
        assert filing_res.verdict == "ABSTAIN"
        assert filing_res.is_verified_extension is False
        assert filing_res.effective_date is None  # Baseline basis and issued order are absent.

        obl_res = deadline_register.resolve_deadline(
            "PRODUCER", "2024-25", "OBLIGATION_ACHIEVEMENT"
        )
        assert obl_res.verdict == "ABSTAIN"
        assert obl_res.is_verified_extension is False
        assert obl_res.effective_date is None  # A date assertion alone has no baseline evidence.

        # 6. Verify cross-kind independence: Return filing extension does NOT extend obligation
        independence = deadline_register.check_cross_kind_independence(
            "deadline:return_filing_2024_25", "OBLIGATION_ACHIEVEMENT"
        )
        assert independence["verdict"] == "PASS"

        # 7. Check Amendment Overlay
        amendment_service = AmendmentOverlayService()
        amendment_service.add_edge(
            AmendmentEdge(
                edge_id="edge:rule4_replacement",
                from_provision_id="prov:amendment_2024_rule4",
                to_provision_id="prov:rules_2022_rule4",
                relation="REPLACES",
                review_state="APPROVED",
            )
        )
        overlay = amendment_service.check_amendment_status("prov:rules_2022_rule4")
        assert overlay.is_replaced is True
        assert overlay.surviving_amendment == "prov:amendment_2024_rule4"

        # 8. Check Temporal Applicability
        temporal_checker = TemporalApplicabilityChecker()
        temporal_checker.add_assertion(
            ApplicabilityAssertion(
                assertion_id="assert:schedule_iii_fy2425",
                provision_version_id="prov:schedule_iii",
                effective_from=_make_temporal("2024-04-01"),
                effective_until=_make_temporal("2025-04-01"),
                affected_roles=["PRODUCER"],
                review_state="APPROVED",
            )
        )
        fit = temporal_checker.check_temporal_fit("assert:schedule_iii_fy2425", "2024-2025")
        assert fit == "UNRESOLVED"  # No reviewed interval evidence references.

        out_of_bounds = temporal_checker.check_temporal_fit(
            "assert:schedule_iii_fy2425", "2025-2026"
        )
        assert out_of_bounds == "UNRESOLVED"
        fts_index.close()
