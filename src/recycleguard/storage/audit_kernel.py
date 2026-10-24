"""V02 audited commit kernel — production replacement for the V01 CommitBoundary prototype.

Extends the V01 prototype with:
  - WAL-mode SQLite for safe concurrent readers
  - Attempt tracking: every attempt remains separately visible
  - Multi-stream support: stream_id drives per-stream sequence/hash heads
  - Capability checks: actor_kind must match the allowed set for each event_type prefix
  - Crash-window safety: blob placement before intent commit; no dispatch before intent commit
  - OUTCOME_UNKNOWN result on external-dispatch loss
  - Audit sink failure stops dispatch/completion (fail closed)

V01 CommitBoundary remains importable for tests that exercise the prototype directly.
"""

import hashlib
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from recycleguard.contracts import CommandContext
from recycleguard.contracts.audit import AuditEvent, OperationIntent, OperationResult
from recycleguard.contracts.core import ActorRef

from .blob_store import BlobStore, canonical_json_bytes


_KERNEL_SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS operation_intents (
    operation_id     TEXT PRIMARY KEY,
    idempotency_key  TEXT NOT NULL UNIQUE,
    stream_id        TEXT NOT NULL,
    intent_json      TEXT NOT NULL,
    recorded_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS operation_attempts (
    attempt_id    TEXT PRIMARY KEY,
    operation_id  TEXT NOT NULL REFERENCES operation_intents(operation_id),
    attempt_json  TEXT NOT NULL,
    committed_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_attempts_op ON operation_attempts (operation_id);

CREATE TABLE IF NOT EXISTS operation_results (
    operation_id  TEXT PRIMARY KEY REFERENCES operation_intents(operation_id),
    attempt_id    TEXT NOT NULL,
    status        TEXT NOT NULL,
    result_json   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_events (
    event_id    TEXT PRIMARY KEY,
    stream_id   TEXT NOT NULL,
    sequence    INTEGER NOT NULL,
    event_hash  TEXT NOT NULL,
    event_json  TEXT NOT NULL,
    UNIQUE (stream_id, sequence)
);

CREATE INDEX IF NOT EXISTS idx_events_stream ON audit_events (stream_id, sequence);
"""

# Maps event_type prefix to the set of actor_kind values permitted to produce it.
# Prefixes match the start of event_type strings (e.g. "intake." allows "intake.result").
_ACTOR_PERMISSIONS: dict[str, frozenset[str]] = {
    "cp0.": frozenset({"SERVICE", "EVALUATOR"}),
    "intake.": frozenset({"SERVICE"}),
    "extraction.": frozenset({"SERVICE"}),
    "normalization.": frozenset({"SERVICE"}),
    "snapshot.": frozenset({"SERVICE"}),
    "review.": frozenset({"HUMAN"}),
    "graph.": frozenset({"SERVICE", "MODEL_PROPOSAL"}),
    "report.": frozenset({"SERVICE"}),
    "export.": frozenset({"SERVICE", "HUMAN"}),
    "evaluation.": frozenset({"EVALUATOR"}),
}


def _check_actor_permission(event_type: str, actor: ActorRef) -> None:
    """Raise ValueError when actor_kind is not allowed for the given event_type prefix."""
    for prefix, allowed in _ACTOR_PERMISSIONS.items():
        if event_type.startswith(prefix):
            if actor.actor_kind not in allowed:
                raise ValueError(
                    f"actor_kind {actor.actor_kind!r} is not permitted for event_type "
                    f"{event_type!r} (allowed: {sorted(allowed)})"
                )
            return
    # Unknown prefix: allow any; production can tighten this list.


def _make_event(
    *,
    intent: OperationIntent,
    result: OperationResult,
    previous_sequence: int | None,
    previous_hash: str | None,
) -> AuditEvent:
    context = intent.context
    now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    output_refs = ([result.payload] if result.payload is not None else []) + result.output_refs
    event = AuditEvent(
        event_id=f"event:result_{context.operation_id}",
        stream_id=intent.stream_id,
        sequence=1 if previous_sequence is None else previous_sequence + 1,
        event_type=f"{intent.event_type}.result",
        recorded_at=now,
        actor=context.actor,
        command_id=context.command_id,
        operation_id=context.operation_id,
        attempt_id=context.attempt_id,
        case_version_id=context.case_version_id,
        run_id=context.run_id,
        turn_id=context.turn_id,
        input_refs=intent.input_refs,
        output_refs=output_refs,
        dependency_refs=[],
        payload_blob=result.payload or intent.payload,
        previous_event_hash=previous_hash,
        event_hash="0" * 64,
    )
    digest = hashlib.sha256(
        canonical_json_bytes(event.model_dump(mode="json", exclude={"event_hash"}))
    ).hexdigest()
    return event.model_copy(update={"event_hash": digest})


class AuditKernel:
    """Production audit kernel (V02).

    Usage pattern (mirrors the V01 CommitBoundary API but adds capability checks and attempts):

        kernel = AuditKernel(db_path, blob_store)

        # 1. Persist request bytes and intent BEFORE any external call.
        stored_intent = kernel.commit_intent(intent)

        # 2. Perform the side effect (acquisition, tool call, …).
        #    If you lose the response: use status=OUTCOME_UNKNOWN with AUDIT_UNAVAILABLE.

        # 3. Persist full returned bytes and commit result+event atomically.
        event = kernel.commit_result(stored_intent, result)

    No external dispatch may precede step 1.  The audit sink failure in step 3 stops
    completion (fail closed); re-drive from the stored intent.
    """

    def __init__(self, database: str | Path, blob_store: BlobStore) -> None:
        self.blob_store = blob_store
        self.connection = sqlite3.connect(database)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(_KERNEL_SCHEMA)

    def close(self) -> None:
        self.connection.close()

    # ------------------------------------------------------------------
    # Intent commit (step 1 of the write protocol)
    # ------------------------------------------------------------------

    def commit_intent(self, intent: OperationIntent) -> OperationIntent:
        """Persist intent; verify all input blobs and actor permission first.

        Idempotent: identical re-submission returns the stored intent.
        Different content on the same idempotency_key raises ValueError.
        """
        # Capability check BEFORE any database write.
        _check_actor_permission(intent.event_type, intent.context.actor)

        # blob-before-reference: every declared input blob must be retrievable.
        self.blob_store.get(intent.payload)
        for ref in intent.input_refs:
            self.blob_store.get(ref)

        encoded = canonical_json_bytes(intent.model_dump(mode="json")).decode()
        now = datetime.now(UTC).isoformat().replace("+00:00", "Z")

        existing = self.connection.execute(
            "SELECT intent_json FROM operation_intents WHERE idempotency_key = ?",
            (intent.idempotency_key,),
        ).fetchone()
        if existing is not None:
            if existing["intent_json"] != encoded:
                raise ValueError(
                    f"idempotency_key {intent.idempotency_key!r} already bound to "
                    "a different intent"
                )
            return OperationIntent.model_validate_json(existing["intent_json"])

        with self.connection:
            self.connection.execute(
                "INSERT INTO operation_intents VALUES (?, ?, ?, ?, ?)",
                (
                    intent.context.operation_id,
                    intent.idempotency_key,
                    intent.stream_id,
                    encoded,
                    now,
                ),
            )
        return intent

    # ------------------------------------------------------------------
    # Attempt tracking (optional; call between intent and result)
    # ------------------------------------------------------------------

    def record_attempt(self, intent: OperationIntent) -> None:
        """Record that an attempt for this intent is starting.

        Attempts are informational; multiple calls with the same attempt_id are idempotent.
        """
        context = intent.context
        attempt_encoded = canonical_json_bytes(
            {"operation_id": context.operation_id, "attempt_id": context.attempt_id}
        ).decode()
        now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        existing = self.connection.execute(
            "SELECT 1 FROM operation_attempts WHERE attempt_id = ?",
            (context.attempt_id,),
        ).fetchone()
        if existing is not None:
            return
        with self.connection:
            self.connection.execute(
                "INSERT INTO operation_attempts VALUES (?, ?, ?, ?)",
                (context.attempt_id, context.operation_id, attempt_encoded, now),
            )

    # ------------------------------------------------------------------
    # Result commit (step 3 of the write protocol)
    # ------------------------------------------------------------------

    def commit_result(
        self, intent: OperationIntent, result: OperationResult
    ) -> AuditEvent:
        """Atomically persist result and audit event.

        Preconditions:
          - The exact intent must already be committed (intent_before_write ordering).
          - result.operation_id and result.attempt_id must match the intent context.
          - All output blobs must be in the blob store.

        Idempotent: identical re-submission returns the stored event.
        Terminal collision with different content raises ValueError.
        Audit table insert failure rolls back result insert (fail closed).
        """
        context = intent.context
        if (result.operation_id, result.attempt_id) != (
            context.operation_id,
            context.attempt_id,
        ):
            raise ValueError("result operation/attempt IDs do not match intent context")

        stored = self.connection.execute(
            "SELECT intent_json FROM operation_intents WHERE operation_id = ?",
            (context.operation_id,),
        ).fetchone()
        expected_encoded = canonical_json_bytes(intent.model_dump(mode="json")).decode()
        if stored is None or stored["intent_json"] != expected_encoded:
            raise ValueError(
                "exact intent must be committed before committing its result "
                "(intent-before-write ordering violated)"
            )

        # blob-before-reference for all output blobs
        if result.payload is not None:
            self.blob_store.get(result.payload)
        for ref in result.output_refs:
            self.blob_store.get(ref)

        result_encoded = canonical_json_bytes(result.model_dump(mode="json")).decode()

        with self.connection:
            existing_result = self.connection.execute(
                "SELECT result_json, attempt_id FROM operation_results WHERE operation_id = ?",
                (context.operation_id,),
            ).fetchone()
            if existing_result is not None:
                if existing_result["result_json"] != result_encoded:
                    raise ValueError(
                        f"operation {context.operation_id!r} already has a different terminal result"
                    )
                # Idempotent: return the stored event.
                event_row = self.connection.execute(
                    "SELECT event_json FROM audit_events WHERE event_id = ?",
                    (f"event:result_{context.operation_id}",),
                ).fetchone()
                return AuditEvent.model_validate_json(event_row["event_json"])

            previous = self.connection.execute(
                "SELECT sequence, event_hash FROM audit_events "
                "WHERE stream_id = ? ORDER BY sequence DESC LIMIT 1",
                (intent.stream_id,),
            ).fetchone()
            event = _make_event(
                intent=intent,
                result=result,
                previous_sequence=None if previous is None else previous["sequence"],
                previous_hash=None if previous is None else previous["event_hash"],
            )

            # Both rows in one transaction — audit event failure rolls back result.
            self.connection.execute(
                "INSERT INTO operation_results VALUES (?, ?, ?, ?)",
                (context.operation_id, context.attempt_id, result.status, result_encoded),
            )
            self.connection.execute(
                "INSERT INTO audit_events VALUES (?, ?, ?, ?, ?)",
                (
                    event.event_id,
                    event.stream_id,
                    event.sequence,
                    event.event_hash,
                    event.model_dump_json(),
                ),
            )
        return event

    # ------------------------------------------------------------------
    # Read helpers
    # ------------------------------------------------------------------

    def get_intent(self, operation_id: str) -> OperationIntent | None:
        row = self.connection.execute(
            "SELECT intent_json FROM operation_intents WHERE operation_id = ?",
            (operation_id,),
        ).fetchone()
        if row is None:
            return None
        return OperationIntent.model_validate_json(row["intent_json"])

    def get_result(self, operation_id: str) -> OperationResult | None:
        row = self.connection.execute(
            "SELECT result_json FROM operation_results WHERE operation_id = ?",
            (operation_id,),
        ).fetchone()
        if row is None:
            return None
        return OperationResult.model_validate_json(row["result_json"])

    def get_event(self, event_id: str) -> AuditEvent | None:
        row = self.connection.execute(
            "SELECT event_json FROM audit_events WHERE event_id = ?",
            (event_id,),
        ).fetchone()
        if row is None:
            return None
        return AuditEvent.model_validate_json(row["event_json"])

    def list_stream_events(self, stream_id: str) -> list[AuditEvent]:
        rows = self.connection.execute(
            "SELECT event_json FROM audit_events WHERE stream_id = ? ORDER BY sequence",
            (stream_id,),
        ).fetchall()
        return [AuditEvent.model_validate_json(r["event_json"]) for r in rows]

    def list_attempts(self, operation_id: str) -> list[dict]:
        rows = self.connection.execute(
            "SELECT attempt_json, committed_at FROM operation_attempts WHERE operation_id = ?",
            (operation_id,),
        ).fetchall()
        return [{"attempt": r["attempt_json"], "committed_at": r["committed_at"]} for r in rows]

    def stream_head(self, stream_id: str) -> tuple[int, str] | None:
        """Return (sequence, event_hash) of the latest event on the stream, or None."""
        row = self.connection.execute(
            "SELECT sequence, event_hash FROM audit_events "
            "WHERE stream_id = ? ORDER BY sequence DESC LIMIT 1",
            (stream_id,),
        ).fetchone()
        if row is None:
            return None
        return (row["sequence"], row["event_hash"])
