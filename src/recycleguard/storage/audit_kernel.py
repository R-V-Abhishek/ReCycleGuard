"""V02 coordinator for stable requests, attempts and atomic audited writes."""

import hashlib
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from recycleguard.contracts.audit import AuditEvent, OperationIntent, OperationResult

from .authority import Capability, LocalAuthority
from .blob_store import BlobStore, canonical_json_bytes

_SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS operation_intents (
 operation_id TEXT PRIMARY KEY, idempotency_key TEXT NOT NULL UNIQUE,
 stream_id TEXT NOT NULL, intent_json TEXT NOT NULL, recorded_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS operation_attempts (
 attempt_id TEXT PRIMARY KEY, operation_id TEXT NOT NULL REFERENCES operation_intents(operation_id),
 attempt_json TEXT NOT NULL, committed_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS operation_results (
 operation_id TEXT PRIMARY KEY REFERENCES operation_intents(operation_id),
 attempt_id TEXT NOT NULL, status TEXT NOT NULL, result_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS attempt_results (
 attempt_id TEXT PRIMARY KEY REFERENCES operation_attempts(attempt_id),
 result_json TEXT NOT NULL, terminal INTEGER NOT NULL, event_id TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_events (
 event_id TEXT PRIMARY KEY, stream_id TEXT NOT NULL, sequence INTEGER NOT NULL,
 event_hash TEXT NOT NULL, event_json TEXT NOT NULL, UNIQUE(stream_id,sequence)
);
"""


def _now():
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _encode(model):
    return canonical_json_bytes(model.model_dump(mode="json")).decode("utf-8")


def _logical(intent: OperationIntent):
    value = intent.model_dump(mode="json")
    del value["context"]["attempt_id"]
    return canonical_json_bytes(value)


class AuditKernel:
    def __init__(
        self,
        database: str | Path,
        blob_store: BlobStore,
        *,
        authority: LocalAuthority | None = None,
    ):
        self.blob_store = blob_store
        self.authority = authority or LocalAuthority()
        self.connection = sqlite3.connect(database)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(_SCHEMA)
        self.active_intent: OperationIntent | None = None

    def close(self):
        self.connection.close()

    def _authorize(self, intent, capability):
        self.authority.check(capability, intent.context.actor, intent.event_type)

    def commit_intent(self, intent: OperationIntent, *, capability: Capability | None = None):
        self._authorize(intent, capability)
        for ref in [intent.payload, *intent.input_refs]:
            self.blob_store.get(ref)
        with self.connection:
            self.connection.execute("BEGIN IMMEDIATE")
            row = self.connection.execute(
                "SELECT intent_json FROM operation_intents WHERE idempotency_key=?",
                (intent.idempotency_key,),
            ).fetchone()
            if row is not None:
                stored = OperationIntent.model_validate_json(row["intent_json"])
                if _logical(stored) != _logical(intent):
                    raise ValueError("idempotency key already bound to a different intent")
            else:
                self.connection.execute(
                    "INSERT INTO operation_intents VALUES (?,?,?,?,?)",
                    (
                        intent.context.operation_id,
                        intent.idempotency_key,
                        intent.stream_id,
                        _encode(intent),
                        _now(),
                    ),
                )
            terminal = self.get_result(intent.context.operation_id)
            if terminal is not None and terminal.attempt_id != intent.context.attempt_id:
                raise ValueError(
                    "operation is already terminal; no new dispatch attempt is permitted"
                )
            self._record_attempt(intent)
        return intent

    def _record_attempt(self, intent):
        row = self.connection.execute(
            "SELECT attempt_json FROM operation_attempts WHERE attempt_id=?",
            (intent.context.attempt_id,),
        ).fetchone()
        if row is not None:
            if row["attempt_json"] != _encode(intent):
                raise ValueError("attempt ID already bound to different input")
        else:
            self.connection.execute(
                "INSERT INTO operation_attempts VALUES (?,?,?,?)",
                (intent.context.attempt_id, intent.context.operation_id, _encode(intent), _now()),
            )

    def record_attempt(self, intent: OperationIntent, *, capability: Capability | None = None):
        # Same validation and atomic registration as the initial attempt; not informational only.
        return self.commit_intent(intent, capability=capability)

    def commit_result(
        self,
        intent: OperationIntent,
        result: OperationResult,
        *,
        capability: Capability | None = None,
        mutation: Callable[[], None] | None = None,
        terminal: bool = True,
    ):
        self._authorize(intent, capability)
        if not terminal and result.status != "FAILED":
            raise ValueError("only a known failed attempt may remain retryable")
        context = intent.context
        if (result.operation_id, result.attempt_id) != (context.operation_id, context.attempt_id):
            raise ValueError("result operation/attempt IDs do not match intent context")
        for ref in ([result.payload] if result.payload is not None else []) + result.output_refs:
            self.blob_store.get(ref)
        with self.connection:
            self.connection.execute("BEGIN IMMEDIATE")
            attempt = self.connection.execute(
                "SELECT attempt_json FROM operation_attempts WHERE attempt_id=? AND operation_id=?",
                (context.attempt_id, context.operation_id),
            ).fetchone()
            if attempt is None or attempt["attempt_json"] != _encode(intent):
                raise ValueError("exact intent must be committed before its result")
            previous_attempt = self.connection.execute(
                "SELECT result_json,terminal,event_id FROM attempt_results WHERE attempt_id=?",
                (context.attempt_id,),
            ).fetchone()
            if previous_attempt is not None:
                if previous_attempt["result_json"] != _encode(result) or previous_attempt[
                    "terminal"
                ] != int(terminal):
                    raise ValueError("attempt already has a different terminal result")
                return self.get_event(previous_attempt["event_id"])
            prior = self.connection.execute(
                "SELECT result_json FROM operation_results WHERE operation_id=?",
                (context.operation_id,),
            ).fetchone()
            if prior is not None:
                if prior["result_json"] != _encode(result):
                    raise ValueError("operation already has a different terminal result")
                return self.get_event(f"event:result_{context.operation_id}")
            if not terminal and mutation is not None:
                raise ValueError("failed retryable attempts cannot commit domain mutations")
            self.active_intent = intent
            try:
                if mutation is not None:
                    mutation()
                previous = self.connection.execute(
                    "SELECT sequence,event_hash FROM audit_events WHERE stream_id=? "
                    "ORDER BY sequence DESC LIMIT 1",
                    (intent.stream_id,),
                ).fetchone()
                event = AuditEvent(
                    event_id=(
                        f"event:result_{context.operation_id}"
                        if terminal
                        else f"event:attempt_{context.attempt_id}"
                    ),
                    stream_id=intent.stream_id,
                    sequence=1 if previous is None else previous["sequence"] + 1,
                    event_type=f"{intent.event_type}.result",
                    recorded_at=_now(),
                    actor=context.actor,
                    command_id=context.command_id,
                    operation_id=context.operation_id,
                    attempt_id=context.attempt_id,
                    case_version_id=context.case_version_id,
                    run_id=context.run_id,
                    turn_id=context.turn_id,
                    input_refs=[intent.payload, *intent.input_refs],
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
                    "INSERT INTO attempt_results VALUES (?,?,?,?)",
                    (context.attempt_id, _encode(result), int(terminal), event.event_id),
                )
                if terminal:
                    self.connection.execute(
                        "INSERT INTO operation_results VALUES (?,?,?,?)",
                        (context.operation_id, context.attempt_id, result.status, _encode(result)),
                    )
                self.connection.execute(
                    "INSERT INTO audit_events VALUES (?,?,?,?,?)",
                    (
                        event.event_id,
                        event.stream_id,
                        event.sequence,
                        event.event_hash,
                        _encode(event),
                    ),
                )
            finally:
                self.active_intent = None
        return event

    def get_intent(self, operation_id):
        row = self.connection.execute(
            "SELECT intent_json FROM operation_intents WHERE operation_id=?", (operation_id,)
        ).fetchone()
        return None if row is None else OperationIntent.model_validate_json(row["intent_json"])

    def get_result(self, operation_id):
        row = self.connection.execute(
            "SELECT result_json FROM operation_results WHERE operation_id=?", (operation_id,)
        ).fetchone()
        return None if row is None else OperationResult.model_validate_json(row["result_json"])

    def get_event(self, event_id):
        row = self.connection.execute(
            "SELECT event_json FROM audit_events WHERE event_id=?", (event_id,)
        ).fetchone()
        return None if row is None else AuditEvent.model_validate_json(row["event_json"])

    def list_stream_events(self, stream_id):
        rows = self.connection.execute(
            "SELECT event_json FROM audit_events WHERE stream_id=? ORDER BY sequence", (stream_id,)
        ).fetchall()
        return [AuditEvent.model_validate_json(r["event_json"]) for r in rows]

    def list_attempts(self, operation_id):
        rows = self.connection.execute(
            "SELECT attempt_json,committed_at FROM operation_attempts "
            "WHERE operation_id=? ORDER BY rowid",
            (operation_id,),
        ).fetchall()
        return [{"attempt": r["attempt_json"], "committed_at": r["committed_at"]} for r in rows]

    def stream_head(self, stream_id):
        row = self.connection.execute(
            "SELECT sequence,event_hash FROM audit_events WHERE stream_id=? "
            "ORDER BY sequence DESC LIMIT 1",
            (stream_id,),
        ).fetchone()
        return None if row is None else (row["sequence"], row["event_hash"])
