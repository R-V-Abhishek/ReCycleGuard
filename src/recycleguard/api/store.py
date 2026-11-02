"""API catalogue/job metadata. Investigation state remains in the application ledger."""

import sqlite3
from contextlib import contextmanager

_SCHEMA = """
CREATE TABLE IF NOT EXISTS dossiers (
 dossier_id TEXT PRIMARY KEY, path TEXT NOT NULL, name TEXT NOT NULL,
 candidate TEXT, approved TEXT
);
CREATE TABLE IF NOT EXISTS jobs (
 run_id TEXT PRIMARY KEY, dossier_id TEXT NOT NULL REFERENCES dossiers(dossier_id),
 status TEXT NOT NULL, detail TEXT, cancel_requested INTEGER NOT NULL DEFAULT 0
);
"""


class ApiStore:
    def __init__(self, path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.executescript(_SCHEMA)
            db.execute("UPDATE jobs SET status='INTERRUPTED' WHERE status IN ('QUEUED','RUNNING')")

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def dossier(self, dossier_id):
        with self.connection() as db:
            row = db.execute("SELECT * FROM dossiers WHERE dossier_id=?", (dossier_id,)).fetchone()
        if row is None:
            raise KeyError("dossier does not exist")
        return dict(row)

    def dossiers(self):
        with self.connection() as db:
            return [dict(row) for row in db.execute("SELECT * FROM dossiers ORDER BY rowid DESC")]

    def register(self, dossier_id, path, name):
        with self.connection() as db:
            db.execute(
                "INSERT INTO dossiers VALUES (?,?,?,NULL,NULL)", (dossier_id, str(path), name)
            )

    def foundation(self, dossier_id, blob, *, approved=False):
        column = "approved" if approved else "candidate"
        with self.connection() as db:
            db.execute(
                f"UPDATE dossiers SET {column}=? WHERE dossier_id=?",
                (blob.model_dump_json(), dossier_id),
            )

    def job(self, run_id):
        with self.connection() as db:
            row = db.execute("SELECT * FROM jobs WHERE run_id=?", (run_id,)).fetchone()
        if row is None:
            raise KeyError("run is not registered with this API")
        return dict(row)

    def jobs(self, dossier_id=None):
        with self.connection() as db:
            if dossier_id is None:
                rows = db.execute("SELECT * FROM jobs ORDER BY rowid DESC")
            else:
                rows = db.execute(
                    "SELECT * FROM jobs WHERE dossier_id=? ORDER BY rowid DESC", (dossier_id,)
                )
            return [dict(row) for row in rows]

    def add_job(self, run_id, dossier_id):
        with self.connection() as db:
            db.execute("INSERT INTO jobs VALUES (?,?,'QUEUED',NULL,0)", (run_id, dossier_id))

    def job_status(self, run_id, status, detail=None):
        with self.connection() as db:
            db.execute("UPDATE jobs SET status=?,detail=? WHERE run_id=?", (status, detail, run_id))

    def request_cancel(self, run_id):
        self.job(run_id)
        with self.connection() as db:
            db.execute("UPDATE jobs SET cancel_requested=1 WHERE run_id=?", (run_id,))

    def clear_cancel(self, run_id):
        with self.connection() as db:
            db.execute("UPDATE jobs SET cancel_requested=0 WHERE run_id=?", (run_id,))
