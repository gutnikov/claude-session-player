"""Config manager for watched session files."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

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
# IndexConfig dataclass
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# BackupConfig dataclass
# ---------------------------------------------------------------------------


@dataclass
class BackupConfig:
    """Configuration for database backups."""

    enabled: bool = False
    path: str = "~/.claude-session-player/backups"
    keep_count: int = 3

    def to_dict(self) -> dict:
        """Serialize to dict for YAML storage."""
        return {
            "enabled": self.enabled,
            "path": self.path,
            "keep_count": self.keep_count,
        }

    @classmethod
    def from_dict(cls, data: dict) -> BackupConfig:
        """Deserialize from dict."""
        return cls(
            enabled=data.get("enabled", False),
            path=data.get("path", "~/.claude-session-player/backups"),
            keep_count=data.get("keep_count", 3),
        )

    def get_backup_dir(self) -> Path:
        """Get expanded backup directory path."""
        return Path(self.path).expanduser().resolve()


# ---------------------------------------------------------------------------
# DatabaseConfig dataclass
# ---------------------------------------------------------------------------


@dataclass
class DatabaseConfig:
    """Configuration for SQLite database settings."""

    state_dir: str = "~/.claude-session-player/state"
    checkpoint_interval: int = 300  # seconds, 0 = auto
    vacuum_on_startup: bool = False
    backup: BackupConfig = field(default_factory=BackupConfig)

    def to_dict(self) -> dict:
        """Serialize to dict for YAML storage."""
        return {
            "state_dir": self.state_dir,
            "checkpoint_interval": self.checkpoint_interval,
            "vacuum_on_startup": self.vacuum_on_startup,
            "backup": self.backup.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> DatabaseConfig:
        """Deserialize from dict."""
        backup_data = data.get("backup", {})
        return cls(
            state_dir=data.get("state_dir", "~/.claude-session-player/state"),
            checkpoint_interval=data.get("checkpoint_interval", 300),
            vacuum_on_startup=data.get("vacuum_on_startup", False),
            backup=BackupConfig.from_dict(backup_data),
        )

    def get_state_dir(self) -> Path:
        """Get expanded state directory path."""
        return Path(self.state_dir).expanduser().resolve()

    def get_backup_dir(self) -> Path:
        """Get expanded backup directory path."""
        return self.backup.get_backup_dir()


# ---------------------------------------------------------------------------
# IndexConfig dataclass
# ---------------------------------------------------------------------------


@dataclass
class IndexConfig:
    """Configuration for session indexing."""

    paths: list[str] = field(default_factory=lambda: ["~/.claude/projects"])
    refresh_interval: int = 300  # seconds
    max_sessions_per_project: int = 100
    include_subagents: bool = False
    persist: bool = True

    def to_dict(self) -> dict:
        """Serialize to dict for YAML storage."""
        return {
            "paths": self.paths,
            "refresh_interval": self.refresh_interval,
            "max_sessions_per_project": self.max_sessions_per_project,
            "include_subagents": self.include_subagents,
            "persist": self.persist,
        }

    @classmethod
    def from_dict(cls, data: dict) -> IndexConfig:
        """Deserialize from dict."""
        return cls(
            paths=data.get("paths", ["~/.claude/projects"]),
            refresh_interval=data.get("refresh_interval", 300),
            max_sessions_per_project=data.get("max_sessions_per_project", 100),
            include_subagents=data.get("include_subagents", False),
            persist=data.get("persist", True),
        )

    def expand_paths(self) -> list[Path]:
        """Expand ~ and resolve paths.

        Returns:
            List of expanded and resolved Path objects.
        """
        return [Path(p).expanduser().resolve() for p in self.paths]


# ---------------------------------------------------------------------------
# SearchConfig dataclass
# ---------------------------------------------------------------------------


@dataclass
class SearchConfig:
    """Configuration for search settings."""

    default_limit: int = 5
    max_limit: int = 10
    default_sort: str = "recent"
    state_ttl_seconds: int = 300

    def to_dict(self) -> dict:
        """Serialize to dict for YAML storage."""
        return {
            "default_limit": self.default_limit,
            "max_limit": self.max_limit,
            "default_sort": self.default_sort,
            "state_ttl_seconds": self.state_ttl_seconds,
        }

    @classmethod
    def from_dict(cls, data: dict) -> SearchConfig:
        """Deserialize from dict."""
        return cls(
            default_limit=data.get("default_limit", 5),
            max_limit=data.get("max_limit", 10),
            default_sort=data.get("default_sort", "recent"),
            state_ttl_seconds=data.get("state_ttl_seconds", 300),
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


def migrate_config(config: dict[str, Any]) -> dict[str, Any]:
    """Migrate config from older versions to current format.

    Adds default index, search, and database config sections if missing.
    Updates telegram config with mode field if missing.

    Args:
        config: Raw config dict loaded from YAML.

    Returns:
        Migrated config dict with all required sections.
    """
    # Add default index config if missing
    if "index" not in config:
        config["index"] = {
            "paths": ["~/.claude/projects"],
            "refresh_interval": 300,
            "max_sessions_per_project": 100,
            "include_subagents": False,
            "persist": True,
        }

    # Add default search config if missing
    if "search" not in config:
        config["search"] = {
            "default_limit": 5,
            "max_limit": 10,
            "default_sort": "recent",
            "state_ttl_seconds": 300,
        }

    # Add default database config if missing
    if "database" not in config:
        config["database"] = {
            "state_dir": "~/.claude-session-player/state",
            "checkpoint_interval": 300,
            "vacuum_on_startup": False,
            "backup": {
                "enabled": False,
                "path": "~/.claude-session-player/backups",
                "keep_count": 3,
            },
        }

    # Migrate telegram config - add mode if missing
    if "bots" in config and "telegram" in config["bots"]:
        tg = config["bots"]["telegram"]
        if tg and "mode" not in tg:
            tg["mode"] = "webhook"

    return config


def apply_env_overrides(config: dict[str, Any]) -> dict[str, Any]:
    """Apply environment variable overrides to config.

    Supports the following environment variables:
    - CLAUDE_INDEX_PATHS: Comma-separated list of index paths
    - CLAUDE_INDEX_REFRESH_INTERVAL: Refresh interval in seconds
    - TELEGRAM_WEBHOOK_URL: Telegram webhook URL
    - CLAUDE_STATE_DIR: Override state directory for database
    - CLAUDE_DB_CHECKPOINT_INTERVAL: WAL checkpoint interval in seconds

    Args:
        config: Config dict to apply overrides to.

    Returns:
        Config dict with environment overrides applied.
    """
    # Ensure index section exists
    if "index" not in config:
        config["index"] = {}

    # Index paths override
    if env_paths := os.environ.get("CLAUDE_INDEX_PATHS"):
        config["index"]["paths"] = [p.strip() for p in env_paths.split(",")]

    # Refresh interval override
    if env_interval := os.environ.get("CLAUDE_INDEX_REFRESH_INTERVAL"):
        try:
            config["index"]["refresh_interval"] = int(env_interval)
        except ValueError:
            pass  # Ignore invalid values

    # Telegram webhook URL override
    if env_webhook := os.environ.get("TELEGRAM_WEBHOOK_URL"):
        config.setdefault("bots", {}).setdefault("telegram", {})
        config["bots"]["telegram"]["webhook_url"] = env_webhook

    # Database state_dir override
    if env_state_dir := os.environ.get("CLAUDE_STATE_DIR"):
        config.setdefault("database", {})
        config["database"]["state_dir"] = env_state_dir

    # Database checkpoint_interval override
    if env_checkpoint := os.environ.get("CLAUDE_DB_CHECKPOINT_INTERVAL"):
        try:
            config.setdefault("database", {})
            config["database"]["checkpoint_interval"] = int(env_checkpoint)
        except ValueError:
            pass  # Ignore invalid values

    return config


def expand_paths(paths: list[str]) -> list[Path]:
    """Expand ~ and resolve paths.

    Args:
        paths: List of path strings to expand.

    Returns:
        List of expanded and resolved Path objects.
    """
    return [Path(p).expanduser().resolve() for p in paths]


class ConfigManager:
    """Manages watched session files via config.yaml.

    Provides CRUD operations for session configurations with atomic writes
    to prevent corruption. Supports both old format (list of sessions) and
    new format (dict with bots, sessions, index, and search).
    """

    def __init__(self, config_path: Path) -> None:
        """Initialize with path to config.yaml file.

        Args:
            config_path: Path to the YAML configuration file.
        """
        self._config_path = config_path
        self._bot_config: BotConfig = BotConfig()
        self._index_config: IndexConfig = IndexConfig()
        self._search_config: SearchConfig = SearchConfig()
        self._database_config: DatabaseConfig = DatabaseConfig()

    @property
    def config_path(self) -> Path:
        """Return the configuration file path."""
        return self._config_path

    def load(self) -> list[SessionConfig]:
        """Load all session configurations from the YAML file.

        Automatically migrates old format to new format in memory.
        Applies environment variable overrides after loading.
        Bot, index, search, and database configs are cached and available via getters.

        Returns:
            List of SessionConfig objects. Empty list if file doesn't exist.
        """
        if not self._config_path.exists():
            self._bot_config = BotConfig()
            self._index_config = IndexConfig()
            self._search_config = SearchConfig()
            self._database_config = DatabaseConfig()
            return []

        with open(self._config_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if data is None:
            self._bot_config = BotConfig()
            self._index_config = IndexConfig()
            self._search_config = SearchConfig()
            self._database_config = DatabaseConfig()
            return []

        # Check if old format and migrate
        if _is_old_format(data):
            data = _migrate_old_format(data["sessions"])

        # Apply config migration (adds default index/search/database if missing)
        data = migrate_config(data)

        # Apply environment variable overrides
        data = apply_env_overrides(data)

        # Load bot config
        if "bots" in data:
            self._bot_config = BotConfig.from_dict(data["bots"])
        else:
            self._bot_config = BotConfig()

        # Load index config
        if "index" in data:
            self._index_config = IndexConfig.from_dict(data["index"])
        else:
            self._index_config = IndexConfig()

        # Load search config
        if "search" in data:
            self._search_config = SearchConfig.from_dict(data["search"])
        else:
            self._search_config = SearchConfig()

        # Load database config
        if "database" in data:
            self._database_config = DatabaseConfig.from_dict(data["database"])
        else:
            self._database_config = DatabaseConfig()

        # Handle case with no sessions key (but we still loaded configs)
        if "sessions" not in data:
            return []

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
            "index": self._index_config.to_dict(),
            "search": self._search_config.to_dict(),
            "database": self._database_config.to_dict(),
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

    def get_index_config(self) -> IndexConfig:
        """Return the current index configuration.

        Note: Call load() first to ensure index config is up to date.

        Returns:
            IndexConfig with index paths and settings.
        """
        return self._index_config

    def set_index_config(self, index_config: IndexConfig) -> None:
        """Set the index configuration (in memory only, call save() to persist).

        Args:
            index_config: New index configuration.
        """
        self._index_config = index_config

    def get_search_config(self) -> SearchConfig:
        """Return the current search configuration.

        Note: Call load() first to ensure search config is up to date.

        Returns:
            SearchConfig with search settings.
        """
        return self._search_config

    def set_search_config(self, search_config: SearchConfig) -> None:
        """Set the search configuration (in memory only, call save() to persist).

        Args:
            search_config: New search configuration.
        """
        self._search_config = search_config

    def get_database_config(self) -> DatabaseConfig:
        """Return the current database configuration.

        Note: Call load() first to ensure database config is up to date.

        Returns:
            DatabaseConfig with database settings.
        """
        return self._database_config

    def set_database_config(self, database_config: DatabaseConfig) -> None:
        """Set the database configuration (in memory only, call save() to persist).

        Args:
            database_config: New database configuration.
        """
        self._database_config = database_config

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
