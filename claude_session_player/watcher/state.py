"""State manager for session processing state persistence."""

from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from claude_session_player.events import ProcessingContext


@dataclass
class SessionState:
    """Processing state for a session file.

    Tracks file position and processing context for resuming from where
    we left off after restarts.
    """

    file_position: int  # byte offset
    line_number: int  # for debugging
    processing_context: ProcessingContext
    last_modified: datetime

    def to_dict(self) -> dict:
        """Serialize to dictionary for JSON storage."""
        return {
            "file_position": self.file_position,
            "line_number": self.line_number,
            "processing_context": self.processing_context.to_dict(),
            "last_modified": self.last_modified.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> SessionState:
        """Deserialize from dictionary."""
        return cls(
            file_position=data["file_position"],
            line_number=data["line_number"],
            processing_context=ProcessingContext.from_dict(data["processing_context"]),
            last_modified=datetime.fromisoformat(data["last_modified"]),
        )


def _sanitize_session_id(session_id: str) -> str:
    """Sanitize session ID for safe filesystem usage.

    Replaces characters that are problematic on various filesystems:
    - Windows: < > : " / \\ | ? *
    - All platforms: null bytes, control characters

    Args:
        session_id: The raw session ID.

    Returns:
        Sanitized session ID safe for use as a filename.
    """
    # Replace problematic characters with underscores
    sanitized = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", session_id)
    # Collapse multiple underscores
    sanitized = re.sub(r"_+", "_", sanitized)
    # Remove leading/trailing underscores and dots (Windows issue)
    sanitized = sanitized.strip("_.")
    # Ensure non-empty
    if not sanitized:
        sanitized = "_"
    return sanitized


class StateManager:
    """Manages session processing state files.

    Provides save/load/delete operations for SessionState with atomic writes
    and graceful handling of corrupt state files.
    """

    def __init__(self, state_dir: Path) -> None:
        """Initialize with state directory path.

        Args:
            state_dir: Directory where state files will be stored.
        """
        self._state_dir = state_dir

    @property
    def state_dir(self) -> Path:
        """Return the state directory path."""
        return self._state_dir

    def _state_file_path(self, session_id: str) -> Path:
        """Get the state file path for a session.

        Args:
            session_id: The session identifier.

        Returns:
            Path to the state file.
        """
        safe_id = _sanitize_session_id(session_id)
        return self._state_dir / f"{safe_id}.json"

    def exists(self, session_id: str) -> bool:
        """Check if state file exists for a session.

        Args:
            session_id: The session identifier.

        Returns:
            True if state file exists, False otherwise.
        """
        return self._state_file_path(session_id).exists()

    def load(self, session_id: str) -> SessionState | None:
        """Load session state from file.

        Args:
            session_id: The session identifier.

        Returns:
            SessionState if loaded successfully, None if file doesn't exist
            or is corrupt.
        """
        state_path = self._state_file_path(session_id)

        if not state_path.exists():
            return None

        try:
            with open(state_path, encoding="utf-8") as f:
                data = json.load(f)
            return SessionState.from_dict(data)
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            # Corrupt state file - log warning would go here
            # Return None so caller can reset
            return None

    def save(self, session_id: str, state: SessionState) -> None:
        """Save session state to file.

        Uses atomic write (temp file + rename) to prevent corruption.

        Args:
            session_id: The session identifier.
            state: The SessionState to save.
        """
        state_path = self._state_file_path(session_id)

        # Ensure state directory exists
        self._state_dir.mkdir(parents=True, exist_ok=True)

        data = state.to_dict()

        # Atomic write: write to temp file in same directory, then rename
        fd, temp_path = tempfile.mkstemp(
            dir=self._state_dir,
            prefix=".state_",
            suffix=".json.tmp",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            # Atomic rename
            os.replace(temp_path, state_path)
        except Exception:
            # Clean up temp file on failure
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise

    def delete(self, session_id: str) -> None:
        """Delete session state file.

        Args:
            session_id: The session identifier.

        Note:
            Does nothing if state file doesn't exist.
        """
        state_path = self._state_file_path(session_id)
        if state_path.exists():
            state_path.unlink()
