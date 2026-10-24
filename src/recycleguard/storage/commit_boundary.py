"""Small SQLite intent/result commit boundary for V01.

This is deliberately narrower than the production V02 audit kernel. It proves
that blobs are durable before references are committed and that an operation's
intent, terminal result, and hash-chained event commit atomically.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any
import uuid

from .blob_store import BlobRef, BlobStore, canonical_json_bytes


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _id(prefix: str) -> str:
    return f"{prefix}:{uuid.uuid4().hex}"


@dataclass(frozen=True)
class AuditContext:
    command_id: str
    operation_id: str
    attempt_id: str
    actor_id: str
    actor_kind: str
    stream_id: str = "stream:prototype"
    case_version_id: str | None = None
    run_id: str | None = None
    turn_id: str | None = None


@dataclass(frozen=True)
class OperationIntent:
    context: AuditContext
    idempotency_key: str
    event_type: str
    payload: BlobRef
    input_refs: tuple[BlobRef, ...] = ()


@dataclass(frozen=True)
class OperationResult:
    operation_id: str
    status: str
    payload: BlobRef | None
    output_refs: tuple[BlobRef, ...] = ()
    issue_codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class AuditEvent:
    event_id: str
    stream_id: str
    sequence: int
    event_type: str
    recorded_at: str
    context: AuditContext
    input_refs: tuple[BlobRef, ...]
    output_refs: tuple[BlobRef, ...]
    payload: BlobRef
    previous_event_hash: str | None
    event_hash: str

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["context"] = asdict(self.context)
        value["input_refs"] = [asdict(ref) for ref in self.input_refs]
        value["output_refs"] = [asdict(ref) for ref in self.output_refs]
        value["payload"] = asdict(self.payload)
        return value


class CommitBoundary:
    """Prototype coordinator for durable blob references and SQLite events."""

    def __init__(self, database: str | Path, blob_store: BlobStore) -> None:
        self.blob_store = blob_store
        self.connection = sqlite3.connect(database)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self._create_schema()

    def close(self) -> None:
        self.connection.close()

    def commit_intent(self, intent: OperationIntent) -> OperationIntent:
        self._require_blob(intent.payload)
        for reference in intent.input_refs:
            self._require_blob(reference)
        context = intent.context
        payload_json = json.dumps(asdict(intent.payload), sort_keys=True)
        try:
            with self.connection:
                self.connection.execute(
                    """
                    INSERT INTO operation_intents
                    (operation_id, attempt_id, idempotency_key, event_type,
                     context_json, payload_json)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        context.operation_id,
                        context.attempt_id,
                        intent.idempotency_key,
                        intent.event_type,
                        json.dumps(asdict(context), sort_keys=True),
                        payload_json,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            existing = self.connection.execute(
                "SELECT payload_json FROM operation_intents WHERE idempotency_key = ?",
                (intent.idempotency_key,),
            ).fetchone()
            if existing is None or existing["payload_json"] != payload_json:
                raise ValueError("idempotency key already has different input") from exc
            return intent
        return intent

    def commit_result(self, intent: OperationIntent, result: OperationResult) -> AuditEvent:
        if result.operation_id != intent.context.operation_id:
            raise ValueError("result operation_id does not match intent")
        if result.payload is not None:
            self._require_blob(result.payload)
        for reference in result.output_refs:
            self._require_blob(reference)
        context = intent.context
        with self.connection:
            stored_intent = self.connection.execute(
                "SELECT 1 FROM operation_intents WHERE operation_id = ?",
                (context.operation_id,),
            ).fetchone()
            if stored_intent is None:
                raise ValueError("intent must be committed before result")
            if self.connection.execute(
                "SELECT 1 FROM operation_results WHERE operation_id = ?",
                (context.operation_id,),
            ).fetchone():
                raise ValueError("operation already has a terminal result")
            previous = self.connection.execute(
                "SELECT event_hash, sequence FROM audit_events "
                "WHERE stream_id = ? ORDER BY sequence DESC LIMIT 1",
                (context.stream_id,),
            ).fetchone()
            sequence = 1 if previous is None else int(previous["sequence"]) + 1
            previous_hash = None if previous is None else previous["event_hash"]
            event = self._make_event(
                intent,
                result,
                sequence,
                previous_hash,
            )
            self.connection.execute(
                """
                INSERT INTO operation_results
                (operation_id, status, payload_json, output_refs_json, issue_codes_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    result.operation_id,
                    result.status,
                    None
                    if result.payload is None
                    else json.dumps(asdict(result.payload), sort_keys=True),
                    json.dumps([asdict(ref) for ref in result.output_refs]),
                    json.dumps(result.issue_codes),
                ),
            )
            self.connection.execute(
                """
                INSERT INTO audit_events
                (event_id, stream_id, sequence, event_type, recorded_at,
                 context_json, input_refs_json, output_refs_json, payload_json,
                 previous_event_hash, event_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    event.stream_id,
                    event.sequence,
                    event.event_type,
                    event.recorded_at,
                    json.dumps(asdict(event.context), sort_keys=True),
                    json.dumps([asdict(ref) for ref in event.input_refs]),
                    json.dumps([asdict(ref) for ref in event.output_refs]),
                    json.dumps(asdict(event.payload), sort_keys=True),
                    event.previous_event_hash,
                    event.event_hash,
                ),
            )
        return event

    def _make_event(
        self,
        intent: OperationIntent,
        result: OperationResult,
        sequence: int,
        previous_hash: str | None,
    ) -> AuditEvent:
        output_refs = result.output_refs
        if result.payload is not None:
            output_refs = (result.payload, *output_refs)
        event = AuditEvent(
            event_id=_id("event"),
            stream_id=intent.context.stream_id,
            sequence=sequence,
            event_type=f"{intent.event_type}.result",
            recorded_at=now(),
            context=intent.context,
            input_refs=intent.input_refs,
            output_refs=output_refs,
            payload=result.payload or intent.payload,
            previous_event_hash=previous_hash,
            event_hash="",
        )
        digest = hashlib.sha256(
            canonical_json_bytes(
                {
                    key: value
                    for key, value in event.as_dict().items()
                    if key != "event_hash"
                }
            )
        ).hexdigest()
        return AuditEvent(
            event_id=event.event_id,
            stream_id=event.stream_id,
            sequence=event.sequence,
            event_type=event.event_type,
            recorded_at=event.recorded_at,
            context=event.context,
            input_refs=event.input_refs,
            output_refs=event.output_refs,
            payload=event.payload,
            previous_event_hash=event.previous_event_hash,
            event_hash=digest,
        )

    def _require_blob(self, reference: BlobRef) -> None:
        self.blob_store.get(reference)

    def _create_schema(self) -> None:
        with self.connection:
            self.connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS operation_intents (
                    operation_id TEXT PRIMARY KEY,
                    attempt_id TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    event_type TEXT NOT NULL,
                    context_json TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS operation_results (
                    operation_id TEXT PRIMARY KEY REFERENCES operation_intents(operation_id),
                    status TEXT NOT NULL,
                    payload_json TEXT,
                    output_refs_json TEXT NOT NULL,
                    issue_codes_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS audit_events (
                    event_id TEXT PRIMARY KEY,
                    stream_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    recorded_at TEXT NOT NULL,
                    context_json TEXT NOT NULL,
                    input_refs_json TEXT NOT NULL,
                    output_refs_json TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    previous_event_hash TEXT,
                    event_hash TEXT NOT NULL,
                    UNIQUE(stream_id, sequence)
                );
                """
            )
