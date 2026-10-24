"""V01 SQLite prototype, adapted to shared CP0 contracts.

Proves blob-before-reference placement, intent binding and terminal event atomicity.
Production audit/recovery, capabilities, migrations and multi-attempt retries are V02+.
"""

import hashlib
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from recycleguard.contracts import CommandContext
from recycleguard.contracts.audit import AuditEvent, OperationIntent, OperationResult

from .blob_store import BlobStore, canonical_json_bytes

# Compatibility import name only: there is one context model, not a second schema.
AuditContext = CommandContext


class CommitBoundary:
    def __init__(self, database: str | Path, blob_store: BlobStore) -> None:
        self.blob_store = blob_store
        self.connection = sqlite3.connect(database)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.executescript("""
            CREATE TABLE IF NOT EXISTS operation_intents (
                operation_id TEXT PRIMARY KEY,
                idempotency_key TEXT NOT NULL UNIQUE,
                intent_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS operation_results (
                operation_id TEXT PRIMARY KEY REFERENCES operation_intents(operation_id),
                result_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS audit_events (
                event_id TEXT PRIMARY KEY,
                stream_id TEXT NOT NULL,
                sequence INTEGER NOT NULL,
                event_hash TEXT NOT NULL,
                event_json TEXT NOT NULL,
                UNIQUE(stream_id, sequence)
            );
        """)

    def close(self) -> None:
        self.connection.close()

    def commit_intent(self, intent: OperationIntent) -> OperationIntent:
        for ref in [intent.payload, *intent.input_refs]:
            self.blob_store.get(ref)
        encoded = canonical_json_bytes(intent.model_dump(mode="json")).decode()
        existing = self.connection.execute(
            "SELECT intent_json FROM operation_intents WHERE idempotency_key = ?",
            (intent.idempotency_key,),
        ).fetchone()
        if existing is not None:
            if existing["intent_json"] != encoded:
                raise ValueError("idempotency key already has different input/context")
            return OperationIntent.model_validate_json(existing["intent_json"])
        with self.connection:
            self.connection.execute(
                "INSERT INTO operation_intents VALUES (?, ?, ?)",
                (intent.context.operation_id, intent.idempotency_key, encoded),
            )
        return intent

    def commit_result(self, intent: OperationIntent, result: OperationResult) -> AuditEvent:
        context = intent.context
        if (result.operation_id, result.attempt_id) != (context.operation_id, context.attempt_id):
            raise ValueError("result operation/attempt does not match intent")
        stored = self.connection.execute(
            "SELECT intent_json FROM operation_intents WHERE operation_id = ?",
            (context.operation_id,),
        ).fetchone()
        if (
            stored is None
            or stored["intent_json"]
            != canonical_json_bytes(intent.model_dump(mode="json")).decode()
        ):
            raise ValueError("exact intent must be committed before result")
        encoded = canonical_json_bytes(result.model_dump(mode="json")).decode()
        for ref in ([result.payload] if result.payload is not None else []) + result.output_refs:
            self.blob_store.get(ref)
        with self.connection:
            existing = self.connection.execute(
                "SELECT result_json FROM operation_results WHERE operation_id = ?",
                (result.operation_id,),
            ).fetchone()
            if existing is not None:
                if existing["result_json"] != encoded:
                    raise ValueError("operation already has a different terminal result")
                row = self.connection.execute(
                    "SELECT event_json FROM audit_events WHERE event_id = ?",
                    (f"event:result_{result.operation_id}",),
                ).fetchone()
                return AuditEvent.model_validate_json(row["event_json"])
            previous = self.connection.execute(
                "SELECT sequence, event_hash FROM audit_events WHERE stream_id = ? "
                "ORDER BY sequence DESC LIMIT 1",
                (intent.stream_id,),
            ).fetchone()
            event = AuditEvent(
                event_id=f"event:result_{result.operation_id}",
                stream_id=intent.stream_id,
                sequence=1 if previous is None else previous["sequence"] + 1,
                event_type=f"{intent.event_type}.result",
                recorded_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                actor=context.actor,
                command_id=context.command_id,
                operation_id=context.operation_id,
                attempt_id=context.attempt_id,
                case_version_id=context.case_version_id,
                run_id=context.run_id,
                turn_id=context.turn_id,
                input_refs=intent.input_refs,
                output_refs=([result.payload] if result.payload is not None else [])
                + result.output_refs,
                dependency_refs=[],
                payload_blob=result.payload or intent.payload,
                previous_event_hash=None if previous is None else previous["event_hash"],
                event_hash="0" * 64,
            )
            digest = hashlib.sha256(
                canonical_json_bytes(event.model_dump(mode="json", exclude={"event_hash"}))
            ).hexdigest()
            event = event.model_copy(update={"event_hash": digest})
            self.connection.execute(
                "INSERT INTO operation_results VALUES (?, ?)", (result.operation_id, encoded)
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
