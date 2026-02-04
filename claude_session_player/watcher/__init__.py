"""Session watcher module for Claude Session Player."""

from __future__ import annotations

from claude_session_player.watcher.api import WatcherAPI
from claude_session_player.watcher.config import (
    BackupConfig,
    BotConfig,
    ConfigManager,
    DatabaseConfig,
    IndexConfig,
    SearchConfig,
    SessionConfig,
    SessionDestinations,
    SlackDestination,
    TelegramDestination,
    apply_env_overrides,
    expand_paths,
    migrate_config,
)
from claude_session_player.watcher.search_db import (
    IndexedSession,
    SearchDatabase,
    SearchFilters,
    SearchResult,
)
from claude_session_player.watcher.indexer import SQLiteSessionIndexer
from claude_session_player.watcher.debouncer import MessageDebouncer, PendingUpdate
from claude_session_player.watcher.deps import check_slack_available, check_telegram_available
from claude_session_player.watcher.destinations import (
    AttachedDestination,
    DestinationManager,
    make_telegram_identifier,
    parse_telegram_identifier,
)
from claude_session_player.watcher.event_buffer import EventBuffer, EventBufferManager
from claude_session_player.watcher.file_watcher import FileWatcher, IncrementalReader
from claude_session_player.watcher.message_binding import (
    MessageBinding,
    MessageBindingManager,
)
from claude_session_player.watcher.render_cache import CachedRender, RenderCache
from claude_session_player.watcher.message_state import (
    MessageAction,
    MessageStateTracker,
    NoAction,
    QuestionState,
    SendNewMessage,
    SessionMessageState,
    TurnState,
    UpdateExistingMessage,
)
from claude_session_player.watcher.service import WatcherService
from claude_session_player.watcher.sse import SSEConnection, SSEManager
from claude_session_player.watcher.state import SessionState, StateManager
from claude_session_player.watcher.slack_publisher import (
    MAX_QUESTION_BUTTONS as SLACK_MAX_QUESTION_BUTTONS,
    SlackAuthError,
    SlackError,
    SlackPublisher,
    escape_mrkdwn,
    format_answered_question_blocks,
    format_question_blocks,
)
from claude_session_player.watcher.telegram_bot import (
    BotCommandDef,
    TelegramBotConfig,
    TelegramBotState,
    TelegramPollingRunner,
    build_webhook_url,
    create_question_callback_handler,
    delete_telegram_webhook,
    get_bot_info,
    get_webhook_info,
    initialize_telegram_bot,
    setup_telegram_webhook,
    shutdown_telegram_bot,
    start_telegram_polling,
)
from claude_session_player.watcher.telegram_publisher import (
    MAX_QUESTION_BUTTONS,
    TelegramAuthError,
    TelegramError,
    TelegramPublisher,
    escape_html,
    escape_markdown,
    format_question_keyboard,
    format_question_text,
)
from claude_session_player.watcher.transformer import transform

__all__ = [
    "apply_env_overrides",
    "AttachedDestination",
    "BackupConfig",
    "BotCommandDef",
    "BotConfig",
    "create_question_callback_handler",
    "DatabaseConfig",
    "build_webhook_url",
    "check_slack_available",
    "check_telegram_available",
    "ConfigManager",
    "expand_paths",
    "format_question_keyboard",
    "format_question_text",
    "IndexConfig",
    "IndexedSession",
    "make_telegram_identifier",
    "MAX_QUESTION_BUTTONS",
    "migrate_config",
    "delete_telegram_webhook",
    "DestinationManager",
    "MessageDebouncer",
    "PendingUpdate",
    "escape_markdown",
    "escape_mrkdwn",
    "EventBuffer",
    "EventBufferManager",
    "FileWatcher",
    "escape_html",
    "format_answered_question_blocks",
    "format_question_blocks",
    "SLACK_MAX_QUESTION_BUTTONS",
    "get_bot_info",
    "get_webhook_info",
    "initialize_telegram_bot",
    "IncrementalReader",
    "MessageAction",
    "MessageBinding",
    "MessageBindingManager",
    "MessageStateTracker",
    "NoAction",
    "QuestionState",
    "RenderCache",
    "CachedRender",
    "SearchConfig",
    "SendNewMessage",
    "SessionConfig",
    "SessionDestinations",
    "SessionMessageState",
    "SessionState",
    "setup_telegram_webhook",
    "shutdown_telegram_bot",
    "SlackAuthError",
    "SlackDestination",
    "SlackError",
    "SlackPublisher",
    "SSEConnection",
    "SSEManager",
    "start_telegram_polling",
    "StateManager",
    "TelegramAuthError",
    "TelegramBotConfig",
    "TelegramBotState",
    "TelegramDestination",
    "TelegramError",
    "parse_telegram_identifier",
    "TelegramPollingRunner",
    "TelegramPublisher",
    "TurnState",
    "UpdateExistingMessage",
    "SearchDatabase",
    "SearchFilters",
    "SearchResult",
    "SQLiteSessionIndexer",
    "WatcherAPI",
    "WatcherService",
    "transform",
]
