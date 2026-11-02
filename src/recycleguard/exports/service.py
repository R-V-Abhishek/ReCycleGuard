"""Content-addressed local audit packages and conservative publication manifests.

Artifact replay verifies and reads the frozen package; it does not restore a live
application database or rerun a model. Recompute requires a separate executor.
"""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from recycleguard.contracts.audit import AuditEvent, OperationIntent, OperationResult
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
from recycleguard.contracts.core import BlobRef, CommandContext, Issue, ServiceResult
from recycleguard.contracts.results import CalculationResult
from recycleguard.reporting.baseline import BaselineReport
from recycleguard.storage import BlobStore, canonical_json_bytes
from recycleguard.storage.authority import Capability


def _now_utc():
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _issue(code, message):
    return Issue(
        issue_id=f"issue:{uuid4().hex}",
        code=code,
        severity="BLOCKING",
        message=message,
        field_path=None,
        evidence_refs=[],
        retryable=False,
    )


class ExportService:
    """Persist manifests and their complete referenced blob closure locally."""

    def __init__(self, cases=None, *, kernel=None, blob_store=None):
        self.cases = cases
        self.kernel = kernel or (cases.kernel if cases is not None else None)
        self.blobs = blob_store or (self.kernel.blob_store if self.kernel is not None else None)
        self._bundles: dict[str, BundleManifest] = {}

    def _require_storage(self):
        if self.kernel is None or self.blobs is None:
            raise ValueError("export requires durable audit and blob storage")

    def _load(self, bundle_id):
        if self.kernel is None and bundle_id in self._bundles:
            return self._bundles[bundle_id]
        self._require_storage()
        self.kernel.connection.execute(
            "CREATE TABLE IF NOT EXISTS bundles ("
            "bundle_id TEXT PRIMARY KEY, manifest_json TEXT NOT NULL)"
        )
        row = self.kernel.connection.execute(
            "SELECT manifest_json FROM bundles WHERE bundle_id=?", (bundle_id,)
        ).fetchone()
        if row is None:
            raise ValueError("unknown bundle ID")
        return BundleManifest.model_validate_json(row["manifest_json"])

    def _begin(self, context, payload, event_type, capability):
        suffix = event_type.replace(".", "_")
        context = context.model_copy(
            update={
                "command_id": f"{context.command_id}:{suffix}",
                "operation_id": f"{context.operation_id}:{suffix}",
                "attempt_id": f"{context.attempt_id}:{suffix}",
                "idempotency_key": f"{context.idempotency_key}:{suffix}",
            }
        )
        intent = OperationIntent(
            context=context,
            idempotency_key=context.idempotency_key,
            event_type=event_type,
            payload=self.blobs.put(canonical_json_bytes(payload), "application/json"),
            stream_id=f"stream:{suffix}:{context.run_id or 'local'}",
        )
        self.kernel.commit_intent(intent, capability=capability)
        return intent, self.kernel.get_result(context.operation_id)

    def _commit(self, intent, output, capability, *, issues=(), mutation=None):
        reference = self.blobs.put(
            canonical_json_bytes(output.model_dump(mode="json")), "application/json"
        )
        result = OperationResult(
            operation_id=intent.context.operation_id,
            attempt_id=intent.context.attempt_id,
            status="FAILED" if issues else "SUCCESS",
            payload=reference,
            issue_codes=[issue.code for issue in issues],
        )
        event = self.kernel.commit_result(intent, result, capability=capability, mutation=mutation)
        return event, reference

    def _closure(self, events):
        """Follow typed blob references plus exact catalog/profile metadata pins."""
        entries = {}
        visited = set()
        tables = {
            row[0]
            for row in self.kernel.connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }

        def add(ref, kind="BLOB", object_ref=None):
            data = self.blobs.get(ref)
            if ref.sha256 in entries:
                return
            entries[ref.sha256] = IncludedObjectEntry(
                object_ref=object_ref or f"blob:{ref.sha256}",
                object_kind=kind,
                sha256=ref.sha256,
                byte_length=ref.byte_length,
                media_type=ref.media_type,
            )
            if ref.media_type == "application/json":
                walk(json.loads(data))

        def catalog(table, id_column, json_column, value):
            key = (table, value)
            if key in visited or table not in tables:
                return
            visited.add(key)
            row = self.kernel.connection.execute(
                f"SELECT {json_column} FROM {table} WHERE {id_column}=?", (value,)
            ).fetchone()
            if row is None:
                raise ValueError(f"missing referenced {table} metadata")
            ref = self.blobs.put(row[0].encode("utf-8"), "application/json")
            add(ref, "CATALOG_METADATA", value)

        def walk(value):
            match value:
                case dict():
                    if {"sha256", "byte_length", "media_type"} <= value.keys() and type(
                        value["sha256"]
                    ) is str:
                        add(
                            BlobRef.model_validate(
                                {k: value[k] for k in ("sha256", "byte_length", "media_type")}
                            )
                        )
                    if (
                        type(value.get("snapshot_id")) is str
                        and type(value.get("membership_digest")) is str
                    ):
                        catalog(
                            "frozen_snapshots", "snapshot_id", "snapshot_json", value["snapshot_id"]
                        )
                    if (
                        type(value.get("artifact_revision_id")) is str
                        and value["artifact_revision_id"]
                    ):
                        catalog(
                            "artifact_revisions",
                            "artifact_revision_id",
                            "revision_json",
                            value["artifact_revision_id"],
                        )
                    if type(value.get("source_receipt_ids")) is list:
                        for receipt in value["source_receipt_ids"]:
                            catalog("intake_receipts", "receipt_id", "receipt_json", receipt)
                    if (
                        {
                            "profile_id",
                            "profile_version",
                            "digest",
                        }
                        <= value.keys()
                        and type(value["profile_id"]) is str
                        and "profile_revisions" in tables
                    ):
                        key = ("profile", value["profile_id"], value["profile_version"])
                        if key not in visited:
                            visited.add(key)
                            row = self.kernel.connection.execute(
                                "SELECT profile_json FROM profile_revisions "
                                "WHERE profile_id=? AND profile_version=?",
                                (value["profile_id"], value["profile_version"]),
                            ).fetchone()
                            if row is None:
                                raise ValueError("missing pinned profile")
                            add(
                                self.blobs.put(row[0].encode("utf-8"), "application/json"),
                                "PROFILE",
                            )
                    for item in value.values():
                        walk(item)
                case list():
                    for item in value:
                        walk(item)

        for event in events:
            add(
                self.blobs.put(
                    canonical_json_bytes(event.model_dump(mode="json")), "application/json"
                ),
                "AUDIT_EVENT",
                event.event_id,
            )
        return list(entries.values())

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
        self._require_storage()
        self.kernel.authority.check(capability, context.actor, "export.bundle")
        if bundle_kind not in {"COMPLETE_LOCAL", "QUALIFIED_PUBLIC"}:
            raise ValueError("unsupported bundle kind")
        events = self._collect_run_events(run_id)
        if not events:
            raise ValueError("run has no auditable events")
        self._verify_events(events)
        intent, prior = self._begin(
            context.model_copy(
                update={"run_id": run_id, "case_version_id": events[0].case_version_id}
            ),
            {
                "run_id": run_id,
                "bundle_kind": bundle_kind,
                "rights_decisions": [
                    item.model_dump(mode="json") for item in rights_decisions or []
                ],
                "raw_artifacts": raw_artifacts,
                "provisions": provisions,
                "prompts": prompts,
            },
            "export.bundle",
            capability,
        )
        if prior is not None:
            if prior.status != "SUCCESS" or prior.payload is None:
                raise ValueError("export operation already failed")
            manifest = BundleManifest.model_validate_json(self.blobs.get(prior.payload))
            return ServiceResult[BundleManifest](
                contract_version="1.1",
                operation_id=intent.context.operation_id,
                attempt_id=intent.context.attempt_id,
                status="SUCCESS",
                output=manifest,
                output_blob=prior.payload,
                issues=[],
                dependencies=[],
                audit_event_ids=[f"event:result_{intent.context.operation_id}"],
            )
        entries = self._closure(events)
        omissions = []
        attributions = []
        # Public clearance is deliberately conservative: opaque run payloads may
        # contain source excerpts. Withhold the entire unreviewed closure rather
        # than pretending that a caller-provided source list covers every derivative.
        if bundle_kind == "QUALIFIED_PUBLIC":
            for entry in entries:
                omissions.append(
                    OmissionDisposition(
                        object_ref=entry.object_ref,
                        object_kind=entry.object_kind,
                        restriction_reason="RIGHTS_RESTRICTED",
                        explanation=(
                            "Run payload and derivatives lack explicit publication clearance"
                        ),
                        original_sha256=entry.sha256,
                    )
                )
            entries = []
        raw = raw_artifacts or []
        for art in raw:
            art_id = art.get("artifact_revision_id", art.get("artifact_id"))
            attributions.append(
                AttributionRecord(
                    artifact_revision_id=art_id,
                    title_or_description=art.get("title", art_id),
                    copyright_owner=art.get("copyright_owner", "Unknown"),
                    license_or_basis=art.get("license", "Unreviewed"),
                    attribution_text=art.get("attribution_text", "Unreviewed source"),
                    redistribution_status=art.get("redistribution_status", "REVIEW_REQUIRED"),
                )
            )
        for kind, items, key in (
            ("ARTIFACT_RAW", raw, "artifact_revision_id"),
            ("PROVISION_CHUNK", provisions or [], "provision_version_id"),
            ("MODEL_PROMPT", prompts or [], "prompt_id"),
        ):
            for item in items:
                object_id = item.get(key, item.get("id", item.get("artifact_id")))
                # Caller dictionaries do not establish reviewed rights. All extra
                # artifacts/derivatives are withheld in publication mode.
                if bundle_kind == "QUALIFIED_PUBLIC":
                    omissions.append(
                        OmissionDisposition(
                            object_ref=object_id,
                            object_kind=kind,
                            restriction_reason="PROMPT_DERIVATIVE_RESTRICTED"
                            if kind == "MODEL_PROMPT"
                            else "RIGHTS_RESTRICTED",
                            explanation=(
                                "Publication requires independently reviewed exact-object clearance"
                            ),
                            original_sha256=item.get("sha256"),
                        )
                    )
                else:
                    ref = BlobRef(
                        sha256=item["sha256"],
                        byte_length=item["byte_length"],
                        media_type=item.get("media_type", "application/json"),
                    )
                    self.blobs.get(ref)
                    entries.append(
                        IncludedObjectEntry(
                            object_ref=object_id, object_kind=kind, **ref.model_dump()
                        )
                    )
        if bundle_kind == "QUALIFIED_PUBLIC":
            # Caller-provided titles and attribution text may themselves contain
            # confidential excerpts. No exact publication review exists here.
            attributions = []
        # Canonical metadata and exact event heads freeze the package independently
        # of later live-ledger changes.
        heads = [
            f"head:{stream}:{stream_events[-1].sequence}:{stream_events[-1].event_hash}"
            for stream, stream_events in self._streams(events).items()
        ]
        digest = self._dependency_digest(entries, omissions, attributions, heads)

        def put(values):
            return self.blobs.put(canonical_json_bytes(values), "application/json")

        manifest = BundleManifest(
            bundle_id=f"bundle:{uuid4().hex}",
            bundle_kind=bundle_kind,
            selected_run_refs=[run_id],
            included_objects_blob=put([e.model_dump(mode="json") for e in entries]),
            omission_dispositions_blob=put([o.model_dump(mode="json") for o in omissions]),
            attribution_blob=put([a.model_dump(mode="json") for a in attributions]),
            audit_head_refs=heads,
            dependency_digest=digest,
            completeness="COMPLETE_LOCAL" if bundle_kind == "COMPLETE_LOCAL" else "PARTIAL",
        )
        integrity = self.verify_bundle(manifest)
        if integrity.verdict != "PASS":
            raise ValueError("bundle failed integrity verification")
        manifest = manifest.model_copy(update={"integrity_result_ref": integrity.check_id})
        self.kernel.connection.execute(
            "CREATE TABLE IF NOT EXISTS bundles ("
            "bundle_id TEXT PRIMARY KEY, manifest_json TEXT NOT NULL)"
        )

        def mutation():
            self.kernel.connection.execute(
                "INSERT INTO bundles VALUES (?, ?)",
                (manifest.bundle_id, manifest.model_dump_json()),
            )

        event, output_ref = self._commit(intent, manifest, capability, mutation=mutation)
        return ServiceResult[BundleManifest](
            contract_version="1.1",
            operation_id=intent.context.operation_id,
            attempt_id=intent.context.attempt_id,
            status="SUCCESS",
            output=manifest,
            output_blob=output_ref,
            issues=[],
            dependencies=[],
            audit_event_ids=[event.event_id],
        )

    @staticmethod
    def _streams(events):
        streams = {}
        for event in events:
            streams.setdefault(event.stream_id, []).append(event)
        for values in streams.values():
            values.sort(key=lambda event: event.sequence)
        return streams

    @classmethod
    def _verify_events(cls, events):
        for values in cls._streams(events).values():
            previous = None
            for sequence, event in enumerate(values, 1):
                digest = hashlib.sha256(
                    canonical_json_bytes(event.model_dump(mode="json", exclude={"event_hash"}))
                ).hexdigest()
                if (
                    event.sequence != sequence
                    or event.previous_event_hash != previous
                    or event.event_hash != digest
                ):
                    raise ValueError("audit chain continuity failed")
                previous = digest

    @staticmethod
    def _dependency_digest(entries, omissions, attributions, heads):
        return hashlib.sha256(
            canonical_json_bytes(
                {
                    "objects": [item.model_dump(mode="json") for item in entries],
                    "omissions": [item.model_dump(mode="json") for item in omissions],
                    "attribution": [item.model_dump(mode="json") for item in attributions],
                    "heads": heads,
                }
            )
        ).hexdigest()

    def verify_bundle(
        self, manifest_or_id: BundleManifest | str, *, events=None
    ) -> IntegrityResult:
        issues, mismatched = [], []
        checked = 0
        target = "bundle:unknown"
        try:
            match manifest_or_id:
                case str():
                    target = manifest_or_id
                    manifest = self._load(manifest_or_id)
                case _:
                    manifest = manifest_or_id
                    target = manifest.bundle_id
            entries = [
                IncludedObjectEntry.model_validate(item)
                for item in json.loads(self.blobs.get(manifest.included_objects_blob))
            ]
            omissions = [
                OmissionDisposition.model_validate(item)
                for item in json.loads(self.blobs.get(manifest.omission_dispositions_blob))
            ]
            attribution = [
                AttributionRecord.model_validate(item)
                for item in json.loads(self.blobs.get(manifest.attribution_blob))
            ]
            checked += 3
            if manifest.dependency_digest != self._dependency_digest(
                entries, omissions, attribution, manifest.audit_head_refs
            ):
                issues.append(_issue("HASH_MISMATCH", "bundle dependency metadata changed"))
            packaged_events = []
            refs = set()
            nested_refs = set()

            def references(value):
                match value:
                    case {"sha256": str() as digest, "byte_length": int(), "media_type": str()}:
                        nested_refs.add(digest)
                    case dict():
                        for child in value.values():
                            references(child)
                    case list():
                        for child in value:
                            references(child)

            for entry in entries:
                reference = BlobRef(
                    sha256=entry.sha256, byte_length=entry.byte_length, media_type=entry.media_type
                )
                data = self.blobs.get(reference)
                refs.add(reference.sha256)
                checked += 1
                if reference.media_type == "application/json":
                    references(json.loads(data))
                if entry.object_kind == "AUDIT_EVENT":
                    packaged_events.append(AuditEvent.model_validate_json(data))
            if manifest.bundle_kind == "COMPLETE_LOCAL":
                if omissions or not packaged_events:
                    raise ValueError("complete package lacks events or contains omissions")
                if not nested_refs <= refs:
                    raise ValueError("package omits transitive blob dependencies")
                self._verify_events(packaged_events)
                expected_heads = [
                    f"head:{stream}:{values[-1].sequence}:{values[-1].event_hash}"
                    for stream, values in self._streams(packaged_events).items()
                ]
                if expected_heads != manifest.audit_head_refs:
                    raise ValueError("frozen audit heads disagree")
                for event in packaged_events:
                    if (
                        not {
                            r.sha256
                            for r in [event.payload_blob, *event.input_refs, *event.output_refs]
                        }
                        <= refs
                    ):
                        raise ValueError("package lacks audit dependency bytes")
            elif entries or not omissions or manifest.completeness != "PARTIAL":
                raise ValueError("unreviewed publication must remain fully withheld and partial")
        except (ValueError, OSError, KeyError, TypeError) as exc:
            mismatched.append(target)
            issues.append(_issue("INTEGRITY_FAILED", f"bundle integrity failed: {exc}"))
        return IntegrityResult(
            check_id=f"check:{uuid4().hex}",
            target_ref=target,
            checked_at=_now_utc(),
            verdict="FAIL" if issues else "PASS",
            checked_count=checked,
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
        if self.kernel is not None:
            self.kernel.authority.check(capability, context.actor, "replay.bundle")
        intent = None
        if self.kernel is not None:
            intent, prior = self._begin(
                context, request.model_dump(mode="json"), "replay.bundle", capability
            )
            if prior is not None:
                output = ReplayResult.model_validate_json(self.blobs.get(prior.payload))
                return ServiceResult[ReplayResult](
                    contract_version="1.1",
                    operation_id=intent.context.operation_id,
                    attempt_id=intent.context.attempt_id,
                    status=prior.status,
                    output=output,
                    output_blob=prior.payload,
                    issues=output.issues,
                    dependencies=[],
                    audit_event_ids=[f"event:result_{intent.context.operation_id}"],
                )
        issues = []
        reconstructed, comparison = [], []
        integrity = None
        try:
            manifest = self._load(request.bundle_id)
            integrity = self.verify_bundle(manifest)
            issues.extend(integrity.issues)
            if request.mode != "ARTIFACT":
                issues.append(
                    _issue(
                        "UNSUPPORTED_FEATURE",
                        "recompute and model rerun require a separately pinned executor",
                    )
                )
            if manifest.bundle_kind != "COMPLETE_LOCAL":
                issues.append(
                    _issue(
                        "INTEGRITY_FAILED",
                        "partial publication cannot reconstruct omitted evidence",
                    )
                )
            if not issues:
                entries = [
                    IncludedObjectEntry.model_validate(item)
                    for item in json.loads(self.blobs.get(manifest.included_objects_blob))
                ]
                digests = {entry.sha256 for entry in entries}
                reconstructed = [entry.object_ref for entry in entries]
                for expected, ref in (
                    (
                        expected_report,
                        None
                        if expected_report is None
                        else expected_report.revision.report_revision_id,
                    ),
                    (
                        expected_calculation,
                        None
                        if expected_calculation is None
                        else expected_calculation.calculation_id,
                    ),
                ):
                    if expected is not None:
                        digest = hashlib.sha256(
                            canonical_json_bytes(expected.model_dump(mode="json"))
                        ).hexdigest()
                        if digest not in digests:
                            issues.append(
                                _issue(
                                    "HASH_MISMATCH",
                                    "expected comparison object is absent from frozen package",
                                )
                            )
                        else:
                            comparison.append(ref)
        except (ValueError, OSError) as exc:
            issues.append(_issue("MISSING_ARTIFACT", str(exc)))
        output = ReplayResult(
            replay_id=f"replay:{uuid4().hex}",
            mode=request.mode,
            source_bundle_id=request.bundle_id,
            reconstructed_state_refs=reconstructed if not issues else [],
            comparison_refs=comparison if not issues else [],
            new_run_id=None,
            integrity_result_ref=integrity.check_id if integrity else f"check:{uuid4().hex}",
            issues=issues,
        )
        event_ids, output_ref = [], None
        if intent is not None:
            event, output_ref = self._commit(intent, output, capability, issues=issues)
            event_ids = [event.event_id]
        return ServiceResult[ReplayResult](
            contract_version="1.1",
            operation_id=context.operation_id,
            attempt_id=context.attempt_id,
            status="FAILED" if issues else "SUCCESS",
            output=output,
            output_blob=output_ref,
            issues=issues,
            dependencies=[],
            audit_event_ids=event_ids,
        )

    def write_package(self, manifest: BundleManifest, destination: Path) -> Path:
        """Copy exactly the manifest's verified objects to a new standalone directory."""
        if self.verify_bundle(manifest).verdict != "PASS":
            raise ValueError("cannot package an invalid bundle")
        destination = Path(destination)
        destination.mkdir(parents=True, exist_ok=False)
        target = BlobStore(destination)
        metadata = [
            manifest.included_objects_blob,
            manifest.omission_dispositions_blob,
            manifest.attribution_blob,
        ]
        entries = [
            IncludedObjectEntry.model_validate(item)
            for item in json.loads(self.blobs.get(manifest.included_objects_blob))
        ]
        refs = [
            *metadata,
            *[
                BlobRef(
                    sha256=item.sha256, byte_length=item.byte_length, media_type=item.media_type
                )
                for item in entries
            ],
        ]
        for ref in refs:
            target.put(self.blobs.get(ref), ref.media_type)
        (destination / "manifest.json").write_bytes(
            canonical_json_bytes(manifest.model_dump(mode="json"))
        )
        return destination

    @classmethod
    def open_package(cls, directory: Path):
        """Open a read-only artifact replay view without a source application database."""
        directory = Path(directory)
        manifest = BundleManifest.model_validate_json((directory / "manifest.json").read_bytes())
        service = cls(blob_store=BlobStore(directory))
        service._bundles[manifest.bundle_id] = manifest
        if service.verify_bundle(manifest).verdict != "PASS":
            raise ValueError("package failed integrity verification")
        return service, manifest

    def _collect_run_events(self, run_id):
        # Include complete prefixes for streams whose operations name this run;
        # filtering individual events could conceal gaps in a chain.
        rows = self.kernel.connection.execute(
            "SELECT DISTINCT stream_id FROM audit_events WHERE stream_id=? "
            "OR json_extract(event_json, '$.run_id')=?",
            (f"stream:{run_id}", run_id),
        ).fetchall()
        events = []
        for row in rows:
            events.extend(
                AuditEvent.model_validate_json(event[0])
                for event in self.kernel.connection.execute(
                    "SELECT event_json FROM audit_events WHERE stream_id=? ORDER BY sequence",
                    (row[0],),
                )
            )
        return events
