"""Session watcher module for Claude Session Player."""

from __future__ import annotations

from claude_session_player.watcher.api import WatcherAPI
from claude_session_player.watcher.config import (
    BotConfig,
    ConfigManager,
    SessionConfig,
    SessionDestinations,
    SlackDestination,
    TelegramDestination,
)
from claude_session_player.watcher.deps import check_slack_available, check_telegram_available
from claude_session_player.watcher.destinations import AttachedDestination, DestinationManager
from claude_session_player.watcher.event_buffer import EventBuffer, EventBufferManager
from claude_session_player.watcher.file_watcher import FileWatcher, IncrementalReader
from claude_session_player.watcher.service import WatcherService
from claude_session_player.watcher.sse import SSEConnection, SSEManager
from claude_session_player.watcher.state import SessionState, StateManager
from claude_session_player.watcher.telegram_publisher import (
    TelegramAuthError,
    TelegramError,
    TelegramPublisher,
    ToolCallInfo,
    escape_markdown,
    format_context_compacted,
    format_system_message,
    format_turn_message,
    format_user_message,
    get_tool_icon,
)
from claude_session_player.watcher.transformer import transform

__all__ = [
    "AttachedDestination",
    "BotConfig",
    "check_slack_available",
    "check_telegram_available",
    "ConfigManager",
    "DestinationManager",
    "escape_markdown",
    "EventBuffer",
    "EventBufferManager",
    "FileWatcher",
    "format_context_compacted",
    "format_system_message",
    "format_turn_message",
    "format_user_message",
    "get_tool_icon",
    "IncrementalReader",
    "SessionConfig",
    "SessionDestinations",
    "SessionState",
    "SlackDestination",
    "SSEConnection",
    "SSEManager",
    "StateManager",
    "TelegramAuthError",
    "TelegramDestination",
    "TelegramError",
    "TelegramPublisher",
    "ToolCallInfo",
    "WatcherAPI",
    "WatcherService",
    "transform",
]
