"""Authoritative graph state and turn ledger, atomically committed with audit results."""

import hashlib

from recycleguard.contracts.audit import OperationIntent, OperationResult
from recycleguard.contracts.core import BlobRef, BoundaryModel
from recycleguard.contracts.workflow import BudgetUsage, RunSpec, RunState, TurnManifest
from recycleguard.storage import AuditKernel, canonical_json_bytes
from recycleguard.storage.authority import AuthorizationError

_SCHEMA = """
CREATE TABLE IF NOT EXISTS workflow_runs (
 run_id TEXT PRIMARY KEY, spec_blob TEXT NOT NULL, state_blob TEXT NOT NULL,
 version INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS workflow_turns (
 turn_id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES workflow_runs(run_id),
 turn_index INTEGER NOT NULL, manifest_blob TEXT NOT NULL, UNIQUE(run_id,turn_index)
);
"""
_TERMINAL = {"COMPLETED", "FAILED", "CANCELLED", "BLOCKED_INPUT", "BLOCKED_OUTPUT"}


class GraphStore:
    def __init__(self, kernel: AuditKernel):
        self.kernel = kernel
        self.blobs = kernel.blob_store
        self.connection = kernel.connection
        self.connection.executescript(_SCHEMA)

    def _blob(self, value) -> BlobRef:
        return self.blobs.put(canonical_json_bytes(value), "application/json")

    def _authorize(self, context, event_type, capability, run_id=None):
        if context.actor.actor_kind != "SERVICE":
            raise AuthorizationError("authoritative graph writes require a SERVICE actor")
        if not event_type.startswith("graph."):
            raise AuthorizationError("graph store only accepts graph event types")
        if context.run_id is None or (run_id is not None and context.run_id != run_id):
            raise ValueError("graph context must pin the exact run ID")
        self.kernel.authority.check(capability, context.actor, event_type)
        if (
            self.connection.execute(
                "SELECT 1 FROM workflow_runs WHERE run_id=?", (context.run_id,)
            ).fetchone()
            is not None
        ):
            if context.case_version_id != self.spec(context.run_id).case_snapshot.snapshot_id:
                raise ValueError("graph context must pin the exact case snapshot")

    def _intent(self, context, event_type, payload, capability):
        self._authorize(context, event_type, capability)
        intent = OperationIntent(
            context=context,
            idempotency_key=context.idempotency_key,
            event_type=event_type,
            payload=self._blob(payload),
            stream_id=f"stream:{context.run_id}",
        )
        self.kernel.commit_intent(intent, capability=capability)
        return intent

    def _verify_stream(self, run_id):
        previous = None
        events = self.kernel.list_stream_events(f"stream:{run_id}")
        for sequence, event in enumerate(events, 1):
            digest = hashlib.sha256(
                canonical_json_bytes(event.model_dump(mode="json", exclude={"event_hash"}))
            ).hexdigest()
            if (
                event.sequence != sequence
                or event.run_id != run_id
                or event.previous_event_hash != previous
                or event.event_hash != digest
            ):
                raise ValueError("graph audit hash chain failed verification")
            for ref in [event.payload_blob, *event.input_refs, *event.output_refs]:
                self.blobs.get(ref)
            previous = digest
        return events

    def read(self, operation_id, model):
        result = self.kernel.get_result(operation_id)
        if result is None:
            return None
        original = self.kernel.get_intent(operation_id)
        attempt_row = self.connection.execute(
            "SELECT attempt_json FROM operation_attempts WHERE operation_id=? AND attempt_id=?",
            (operation_id, result.attempt_id),
        ).fetchone()
        if original is None or attempt_row is None:
            raise ValueError("graph result has no exact registered attempt")
        intent = OperationIntent.model_validate_json(attempt_row["attempt_json"])
        original_input = original.model_dump(mode="json")
        attempt_input = intent.model_dump(mode="json")
        del original_input["context"]["attempt_id"]
        del attempt_input["context"]["attempt_id"]
        if original_input != attempt_input:
            raise ValueError("graph attempt differs from its original logical operation")
        if (
            not intent.event_type.startswith("graph.")
            or intent.context.run_id is None
            or intent.stream_id != f"stream:{intent.context.run_id}"
            or result.operation_id != operation_id
            or result.attempt_id != intent.context.attempt_id
            or result.payload is None
        ):
            raise ValueError("operation is not a committed graph result")
        self._verify_stream(intent.context.run_id)
        event = self.kernel.get_event(f"event:result_{operation_id}")
        if (
            event is None
            or event.payload_blob != result.payload
            or event.stream_id != intent.stream_id
            or event.operation_id != operation_id
            or event.event_type != f"{intent.event_type}.result"
            or event.actor != intent.context.actor
            or event.attempt_id != result.attempt_id
            or event.case_version_id != intent.context.case_version_id
            or event.run_id != intent.context.run_id
            or event.turn_id != intent.context.turn_id
            or event.command_id != intent.context.command_id
        ):
            raise ValueError("graph result is not bound to its audit event")
        self.blobs.get(intent.payload)
        return model.model_validate_json(self.blobs.get(result.payload))

    def _row(self, run_id):
        row = self.connection.execute(
            "SELECT spec_blob,state_blob,version FROM workflow_runs WHERE run_id=?", (run_id,)
        ).fetchone()
        if row is None:
            raise ValueError(f"graph run does not exist: {run_id}")
        return row

    def state_blob(self, run_id) -> BlobRef:
        ref = BlobRef.model_validate_json(self._row(run_id)["state_blob"])
        self.blobs.get(ref)
        return ref

    def load(self, run_id) -> RunState:
        row = self._row(run_id)
        ref = BlobRef.model_validate_json(row["state_blob"])
        state = RunState.model_validate_json(self.blobs.get(ref))
        if state.run_id != run_id or state.version != row["version"]:
            raise ValueError("graph state ledger does not match its immutable state")
        events = self._verify_stream(run_id)
        if (
            state.last_audit_sequence < 1
            or state.last_audit_sequence > len(events)
            or events[state.last_audit_sequence - 1].payload_blob != ref
        ):
            raise ValueError("graph state is not bound to its audit sequence")
        return state

    def spec(self, run_id) -> RunSpec:
        ref = BlobRef.model_validate_json(self._row(run_id)["spec_blob"])
        spec = RunSpec.model_validate_json(self.blobs.get(ref))
        if spec.run_id != run_id:
            raise ValueError("graph specification belongs to a different run")
        starts = [e for e in self._verify_stream(run_id) if e.event_type == "graph.start.result"]
        if len(starts) != 1:
            raise ValueError("graph specification has no unique audited start")
        start = starts[0]
        intent = self.kernel.get_intent(start.operation_id)
        if intent is None or intent.payload != ref or ref not in start.output_refs:
            raise ValueError("graph specification is not bound to its audited start")
        self.read(start.operation_id, RunState)
        return spec

    def _next_sequence(self, run_id):
        head = self.kernel.stream_head(f"stream:{run_id}")
        return 1 if head is None else head[0] + 1

    def _check_head(self, run_id, expected):
        if self._next_sequence(run_id) != expected:
            raise ValueError("CONCURRENT_MODIFICATION: graph audit head changed")

    def _commit(self, intent, payload, capability, *, mutation=None, output_refs=None):
        self.kernel.commit_result(
            intent,
            OperationResult(
                operation_id=intent.context.operation_id,
                attempt_id=intent.context.attempt_id,
                status="SUCCESS",
                payload=payload,
                output_refs=output_refs or [],
            ),
            capability=capability,
            mutation=mutation,
        )

    def start(self, context, spec: RunSpec, *, capability, now: str) -> RunState:
        self._authorize(context, "graph.start", capability, spec.run_id)
        if context.case_version_id != spec.case_snapshot.snapshot_id:
            raise ValueError("graph context must pin the exact case snapshot")
        # The clock is trusted execution metadata, not a changed caller request on replay.
        intent = self._intent(context, "graph.start", spec.model_dump(mode="json"), capability)
        previous = self.read(context.operation_id, RunState)
        if previous is not None:
            return previous
        if (
            self.connection.execute(
                "SELECT 1 FROM workflow_runs WHERE run_id=?", (spec.run_id,)
            ).fetchone()
            is not None
        ):
            raise ValueError("graph run ID already exists")
        sequence = self._next_sequence(spec.run_id)
        state = RunState(
            run_id=spec.run_id,
            version=1,
            status="CREATED",
            current_turn=0,
            pending_finding_ids=spec.finding_ids,
            resolved_finding_ids=[],
            abstained_finding_ids=[],
            budget=BudgetUsage(),
            created_at=now,
            updated_at=now,
            stop_reason=None,
            review_outcome="NOT_REQUESTED",
            plan_refs=[],
            assessment_refs=[],
            result_refs=[],
            action_fingerprints=[],
            last_audit_sequence=sequence,
            pending_operation_id=None,
            active_turn_input=None,
            last_checkpoint_ref=None,
        )
        state_blob = self._blob(state.model_dump(mode="json"))
        spec_blob = self._blob(spec.model_dump(mode="json"))

        def insert():
            self._check_head(spec.run_id, sequence)
            if (
                self.connection.execute(
                    "SELECT 1 FROM workflow_runs WHERE run_id=?", (spec.run_id,)
                ).fetchone()
                is not None
            ):
                raise ValueError("graph run ID already exists")
            self.connection.execute(
                "INSERT INTO workflow_runs VALUES (?,?,?,?)",
                (spec.run_id, spec_blob.model_dump_json(), state_blob.model_dump_json(), 1),
            )

        self._commit(intent, state_blob, capability, mutation=insert, output_refs=[spec_blob])
        return state

    def _current(self, state, expected_version):
        current = self.load(state.run_id)
        if current.version != expected_version or state.version != expected_version:
            raise ValueError("CONCURRENT_MODIFICATION: stale graph state version")
        if current.status in _TERMINAL:
            raise ValueError("terminal graph run cannot be changed")
        if state.created_at != current.created_at:
            raise ValueError("graph creation timestamp is immutable")
        for ref in [*state.result_refs, state.active_turn_input, state.last_checkpoint_ref]:
            if ref is not None:
                self.blobs.get(ref)
        if state.active_turn_input is not None:
            active = RunState.model_validate_json(self.blobs.get(state.active_turn_input))
            if active.run_id != state.run_id or active.current_turn != current.current_turn:
                raise ValueError("active turn input belongs to a different run or turn")
        return current

    def _update(self, state, expected_version, ref, sequence):
        self._check_head(state.run_id, sequence)
        current = self.load(state.run_id)
        if current.version != expected_version or current.status in _TERMINAL:
            raise ValueError("CONCURRENT_MODIFICATION: graph state changed")
        updated = self.connection.execute(
            "UPDATE workflow_runs SET state_blob=?,version=? WHERE run_id=? AND version=?",
            (ref.model_dump_json(), state.version, state.run_id, expected_version),
        )
        if updated.rowcount != 1:
            raise ValueError("CONCURRENT_MODIFICATION: graph state changed")

    def save(
        self,
        context,
        state: RunState,
        expected_version: int,
        *,
        event_type="graph.state",
        capability,
    ) -> RunState:
        self._authorize(context, event_type, capability, state.run_id)
        intent = self._intent(
            context,
            event_type,
            {"expected_version": expected_version, "state": state.model_dump(mode="json")},
            capability,
        )
        previous = self.read(context.operation_id, RunState)
        if previous is not None:
            return previous
        current = self._current(state, expected_version)
        if state.current_turn != current.current_turn:
            raise ValueError("only finish_turn may advance the completed turn count")
        sequence = self._next_sequence(state.run_id)
        output = state.model_copy(
            update={"version": expected_version + 1, "last_audit_sequence": sequence}
        )
        ref = self._blob(output.model_dump(mode="json"))
        self._commit(
            intent,
            ref,
            capability,
            mutation=lambda: self._update(output, expected_version, ref, sequence),
        )
        return output

    def archive(self, context, event_type, payload: BoundaryModel, *, capability) -> BlobRef:
        intent = self._intent(context, event_type, payload.model_dump(mode="json"), capability)
        previous = self.read(context.operation_id, type(payload))
        if previous is not None:
            return self.kernel.get_result(context.operation_id).payload

        def check_live():
            if self.load(context.run_id).status in _TERMINAL:
                raise ValueError("terminal graph run cannot archive new work")

        check_live()
        self._commit(intent, intent.payload, capability, mutation=check_live)
        return intent.payload

    def list_turns(self, run_id) -> list[TurnManifest]:
        self._row(run_id)
        events = self._verify_stream(run_id)
        rows = self.connection.execute(
            "SELECT turn_id,turn_index,manifest_blob FROM workflow_turns "
            "WHERE run_id=? ORDER BY turn_index",
            (run_id,),
        ).fetchall()
        turns = []
        for row in rows:
            ref = BlobRef.model_validate_json(row["manifest_blob"])
            manifest = TurnManifest.model_validate_json(self.blobs.get(ref))
            if (
                manifest.run_id != run_id
                or manifest.turn_id != row["turn_id"]
                or manifest.turn_index != row["turn_index"]
            ):
                raise ValueError("turn ledger belongs to a different run")
            matches = [
                e
                for e in events
                if (
                    e.event_type == "graph.turn.result"
                    and e.sequence == manifest.last_event_sequence
                    and ref in e.output_refs
                    and e.payload_blob == manifest.output_state_blob
                )
            ]
            if len(matches) != 1:
                raise ValueError("turn manifest is not bound to its audited turn result")
            output = self.read(matches[0].operation_id, RunState)
            if (
                output.run_id != run_id
                or output.current_turn != manifest.turn_index
                or output.last_audit_sequence != manifest.last_event_sequence
            ):
                raise ValueError("turn output state disagrees with its audited manifest")
            self.blobs.get(manifest.input_state_blob)
            self.blobs.get(manifest.output_state_blob)
            self.blobs.get(manifest.coverage_summary_blob)
            turns.append(manifest)
        return turns

    def last_turn(self, run_id) -> TurnManifest | None:
        turns = self.list_turns(run_id)
        return turns[-1] if turns else None

    def finish_turn(
        self, context, state: RunState, expected_version: int, manifest: TurnManifest, *, capability
    ) -> RunState:
        self._authorize(context, "graph.turn", capability, state.run_id)
        intent = self._intent(
            context,
            "graph.turn",
            {
                "expected_version": expected_version,
                "state": state.model_dump(mode="json"),
                "manifest": manifest.model_dump(mode="json"),
            },
            capability,
        )
        previous = self.read(context.operation_id, RunState)
        if previous is not None:
            return previous
        current = self._current(state, expected_version)
        last = self.last_turn(state.run_id)
        if (
            manifest.run_id != state.run_id
            or manifest.turn_index != current.current_turn + 1
            or manifest.previous_turn_id != (None if last is None else last.turn_id)
        ):
            raise ValueError("turn manifest does not follow the authoritative run history")
        expected_input = current.active_turn_input or self.state_blob(state.run_id)
        if manifest.input_state_blob != expected_input:
            raise ValueError("turn input is not the pinned active state")
        input_state = RunState.model_validate_json(self.blobs.get(manifest.input_state_blob))
        if input_state.run_id != state.run_id or input_state.current_turn != current.current_turn:
            raise ValueError("turn input belongs to a different run or turn")
        if manifest.budget_before != input_state.budget or manifest.budget_after != state.budget:
            raise ValueError("turn budget does not match its pinned input/output state")
        self.blobs.get(manifest.coverage_summary_blob)
        sequence = self._next_sequence(state.run_id)
        output = state.model_copy(
            update={
                "version": expected_version + 1,
                "current_turn": current.current_turn + 1,
                "last_audit_sequence": sequence,
                "pending_operation_id": None,
                "pending_attempt_id": None,
                "active_turn_input": None,
            }
        )
        output_ref = self._blob(output.model_dump(mode="json"))
        completed = manifest.model_copy(
            update={
                "output_state_blob": output_ref,
                "first_event_sequence": input_state.last_audit_sequence + 1,
                "last_event_sequence": sequence,
            }
        )
        manifest_ref = self._blob(completed.model_dump(mode="json"))

        def finish():
            self._update(output, expected_version, output_ref, sequence)
            self.connection.execute(
                "INSERT INTO workflow_turns VALUES (?,?,?,?)",
                (
                    completed.turn_id,
                    state.run_id,
                    completed.turn_index,
                    manifest_ref.model_dump_json(),
                ),
            )

        self._commit(intent, output_ref, capability, mutation=finish, output_refs=[manifest_ref])
        return output
