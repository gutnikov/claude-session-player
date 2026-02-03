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
from claude_session_player.watcher.message_state import (
    MessageAction,
    MessageStateTracker,
    NoAction,
    SendNewMessage,
    SessionMessageState,
    TurnState,
    UpdateExistingMessage,
)
from claude_session_player.watcher.service import WatcherService
from claude_session_player.watcher.sse import SSEConnection, SSEManager
from claude_session_player.watcher.state import SessionState, StateManager
from claude_session_player.watcher.slack_publisher import (
    SlackAuthError,
    SlackError,
    SlackPublisher,
    ToolCallInfo as SlackToolCallInfo,
    escape_mrkdwn,
    format_context_compacted_blocks,
    format_system_message_blocks,
    format_turn_message_blocks,
    format_user_message_blocks,
    get_tool_icon as slack_get_tool_icon,
)
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
    "escape_mrkdwn",
    "EventBuffer",
    "EventBufferManager",
    "FileWatcher",
    "format_context_compacted",
    "format_context_compacted_blocks",
    "format_system_message",
    "format_system_message_blocks",
    "format_turn_message",
    "format_turn_message_blocks",
    "format_user_message",
    "format_user_message_blocks",
    "get_tool_icon",
    "IncrementalReader",
    "MessageAction",
    "MessageStateTracker",
    "NoAction",
    "SendNewMessage",
    "SessionConfig",
    "SessionDestinations",
    "SessionMessageState",
    "SessionState",
    "SlackAuthError",
    "SlackDestination",
    "SlackError",
    "SlackPublisher",
    "SlackToolCallInfo",
    "slack_get_tool_icon",
    "SSEConnection",
    "SSEManager",
    "StateManager",
    "TelegramAuthError",
    "TelegramDestination",
    "TelegramError",
    "TelegramPublisher",
    "ToolCallInfo",
    "TurnState",
    "UpdateExistingMessage",
    "WatcherAPI",
    "WatcherService",
    "transform",
]
