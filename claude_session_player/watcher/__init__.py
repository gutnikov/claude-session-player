"""Session watcher module for Claude Session Player."""

from __future__ import annotations

from claude_session_player.watcher.api import WatcherAPI
from claude_session_player.watcher.config import ConfigManager, SessionConfig
from claude_session_player.watcher.deps import check_slack_available, check_telegram_available
from claude_session_player.watcher.event_buffer import EventBuffer, EventBufferManager
from claude_session_player.watcher.file_watcher import FileWatcher, IncrementalReader
from claude_session_player.watcher.service import WatcherService
from claude_session_player.watcher.sse import SSEConnection, SSEManager
from claude_session_player.watcher.state import SessionState, StateManager
from claude_session_player.watcher.transformer import transform

__all__ = [
    "check_slack_available",
    "check_telegram_available",
    "ConfigManager",
    "EventBuffer",
    "EventBufferManager",
    "FileWatcher",
    "IncrementalReader",
    "SessionConfig",
    "SessionState",
    "SSEConnection",
    "SSEManager",
    "StateManager",
    "WatcherAPI",
    "WatcherService",
    "transform",
]
