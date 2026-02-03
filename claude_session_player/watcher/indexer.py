"""Session indexer for discovering and indexing Claude Code sessions.

This module provides:
- SessionIndexer: Scans directories for session files and builds a searchable index
- Path encoding/decoding: Handles Claude Code's project path encoding scheme
- Metadata extraction: Extracts summaries and line counts from session files
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Path encoding/decoding functions
# ---------------------------------------------------------------------------


def decode_project_path(encoded: str) -> str:
    """Decode project directory name to original path.

    Claude Code encodes project paths by replacing:
    - `/` → `-` (single hyphen)
    - `-` → `--` (double hyphen)

    Examples:
        -Users-user-work-trello → /Users/user/work/trello
        -Users-user-work-my--app → /Users/user/work/my-app
        -Users-user-work-foo----bar → /Users/user/work/foo--bar

    Args:
        encoded: The encoded project directory name.

    Returns:
        The decoded absolute path.
    """
    if not encoded.startswith("-"):
        return encoded  # Not an encoded path

    # Temporarily replace -- with a placeholder (null byte won't appear in paths)
    PLACEHOLDER = "\x00"
    temp = encoded.replace("--", PLACEHOLDER)

    # Replace single hyphens with /
    temp = temp.replace("-", "/")

    # Restore literal hyphens from placeholder
    result = temp.replace(PLACEHOLDER, "-")

    return result


def encode_project_path(path: str) -> str:
    """Encode a path for use as a directory name.

    Inverse of decode_project_path.

    Args:
        path: The absolute path to encode.

    Returns:
        The encoded directory name.
    """
    # First escape existing hyphens
    encoded = path.replace("-", "--")
    # Then replace slashes with single hyphen
    encoded = encoded.replace("/", "-")
    return encoded


def get_display_name(decoded_path: str) -> str:
    """Extract friendly project name from decoded path.

    Examples:
        /Users/user/work/trello-clone → trello-clone
        /Users/user/work/my-app → my-app

    Args:
        decoded_path: The decoded absolute path.

    Returns:
        The last path component (project name).
    """
    return Path(decoded_path).name


# ---------------------------------------------------------------------------
# Subagent detection
# ---------------------------------------------------------------------------


def is_subagent_session(file_path: Path) -> bool:
    """Check if a session is a subagent session.

    Subagent sessions live in: {project}/{parent_session_id}/subagents/{agent_id}.jsonl

    Args:
        file_path: Path to the session file.

    Returns:
        True if this is a subagent session.
    """
    return "subagents" in file_path.parts


# ---------------------------------------------------------------------------
# Metadata extraction
# ---------------------------------------------------------------------------


def extract_session_metadata(file_path: Path) -> tuple[str | None, int]:
    """Extract summary and line count from a session file.

    Reads the file once, returns (latest_summary, line_count).
    Uses string search before JSON parsing for speed.

    Args:
        file_path: Path to the session JSONL file.

    Returns:
        Tuple of (summary or None, line_count).
    """
    summary = None
    line_count = 0

    try:
        with open(file_path, encoding="utf-8") as f:
            for line in f:
                line_count += 1
                # Quick check before JSON parsing
                if '"type":"summary"' in line or '"type": "summary"' in line:
                    try:
                        data = json.loads(line)
                        if data.get("type") == "summary":
                            summary = data.get("summary")
                    except json.JSONDecodeError:
                        pass
    except OSError as e:
        logger.warning(f"Failed to read {file_path}: {e}")
        return None, 0

    return summary, line_count


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class IndexConfig:
    """Configuration for the session indexer."""

    refresh_interval: int = 300  # 5 minutes
    max_sessions_per_project: int = 100
    include_subagents: bool = False
    persist: bool = True
    max_index_age_hours: float = 1.0  # Load from cache if < 1 hour old


@dataclass
class SessionInfo:
    """Indexed information about a session."""

    session_id: str
    project_encoded: str
    project_display_name: str
    file_path: Path
    summary: str | None
    created_at: datetime
    modified_at: datetime
    size_bytes: int
    line_count: int
    has_subagents: bool

    # Lazy duration calculation
    _duration_ms: int | None = field(default=None, repr=False)
    _duration_loaded: bool = field(default=False, repr=False)

    @property
    def duration_ms(self) -> int | None:
        """Calculate total duration lazily from turn_duration events."""
        if not self._duration_loaded:
            self._duration_ms = self._calculate_duration()
            self._duration_loaded = True
        return self._duration_ms

    def _calculate_duration(self) -> int | None:
        """Calculate total duration by summing turn_duration events."""
        total_ms = 0
        try:
            with open(self.file_path, encoding="utf-8") as f:
                for line in f:
                    if '"turn_duration"' in line:
                        try:
                            data = json.loads(line)
                            if data.get("type") == "turn_duration":
                                total_ms += data.get("duration", 0)
                        except json.JSONDecodeError:
                            pass
        except OSError:
            return None
        return total_ms if total_ms > 0 else None

    def to_dict(self) -> dict:
        """Serialize to dictionary for JSON storage."""
        return {
            "session_id": self.session_id,
            "project_encoded": self.project_encoded,
            "project_display_name": self.project_display_name,
            "file_path": str(self.file_path),
            "summary": self.summary,
            "created_at": self.created_at.isoformat(),
            "modified_at": self.modified_at.isoformat(),
            "size_bytes": self.size_bytes,
            "line_count": self.line_count,
            "has_subagents": self.has_subagents,
        }

    @classmethod
    def from_dict(cls, data: dict) -> SessionInfo:
        """Deserialize from dictionary."""
        return cls(
            session_id=data["session_id"],
            project_encoded=data["project_encoded"],
            project_display_name=data["project_display_name"],
            file_path=Path(data["file_path"]),
            summary=data.get("summary"),
            created_at=datetime.fromisoformat(data["created_at"]),
            modified_at=datetime.fromisoformat(data["modified_at"]),
            size_bytes=data["size_bytes"],
            line_count=data["line_count"],
            has_subagents=data.get("has_subagents", False),
        )


@dataclass
class ProjectInfo:
    """Indexed information about a project."""

    encoded_name: str
    decoded_path: str
    display_name: str
    session_ids: list[str] = field(default_factory=list)
    total_size_bytes: int = 0
    latest_modified_at: datetime | None = None

    def to_dict(self) -> dict:
        """Serialize to dictionary for JSON storage."""
        return {
            "encoded_name": self.encoded_name,
            "decoded_path": self.decoded_path,
            "display_name": self.display_name,
            "session_ids": self.session_ids,
            "total_size_bytes": self.total_size_bytes,
            "latest_modified_at": (
                self.latest_modified_at.isoformat()
                if self.latest_modified_at
                else None
            ),
        }

    @classmethod
    def from_dict(cls, data: dict) -> ProjectInfo:
        """Deserialize from dictionary."""
        latest_modified_at = None
        if data.get("latest_modified_at"):
            latest_modified_at = datetime.fromisoformat(data["latest_modified_at"])
        return cls(
            encoded_name=data["encoded_name"],
            decoded_path=data["decoded_path"],
            display_name=data["display_name"],
            session_ids=data.get("session_ids", []),
            total_size_bytes=data.get("total_size_bytes", 0),
            latest_modified_at=latest_modified_at,
        )


@dataclass
class SessionIndex:
    """In-memory index of all sessions."""

    sessions: dict[str, SessionInfo] = field(default_factory=dict)
    projects: dict[str, ProjectInfo] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_refresh: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    refresh_duration_ms: int = 0
    # File mtimes for incremental refresh
    file_mtimes: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Serialize to dictionary for JSON storage."""
        return {
            "version": 1,
            "created_at": self.created_at.isoformat(),
            "last_refresh": self.last_refresh.isoformat(),
            "refresh_duration_ms": self.refresh_duration_ms,
            "sessions": {k: v.to_dict() for k, v in self.sessions.items()},
            "projects": {k: v.to_dict() for k, v in self.projects.items()},
            "file_mtimes": self.file_mtimes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> SessionIndex:
        """Deserialize from dictionary."""
        return cls(
            sessions={k: SessionInfo.from_dict(v) for k, v in data.get("sessions", {}).items()},
            projects={k: ProjectInfo.from_dict(v) for k, v in data.get("projects", {}).items()},
            created_at=datetime.fromisoformat(data["created_at"]),
            last_refresh=datetime.fromisoformat(data["last_refresh"]),
            refresh_duration_ms=data.get("refresh_duration_ms", 0),
            file_mtimes=data.get("file_mtimes", {}),
        )


# ---------------------------------------------------------------------------
# Rate limit error
# ---------------------------------------------------------------------------


class RateLimitError(Exception):
    """Raised when refresh is rate limited."""

    def __init__(self, retry_after: int):
        self.retry_after = retry_after
        super().__init__(f"Rate limited. Retry after {retry_after} seconds.")


# ---------------------------------------------------------------------------
# SessionIndexer
# ---------------------------------------------------------------------------


class SessionIndexer:
    """Indexes sessions from .claude/projects directories.

    The indexer scans configured directories for session JSONL files,
    extracts metadata (summaries, line counts, file stats), and maintains
    a searchable index with persistence support.
    """

    def __init__(
        self,
        paths: list[Path],
        config: IndexConfig | None = None,
        state_dir: Path | None = None,
    ) -> None:
        """Initialize the indexer.

        Args:
            paths: List of directories to scan for projects (e.g., ~/.claude/projects).
            config: Indexer configuration. Uses defaults if not provided.
            state_dir: Directory for persisting the index. Required if config.persist is True.
        """
        self.paths = [Path(p).expanduser() for p in paths]
        self.config = config or IndexConfig()
        self.state_dir = Path(state_dir).expanduser() if state_dir else None
        self._index: SessionIndex | None = None
        self._index_lock = asyncio.Lock()
        self._last_refresh_request: datetime | None = None

    def _index_file_path(self) -> Path | None:
        """Get the path to the persisted index file."""
        if self.state_dir is None:
            return None
        return self.state_dir / "search_index.json"

    async def get_index(self) -> SessionIndex:
        """Get the current index, initializing if needed.

        Returns:
            The current SessionIndex.
        """
        if self._index is None:
            await self._load_or_build_index()
        return self._index  # type: ignore

    async def refresh(self, force: bool = False) -> SessionIndex:
        """Refresh the index.

        Rate-limited to once per 60 seconds unless force=True.

        Args:
            force: If True, bypass rate limiting.

        Returns:
            The refreshed SessionIndex.

        Raises:
            RateLimitError: If refresh was called too recently.
        """
        if not force and self._last_refresh_request:
            elapsed = (datetime.now(timezone.utc) - self._last_refresh_request).total_seconds()
            if elapsed < 60:
                raise RateLimitError(retry_after=60 - int(elapsed))

        async with self._index_lock:
            self._last_refresh_request = datetime.now(timezone.utc)
            await self._do_refresh()
            return self._index  # type: ignore

    def get_session(self, session_id: str) -> SessionInfo | None:
        """Get a session by ID.

        Args:
            session_id: The session identifier.

        Returns:
            SessionInfo if found, None otherwise.
        """
        if self._index is None:
            return None
        return self._index.sessions.get(session_id)

    def get_project(self, encoded_name: str) -> ProjectInfo | None:
        """Get a project by encoded name.

        Args:
            encoded_name: The encoded project directory name.

        Returns:
            ProjectInfo if found, None otherwise.
        """
        if self._index is None:
            return None
        return self._index.projects.get(encoded_name)

    async def _load_or_build_index(self) -> None:
        """Load index from cache or build from scratch."""
        async with self._index_lock:
            # Try to load from cache
            if self.config.persist:
                loaded = self._load_persisted_index()
                if loaded:
                    self._index = loaded
                    # Do incremental refresh
                    await self._do_refresh(incremental=True)
                    return

            # Build from scratch
            await self._do_refresh(incremental=False)

    def _load_persisted_index(self) -> SessionIndex | None:
        """Load index from disk if it exists and is fresh enough.

        Returns:
            SessionIndex if loaded successfully, None otherwise.
        """
        index_path = self._index_file_path()
        if index_path is None or not index_path.exists():
            return None

        try:
            with open(index_path, encoding="utf-8") as f:
                data = json.load(f)

            index = SessionIndex.from_dict(data)

            # Check if cache is too old
            age_hours = (datetime.now(timezone.utc) - index.last_refresh).total_seconds() / 3600
            if age_hours > self.config.max_index_age_hours:
                logger.info(
                    f"Index cache is {age_hours:.1f} hours old, exceeds max age "
                    f"({self.config.max_index_age_hours} hours). Will rebuild."
                )
                return None

            logger.info(
                f"Loaded index cache with {len(index.sessions)} sessions "
                f"from {index_path}"
            )
            return index

        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
            logger.warning(f"Failed to load index cache: {e}")
            return None

    def _save_index(self) -> None:
        """Save the current index to disk."""
        if not self.config.persist or self._index is None:
            return

        index_path = self._index_file_path()
        if index_path is None:
            return

        # Ensure state directory exists
        index_path.parent.mkdir(parents=True, exist_ok=True)

        # Atomic write
        fd, temp_path = tempfile.mkstemp(
            dir=index_path.parent,
            prefix=".index_",
            suffix=".json.tmp",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self._index.to_dict(), f, indent=2)
            os.replace(temp_path, index_path)
            logger.debug(f"Saved index with {len(self._index.sessions)} sessions to {index_path}")
        except Exception:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise

    async def _do_refresh(self, incremental: bool = True) -> None:
        """Perform the actual refresh.

        Args:
            incremental: If True, only update changed files.
        """
        start_time = datetime.now(timezone.utc)

        if self._index is None:
            self._index = SessionIndex()
            incremental = False

        # Discover all session files
        discovered_files = await self._discover_session_files()

        # Track which files still exist
        existing_file_paths = set(discovered_files.keys())

        # Remove entries for deleted files
        if incremental:
            deleted_sessions = [
                sid for sid, info in self._index.sessions.items()
                if str(info.file_path) not in existing_file_paths
            ]
            for sid in deleted_sessions:
                self._remove_session(sid)

        # Process each discovered file
        for file_path_str, (file_path, project_encoded) in discovered_files.items():
            await self._process_file(file_path, project_encoded, incremental)

        # Rebuild project info from sessions
        self._rebuild_project_info()

        # Update timestamps
        end_time = datetime.now(timezone.utc)
        self._index.last_refresh = end_time
        self._index.refresh_duration_ms = int((end_time - start_time).total_seconds() * 1000)

        # Save to disk
        self._save_index()

        logger.info(
            f"Index refresh complete: {len(self._index.sessions)} sessions, "
            f"{len(self._index.projects)} projects in {self._index.refresh_duration_ms}ms"
        )

    async def _discover_session_files(self) -> dict[str, tuple[Path, str]]:
        """Discover all session files in configured paths.

        Returns:
            Dict mapping file path string to (Path, project_encoded) tuple.
        """
        discovered: dict[str, tuple[Path, str]] = {}

        for base_path in self.paths:
            if not base_path.exists():
                logger.debug(f"Index path does not exist: {base_path}")
                continue

            if not base_path.is_dir():
                logger.warning(f"Index path is not a directory: {base_path}")
                continue

            # Iterate through project directories
            try:
                for project_dir in base_path.iterdir():
                    if not project_dir.is_dir():
                        continue

                    project_encoded = project_dir.name

                    # Find all JSONL files
                    for jsonl_file in project_dir.rglob("*.jsonl"):
                        # Check if this is a subagent session
                        if is_subagent_session(jsonl_file):
                            if not self.config.include_subagents:
                                continue

                        discovered[str(jsonl_file)] = (jsonl_file, project_encoded)

            except OSError as e:
                logger.warning(f"Error scanning {base_path}: {e}")

        return discovered

    async def _process_file(
        self,
        file_path: Path,
        project_encoded: str,
        incremental: bool,
    ) -> None:
        """Process a single session file.

        Args:
            file_path: Path to the session file.
            project_encoded: The encoded project directory name.
            incremental: If True, skip files that haven't changed.
        """
        file_path_str = str(file_path)

        # Check if we need to process this file
        try:
            stat = file_path.stat()
            current_mtime = stat.st_mtime
        except OSError as e:
            logger.warning(f"Cannot stat {file_path}: {e}")
            return

        if incremental:
            cached_mtime = self._index.file_mtimes.get(file_path_str)  # type: ignore
            if cached_mtime is not None and cached_mtime >= current_mtime:
                return  # File hasn't changed

        # Extract session ID from filename
        session_id = file_path.stem

        # Decode project path
        decoded_path = decode_project_path(project_encoded)
        display_name = get_display_name(decoded_path)

        # Check for ambiguous paths (legacy encoding without double-hyphen escape)
        if "-" in display_name and "--" not in project_encoded:
            # This path might be ambiguous
            logger.debug(
                f"Possibly ambiguous path encoding for project '{project_encoded}': "
                f"decoded as '{decoded_path}'"
            )

        # Extract metadata
        summary, line_count = extract_session_metadata(file_path)

        # Get file timestamps
        try:
            # Try to get creation time (birth time)
            created_at = datetime.fromtimestamp(stat.st_birthtime, tz=timezone.utc)
        except AttributeError:
            # Fallback to mtime if birthtime not available (Linux)
            created_at = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)

        modified_at = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)

        # Check if this session has subagents
        has_subagents = self._check_has_subagents(file_path)

        # Create session info
        session_info = SessionInfo(
            session_id=session_id,
            project_encoded=project_encoded,
            project_display_name=display_name,
            file_path=file_path,
            summary=summary,
            created_at=created_at,
            modified_at=modified_at,
            size_bytes=stat.st_size,
            line_count=line_count,
            has_subagents=has_subagents,
        )

        # Add to index
        self._index.sessions[session_id] = session_info  # type: ignore
        self._index.file_mtimes[file_path_str] = current_mtime  # type: ignore

    def _check_has_subagents(self, session_file: Path) -> bool:
        """Check if a session has a subagents directory.

        Args:
            session_file: Path to the main session file.

        Returns:
            True if a subagents directory exists.
        """
        # Subagents are in {session_id}/subagents/ relative to session file
        session_id = session_file.stem
        subagents_dir = session_file.parent / session_id / "subagents"
        return subagents_dir.is_dir()

    def _remove_session(self, session_id: str) -> None:
        """Remove a session from the index.

        Args:
            session_id: The session identifier to remove.
        """
        if self._index is None:
            return

        session_info = self._index.sessions.get(session_id)
        if session_info:
            # Remove from file_mtimes
            file_path_str = str(session_info.file_path)
            self._index.file_mtimes.pop(file_path_str, None)
            # Remove session
            del self._index.sessions[session_id]

    def _rebuild_project_info(self) -> None:
        """Rebuild project info from current sessions."""
        if self._index is None:
            return

        # Clear existing project info
        self._index.projects.clear()

        # Group sessions by project
        for session_id, session_info in self._index.sessions.items():
            project_encoded = session_info.project_encoded

            if project_encoded not in self._index.projects:
                decoded_path = decode_project_path(project_encoded)
                self._index.projects[project_encoded] = ProjectInfo(
                    encoded_name=project_encoded,
                    decoded_path=decoded_path,
                    display_name=get_display_name(decoded_path),
                )

            project = self._index.projects[project_encoded]
            project.session_ids.append(session_id)
            project.total_size_bytes += session_info.size_bytes

            if (
                project.latest_modified_at is None
                or session_info.modified_at > project.latest_modified_at
            ):
                project.latest_modified_at = session_info.modified_at
