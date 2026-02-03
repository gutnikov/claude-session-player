"""SQLite-based search index for session metadata.

This module provides:
- IndexedSession: Dataclass representing a session stored in the search index
- SearchDatabase: SQLite database interface for the search index

The database is a CACHE - it can be fully rebuilt from session files at any time.
The source of truth is the session .jsonl files on disk.

Features:
- Full-text search with FTS5 (graceful fallback if unavailable)
- Efficient filtering by project, date range
- Incremental updates based on file mtime
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------


@dataclass
class SearchFilters:
    """Filters for search queries."""

    query: str | None = None
    project: str | None = None
    since: datetime | None = None
    until: datetime | None = None
    include_subagents: bool = False


@dataclass
class IndexedSession:
    """Session metadata stored in the search index."""

    session_id: str
    project_encoded: str
    project_display_name: str
    project_path: str
    summary: str | None
    file_path: str
    file_created_at: datetime
    file_modified_at: datetime
    indexed_at: datetime
    size_bytes: int
    line_count: int
    duration_ms: int | None
    has_subagents: bool
    is_subagent: bool

    def to_row(self) -> tuple:
        """Convert to SQLite row tuple.

        Returns:
            Tuple of values in column order for INSERT statements.
        """
        return (
            self.session_id,
            self.project_encoded,
            self.project_display_name,
            self.project_path,
            self.summary,
            self.file_path,
            self.file_created_at.isoformat(),
            self.file_modified_at.isoformat(),
            self.indexed_at.isoformat(),
            self.size_bytes,
            self.line_count,
            self.duration_ms,
            1 if self.has_subagents else 0,
            1 if self.is_subagent else 0,
        )

    @classmethod
    def from_row(cls, row: aiosqlite.Row) -> IndexedSession:
        """Create from SQLite row.

        Args:
            row: A row object with named columns.

        Returns:
            IndexedSession instance populated from row data.
        """
        return cls(
            session_id=row["session_id"],
            project_encoded=row["project_encoded"],
            project_display_name=row["project_display_name"],
            project_path=row["project_path"],
            summary=row["summary"],
            file_path=row["file_path"],
            file_created_at=datetime.fromisoformat(row["file_created_at"]),
            file_modified_at=datetime.fromisoformat(row["file_modified_at"]),
            indexed_at=datetime.fromisoformat(row["indexed_at"]),
            size_bytes=row["size_bytes"],
            line_count=row["line_count"],
            duration_ms=row["duration_ms"],
            has_subagents=bool(row["has_subagents"]),
            is_subagent=bool(row["is_subagent"]),
        )


@dataclass
class SearchResult:
    """Search result with ranking score."""

    session: IndexedSession
    score: float


# ---------------------------------------------------------------------------
# SQL Schema Constants
# ---------------------------------------------------------------------------


CORE_SCHEMA = """
-- Sessions table
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    project_encoded TEXT NOT NULL,
    project_display_name TEXT NOT NULL,
    project_path TEXT NOT NULL,
    summary TEXT,
    file_path TEXT NOT NULL UNIQUE,
    file_created_at TEXT NOT NULL,
    file_modified_at TEXT NOT NULL,
    indexed_at TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    line_count INTEGER NOT NULL,
    duration_ms INTEGER,
    has_subagents INTEGER NOT NULL DEFAULT 0,
    is_subagent INTEGER NOT NULL DEFAULT 0
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_sessions_project ON sessions(project_encoded);
CREATE INDEX IF NOT EXISTS idx_sessions_project_name ON sessions(project_display_name COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_sessions_modified ON sessions(file_modified_at DESC);
CREATE INDEX IF NOT EXISTS idx_sessions_project_modified ON sessions(project_encoded, file_modified_at DESC);

-- Metadata table
CREATE TABLE IF NOT EXISTS index_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- File mtime tracking
CREATE TABLE IF NOT EXISTS file_mtimes (
    file_path TEXT PRIMARY KEY,
    mtime_ns INTEGER NOT NULL,
    indexed_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_file_mtimes_mtime ON file_mtimes(mtime_ns DESC);
"""

FTS_SCHEMA = """
-- FTS5 virtual table (content-sync mode)
CREATE VIRTUAL TABLE IF NOT EXISTS sessions_fts USING fts5(
    session_id,
    summary,
    project_display_name,
    content='sessions',
    content_rowid='rowid',
    tokenize='porter unicode61'
);

-- Triggers to keep FTS in sync with main table
CREATE TRIGGER IF NOT EXISTS sessions_fts_insert
AFTER INSERT ON sessions BEGIN
    INSERT INTO sessions_fts(rowid, session_id, summary, project_display_name)
    VALUES (new.rowid, new.session_id, new.summary, new.project_display_name);
END;

CREATE TRIGGER IF NOT EXISTS sessions_fts_delete
AFTER DELETE ON sessions BEGIN
    INSERT INTO sessions_fts(sessions_fts, rowid, session_id, summary, project_display_name)
    VALUES ('delete', old.rowid, old.session_id, old.summary, old.project_display_name);
END;

CREATE TRIGGER IF NOT EXISTS sessions_fts_update
AFTER UPDATE ON sessions BEGIN
    INSERT INTO sessions_fts(sessions_fts, rowid, session_id, summary, project_display_name)
    VALUES ('delete', old.rowid, old.session_id, old.summary, old.project_display_name);
    INSERT INTO sessions_fts(rowid, session_id, summary, project_display_name)
    VALUES (new.rowid, new.session_id, new.summary, new.project_display_name);
END;
"""


# ---------------------------------------------------------------------------
# SearchDatabase Class
# ---------------------------------------------------------------------------


class SearchDatabase:
    """SQLite-based search index for sessions.

    This database is a CACHE - it can be fully rebuilt from
    session files at any time. The source of truth is the
    session .jsonl files on disk.

    Features:
    - Efficient filtering by project, date range
    - Incremental updates based on file mtime
    - Automatic schema creation

    Usage:
        db = SearchDatabase(Path("~/.claude-session-player/state"))
        await db.initialize()

        # Index sessions
        await db.upsert_session(session_info)

        # Retrieve
        session = await db.get_session("session-id")

        # Cleanup
        await db.close()
    """

    def __init__(self, state_dir: Path) -> None:
        """Initialize the SearchDatabase.

        Args:
            state_dir: Directory for storing the database file.
        """
        self.state_dir = Path(state_dir)
        self.db_path = self.state_dir / "search.db"
        self._connection: aiosqlite.Connection | None = None
        self._fts_available: bool | None = None

    # ================================================================
    # FTS5 Support
    # ================================================================

    @staticmethod
    def _check_fts5_available() -> bool:
        """Check if FTS5 extension is available.

        Returns:
            True if FTS5 is available, False otherwise.
        """
        try:
            conn = sqlite3.connect(":memory:")
            conn.execute("CREATE VIRTUAL TABLE t USING fts5(x)")
            conn.close()
            return True
        except sqlite3.OperationalError:
            return False

    @property
    def fts_available(self) -> bool:
        """Check if FTS5 is available (cached after first check).

        Returns:
            True if FTS5 is available, False otherwise.
        """
        if self._fts_available is None:
            self._fts_available = self._check_fts5_available()
        return self._fts_available

    def _build_fts_query(self, query: str) -> str:
        """Convert user query to FTS5 query syntax.

        Converts a user-friendly query into FTS5 syntax:
        - "auth bug" -> "auth OR bug" (multiple terms OR'd)
        - '"auth bug"' -> '"auth bug"' (exact phrase preserved)
        - 'fix "auth bug"' -> 'fix OR "auth bug"' (mixed)

        Args:
            query: The user's search query.

        Returns:
            FTS5-compatible query string.
        """
        tokens: list[str] = []
        current: list[str] = []
        in_quote = False

        for char in query:
            if char == '"':
                if in_quote:
                    # End quote - create quoted phrase
                    phrase = "".join(current)
                    if phrase:  # Only add non-empty phrases
                        tokens.append('"' + phrase + '"')
                    current = []
                in_quote = not in_quote
            elif char == " " and not in_quote:
                if current:
                    tokens.append("".join(current))
                    current = []
            else:
                current.append(char)

        # Handle remaining characters
        if current:
            word = "".join(current)
            if in_quote:
                # Unclosed quote - treat as regular word
                tokens.append(word)
            else:
                tokens.append(word)

        # Filter out empty tokens
        tokens = [t for t in tokens if t.strip()]

        # Join with OR for multi-word queries
        return " OR ".join(tokens) if tokens else "*"

    async def _setup_fts(self) -> None:
        """Setup FTS5 virtual table and triggers.

        Creates the FTS5 virtual table and sync triggers.
        If FTS5 is not available, this method does nothing.
        """
        if not self.fts_available:
            return

        conn = await self._get_connection()
        try:
            await conn.executescript(FTS_SCHEMA)
            await conn.commit()
            logger.info("FTS5 search enabled")
        except sqlite3.OperationalError as e:
            logger.warning(f"Failed to create FTS5 table: {e}")
            self._fts_available = False

    # ================================================================
    # Lifecycle
    # ================================================================

    async def initialize(self) -> None:
        """Initialize database and create schema.

        Creates the state directory if it doesn't exist,
        opens the connection, sets pragmas, and creates tables.
        Also sets up FTS5 if available.
        """
        self.state_dir.mkdir(parents=True, exist_ok=True)

        conn = await self._get_connection()

        # Set pragmas for performance and reliability
        await conn.execute("PRAGMA journal_mode = WAL")
        await conn.execute("PRAGMA busy_timeout = 5000")
        await conn.execute("PRAGMA synchronous = NORMAL")
        await conn.execute("PRAGMA foreign_keys = ON")

        # Create schema
        await conn.executescript(CORE_SCHEMA)
        await conn.commit()

        # Setup FTS5 if available
        if self.fts_available:
            await self._setup_fts()
            await self._set_metadata("fts_available", "1")
        else:
            await self._set_metadata("fts_available", "0")
            logger.warning("FTS5 not available - using LIKE fallback for search")

        logger.info(f"SearchDatabase initialized at {self.db_path}")

    async def close(self) -> None:
        """Close database connection."""
        if self._connection:
            await self._connection.close()
            self._connection = None
            logger.debug("SearchDatabase connection closed")

    # ================================================================
    # Connection Management
    # ================================================================

    async def _get_connection(self) -> aiosqlite.Connection:
        """Get or create database connection.

        Returns:
            The aiosqlite connection object.
        """
        if self._connection is None:
            self._connection = await aiosqlite.connect(self.db_path)
            self._connection.row_factory = aiosqlite.Row
        return self._connection

    # ================================================================
    # CRUD Operations
    # ================================================================

    async def upsert_session(self, session: IndexedSession) -> None:
        """Insert or update a session in the index.

        Args:
            session: The session metadata to insert or update.
        """
        conn = await self._get_connection()
        await conn.execute(
            """
            INSERT INTO sessions (
                session_id, project_encoded, project_display_name, project_path,
                summary, file_path, file_created_at, file_modified_at, indexed_at,
                size_bytes, line_count, duration_ms, has_subagents, is_subagent
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                summary = excluded.summary,
                file_modified_at = excluded.file_modified_at,
                indexed_at = excluded.indexed_at,
                size_bytes = excluded.size_bytes,
                line_count = excluded.line_count,
                duration_ms = excluded.duration_ms,
                has_subagents = excluded.has_subagents
            """,
            session.to_row(),
        )
        await conn.commit()

    async def upsert_sessions_batch(self, sessions: list[IndexedSession]) -> int:
        """Batch insert/update sessions.

        Args:
            sessions: List of sessions to insert or update.

        Returns:
            The number of sessions processed.
        """
        if not sessions:
            return 0

        conn = await self._get_connection()
        await conn.executemany(
            """
            INSERT INTO sessions (
                session_id, project_encoded, project_display_name, project_path,
                summary, file_path, file_created_at, file_modified_at, indexed_at,
                size_bytes, line_count, duration_ms, has_subagents, is_subagent
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                summary = excluded.summary,
                file_modified_at = excluded.file_modified_at,
                indexed_at = excluded.indexed_at,
                size_bytes = excluded.size_bytes,
                line_count = excluded.line_count,
                duration_ms = excluded.duration_ms,
                has_subagents = excluded.has_subagents
            """,
            [s.to_row() for s in sessions],
        )
        await conn.commit()
        return len(sessions)

    async def delete_session(self, session_id: str) -> bool:
        """Delete a session from the index.

        Args:
            session_id: The session identifier to delete.

        Returns:
            True if a session was deleted, False if not found.
        """
        conn = await self._get_connection()
        cursor = await conn.execute(
            "DELETE FROM sessions WHERE session_id = ?",
            (session_id,),
        )
        await conn.commit()
        return cursor.rowcount > 0

    async def get_session(self, session_id: str) -> IndexedSession | None:
        """Get a session by ID.

        Args:
            session_id: The session identifier.

        Returns:
            IndexedSession if found, None otherwise.
        """
        conn = await self._get_connection()
        async with conn.execute(
            "SELECT * FROM sessions WHERE session_id = ?",
            (session_id,),
        ) as cursor:
            row = await cursor.fetchone()
            return IndexedSession.from_row(row) if row else None

    async def get_session_by_path(self, file_path: str) -> IndexedSession | None:
        """Get a session by file path.

        Args:
            file_path: The absolute path to the session file.

        Returns:
            IndexedSession if found, None otherwise.
        """
        conn = await self._get_connection()
        async with conn.execute(
            "SELECT * FROM sessions WHERE file_path = ?",
            (file_path,),
        ) as cursor:
            row = await cursor.fetchone()
            return IndexedSession.from_row(row) if row else None

    # ================================================================
    # Metadata Operations
    # ================================================================

    async def _set_metadata(self, key: str, value: str) -> None:
        """Set metadata value.

        Args:
            key: The metadata key.
            value: The metadata value.
        """
        conn = await self._get_connection()
        await conn.execute(
            """
            INSERT INTO index_metadata (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
            """,
            (key, value, datetime.now(timezone.utc).isoformat()),
        )
        await conn.commit()

    async def _get_metadata(self, key: str) -> str | None:
        """Get metadata value.

        Args:
            key: The metadata key.

        Returns:
            The value if found, None otherwise.
        """
        conn = await self._get_connection()
        async with conn.execute(
            "SELECT value FROM index_metadata WHERE key = ?",
            (key,),
        ) as cursor:
            row = await cursor.fetchone()
            return row["value"] if row else None

    # ================================================================
    # File mtime tracking for incremental updates
    # ================================================================

    async def get_file_mtime(self, file_path: str) -> int | None:
        """Get stored mtime for a file.

        Args:
            file_path: The absolute path to the file.

        Returns:
            The mtime in nanoseconds if found, None otherwise.
        """
        conn = await self._get_connection()
        async with conn.execute(
            "SELECT mtime_ns FROM file_mtimes WHERE file_path = ?",
            (file_path,),
        ) as cursor:
            row = await cursor.fetchone()
            return row["mtime_ns"] if row else None

    async def set_file_mtime(self, file_path: str, mtime_ns: int) -> None:
        """Store mtime for a file.

        Args:
            file_path: The absolute path to the file.
            mtime_ns: The file mtime in nanoseconds.
        """
        conn = await self._get_connection()
        await conn.execute(
            """
            INSERT INTO file_mtimes (file_path, mtime_ns, indexed_at)
            VALUES (?, ?, ?)
            ON CONFLICT(file_path) DO UPDATE SET
                mtime_ns = excluded.mtime_ns,
                indexed_at = excluded.indexed_at
            """,
            (file_path, mtime_ns, datetime.now(timezone.utc).isoformat()),
        )
        await conn.commit()

    async def get_all_indexed_paths(self) -> set[str]:
        """Get all indexed file paths.

        Returns:
            Set of file paths that are currently indexed.
        """
        conn = await self._get_connection()
        async with conn.execute("SELECT file_path FROM sessions") as cursor:
            rows = await cursor.fetchall()
            return {row["file_path"] for row in rows}

    # ================================================================
    # Maintenance Operations
    # ================================================================

    async def clear_all(self) -> None:
        """Clear all indexed data (for rebuild).

        Deletes all data from sessions, file_mtimes, and sessions_fts tables.
        """
        conn = await self._get_connection()
        await conn.execute("DELETE FROM sessions")
        await conn.execute("DELETE FROM file_mtimes")
        # Clear FTS table if it exists
        if self.fts_available:
            try:
                await conn.execute("DELETE FROM sessions_fts")
            except sqlite3.OperationalError:
                # FTS table may not exist
                pass
        await conn.commit()
        logger.info("SearchDatabase cleared all data")

    async def verify_integrity(self) -> bool:
        """Check database integrity.

        Returns:
            True if the database passes integrity check, False otherwise.
        """
        conn = await self._get_connection()
        async with conn.execute("PRAGMA integrity_check") as cursor:
            result = await cursor.fetchone()
            return result[0] == "ok"

    async def backup(self, backup_path: Path) -> None:
        """Create a backup using SQLite backup API.

        This is safe to call while the database is in use.

        Args:
            backup_path: Path where the backup will be created.
        """
        # Ensure parent directory exists
        backup_path.parent.mkdir(parents=True, exist_ok=True)

        conn = await self._get_connection()
        backup_conn = await aiosqlite.connect(backup_path)
        try:
            await conn.backup(backup_conn)
            logger.info(f"Database backed up to {backup_path}")
        finally:
            await backup_conn.close()

    async def vacuum(self) -> None:
        """Reclaim disk space from deleted rows.

        Uses incremental vacuum to avoid blocking for long periods.
        """
        conn = await self._get_connection()
        await conn.execute("PRAGMA incremental_vacuum")
        await conn.commit()
        logger.info("SearchDatabase vacuum completed")

    async def checkpoint(self) -> None:
        """Force WAL checkpoint to reduce WAL file size.

        Uses TRUNCATE mode to reset WAL file.
        """
        conn = await self._get_connection()
        await conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        logger.info("SearchDatabase WAL checkpoint completed")

    async def safe_initialize(self) -> None:
        """Initialize with automatic corruption recovery.

        Attempts normal initialization, then verifies integrity.
        If corruption is detected, automatically recovers the database.
        """
        try:
            await self.initialize()

            if not await self.verify_integrity():
                raise sqlite3.DatabaseError("Integrity check failed")

        except sqlite3.DatabaseError as e:
            logger.error(f"Database error during initialization: {e}")
            await self._recover_database()

    async def _recover_database(self) -> None:
        """Recover from database corruption.

        Steps:
        1. Close connection
        2. Rename corrupt DB to .corrupt
        3. Remove WAL/SHM files
        4. Reinitialize fresh database
        """
        logger.warning("Attempting database recovery...")

        # Close existing connection
        await self.close()

        # Backup corrupt database
        if self.db_path.exists():
            corrupt_path = self.db_path.with_suffix(".db.corrupt")
            self.db_path.rename(corrupt_path)
            logger.info(f"Corrupt database backed up to {corrupt_path}")

        # Remove WAL files
        for suffix in ["-wal", "-shm"]:
            wal_file = self.db_path.parent / (self.db_path.name + suffix)
            if wal_file.exists():
                wal_file.unlink()
                logger.debug(f"Removed WAL file: {wal_file}")

        # Reinitialize (creates fresh database)
        await self.initialize()
        logger.info("Database recovered - full rebuild required")

    async def execute_with_retry(
        self,
        sql: str,
        params: tuple = (),
        max_retries: int = 3,
    ) -> aiosqlite.Cursor:
        """Execute with retry on busy/locked errors.

        Args:
            sql: The SQL statement to execute.
            params: Parameters for the SQL statement.
            max_retries: Maximum number of retry attempts.

        Returns:
            The cursor from the executed statement.

        Raises:
            sqlite3.OperationalError: If all retries are exhausted.
        """
        conn = await self._get_connection()

        for attempt in range(max_retries):
            try:
                return await conn.execute(sql, params)
            except sqlite3.OperationalError as e:
                if "locked" in str(e).lower() and attempt < max_retries - 1:
                    wait_time = 0.1 * (attempt + 1)
                    logger.debug(
                        f"Database locked, retrying in {wait_time}s "
                        f"(attempt {attempt + 1}/{max_retries})"
                    )
                    await asyncio.sleep(wait_time)
                    continue
                raise

        # This should not be reached, but satisfy type checker
        raise sqlite3.OperationalError("Max retries exceeded")

    # ================================================================
    # Search Operations
    # ================================================================

    async def search(
        self,
        filters: SearchFilters,
        sort: str = "recent",
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[IndexedSession], int]:
        """Search sessions with filters.

        Returns (results, total_count).

        Note: This returns unranked results. Use search_ranked()
        for results with relevance scoring.

        Args:
            filters: Search filters to apply.
            sort: Sort order. One of: recent, oldest, size, duration, name.
            limit: Maximum number of results to return.
            offset: Number of results to skip.

        Returns:
            Tuple of (list of matching sessions, total count).
        """
        conn = await self._get_connection()

        # Build WHERE clause
        conditions: list[str] = []
        params: list = []

        if not filters.include_subagents:
            conditions.append("is_subagent = 0")

        if filters.project:
            conditions.append("project_display_name LIKE ?")
            params.append(f"%{filters.project}%")

        if filters.since:
            conditions.append("file_modified_at >= ?")
            params.append(filters.since.isoformat())

        if filters.until:
            conditions.append("file_modified_at <= ?")
            params.append(filters.until.isoformat())

        # Text search
        if filters.query:
            if self.fts_available:
                # Use FTS5
                fts_query = self._build_fts_query(filters.query)
                conditions.append(
                    """
                    session_id IN (
                        SELECT session_id FROM sessions_fts
                        WHERE sessions_fts MATCH ?
                    )
                """
                )
                params.append(fts_query)
            else:
                # Fallback to LIKE
                terms = filters.query.lower().split()
                term_conditions = []
                for term in terms:
                    term_conditions.append(
                        "(LOWER(summary) LIKE ? OR LOWER(project_display_name) LIKE ?)"
                    )
                    params.extend([f"%{term}%", f"%{term}%"])
                if term_conditions:
                    conditions.append(f"({' OR '.join(term_conditions)})")

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        # Sort
        order_by = {
            "recent": "file_modified_at DESC",
            "oldest": "file_modified_at ASC",
            "size": "size_bytes DESC",
            "duration": "COALESCE(duration_ms, 0) DESC",
            "name": "project_display_name ASC, file_modified_at DESC",
        }.get(sort, "file_modified_at DESC")

        # Count total
        count_sql = f"SELECT COUNT(*) FROM sessions WHERE {where_clause}"
        async with conn.execute(count_sql, params) as cursor:
            total = (await cursor.fetchone())[0]

        # Fetch results
        sql = f"""
            SELECT * FROM sessions
            WHERE {where_clause}
            ORDER BY {order_by}
            LIMIT ? OFFSET ?
        """
        params.extend([limit, offset])

        async with conn.execute(sql, params) as cursor:
            rows = await cursor.fetchall()
            results = [IndexedSession.from_row(row) for row in rows]

        return results, total

    async def search_ranked(
        self,
        filters: SearchFilters,
        limit: int = 10,
        offset: int = 0,
    ) -> tuple[list[SearchResult], int]:
        """Search sessions with relevance ranking.

        Uses the ranking algorithm from the search API spec:
        - Summary match: 2.0 per term
        - Exact phrase match: +1.0 bonus
        - Project name match: 1.0 per term
        - Recency boost: max 1.0, decays over 30 days

        Args:
            filters: Search filters to apply.
            limit: Maximum number of results to return.
            offset: Number of results to skip.

        Returns:
            Tuple of (list of ranked search results, total count).
        """
        # Get more candidates than needed for ranking
        candidates, _ = await self.search(
            filters=filters,
            sort="recent",
            limit=limit * 3 + offset,
            offset=0,
        )

        if not filters.query:
            # No query = no ranking, just return by recency
            return [
                SearchResult(session=s, score=0.0)
                for s in candidates[offset : offset + limit]
            ], len(candidates)

        # Rank candidates
        terms = [t.lower() for t in filters.query.split()]
        query_lower = filters.query.lower()
        now = datetime.now(timezone.utc)

        scored: list[SearchResult] = []
        for session in candidates:
            score = self._calculate_score(session, query_lower, terms, now)
            if score > 0:
                scored.append(SearchResult(session=session, score=score))

        # Sort by score descending, then by modified_at descending for tiebreaker
        scored.sort(key=lambda r: (-r.score, -r.session.file_modified_at.timestamp()))

        return scored[offset : offset + limit], len(scored)

    def _calculate_score(
        self,
        session: IndexedSession,
        query_lower: str,
        terms: list[str],
        now: datetime,
    ) -> float:
        """Calculate relevance score for a session.

        Implements the ranking algorithm from the search API spec.

        Args:
            session: The session to score.
            query_lower: The lowercase query string.
            terms: List of lowercase query terms.
            now: Current datetime for recency calculation.

        Returns:
            Relevance score (higher is better).
        """
        score = 0.0

        # Summary matches (weight: 2.0 per term)
        summary_lower = (session.summary or "").lower()
        for term in terms:
            if term in summary_lower:
                score += 2.0

        # Exact phrase bonus
        if query_lower in summary_lower:
            score += 1.0

        # Project name matches (weight: 1.0 per term)
        project_lower = session.project_display_name.lower()
        for term in terms:
            if term in project_lower:
                score += 1.0

        # Recency boost (max 1.0 for today, decays over 30 days)
        days_old = (now - session.file_modified_at).days
        recency_boost = max(0.0, 1.0 - (days_old / 30))
        score += recency_boost

        return score

    # ================================================================
    # Aggregation Queries
    # ================================================================

    async def get_projects(
        self,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[dict]:
        """Get all projects with session counts.

        Returns a list of projects with aggregated statistics,
        excluding subagent sessions from counts.

        Args:
            since: Only include sessions modified after this date.
            until: Only include sessions modified before this date.

        Returns:
            List of dicts with keys:
            - project_encoded: str
            - project_display_name: str
            - project_path: str
            - session_count: int
            - latest_modified_at: str (ISO format)
            - total_size_bytes: int
        """
        conn = await self._get_connection()

        conditions = ["is_subagent = 0"]
        params: list = []

        if since:
            conditions.append("file_modified_at >= ?")
            params.append(since.isoformat())
        if until:
            conditions.append("file_modified_at <= ?")
            params.append(until.isoformat())

        where_clause = " AND ".join(conditions)

        sql = f"""
            SELECT
                project_encoded,
                project_display_name,
                project_path,
                COUNT(*) as session_count,
                MAX(file_modified_at) as latest_modified_at,
                SUM(size_bytes) as total_size_bytes
            FROM sessions
            WHERE {where_clause}
            GROUP BY project_encoded
            ORDER BY latest_modified_at DESC
        """

        async with conn.execute(sql, params) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_stats(self) -> dict:
        """Get index statistics.

        Returns statistics about the search index including
        session counts, size totals, and metadata.

        Returns:
            Dict with keys:
            - total_sessions: int (excludes subagents)
            - total_projects: int (all distinct projects)
            - total_size_bytes: int (all sessions including subagents)
            - fts_available: bool
            - last_full_index: str | None
            - last_incremental_index: str | None
        """
        conn = await self._get_connection()

        stats: dict = {}

        # Total sessions (excluding subagents)
        async with conn.execute(
            "SELECT COUNT(*) FROM sessions WHERE is_subagent = 0"
        ) as cursor:
            stats["total_sessions"] = (await cursor.fetchone())[0]

        # Total projects (distinct)
        async with conn.execute(
            "SELECT COUNT(DISTINCT project_encoded) FROM sessions"
        ) as cursor:
            stats["total_projects"] = (await cursor.fetchone())[0]

        # Total size (all sessions)
        async with conn.execute("SELECT SUM(size_bytes) FROM sessions") as cursor:
            result = (await cursor.fetchone())[0]
            stats["total_size_bytes"] = result or 0

        # Metadata
        stats["fts_available"] = self.fts_available
        stats["last_full_index"] = await self._get_metadata("last_full_index") or None
        stats["last_incremental_index"] = (
            await self._get_metadata("last_incremental_index") or None
        )

        return stats
