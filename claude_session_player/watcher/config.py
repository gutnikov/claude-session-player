"""Config manager for watched session files."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class SessionConfig:
    """Configuration for a watched session file."""

    session_id: str
    path: Path

    def to_dict(self) -> dict:
        """Serialize to dict for YAML storage."""
        return {
            "id": self.session_id,
            "path": str(self.path),
        }

    @classmethod
    def from_dict(cls, data: dict) -> SessionConfig:
        """Deserialize from dict."""
        return cls(
            session_id=data["id"],
            path=Path(data["path"]),
        )


class ConfigManager:
    """Manages watched session files via config.yaml.

    Provides CRUD operations for session configurations with atomic writes
    to prevent corruption.
    """

    def __init__(self, config_path: Path) -> None:
        """Initialize with path to config.yaml file.

        Args:
            config_path: Path to the YAML configuration file.
        """
        self._config_path = config_path

    @property
    def config_path(self) -> Path:
        """Return the configuration file path."""
        return self._config_path

    def load(self) -> list[SessionConfig]:
        """Load all session configurations from the YAML file.

        Returns:
            List of SessionConfig objects. Empty list if file doesn't exist.
        """
        if not self._config_path.exists():
            return []

        with open(self._config_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if data is None or "sessions" not in data:
            return []

        return [SessionConfig.from_dict(s) for s in data["sessions"]]

    def save(self, sessions: list[SessionConfig]) -> None:
        """Save session configurations to the YAML file.

        Uses atomic write (temp file + rename) to prevent corruption.

        Args:
            sessions: List of SessionConfig objects to save.
        """
        data = {"sessions": [s.to_dict() for s in sessions]}

        # Ensure parent directory exists
        self._config_path.parent.mkdir(parents=True, exist_ok=True)

        # Atomic write: write to temp file in same directory, then rename
        # Using same directory ensures rename is atomic on same filesystem
        fd, temp_path = tempfile.mkstemp(
            dir=self._config_path.parent,
            prefix=".config_",
            suffix=".yaml.tmp",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                yaml.safe_dump(data, f, default_flow_style=False)
            # Atomic rename
            os.replace(temp_path, self._config_path)
        except Exception:
            # Clean up temp file on failure
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise

    def add(self, session_id: str, path: Path) -> None:
        """Add a new session to the watch list.

        Args:
            session_id: Unique identifier for the session.
            path: Absolute path to the session JSONL file.

        Raises:
            ValueError: If session_id already exists.
            ValueError: If path is not absolute.
            FileNotFoundError: If path does not exist.
        """
        # Validate path is absolute
        if not path.is_absolute():
            raise ValueError(f"Path must be absolute: {path}")

        # Validate path exists
        if not path.exists():
            raise FileNotFoundError(f"Session file not found: {path}")

        sessions = self.load()

        # Check for duplicate session_id
        for session in sessions:
            if session.session_id == session_id:
                raise ValueError(f"Session already exists: {session_id}")

        sessions.append(SessionConfig(session_id=session_id, path=path))
        self.save(sessions)

    def remove(self, session_id: str) -> None:
        """Remove a session from the watch list.

        Args:
            session_id: Identifier of the session to remove.

        Raises:
            KeyError: If session_id not found.
        """
        sessions = self.load()
        original_count = len(sessions)

        sessions = [s for s in sessions if s.session_id != session_id]

        if len(sessions) == original_count:
            raise KeyError(f"Session not found: {session_id}")

        self.save(sessions)

    def get(self, session_id: str) -> SessionConfig | None:
        """Get a session configuration by ID.

        Args:
            session_id: Identifier of the session.

        Returns:
            SessionConfig if found, None otherwise.
        """
        sessions = self.load()

        for session in sessions:
            if session.session_id == session_id:
                return session

        return None

    def list_all(self) -> list[SessionConfig]:
        """List all watched sessions.

        Returns:
            List of all SessionConfig objects.
        """
        return self.load()
