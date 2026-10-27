"""SQLite FTS5 lexical index for regulatory clauses and tables.

Owned by Sampreeth (H05).
Implements C06 BM25 search, ranking, and exact locator lookups.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from recycleguard.contracts.retrieval import LexicalConfiguration
from recycleguard.indexing.models import IndexedChunk

re_sub_special = re.compile(r"[^\w\s\-\.]")


def _sanitize_fts5_query(query: str) -> str:
    """Sanitize user query string for safe FTS5 execution without syntax crashes."""
    # Strip any FTS5 control characters or unbalanced quotes
    cleaned = re_sub_special.sub(" ", query).strip()
    tokens = [t for t in cleaned.split() if t]
    if not tokens:
        return '""'
    # Format each token as a prefix search token: "token"*
    # so partial keywords also match
    terms = [f'"{tok}"*' for tok in tokens]
    return " AND ".join(terms)


class FTS5Index:
    """SQLite FTS5 virtual table wrapper with BM25 ranking."""

    def __init__(
        self,
        db_path: Path | str,
        config: LexicalConfiguration | None = None,
    ):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.config = config or LexicalConfiguration()
        self.connection = sqlite3.connect(self.db_path)
        self.connection.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        with self.connection:
            self.connection.execute(
                f"""
                CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
                    chunk_id UNINDEXED,
                    provision_version_id UNINDEXED,
                    source_version_id UNINDEXED,
                    legal_path,
                    title,
                    text,
                    regime,
                    role_scope,
                    affected_roles,
                    disposition UNINDEXED,
                    chunk_type UNINDEXED,
                    tokenize='{self.config.tokenizer}'
                );
                """
            )
            self.connection.execute(
                """
                CREATE TABLE IF NOT EXISTS chunks_metadata (
                    chunk_id TEXT PRIMARY KEY,
                    provision_version_id TEXT NOT NULL,
                    source_version_id TEXT NOT NULL,
                    legal_path TEXT NOT NULL,
                    disposition TEXT NOT NULL,
                    regime TEXT NOT NULL,
                    json_data TEXT NOT NULL
                );
                """
            )

    def insert_chunks(self, chunks: list[IndexedChunk]) -> None:
        """Insert or replace indexed chunks into FTS5 table and metadata store."""
        with self.connection:
            for chunk in chunks:
                roles_csv = ",".join(chunk.affected_roles)
                # Store in metadata table
                self.connection.execute(
                    """
                    INSERT OR REPLACE INTO chunks_metadata (
                        chunk_id, provision_version_id, source_version_id,
                        legal_path, disposition, regime, json_data
                    ) VALUES (?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        chunk.chunk_id,
                        chunk.provision_version_id,
                        chunk.source_version_id,
                        chunk.legal_path,
                        chunk.disposition,
                        chunk.regime,
                        chunk.model_dump_json(),
                    ),
                )
                # Store in FTS5 table if eligible
                if chunk.disposition != "UNINDEXABLE":
                    # Remove prior instance if exists
                    self.connection.execute(
                        "DELETE FROM chunks_fts WHERE chunk_id = ?",
                        (chunk.chunk_id,),
                    )
                    self.connection.execute(
                        """
                        INSERT INTO chunks_fts (
                            chunk_id, provision_version_id, source_version_id,
                            legal_path, title, text, regime, role_scope,
                            affected_roles, disposition, chunk_type
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                        """,
                        (
                            chunk.chunk_id,
                            chunk.provision_version_id,
                            chunk.source_version_id,
                            chunk.legal_path,
                            chunk.title or "",
                            chunk.text,
                            chunk.regime,
                            chunk.role_scope,
                            roles_csv,
                            chunk.disposition,
                            chunk.chunk_type,
                        ),
                    )

    def search(
        self,
        query: str,
        *,
        regime: str | None = None,
        role: str | None = None,
        disposition: str = "INDEXED",
        limit: int = 10,
    ) -> list[tuple[IndexedChunk, float]]:
        """Search chunks with BM25 scoring and optional metadata filters."""
        if not query.strip():
            return []

        fts_query = _sanitize_fts5_query(query)
        sql = """
            SELECT chunk_id, bm25(chunks_fts, 0.0, 0.0, 0.0, 2.0, 1.5, 1.0, 0.0, 0.0, 0.0) AS score
            FROM chunks_fts
            WHERE chunks_fts MATCH ?
              AND disposition = ?
        """
        params: list[object] = [fts_query, disposition]

        if regime is not None:
            sql += " AND regime = ?"
            params.append(regime)
        if role is not None:
            sql += " AND affected_roles LIKE ?"
            params.append(f"%{role}%")

        sql += " ORDER BY score ASC LIMIT ?"
        params.append(limit)

        try:
            rows = self.connection.execute(sql, params).fetchall()
        except sqlite3.OperationalError:
            # Fallback for empty or special match syntax
            return []

        results: list[tuple[IndexedChunk, float]] = []
        for row in rows:
            chunk = self.get_chunk(row["chunk_id"])
            if chunk is not None:
                # In SQLite FTS5, bm25() returns lower scores for better matches (negative/smaller).
                # Convert to normalized positive score
                raw_score = float(row["score"])
                relevance = max(0.0, -raw_score) if raw_score < 0 else 1.0 / (1.0 + raw_score)
                results.append((chunk, relevance))

        return results

    def get_chunk(self, chunk_id: str) -> IndexedChunk | None:
        """Fetch chunk by chunk_id from metadata table."""
        row = self.connection.execute(
            "SELECT json_data FROM chunks_metadata WHERE chunk_id = ?",
            (chunk_id,),
        ).fetchone()
        if row is None:
            return None
        return IndexedChunk.model_validate_json(row["json_data"])

    def list_chunks_for_provision(self, provision_version_id: str) -> list[IndexedChunk]:
        """Fetch all chunks associated with a provision_version_id."""
        rows = self.connection.execute(
            "SELECT json_data FROM chunks_metadata WHERE provision_version_id = ?",
            (provision_version_id,),
        ).fetchall()
        return [IndexedChunk.model_validate_json(r["json_data"]) for r in rows]

    def count(self) -> int:
        """Total chunks recorded in index."""
        row = self.connection.execute("SELECT COUNT(*) AS c FROM chunks_metadata").fetchone()
        return int(row["c"]) if row else 0

    def close(self) -> None:
        self.connection.close()
