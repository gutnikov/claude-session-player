"""Telegram command handler for /search command and callbacks.

This module provides:
- TelegramCommandHandler: Handles /search bot command and inline keyboard callbacks
- Markdown formatting: Formats search results as Telegram messages
- Callback handlers: Watch, Preview, and pagination buttons

Flow:
1. User sends /search query → Telegram sends webhook to /telegram/webhook
2. Handler processes search and sends results with inline keyboard
3. User taps button → Telegram sends callback_query
4. Handler processes action (watch/preview/pagination)

Callback data format (64-byte limit):
- w:0      → Watch result at index 0
- p:2      → Preview result at index 2
- s:n      → Search next page
- s:p      → Search prev page
- s:r      → Search refresh
- noop     → No action (page indicator)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from .indexer import SessionInfo
from .rate_limit import RateLimiter
from .search import SearchEngine, SearchResults
from .search_state import SearchState, SearchStateManager

if TYPE_CHECKING:
    from .telegram_publisher import TelegramPublisher

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


# Results per page
PAGE_SIZE = 5

# Rate limit: 10 searches per minute per chat
SEARCH_RATE_LIMIT = 10
SEARCH_RATE_WINDOW = 60


# ---------------------------------------------------------------------------
# Markdown Formatting
# ---------------------------------------------------------------------------


def _escape_markdown(text: str) -> str:
    """Escape Telegram Markdown V1 special characters.

    Escapes: _ * ` [

    Args:
        text: Raw text to escape.

    Returns:
        Escaped text.
    """
    for char in ("_", "*", "`", "["):
        text = text.replace(char, f"\\{char}")
    return text


def _format_file_size(size_bytes: int) -> str:
    """Format file size for display.

    Args:
        size_bytes: Size in bytes.

    Returns:
        Human-readable size string.
    """
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"


def _format_duration(duration_ms: int | None) -> str:
    """Format duration for display.

    Args:
        duration_ms: Duration in milliseconds.

    Returns:
        Human-readable duration string.
    """
    if duration_ms is None:
        return "?"
    seconds = duration_ms / 1000
    if seconds < 60:
        return f"{int(seconds)}s"
    minutes = int(seconds / 60)
    if minutes < 60:
        return f"{minutes}m"
    hours = int(minutes / 60)
    remaining_minutes = minutes % 60
    return f"{hours}h {remaining_minutes}m"


def _format_date(dt: datetime) -> str:
    """Format date for display.

    Args:
        dt: Datetime to format.

    Returns:
        Human-readable date string.
    """
    return dt.strftime("%b %d")


def format_search_results_telegram(
    results: SearchResults,
    state: SearchState,
) -> tuple[str, list[list[dict[str, Any]]]]:
    """Format search results as Telegram message with inline keyboard.

    Args:
        results: Search results from SearchEngine.
        state: Search state for pagination info.

    Returns:
        Tuple of (message_text, inline_keyboard).
    """
    # Build message text
    parts: list[str] = []

    # Header
    header = f"🔍 *Found {results.total} session"
    if results.total != 1:
        header += "s"
    if results.query:
        header += f' matching "{_escape_markdown(results.query)}"'
    header += "*"
    parts.append(header)
    parts.append("")
    parts.append("━" * 28)
    parts.append("")

    # Results
    page = state.get_page(PAGE_SIZE)
    for i, session in enumerate(page):
        # Format session info
        summary = session.summary or "No summary"
        summary = _escape_markdown(summary[:80])
        if len(session.summary or "") > 80:
            summary += "..."

        date_str = _format_date(session.modified_at)
        duration_str = _format_duration(session.duration_ms)
        size_str = _format_file_size(session.size_bytes)

        parts.append(f"*{i + 1}. 📁 {_escape_markdown(session.project_display_name)}*")
        parts.append(f'"{summary}"')
        parts.append(f"📅 {date_str} • ⏱ {duration_str} • 📄 {size_str}")
        parts.append("")

    # Footer
    parts.append("━" * 28)

    # Page indicator
    current_page = (state.current_offset // PAGE_SIZE) + 1
    total_pages = max(1, (results.total + PAGE_SIZE - 1) // PAGE_SIZE)
    parts.append(f"Page {current_page} of {total_pages}")

    text = "\n".join(parts)

    # Build inline keyboard
    keyboard = _build_search_keyboard(page, state, current_page, total_pages)

    return text, keyboard


def _build_search_keyboard(
    page: list[SessionInfo],
    state: SearchState,
    current_page: int,
    total_pages: int,
) -> list[list[dict[str, Any]]]:
    """Build inline keyboard for search results.

    Args:
        page: Current page of results.
        state: Search state for pagination info.
        current_page: Current page number (1-indexed).
        total_pages: Total number of pages.

    Returns:
        Inline keyboard rows.
    """
    keyboard: list[list[dict[str, Any]]] = []

    # Row 1: Watch buttons
    watch_row: list[dict[str, Any]] = []
    for i in range(len(page)):
        watch_row.append({
            "text": f"👁 {i + 1}",
            "callback_data": f"w:{i}",
        })
    if watch_row:
        keyboard.append(watch_row)

    # Row 2: Preview buttons
    preview_row: list[dict[str, Any]] = []
    for i in range(len(page)):
        preview_row.append({
            "text": f"📋 {i + 1}",
            "callback_data": f"p:{i}",
        })
    if preview_row:
        keyboard.append(preview_row)

    # Row 3: Navigation
    nav_row: list[dict[str, Any]] = []

    # Prev button
    if state.has_prev_page():
        nav_row.append({"text": "◀️", "callback_data": "s:p"})
    else:
        nav_row.append({"text": "◀️", "callback_data": "noop"})

    # Page indicator (non-interactive)
    nav_row.append({"text": f"{current_page}/{total_pages}", "callback_data": "noop"})

    # Next button
    if state.has_next_page(PAGE_SIZE):
        nav_row.append({"text": "▶️", "callback_data": "s:n"})
    else:
        nav_row.append({"text": "▶️", "callback_data": "noop"})

    # Refresh button
    nav_row.append({"text": "🔄", "callback_data": "s:r"})

    keyboard.append(nav_row)

    return keyboard


def format_empty_results_telegram(query: str) -> tuple[str, list[list[dict[str, Any]]]]:
    """Format empty search results message for Telegram.

    Args:
        query: The search query that returned no results.

    Returns:
        Tuple of (message_text, inline_keyboard).
    """
    escaped_query = _escape_markdown(query) if query else ""

    text_parts = [
        "🔍 *No sessions found*",
        "",
        f'No matches for "{escaped_query}"' if query else "No sessions found.",
        "",
        "Try:",
        "• Broader search terms",
        "• /search -l 30d for older sessions",
        "• /projects to browse all",
    ]

    text = "\n".join(text_parts)

    # Browse projects button
    keyboard = [[{"text": "📂 Browse Projects", "callback_data": "noop"}]]

    return text, keyboard


def format_rate_limited_telegram(retry_after: int) -> str:
    """Format rate limit error message for Telegram.

    Args:
        retry_after: Seconds to wait before retrying.

    Returns:
        Message text.
    """
    return f"⏳ Please wait {retry_after} seconds."


def format_watch_confirmation_telegram(session: SessionInfo) -> tuple[str, list[list[dict[str, Any]]]]:
    """Format watch confirmation message for Telegram.

    Args:
        session: The session being watched.

    Returns:
        Tuple of (message_text, inline_keyboard).
    """
    summary = session.summary or "No summary"
    summary = _escape_markdown(summary[:100])

    text_parts = [
        "✅ *Now watching*",
        f'"{summary}"',
        f"📁 {_escape_markdown(session.project_display_name)}",
        "",
        "Session events will appear here.",
    ]

    text = "\n".join(text_parts)

    # Stop watching button
    keyboard = [[{"text": "🛑 Stop Watching", "callback_data": "stop"}]]

    return text, keyboard


def format_preview_telegram(
    session: SessionInfo,
    events: list[dict[str, Any]],
) -> str:
    """Format session preview message for Telegram.

    Args:
        session: The session being previewed.
        events: List of preview events.

    Returns:
        Message text.
    """
    summary = session.summary or "No summary"
    summary = _escape_markdown(summary[:100])

    parts = [
        f"📋 *Preview* (last {len(events)} events)",
        f'"{summary}"',
        "",
        "━" * 22,
        "",
    ]

    for event in events:
        event_type = event.get("type", "unknown")
        text = event.get("text", "")

        if event_type == "user":
            parts.append("👤 *User*")
            parts.append(_escape_markdown(text[:500]))
            parts.append("")
        elif event_type == "assistant":
            parts.append("🤖 *Assistant*")
            parts.append(_escape_markdown(text[:500]))
            parts.append("")
        elif event_type == "tool_call":
            tool_name = event.get("tool_name", "Tool")
            label = event.get("label", "")
            result = event.get("result_preview", "")
            parts.append(f"📖 *{_escape_markdown(tool_name)}* `{_escape_markdown(label)}`")
            if result:
                parts.append(f"✓ {_escape_markdown(result[:200])}")
            parts.append("")

    parts.append("━" * 22)

    # Duration footer
    if session.duration_ms:
        duration_str = _format_duration(session.duration_ms)
        parts.append(f"⏱ {duration_str} total")

    return "\n".join(parts)


def format_error_telegram(message: str) -> str:
    """Format error message for Telegram.

    Args:
        message: Error message to display.

    Returns:
        Message text.
    """
    return f"⚠️ {_escape_markdown(message)}"


def format_expired_state_telegram() -> str:
    """Format expired search state message for Telegram.

    Returns:
        Message text.
    """
    return "⚠️ Search expired. Please search again."


# ---------------------------------------------------------------------------
# TelegramCommandHandler
# ---------------------------------------------------------------------------


@dataclass
class TelegramCommandHandler:
    """Handles Telegram /search command and inline keyboard callbacks.

    Processes bot commands, formats results as Markdown messages with
    inline keyboards, and handles callback queries for watch/preview/pagination.
    """

    search_engine: SearchEngine
    search_state_manager: SearchStateManager
    rate_limiter: RateLimiter
    telegram_publisher: TelegramPublisher | None = None
    attach_callback: Any = None  # Callback to attach session to destination

    async def handle_search(
        self,
        query: str,
        chat_id: int | str,
        thread_id: int | None = None,
    ) -> None:
        """Handle /search command.

        Args:
            query: The search query text (after "/search ").
            chat_id: Telegram chat ID.
            thread_id: Topic thread ID for supergroups with topics.
        """
        chat_id_str = str(chat_id)
        # Include thread_id in chat_key for separate state per topic
        from claude_session_player.watcher.destinations import make_telegram_identifier
        identifier = make_telegram_identifier(chat_id_str, thread_id)
        chat_key = f"telegram:{identifier}"

        # Check rate limit
        allowed, retry_after = self.rate_limiter.check(chat_key)
        if not allowed:
            if self.telegram_publisher:
                text = format_rate_limited_telegram(retry_after)
                await self.telegram_publisher.send_message(
                    chat_id_str, text, message_thread_id=thread_id
                )
            return

        try:
            # Parse and execute search
            params = self.search_engine.parse_query(query)
            results = await self.search_engine.search(params)

            # Create search state (with thread_id for later use in Watch)
            state = SearchState(
                query=params.query,
                filters=params.filters,
                results=results.results,
                current_offset=0,
                message_id=0,  # Will be updated after sending
                created_at=datetime.now(timezone.utc),
            )
            # Store thread_id in state for later use in Watch action
            state.thread_id = thread_id  # type: ignore[attr-defined]

            # Format and send response
            if results.total == 0:
                text, keyboard = format_empty_results_telegram(params.query)
            else:
                # Need to update state.results with all results for pagination
                # The SearchEngine search returns paginated results, but for state
                # we need all results. Re-search without pagination.
                params_full = self.search_engine.parse_query(query)
                params_full.limit = 1000  # Get all results for state
                results_full = await self.search_engine.search(params_full)
                state.results = results_full.results

                # Create display results for formatting
                results = SearchResults(
                    query=params.query,
                    filters=params.filters,
                    sort=params.sort,
                    total=len(state.results),
                    offset=0,
                    limit=PAGE_SIZE,
                    results=state.get_page(PAGE_SIZE),
                )
                text, keyboard = format_search_results_telegram(results, state)

            # Send message
            if self.telegram_publisher:
                message_id = await self._send_message_with_keyboard(
                    chat_id_str, text, keyboard, thread_id
                )
                state.message_id = message_id

            # Save state
            self.search_state_manager.save(chat_key, state)

        except Exception as e:
            logger.exception("Error processing search: %s", e)
            if self.telegram_publisher:
                text = format_error_telegram("An error occurred while searching.")
                await self.telegram_publisher.send_message(
                    chat_id_str, text, message_thread_id=thread_id
                )

    async def handle_callback(
        self,
        callback_data: str,
        chat_id: int | str,
        message_id: int,
        thread_id: int | None = None,
    ) -> str | None:
        """Handle inline keyboard callback.

        Args:
            callback_data: The callback data string.
            chat_id: Telegram chat ID.
            message_id: Message ID that triggered the callback.
            thread_id: Topic thread ID for supergroups with topics.

        Returns:
            Answer text for callback_query.answer() or None.
        """
        chat_id_str = str(chat_id)

        # Parse callback data
        parts = callback_data.split(":")
        action = parts[0]

        if action == "noop":
            return None

        if action == "w":  # Watch
            if len(parts) < 2:
                return "Invalid action"
            try:
                index = int(parts[1])
            except ValueError:
                return "Invalid index"
            return await self._handle_watch(chat_id_str, message_id, index, thread_id)

        elif action == "p":  # Preview
            if len(parts) < 2:
                return "Invalid action"
            try:
                index = int(parts[1])
            except ValueError:
                return "Invalid index"
            return await self._handle_preview(chat_id_str, message_id, index, thread_id)

        elif action == "s":  # Search navigation
            if len(parts) < 2:
                return "Invalid action"
            subaction = parts[1]
            if subaction == "n":
                return await self._handle_next_page(chat_id_str, message_id, thread_id)
            elif subaction == "p":
                return await self._handle_prev_page(chat_id_str, message_id, thread_id)
            elif subaction == "r":
                return await self._handle_refresh(chat_id_str, message_id, thread_id)

        elif action == "stop":
            return await self._handle_stop_watching(chat_id_str)

        return None

    async def _handle_watch(
        self,
        chat_id: str,
        message_id: int,
        index: int,
        thread_id: int | None = None,
    ) -> str:
        """Handle watch button callback.

        Args:
            chat_id: Telegram chat ID.
            message_id: Message ID.
            index: Result index (0-based on current page).
            thread_id: Topic thread ID for supergroups with topics.

        Returns:
            Answer text for callback.
        """
        # Build identifier for state lookup
        from claude_session_player.watcher.destinations import make_telegram_identifier
        identifier = make_telegram_identifier(chat_id, thread_id)
        chat_key = f"telegram:{identifier}"

        # Get search state
        state = self.search_state_manager.get(chat_key)
        if state is None:
            if self.telegram_publisher:
                text = format_expired_state_telegram()
                await self.telegram_publisher.send_message(
                    chat_id, text, message_thread_id=thread_id
                )
            return "Search expired"

        # Get session
        session = state.session_at_index(index)
        if session is None:
            return "Session not found"

        # Attach session via callback (use thread_id stored in state if callback didn't get it)
        watch_thread_id = thread_id or getattr(state, "thread_id", None)
        if self.attach_callback:
            try:
                dest: dict = {"type": "telegram", "chat_id": chat_id}
                if watch_thread_id is not None:
                    dest["thread_id"] = watch_thread_id
                await self.attach_callback(
                    session_id=session.session_id,
                    file_path=str(session.file_path),
                    destination=dest,
                    replay_count=5,
                )
            except Exception as e:
                logger.exception("Failed to attach session: %s", e)
                return f"Failed: {e}"

        # Send confirmation
        if self.telegram_publisher:
            text, keyboard = format_watch_confirmation_telegram(session)
            await self._send_message_with_keyboard(chat_id, text, keyboard, watch_thread_id)

        return f"Now watching: {session.project_display_name}"

    async def _handle_preview(
        self,
        chat_id: str,
        message_id: int,
        index: int,
        thread_id: int | None = None,
    ) -> str:
        """Handle preview button callback.

        Args:
            chat_id: Telegram chat ID.
            message_id: Message ID.
            index: Result index (0-based on current page).
            thread_id: Topic thread ID for supergroups with topics.

        Returns:
            Answer text for callback.
        """
        # Build identifier for state lookup
        from claude_session_player.watcher.destinations import make_telegram_identifier
        identifier = make_telegram_identifier(chat_id, thread_id)
        chat_key = f"telegram:{identifier}"

        # Get search state
        state = self.search_state_manager.get(chat_key)
        if state is None:
            if self.telegram_publisher:
                text = format_expired_state_telegram()
                await self.telegram_publisher.send_message(
                    chat_id, text, message_thread_id=thread_id
                )
            return "Search expired"

        # Get session
        session = state.session_at_index(index)
        if session is None:
            return "Session not found"

        # Generate preview events (simplified - just show basic info for now)
        preview_events = self._generate_preview_events(session)

        # Send preview as reply to search message
        if self.telegram_publisher:
            text = format_preview_telegram(session, preview_events)
            await self._send_reply(chat_id, message_id, text, thread_id)

        return "Preview sent"

    def _generate_preview_events(self, session: SessionInfo) -> list[dict[str, Any]]:
        """Generate preview events for a session.

        This is a simplified implementation. A full version would parse
        the session file and extract actual events.

        Args:
            session: The session to preview.

        Returns:
            List of preview event dicts.
        """
        # For now, return a simple placeholder
        # In a real implementation, this would read the session file
        events: list[dict[str, Any]] = []

        if session.summary:
            events.append({
                "type": "assistant",
                "text": session.summary,
            })

        return events

    async def _handle_next_page(
        self,
        chat_id: str,
        message_id: int,
        thread_id: int | None = None,
    ) -> str:
        """Handle next page button callback.

        Args:
            chat_id: Telegram chat ID.
            message_id: Message ID.
            thread_id: Topic thread ID for supergroups with topics.

        Returns:
            Answer text for callback.
        """
        from claude_session_player.watcher.destinations import make_telegram_identifier
        identifier = make_telegram_identifier(chat_id, thread_id)
        chat_key = f"telegram:{identifier}"

        # Get search state
        state = self.search_state_manager.get(chat_key)
        if state is None:
            if self.telegram_publisher:
                text = format_expired_state_telegram()
                await self.telegram_publisher.send_message(
                    chat_id, text, message_thread_id=thread_id
                )
            return "Search expired"

        # Update offset
        new_offset = state.current_offset + PAGE_SIZE
        state = self.search_state_manager.update_offset(chat_key, new_offset)
        if state is None:
            return "Search expired"

        # Update message
        await self._update_search_message(chat_id, message_id, state)
        return "Next page"

    async def _handle_prev_page(
        self,
        chat_id: str,
        message_id: int,
        thread_id: int | None = None,
    ) -> str:
        """Handle prev page button callback.

        Args:
            chat_id: Telegram chat ID.
            message_id: Message ID.
            thread_id: Topic thread ID for supergroups with topics.

        Returns:
            Answer text for callback.
        """
        from claude_session_player.watcher.destinations import make_telegram_identifier
        identifier = make_telegram_identifier(chat_id, thread_id)
        chat_key = f"telegram:{identifier}"

        # Get search state
        state = self.search_state_manager.get(chat_key)
        if state is None:
            if self.telegram_publisher:
                text = format_expired_state_telegram()
                await self.telegram_publisher.send_message(
                    chat_id, text, message_thread_id=thread_id
                )
            return "Search expired"

        # Update offset
        new_offset = max(0, state.current_offset - PAGE_SIZE)
        state = self.search_state_manager.update_offset(chat_key, new_offset)
        if state is None:
            return "Search expired"

        # Update message
        await self._update_search_message(chat_id, message_id, state)
        return "Previous page"

    async def _handle_refresh(
        self,
        chat_id: str,
        message_id: int,
        thread_id: int | None = None,
    ) -> str:
        """Handle refresh button callback.

        Args:
            chat_id: Telegram chat ID.
            message_id: Message ID.
            thread_id: Topic thread ID for supergroups with topics.

        Returns:
            Answer text for callback.
        """
        from claude_session_player.watcher.destinations import make_telegram_identifier
        identifier = make_telegram_identifier(chat_id, thread_id)
        chat_key = f"telegram:{identifier}"

        # Get search state
        state = self.search_state_manager.get(chat_key)
        if state is None:
            if self.telegram_publisher:
                text = format_expired_state_telegram()
                await self.telegram_publisher.send_message(
                    chat_id, text, message_thread_id=thread_id
                )
            return "Search expired"

        try:
            # Re-execute search
            params = self.search_engine.parse_query(state.query)
            params.filters = state.filters
            params.limit = 1000  # Get all results
            results = await self.search_engine.search(params)

            # Create new state
            new_state = SearchState(
                query=state.query,
                filters=state.filters,
                results=results.results,
                current_offset=0,  # Reset to first page
                message_id=message_id,
                created_at=datetime.now(timezone.utc),
            )
            # Preserve thread_id in state
            new_state.thread_id = thread_id  # type: ignore[attr-defined]

            # Save new state
            self.search_state_manager.save(chat_key, new_state)

            # Update message
            await self._update_search_message(chat_id, message_id, new_state)
            return "Refreshed"

        except Exception as e:
            logger.exception("Error refreshing search: %s", e)
            return "Refresh failed"

    async def _handle_stop_watching(self, chat_id: str) -> str:
        """Handle stop watching button callback.

        Args:
            chat_id: Telegram chat ID.

        Returns:
            Answer text for callback.
        """
        # This would need integration with WatcherService to detach
        # For now, just acknowledge
        return "Stopped watching"

    async def _update_search_message(
        self,
        chat_id: str,
        message_id: int,
        state: SearchState,
    ) -> None:
        """Update the search results message.

        Args:
            chat_id: Telegram chat ID.
            message_id: Message ID to edit.
            state: Current search state.
        """
        if self.telegram_publisher is None:
            return

        # Create results for formatting
        results = SearchResults(
            query=state.query,
            filters=state.filters,
            sort="recent",
            total=len(state.results),
            offset=state.current_offset,
            limit=PAGE_SIZE,
            results=state.get_page(PAGE_SIZE),
        )

        if results.total == 0:
            text, keyboard = format_empty_results_telegram(state.query)
        else:
            text, keyboard = format_search_results_telegram(results, state)

        await self._edit_message_with_keyboard(chat_id, message_id, text, keyboard)

    async def _send_message_with_keyboard(
        self,
        chat_id: str,
        text: str,
        keyboard: list[list[dict[str, Any]]],
        thread_id: int | None = None,
    ) -> int:
        """Send a message with inline keyboard.

        Args:
            chat_id: Telegram chat ID.
            text: Message text.
            keyboard: Inline keyboard rows.
            thread_id: Topic thread ID for supergroups with topics.

        Returns:
            Message ID of the sent message.
        """
        if self.telegram_publisher is None:
            return 0

        # Need to use aiogram directly for inline keyboard support
        try:
            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

            # Build keyboard
            inline_keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text=btn["text"],
                            callback_data=btn["callback_data"],
                        )
                        for btn in row
                    ]
                    for row in keyboard
                ]
            )

            # Get bot instance
            await self.telegram_publisher.validate()
            result = await self.telegram_publisher._bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode="Markdown",
                reply_markup=inline_keyboard,
                message_thread_id=thread_id,
            )
            return result.message_id

        except Exception as e:
            logger.warning("Failed to send message with keyboard: %s", e)
            # Fallback to plain message
            return await self.telegram_publisher.send_message(
                chat_id, text, message_thread_id=thread_id
            )

    async def _edit_message_with_keyboard(
        self,
        chat_id: str,
        message_id: int,
        text: str,
        keyboard: list[list[dict[str, Any]]],
    ) -> bool:
        """Edit a message with inline keyboard.

        Args:
            chat_id: Telegram chat ID.
            message_id: Message ID to edit.
            text: New message text.
            keyboard: Inline keyboard rows.

        Returns:
            True if edited successfully.
        """
        if self.telegram_publisher is None:
            return False

        try:
            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

            # Build keyboard
            inline_keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text=btn["text"],
                            callback_data=btn["callback_data"],
                        )
                        for btn in row
                    ]
                    for row in keyboard
                ]
            )

            # Get bot instance
            await self.telegram_publisher.validate()
            await self.telegram_publisher._bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                parse_mode="Markdown",
                reply_markup=inline_keyboard,
            )
            return True

        except Exception as e:
            error_str = str(e).lower()
            if "message is not modified" in error_str:
                return True  # Content unchanged, that's fine
            logger.warning("Failed to edit message with keyboard: %s", e)
            return False

    async def _send_reply(
        self,
        chat_id: str,
        reply_to_message_id: int,
        text: str,
        thread_id: int | None = None,
    ) -> int:
        """Send a reply to a message.

        Args:
            chat_id: Telegram chat ID.
            reply_to_message_id: Message ID to reply to.
            text: Message text.
            thread_id: Topic thread ID for supergroups with topics.

        Returns:
            Message ID of the sent message.
        """
        if self.telegram_publisher is None:
            return 0

        try:
            await self.telegram_publisher.validate()
            result = await self.telegram_publisher._bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode="Markdown",
                reply_to_message_id=reply_to_message_id,
                message_thread_id=thread_id,
            )
            return result.message_id

        except Exception as e:
            logger.warning("Failed to send reply: %s", e)
            # Fallback to regular message
            return await self.telegram_publisher.send_message(
                chat_id, text, message_thread_id=thread_id
            )
