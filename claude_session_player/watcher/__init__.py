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
from claude_session_player.watcher.screen_renderer import (
    Dimensions,
    Preset,
    ScreenRenderer,
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
    format_question_keyboard,
    format_question_text,
)
from claude_session_player.watcher.transformer import transform

__all__ = [
    # Config
    "apply_env_overrides",
    "BackupConfig",
    "BotConfig",
    "ConfigManager",
    "DatabaseConfig",
    "expand_paths",
    "IndexConfig",
    "migrate_config",
    "SearchConfig",
    "SessionConfig",
    "SessionDestinations",
    "SlackDestination",
    "TelegramDestination",
    # Destinations
    "AttachedDestination",
    "DestinationManager",
    "make_telegram_identifier",
    "parse_telegram_identifier",
    # Dependencies
    "check_slack_available",
    "check_telegram_available",
    # Event handling
    "EventBuffer",
    "EventBufferManager",
    "FileWatcher",
    "IncrementalReader",
    "transform",
    # Messaging (new architecture)
    "CachedRender",
    "Dimensions",
    "MessageBinding",
    "MessageBindingManager",
    "MessageDebouncer",
    "PendingUpdate",
    "Preset",
    "RenderCache",
    "ScreenRenderer",
    # Search
    "IndexedSession",
    "SearchDatabase",
    "SearchFilters",
    "SearchResult",
    "SQLiteSessionIndexer",
    # Slack
    "escape_mrkdwn",
    "format_answered_question_blocks",
    "format_question_blocks",
    "SLACK_MAX_QUESTION_BUTTONS",
    "SlackAuthError",
    "SlackError",
    "SlackPublisher",
    # SSE
    "SSEConnection",
    "SSEManager",
    # State
    "SessionState",
    "StateManager",
    # Telegram
    "BotCommandDef",
    "build_webhook_url",
    "create_question_callback_handler",
    "delete_telegram_webhook",
    "escape_html",
    "format_question_keyboard",
    "format_question_text",
    "get_bot_info",
    "get_webhook_info",
    "initialize_telegram_bot",
    "MAX_QUESTION_BUTTONS",
    "setup_telegram_webhook",
    "shutdown_telegram_bot",
    "start_telegram_polling",
    "TelegramAuthError",
    "TelegramBotConfig",
    "TelegramBotState",
    "TelegramError",
    "TelegramPollingRunner",
    "TelegramPublisher",
    # API and Service
    "WatcherAPI",
    "WatcherService",
]
