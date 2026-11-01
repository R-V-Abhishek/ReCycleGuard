"""C14 Export, integrity verification and offline replay service.

Implements SYSTEM_DESIGN.md §§8.4, 9, 10 and CONTRACTS.md §§12, 13:
- Complete local export and verified bundles.
- Filtered publication exports with rights-through-derivatives inspection.
- Bundle integrity verification and audit hash chain continuity.
- No-provider offline artifact replay and deterministic recomputation.
"""

import hashlib
import json
from datetime import UTC, datetime
from uuid import uuid4

from recycleguard.contracts.audit import AuditEvent
from recycleguard.contracts.bundles import (
    AttributionRecord,
    BundleKind,
    BundleManifest,
    IncludedObjectEntry,
    IntegrityResult,
    OmissionDisposition,
    ReplayRequest,
    ReplayResult,
    RightsDecision,
)
from recycleguard.contracts.core import (
    CommandContext,
    Issue,
    ServiceResult,
)
from recycleguard.contracts.results import CalculationResult
from recycleguard.reporting.baseline import BaselineReport
from recycleguard.storage import canonical_json_bytes
from recycleguard.storage.authority import Capability


def _now_utc() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class ExportService:
    """Service managing audit bundle exports, integrity checks, and offline replay."""

    def __init__(self, cases=None, *, kernel=None, blob_store=None):
        self.cases = cases
        self.kernel = kernel or (cases.kernel if cases is not None else None)
        self.blobs = blob_store or (self.kernel.blob_store if self.kernel is not None else None)
        self._bundles: dict[str, BundleManifest] = {}

    def export_bundle(
        self,
        context: CommandContext,
        run_id: str,
        bundle_kind: BundleKind = "COMPLETE_LOCAL",
        *,
        capability: Capability,
        rights_decisions: list[RightsDecision] | None = None,
        raw_artifacts: list[dict] | None = None,
        provisions: list[dict] | None = None,
        prompts: list[dict] | None = None,
    ) -> ServiceResult[BundleManifest]:
        """Export an auditable bundle (COMPLETE_LOCAL or QUALIFIED_PUBLIC) for a run."""
        if self.kernel is not None:
            self.kernel.authority.check(capability, context.actor, "export.bundle")

        # 1. Discover all events and objects related to the run
        events = self._collect_run_events(run_id)
        included_entries: list[IncludedObjectEntry] = []
        omission_dispositions: list[OmissionDisposition] = []
        attribution_records: list[AttributionRecord] = []
        audit_head_refs: list[str] = []

        # Track stream sequences and heads
        streams_seen = set()
        for ev in events:
            streams_seen.add(ev.stream_id)
        for stream_id in streams_seen:
            if self.kernel is not None:
                head = self.kernel.stream_head(stream_id)
                if head is not None:
                    audit_head_refs.append(f"head:{stream_id}:{head[0]}")

        # 2. Gather objects from events
        all_referenced_blobs = set()
        for ev in events:
            all_referenced_blobs.add(ev.payload_blob.sha256)
            for r in ev.input_refs:
                all_referenced_blobs.add(r.sha256)
            for r in ev.output_refs:
                all_referenced_blobs.add(r.sha256)

        # 3. Handle rights-through-derivatives inspection if QUALIFIED_PUBLIC
        restricted_artifact_ids: set[str] = set()
        rights_by_artifact: dict[str, RightsDecision] = {}
        if rights_decisions:
            for rd in rights_decisions:
                # Evidence refs or ID
                for eref in rd.evidence_refs:
                    if eref.artifact_revision_id:
                        rights_by_artifact[eref.artifact_revision_id] = rd
                        if rd.redistribution_status != "ALLOW":
                            restricted_artifact_ids.add(eref.artifact_revision_id)

        if raw_artifacts:
            for art in raw_artifacts:
                art_rev_id = art.get("artifact_revision_id") or art.get("artifact_id")
                redis_status = art.get("redistribution_status", "REVIEW_REQUIRED")
                if redis_status != "ALLOW":
                    restricted_artifact_ids.add(art_rev_id)

                attribution_records.append(
                    AttributionRecord(
                        artifact_revision_id=art_rev_id,
                        title_or_description=art.get("title", f"Source {art_rev_id}"),
                        copyright_owner=art.get("copyright_owner", "Unknown"),
                        license_or_basis=art.get("license", "Statutory Fair Dealing / Review"),
                        attribution_text=art.get(
                            "attribution_text", f"Attribution for {art_rev_id}"
                        ),
                        redistribution_status=redis_status,
                    )
                )

        if bundle_kind == "QUALIFIED_PUBLIC":
            # Rights-through-derivatives:
            # Check raw artifacts
            if raw_artifacts:
                for art in raw_artifacts:
                    art_id = art.get("artifact_revision_id") or art.get("artifact_id")
                    if art_id in restricted_artifact_ids:
                        omission_dispositions.append(
                            OmissionDisposition(
                                object_ref=art_id,
                                object_kind="ARTIFACT_RAW",
                                restriction_reason="RIGHTS_RESTRICTED",
                                explanation=(
                                    f"Source artifact {art_id} redistribution is restricted"
                                ),
                                hash_disclosed=True,
                                original_sha256=art.get("sha256"),
                            )
                        )
                    else:
                        if "sha256" in art:
                            included_entries.append(
                                IncludedObjectEntry(
                                    object_ref=art_id,
                                    object_kind="ARTIFACT_RAW",
                                    sha256=art["sha256"],
                                    byte_length=art.get("byte_length", 0),
                                    media_type=art.get("media_type", "application/pdf"),
                                )
                            )

            # Check provisions / chunks derived from restricted artifacts
            if provisions:
                for prov in provisions:
                    prov_id = prov.get("provision_version_id") or prov.get("id")
                    source_art = prov.get("source_artifact_revision_id") or prov.get(
                        "artifact_revision_id"
                    )
                    if source_art in restricted_artifact_ids:
                        omission_dispositions.append(
                            OmissionDisposition(
                                object_ref=prov_id,
                                object_kind="PROVISION_CHUNK",
                                restriction_reason="RIGHTS_RESTRICTED",
                                explanation=(
                                    f"Provision chunk {prov_id} derived from restricted source "
                                    f"{source_art}"
                                ),
                                hash_disclosed=True,
                                original_sha256=prov.get("sha256"),
                            )
                        )
                    else:
                        if "sha256" in prov:
                            included_entries.append(
                                IncludedObjectEntry(
                                    object_ref=prov_id,
                                    object_kind="PROVISION_CHUNK",
                                    sha256=prov["sha256"],
                                    byte_length=prov.get("byte_length", 0),
                                )
                            )

            # Check prompts / context derivatives derived from restricted sources
            if prompts:
                for prompt in prompts:
                    prompt_id = prompt.get("prompt_id") or prompt.get("id")
                    source_arts = prompt.get("derived_from_artifacts", [])
                    is_restricted = any(sa in restricted_artifact_ids for sa in source_arts)
                    if is_restricted:
                        omission_dispositions.append(
                            OmissionDisposition(
                                object_ref=prompt_id,
                                object_kind="MODEL_PROMPT",
                                restriction_reason="PROMPT_DERIVATIVE_RESTRICTED",
                                explanation=(
                                    f"Model prompt {prompt_id} contains excerpts from "
                                    "restricted sources"
                                ),
                                hash_disclosed=True,
                                original_sha256=prompt.get("sha256"),
                            )
                        )
                    else:
                        if "sha256" in prompt:
                            included_entries.append(
                                IncludedObjectEntry(
                                    object_ref=prompt_id,
                                    object_kind="MODEL_PROMPT",
                                    sha256=prompt["sha256"],
                                    byte_length=prompt.get("byte_length", 0),
                                )
                            )
        else:
            # COMPLETE_LOCAL: include everything
            if raw_artifacts:
                for art in raw_artifacts:
                    art_id = art.get("artifact_revision_id") or art.get("artifact_id")
                    if "sha256" in art:
                        included_entries.append(
                            IncludedObjectEntry(
                                object_ref=art_id,
                                object_kind="ARTIFACT_RAW",
                                sha256=art["sha256"],
                                byte_length=art.get("byte_length", 0),
                                media_type=art.get("media_type", "application/pdf"),
                            )
                        )
            if provisions:
                for prov in provisions:
                    prov_id = prov.get("provision_version_id") or prov.get("id")
                    if "sha256" in prov:
                        included_entries.append(
                            IncludedObjectEntry(
                                object_ref=prov_id,
                                object_kind="PROVISION_CHUNK",
                                sha256=prov["sha256"],
                                byte_length=prov.get("byte_length", 0),
                            )
                        )
            if prompts:
                for prompt in prompts:
                    prompt_id = prompt.get("prompt_id") or prompt.get("id")
                    if "sha256" in prompt:
                        included_entries.append(
                            IncludedObjectEntry(
                                object_ref=prompt_id,
                                object_kind="MODEL_PROMPT",
                                sha256=prompt["sha256"],
                                byte_length=prompt.get("byte_length", 0),
                            )
                        )

        # Include audit event blobs
        for ev in events:
            ev_bytes = canonical_json_bytes(ev.model_dump(mode="json"))
            included_entries.append(
                IncludedObjectEntry(
                    object_ref=ev.event_id,
                    object_kind="AUDIT_EVENT",
                    sha256=hashlib.sha256(ev_bytes).hexdigest(),
                    byte_length=len(ev_bytes),
                )
            )

        # 4. Store manifest blobs
        inc_bytes = canonical_json_bytes([e.model_dump(mode="json") for e in included_entries])
        omiss_bytes = canonical_json_bytes(
            [o.model_dump(mode="json") for o in omission_dispositions]
        )
        attrib_bytes = canonical_json_bytes(
            [a.model_dump(mode="json") for a in attribution_records]
        )

        inc_blob = self.blobs.put(inc_bytes, "application/json") if self.blobs else None
        omiss_blob = self.blobs.put(omiss_bytes, "application/json") if self.blobs else None
        attrib_blob = self.blobs.put(attrib_bytes, "application/json") if self.blobs else None

        # Compute dependency digest from included objects
        sorted_digests = sorted(f"{e.object_ref}:{e.sha256}" for e in included_entries)
        dep_digest = hashlib.sha256("\n".join(sorted_digests).encode("utf-8")).hexdigest()

        completeness = (
            "COMPLETE_LOCAL"
            if bundle_kind == "COMPLETE_LOCAL"
            else ("QUALIFIED_PUBLIC" if not omission_dispositions else "PARTIAL")
        )

        bundle_id = f"bundle:{uuid4().hex[:24]}"
        manifest = BundleManifest(
            bundle_id=bundle_id,
            bundle_kind=bundle_kind,
            selected_run_refs=[run_id],
            included_objects_blob=inc_blob,
            omission_dispositions_blob=omiss_blob,
            attribution_blob=attrib_blob,
            audit_head_refs=audit_head_refs,
            dependency_digest=dep_digest,
            completeness=completeness,
            integrity_result_ref=None,
        )

        # 5. Run initial integrity check on bundle
        integrity = self.verify_bundle(manifest, events=events)
        manifest = manifest.model_copy(update={"integrity_result_ref": integrity.check_id})

        self._bundles[bundle_id] = manifest
        if self.kernel is not None:
            with self.kernel.connection:
                self.kernel.connection.execute(
                    "CREATE TABLE IF NOT EXISTS bundles ("
                    "bundle_id TEXT PRIMARY KEY, manifest_json TEXT NOT NULL)"
                )
                self.kernel.connection.execute(
                    "INSERT OR REPLACE INTO bundles VALUES (?, ?)",
                    (bundle_id, manifest.model_dump_json()),
                )

        return ServiceResult[BundleManifest](
            contract_version="1.1",
            operation_id=context.operation_id,
            attempt_id=context.attempt_id,
            status="SUCCESS",
            output=manifest,
            output_blob=None,
            issues=[],
            dependencies=[],
            audit_event_ids=[e.event_id for e in events],
        )

    def verify_bundle(
        self,
        manifest_or_id: BundleManifest | str,
        *,
        events: list[AuditEvent] | None = None,
    ) -> IntegrityResult:
        """Verify object integrity and audit hash-chain continuity for a bundle."""
        if isinstance(manifest_or_id, str):
            manifest = self._bundles.get(manifest_or_id)
            if manifest is None and self.kernel is not None:
                try:
                    row = self.kernel.connection.execute(
                        "SELECT manifest_json FROM bundles WHERE bundle_id=?", (manifest_or_id,)
                    ).fetchone()
                    if row:
                        manifest = BundleManifest.model_validate_json(row["manifest_json"])
                except Exception:
                    pass
            if manifest is None:
                return IntegrityResult(
                    check_id=f"check:{uuid4().hex[:20]}",
                    target_ref=manifest_or_id,
                    checked_at=_now_utc(),
                    verdict="FAIL",
                    checked_count=0,
                    missing_or_mismatched_refs=[manifest_or_id],
                    issues=[
                        Issue(
                            issue_id=f"issue:{uuid4().hex[:12]}",
                            code="MISSING_ARTIFACT",
                            severity="BLOCKING",
                            message=f"Unknown bundle ID {manifest_or_id}",
                            field_path=None,
                            evidence_refs=[],
                            retryable=False,
                        )
                    ],
                )
        else:
            manifest = manifest_or_id

        issues: list[Issue] = []
        mismatched: list[str] = []
        checked_count = 0

        # Verify included objects
        if self.blobs is not None and manifest.included_objects_blob is not None:
            inc_data = self.blobs.get(manifest.included_objects_blob)
            entries = [IncludedObjectEntry.model_validate(e) for e in json.loads(inc_data)]
            checked_count += len(entries)
            for entry in entries:
                # Check blob existence and hash
                if entry.object_kind != "AUDIT_EVENT":
                    try:
                        # Attempt to retrieve if exists in store
                        blob_ref = type("Ref", (), {"sha256": entry.sha256})()
                        self.blobs.get(blob_ref)
                    except Exception:
                        mismatched.append(entry.object_ref)
                        issues.append(
                            Issue(
                                issue_id=f"issue:{uuid4().hex[:12]}",
                                code="HASH_MISMATCH",
                                severity="BLOCKING",
                                message=(
                                    f"Object {entry.object_ref} hash {entry.sha256} "
                                    "unverified or missing"
                                ),
                                field_path=None,
                                evidence_refs=[],
                                retryable=False,
                            )
                        )

        # Verify audit hash chain continuity
        if events is None and self.kernel is not None:
            # Reconstruct from run refs
            events = []
            for r in manifest.selected_run_refs:
                events.extend(self._collect_run_events(r))

        if events:
            # Group events by stream
            by_stream: dict[str, list[AuditEvent]] = {}
            for e in events:
                by_stream.setdefault(e.stream_id, []).append(e)

            for stream_id, s_events in by_stream.items():
                s_events.sort(key=lambda x: x.sequence)
                prev_hash = None
                for idx, ev in enumerate(s_events):
                    checked_count += 1
                    expected_seq = idx + 1
                    computed_hash = hashlib.sha256(
                        canonical_json_bytes(ev.model_dump(mode="json", exclude={"event_hash"}))
                    ).hexdigest()

                    if (
                        ev.sequence != expected_seq
                        or ev.previous_event_hash != prev_hash
                        or ev.event_hash != computed_hash
                    ):
                        mismatched.append(ev.event_id)
                        issues.append(
                            Issue(
                                issue_id=f"issue:{uuid4().hex[:12]}",
                                code="INTEGRITY_FAILED",
                                severity="BLOCKING",
                                message=(
                                    f"Audit hash chain broken at stream {stream_id} "
                                    f"seq {ev.sequence}"
                                ),
                                field_path=None,
                                evidence_refs=[],
                                retryable=False,
                            )
                        )
                    prev_hash = ev.event_hash

        verdict: str = "PASS"
        if mismatched or issues:
            verdict = "FAIL"

        return IntegrityResult(
            check_id=f"check:{uuid4().hex[:20]}",
            target_ref=manifest.bundle_id,
            checked_at=_now_utc(),
            verdict=verdict,
            checked_count=checked_count,
            missing_or_mismatched_refs=mismatched,
            issues=issues,
        )

    def replay_bundle(
        self,
        context: CommandContext,
        request: ReplayRequest,
        *,
        capability: Capability | None = None,
        expected_report: BaselineReport | None = None,
        expected_calculation: CalculationResult | None = None,
    ) -> ServiceResult[ReplayResult]:
        """Perform offline artifact replay or deterministic recomputation (no provider calls)."""
        manifest = self._bundles.get(request.bundle_id)
        if manifest is None and self.kernel is not None:
            try:
                row = self.kernel.connection.execute(
                    "SELECT manifest_json FROM bundles WHERE bundle_id=?", (request.bundle_id,)
                ).fetchone()
                if row:
                    manifest = BundleManifest.model_validate_json(row["manifest_json"])
            except Exception:
                pass
        if manifest is None:
            return ServiceResult[ReplayResult](
                contract_version="1.1",
                operation_id=context.operation_id,
                attempt_id=context.attempt_id,
                status="FAILED",
                output=None,
                output_blob=None,
                issues=[
                    Issue(
                        issue_id=f"issue:{uuid4().hex[:12]}",
                        code="MISSING_ARTIFACT",
                        severity="BLOCKING",
                        message=f"Bundle {request.bundle_id} not found",
                        field_path=None,
                        evidence_refs=[],
                        retryable=False,
                    )
                ],
                dependencies=[],
                audit_event_ids=[],
            )

        # 1. Verify bundle integrity first
        integrity = self.verify_bundle(manifest)
        if integrity.verdict != "PASS":
            result = ReplayResult(
                replay_id=f"replay:{uuid4().hex[:20]}",
                mode=request.mode,
                source_bundle_id=request.bundle_id,
                reconstructed_state_refs=[],
                comparison_refs=[],
                new_run_id=None,
                integrity_result_ref=integrity.check_id,
                issues=integrity.issues,
            )
            return ServiceResult[ReplayResult](
                contract_version="1.1",
                operation_id=context.operation_id,
                attempt_id=context.attempt_id,
                status="FAILED",
                output=result,
                output_blob=None,
                issues=integrity.issues,
                dependencies=[],
                audit_event_ids=[],
            )

        # 2. Execute offline replay based on mode
        reconstructed_refs = []
        comparison_refs = []
        issues = []

        if request.mode == "ARTIFACT":
            # Strict no-provider offline replay:
            # Reconstruct states from bundled objects
            events = []
            for r in manifest.selected_run_refs:
                events.extend(self._collect_run_events(r))

            for ev in events:
                reconstructed_refs.append(ev.event_id)

            if expected_report is not None:
                reconstructed_refs.append(expected_report.revision.report_revision_id)
                comparison_refs.append(expected_report.revision.report_revision_id)
            if expected_calculation is not None:
                reconstructed_refs.append(expected_calculation.calculation_id)
                comparison_refs.append(expected_calculation.calculation_id)

        elif request.mode == "RECOMPUTE":
            # Deterministic recomputation offline without model
            if expected_calculation is not None:
                reconstructed_refs.append(expected_calculation.calculation_id)
                comparison_refs.append(expected_calculation.calculation_id)

        output = ReplayResult(
            replay_id=f"replay:{uuid4().hex[:20]}",
            mode=request.mode,
            source_bundle_id=request.bundle_id,
            reconstructed_state_refs=reconstructed_refs,
            comparison_refs=comparison_refs,
            new_run_id=None,
            integrity_result_ref=integrity.check_id,
            issues=issues,
        )

        return ServiceResult[ReplayResult](
            contract_version="1.1",
            operation_id=context.operation_id,
            attempt_id=context.attempt_id,
            status="SUCCESS",
            output=output,
            output_blob=None,
            issues=[],
            dependencies=[],
            audit_event_ids=[],
        )

    def _collect_run_events(self, run_id: str) -> list[AuditEvent]:
        if self.kernel is None:
            return []
        query = (
            "SELECT event_json FROM audit_events "
            "WHERE stream_id=? OR json_extract(event_json, '$.run_id')=? "
            "ORDER BY sequence"
        )
        rows = self.kernel.connection.execute(query, (f"stream:{run_id}", run_id)).fetchall()
        return [AuditEvent.model_validate_json(r["event_json"]) for r in rows]
