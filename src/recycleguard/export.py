"""Integrity-checked local/publication bundles and offline artifact replay."""

import hashlib

from recycleguard.contracts import (
    BundleExclusion,
    BundleManifest,
    BundleObject,
    BundleRequest,
    IntegrityResult,
    ReplayRequest,
    ReplayResult,
)
from recycleguard.storage import canonical_json_bytes


class ExportService:
    def __init__(self, store):
        self.store = store
        self.blobs = store.blobs
        self.kernel = store.kernel

    @staticmethod
    def _digest(value):
        return hashlib.sha256(canonical_json_bytes(value)).hexdigest()

    def export_bundle(self, request: BundleRequest) -> BundleManifest:
        spec = self.store.spec(request.run_id)
        state = self.store.load(request.run_id)
        spec_ref = self.store.blobs.put(
            canonical_json_bytes(spec.model_dump(mode="json")), "application/json"
        )
        state_ref = self.store.state_blob(request.run_id)
        objects = [
            BundleObject(reference=spec_ref, role="run_spec"),
            BundleObject(reference=state_ref, role="run_state"),
        ]
        exclusions = []
        for ref in state.result_refs:
            objects.append(BundleObject(reference=ref, role="run_result"))
        for ref, role in (
            (state.active_turn_input, "active_turn_input"),
            (state.last_checkpoint_ref, "checkpoint"),
        ):
            if ref is not None:
                objects.append(BundleObject(reference=ref, role=role))
        for event in self.kernel.list_stream_events(f"stream:{request.run_id}"):
            for ref in [event.payload_blob, *event.input_refs, *event.output_refs]:
                if all(item.reference != ref for item in objects):
                    objects.append(BundleObject(reference=ref, role="audit_event"))
        if request.kind == "PUBLICATION" and not request.allow_restricted:
            exclusions.append(
                BundleExclusion(
                    reference=None,
                    role="raw_material",
                    reason="publication rights require explicit derivative clearance",
                )
            )
        head = self.kernel.stream_head(f"stream:{request.run_id}")
        if head is None:
            raise ValueError("run has no audit head")
        dependency_head = head[1]
        body = {
            "bundle_id": request.bundle_id,
            "run_id": request.run_id,
            "kind": request.kind,
            "spec": spec_ref.model_dump(mode="json"),
            "state": state_ref.model_dump(mode="json"),
            "objects": [item.model_dump(mode="json") for item in objects],
            "exclusions": [item.model_dump(mode="json") for item in exclusions],
            "dependency_head": dependency_head,
        }
        return BundleManifest(**body, manifest_digest=self._digest(body))

    def verify_bundle(self, bundle: BundleManifest) -> IntegrityResult:
        issues = []
        checked = 0
        try:
            spec = self.store.spec(bundle.run_id)
            state = self.store.load(bundle.run_id)
            if spec.run_id != bundle.run_id or state.run_id != bundle.run_id:
                issues.append("RUN_PIN_MISMATCH")
            if bundle.manifest_digest != self._digest(
                bundle.model_dump(mode="json", exclude={"manifest_digest"})
            ):
                issues.append("MANIFEST_HASH_MISMATCH")
            refs = [bundle.spec, bundle.state, *[item.reference for item in bundle.objects]]
            for ref in refs:
                self.blobs.get(ref)
                checked += 1
            events = self.kernel.list_stream_events(f"stream:{bundle.run_id}")
            if not events or events[-1].event_hash != bundle.dependency_head:
                issues.append("DEPENDENCY_HEAD_MISMATCH")
            included = {item.reference for item in bundle.objects}
            expected = {
                ref
                for event in events
                for ref in [event.payload_blob, *event.input_refs, *event.output_refs]
            }
            missing = expected - included
            if missing and not bundle.exclusions:
                issues.append("INCOMPLETE_COVERAGE")
            self.store._verify_stream(bundle.run_id)
        except (FileNotFoundError, ValueError, OSError):
            issues.append("INTEGRITY_FAILED")
        return IntegrityResult(
            valid=not issues,
            bundle_id=bundle.bundle_id,
            checked_objects=checked,
            issue_codes=issues,
        )

    def replay(self, request: ReplayRequest) -> ReplayResult:
        result = self.verify_bundle(request.bundle)
        if not result.valid:
            return ReplayResult(
                valid=False,
                run_id=request.bundle.run_id,
                kind=request.kind,
                state=None,
                issue_codes=result.issue_codes,
            )
        if request.kind != "ARTIFACT":
            return ReplayResult(
                valid=False,
                run_id=request.bundle.run_id,
                kind=request.kind,
                state=None,
                issue_codes=["RECOMPUTE_REQUIRES_PINNED_EXECUTOR"],
            )
        return ReplayResult(
            valid=True,
            run_id=request.bundle.run_id,
            kind=request.kind,
            state=request.bundle.state,
        )
