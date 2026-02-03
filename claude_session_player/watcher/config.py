"""Config manager for watched session files."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import yaml


# ---------------------------------------------------------------------------
# Destination dataclasses
# ---------------------------------------------------------------------------


@dataclass
class TelegramDestination:
    """A Telegram chat destination for session events."""

    chat_id: str

    def to_dict(self) -> dict:
        """Serialize to dict for YAML storage."""
        return {"chat_id": self.chat_id}

    @classmethod
    def from_dict(cls, data: dict) -> TelegramDestination:
        """Deserialize from dict."""
        return cls(chat_id=data["chat_id"])


@dataclass
class SlackDestination:
    """A Slack channel destination for session events."""

    channel: str  # Channel ID or name

    def to_dict(self) -> dict:
        """Serialize to dict for YAML storage."""
        return {"channel": self.channel}

    @classmethod
    def from_dict(cls, data: dict) -> SlackDestination:
        """Deserialize from dict."""
        return cls(channel=data["channel"])


@dataclass
class SessionDestinations:
    """Collection of messaging destinations for a session."""

    telegram: list[TelegramDestination] = field(default_factory=list)
    slack: list[SlackDestination] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Serialize to dict for YAML storage."""
        return {
            "telegram": [d.to_dict() for d in self.telegram],
            "slack": [d.to_dict() for d in self.slack],
        }

    @classmethod
    def from_dict(cls, data: dict) -> SessionDestinations:
        """Deserialize from dict."""
        telegram = [
            TelegramDestination.from_dict(d) for d in data.get("telegram", [])
        ]
        slack = [SlackDestination.from_dict(d) for d in data.get("slack", [])]
        return cls(telegram=telegram, slack=slack)


@dataclass
class BotConfig:
    """Bot credentials configuration."""

    telegram_token: str | None = None
    telegram_mode: str = "webhook"  # "webhook" or "polling"
    telegram_webhook_url: str | None = None
    slack_token: str | None = None
    slack_signing_secret: str | None = None

    def to_dict(self) -> dict:
        """Serialize to dict for YAML storage."""
        result: dict = {}
        if self.telegram_token is not None:
            telegram_config: dict = {"token": self.telegram_token}
            if self.telegram_mode != "webhook":
                telegram_config["mode"] = self.telegram_mode
            if self.telegram_webhook_url is not None:
                telegram_config["webhook_url"] = self.telegram_webhook_url
            result["telegram"] = telegram_config
        if self.slack_token is not None or self.slack_signing_secret is not None:
            slack_config: dict = {}
            if self.slack_token is not None:
                slack_config["token"] = self.slack_token
            if self.slack_signing_secret is not None:
                slack_config["signing_secret"] = self.slack_signing_secret
            result["slack"] = slack_config
        return result

    @classmethod
    def from_dict(cls, data: dict) -> BotConfig:
        """Deserialize from dict."""
        telegram_token = None
        telegram_mode = "webhook"
        telegram_webhook_url = None
        slack_token = None
        slack_signing_secret = None

        if "telegram" in data and data["telegram"]:
            telegram_token = data["telegram"].get("token")
            telegram_mode = data["telegram"].get("mode", "webhook")
            telegram_webhook_url = data["telegram"].get("webhook_url")
        if "slack" in data and data["slack"]:
            slack_token = data["slack"].get("token")
            slack_signing_secret = data["slack"].get("signing_secret")

        return cls(
            telegram_token=telegram_token,
            telegram_mode=telegram_mode,
            telegram_webhook_url=telegram_webhook_url,
            slack_token=slack_token,
            slack_signing_secret=slack_signing_secret,
        )


# ---------------------------------------------------------------------------
# SessionConfig dataclass
# ---------------------------------------------------------------------------


@dataclass
class SessionConfig:
    """Configuration for a watched session file."""

    session_id: str
    path: Path
    destinations: SessionDestinations = field(default_factory=SessionDestinations)

    def to_dict(self) -> dict:
        """Serialize to dict for YAML storage (old format for compatibility)."""
        return {
            "id": self.session_id,
            "path": str(self.path),
        }

    def to_new_dict(self) -> dict:
        """Serialize to dict for new YAML format."""
        return {
            "path": str(self.path),
            "destinations": self.destinations.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> SessionConfig:
        """Deserialize from old format dict."""
        return cls(
            session_id=data["id"],
            path=Path(data["path"]),
            destinations=SessionDestinations(),
        )

    @classmethod
    def from_new_dict(cls, session_id: str, data: dict) -> SessionConfig:
        """Deserialize from new format dict."""
        destinations = SessionDestinations()
        if "destinations" in data:
            destinations = SessionDestinations.from_dict(data["destinations"])
        return cls(
            session_id=session_id,
            path=Path(data["path"]),
            destinations=destinations,
        )


def _is_old_format(data: dict) -> bool:
    """Check if the data is in the old config format.

    Old format: {"sessions": [{"id": ..., "path": ...}, ...]}
    New format: {"bots": {...}, "sessions": {"id": {"path": ..., "destinations": ...}}}
    """
    if "sessions" not in data:
        return False
    sessions = data["sessions"]
    # Old format has sessions as a list
    if isinstance(sessions, list):
        return True
    # New format has sessions as a dict
    return False


def _migrate_old_format(old_sessions: list[dict]) -> dict:
    """Convert old format to new format.

    Args:
        old_sessions: List of session dicts from old format.

    Returns:
        New format dict with bots and sessions keys.
    """
    return {
        "bots": {},
        "sessions": {
            item["id"]: {
                "path": item["path"],
                "destinations": {"telegram": [], "slack": []},
            }
            for item in old_sessions
        },
    }


class ConfigManager:
    """Manages watched session files via config.yaml.

    Provides CRUD operations for session configurations with atomic writes
    to prevent corruption. Supports both old format (list of sessions) and
    new format (dict with bots and sessions).
    """

    def __init__(self, config_path: Path) -> None:
        """Initialize with path to config.yaml file.

        Args:
            config_path: Path to the YAML configuration file.
        """
        self._config_path = config_path
        self._bot_config: BotConfig = BotConfig()

    @property
    def config_path(self) -> Path:
        """Return the configuration file path."""
        return self._config_path

    def load(self) -> list[SessionConfig]:
        """Load all session configurations from the YAML file.

        Automatically migrates old format to new format in memory.
        Bot config is cached and available via get_bot_config().

        Returns:
            List of SessionConfig objects. Empty list if file doesn't exist.
        """
        if not self._config_path.exists():
            self._bot_config = BotConfig()
            return []

        with open(self._config_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if data is None:
            self._bot_config = BotConfig()
            return []

        if "sessions" not in data:
            # Load bot config even if no sessions
            if "bots" in data:
                self._bot_config = BotConfig.from_dict(data["bots"])
            else:
                self._bot_config = BotConfig()
            return []

        # Check if old format and migrate
        if _is_old_format(data):
            data = _migrate_old_format(data["sessions"])

        # Load bot config
        if "bots" in data:
            self._bot_config = BotConfig.from_dict(data["bots"])
        else:
            self._bot_config = BotConfig()

        # Load sessions from new format
        sessions_data = data.get("sessions", {})
        return [
            SessionConfig.from_new_dict(session_id, session_data)
            for session_id, session_data in sessions_data.items()
        ]

    def save(self, sessions: list[SessionConfig]) -> None:
        """Save session configurations to the YAML file in new format.

        Uses atomic write (temp file + rename) to prevent corruption.

        Args:
            sessions: List of SessionConfig objects to save.
        """
        data: dict = {
            "bots": self._bot_config.to_dict(),
            "sessions": {s.session_id: s.to_new_dict() for s in sessions},
        }

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

    def get_bot_config(self) -> BotConfig:
        """Return the current bot configuration.

        Note: Call load() first to ensure bot config is up to date.

        Returns:
            BotConfig with telegram_token and slack_token.
        """
        return self._bot_config

    def set_bot_config(self, bot_config: BotConfig) -> None:
        """Set the bot configuration (in memory only, call save() to persist).

        Args:
            bot_config: New bot configuration.
        """
        self._bot_config = bot_config

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

    def get_destinations(self, session_id: str) -> SessionDestinations | None:
        """Get the destinations for a session.

        Args:
            session_id: Identifier of the session.

        Returns:
            SessionDestinations if session found, None otherwise.
        """
        session = self.get(session_id)
        if session is None:
            return None
        return session.destinations

    def add_destination(
        self,
        session_id: str,
        destination: TelegramDestination | SlackDestination,
        path: Path | None = None,
    ) -> bool:
        """Add a destination to a session.

        If the session doesn't exist and path is provided, creates the session.
        Idempotent: returns True without changes if destination already exists.

        Args:
            session_id: Identifier of the session.
            destination: TelegramDestination or SlackDestination to add.
            path: Path to session file (required if session doesn't exist).

        Returns:
            True if destination was added or already exists, False if session
            doesn't exist and no path provided.

        Raises:
            ValueError: If destination has empty chat_id or channel.
            ValueError: If path is not absolute (when provided).
            FileNotFoundError: If path does not exist (when provided).
        """
        # Validate destination
        if isinstance(destination, TelegramDestination):
            if not destination.chat_id:
                raise ValueError("Telegram chat_id must be non-empty")
        elif isinstance(destination, SlackDestination):
            if not destination.channel:
                raise ValueError("Slack channel must be non-empty")

        sessions = self.load()

        # Find or create session
        session = None
        for s in sessions:
            if s.session_id == session_id:
                session = s
                break

        if session is None:
            if path is None:
                return False
            # Validate path
            if not path.is_absolute():
                raise ValueError(f"Path must be absolute: {path}")
            if not path.exists():
                raise FileNotFoundError(f"Session file not found: {path}")
            session = SessionConfig(session_id=session_id, path=path)
            sessions.append(session)

        # Add destination (idempotent)
        if isinstance(destination, TelegramDestination):
            # Check if already exists
            for existing in session.destinations.telegram:
                if existing.chat_id == destination.chat_id:
                    return True  # Already exists
            session.destinations.telegram.append(destination)
        else:  # SlackDestination
            # Check if already exists
            for existing in session.destinations.slack:
                if existing.channel == destination.channel:
                    return True  # Already exists
            session.destinations.slack.append(destination)

        self.save(sessions)
        return True

    def remove_destination(
        self,
        session_id: str,
        destination: TelegramDestination | SlackDestination,
    ) -> bool:
        """Remove a destination from a session.

        Args:
            session_id: Identifier of the session.
            destination: TelegramDestination or SlackDestination to remove.

        Returns:
            True if destination was removed, False if not found.
        """
        sessions = self.load()

        # Find session
        session = None
        for s in sessions:
            if s.session_id == session_id:
                session = s
                break

        if session is None:
            return False

        # Remove destination
        if isinstance(destination, TelegramDestination):
            original_count = len(session.destinations.telegram)
            session.destinations.telegram = [
                d
                for d in session.destinations.telegram
                if d.chat_id != destination.chat_id
            ]
            if len(session.destinations.telegram) == original_count:
                return False
        else:  # SlackDestination
            original_count = len(session.destinations.slack)
            session.destinations.slack = [
                d
                for d in session.destinations.slack
                if d.channel != destination.channel
            ]
            if len(session.destinations.slack) == original_count:
                return False

        self.save(sessions)
        return True
