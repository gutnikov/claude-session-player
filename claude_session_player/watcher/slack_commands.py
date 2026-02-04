"""Slack command handler for /search command and interactions.

This module provides:
- SlackCommandHandler: Handles /search slash command and button interactions
- Block Kit formatting: Formats search results as Slack messages
- Interaction handlers: Watch, Preview, and pagination buttons

Flow:
1. User types /search query → Slack sends POST to /slack/commands
2. Handler returns 200 OK immediately, processes search async
3. Results posted to response_url as Block Kit message
4. User clicks button → Slack sends POST to /slack/interactions
5. Handler processes action (watch/preview/pagination)
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

import aiohttp

from .indexer import SessionInfo
from .rate_limit import RateLimiter
from .search import SearchEngine, SearchResults
from .search_state import SearchState, SearchStateManager

if TYPE_CHECKING:
    from .slack_publisher import SlackPublisher

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


# Results per page
PAGE_SIZE = 5

# Rate limit: 10 searches per minute per user
SEARCH_RATE_LIMIT = 10
SEARCH_RATE_WINDOW = 60


# ---------------------------------------------------------------------------
# Block Kit Formatting
# ---------------------------------------------------------------------------


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


def _escape_mrkdwn(text: str) -> str:
    """Escape Slack mrkdwn special characters.

    Args:
        text: Raw text to escape.

    Returns:
        Escaped text.
    """
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    return text


def format_search_results(
    results: SearchResults,
    state: SearchState,
) -> list[dict[str, Any]]:
    """Format search results as Slack Block Kit blocks.

    Args:
        results: Search results from SearchEngine.
        state: Search state for pagination info.

    Returns:
        List of Block Kit blocks.
    """
    blocks: list[dict[str, Any]] = []

    # Header
    header_text = f"🔍 Found {results.total} session"
    if results.total != 1:
        header_text += "s"
    if results.query:
        header_text += f' matching "{_escape_mrkdwn(results.query)}"'

    blocks.append({
        "type": "header",
        "text": {"type": "plain_text", "text": header_text[:150], "emoji": True},
    })

    # Results
    page = state.get_page(PAGE_SIZE)
    for i, session in enumerate(page):
        # Format session info
        summary = session.summary or "No summary"
        summary = _escape_mrkdwn(summary[:100])
        if len(session.summary or "") > 100:
            summary += "..."

        date_str = _format_date(session.modified_at)
        duration_str = _format_duration(session.duration_ms)
        size_str = _format_file_size(session.size_bytes)

        section_text = (
            f"*📁 {_escape_mrkdwn(session.project_display_name)}*\n"
            f'"{summary}"\n'
            f"📅 {date_str} • ⏱ {duration_str} • 📄 {size_str}"
        )

        # Section with overflow menu
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": section_text},
            "accessory": {
                "type": "overflow",
                "action_id": f"session_menu:{i}",
                "options": [
                    {
                        "text": {"type": "plain_text", "text": "👁 Watch", "emoji": True},
                        "value": f"watch:{i}",
                    },
                    {
                        "text": {"type": "plain_text", "text": "📋 Preview", "emoji": True},
                        "value": f"preview:{i}",
                    },
                ],
            },
        })
        blocks.append({"type": "divider"})

    # Pagination
    current_page = (state.current_offset // PAGE_SIZE) + 1
    total_pages = max(1, (results.total + PAGE_SIZE - 1) // PAGE_SIZE)

    pagination_elements: list[dict[str, Any]] = []

    # Prev button
    if state.has_prev_page():
        pagination_elements.append({
            "type": "button",
            "text": {"type": "plain_text", "text": "◀ Prev", "emoji": True},
            "action_id": "search_prev",
        })
    else:
        pagination_elements.append({
            "type": "button",
            "text": {"type": "plain_text", "text": "◀ Prev", "emoji": True},
            "action_id": "search_prev_disabled",
            "style": "primary" if False else None,
        })
        # Remove style key if None
        if pagination_elements[-1].get("style") is None:
            del pagination_elements[-1]["style"]

    # Page indicator (non-interactive)
    pagination_elements.append({
        "type": "button",
        "text": {"type": "plain_text", "text": f"Page {current_page}/{total_pages}"},
        "action_id": "search_page_indicator",
    })

    # Next button
    if state.has_next_page(PAGE_SIZE):
        pagination_elements.append({
            "type": "button",
            "text": {"type": "plain_text", "text": "Next ▶", "emoji": True},
            "action_id": "search_next",
        })
    else:
        pagination_elements.append({
            "type": "button",
            "text": {"type": "plain_text", "text": "Next ▶", "emoji": True},
            "action_id": "search_next_disabled",
        })

    # Refresh button
    pagination_elements.append({
        "type": "button",
        "text": {"type": "plain_text", "text": "🔄 Refresh", "emoji": True},
        "action_id": "search_refresh",
    })

    blocks.append({
        "type": "actions",
        "elements": pagination_elements,
    })

    return blocks


def format_empty_results(query: str) -> list[dict[str, Any]]:
    """Format empty search results message.

    Args:
        query: The search query that returned no results.

    Returns:
        List of Block Kit blocks.
    """
    escaped_query = _escape_mrkdwn(query) if query else ""

    blocks: list[dict[str, Any]] = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f'🔍 No sessions found matching "{escaped_query}"' if query else "🔍 No sessions found",
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    "*Suggestions:*\n"
                    "• Try broader search terms\n"
                    "• Remove project filter\n"
                    "• Extend date range with `--last 30d`"
                ),
            },
        },
    ]

    return blocks


def format_rate_limited(retry_after: int) -> list[dict[str, Any]]:
    """Format rate limit error message.

    Args:
        retry_after: Seconds to wait before retrying.

    Returns:
        List of Block Kit blocks.
    """
    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"⏳ Too many searches. Please wait {retry_after} seconds.",
            },
        },
    ]


def format_watch_confirmation(session: SessionInfo) -> list[dict[str, Any]]:
    """Format watch confirmation message.

    Args:
        session: The session being watched.

    Returns:
        List of Block Kit blocks.
    """
    summary = session.summary or "No summary"
    summary = _escape_mrkdwn(summary[:100])

    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f'✅ Now watching: "{summary}"\n'
                    f"📁 {_escape_mrkdwn(session.project_display_name)} • "
                    "Session events will appear in this channel"
                ),
            },
        },
    ]


def format_preview(session: SessionInfo, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Format session preview message.

    Args:
        session: The session being previewed.
        events: List of preview events.

    Returns:
        List of Block Kit blocks.
    """
    summary = session.summary or "No summary"
    summary = _escape_mrkdwn(summary[:100])

    blocks: list[dict[str, Any]] = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f'📋 Preview: "{summary}" (showing last {len(events)} events)',
            },
        },
        {"type": "divider"},
    ]

    for event in events:
        event_type = event.get("type", "unknown")
        text = event.get("text", "")

        if event_type == "user":
            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"👤 *User*\n{_escape_mrkdwn(text[:500])}"},
            })
        elif event_type == "assistant":
            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"🤖 *Assistant*\n{_escape_mrkdwn(text[:500])}"},
            })
        elif event_type == "tool_call":
            tool_name = event.get("tool_name", "Tool")
            label = event.get("label", "")
            result = event.get("result_preview", "")
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"🔧 *{_escape_mrkdwn(tool_name)}* `{_escape_mrkdwn(label)}`\n✓ {_escape_mrkdwn(result[:200])}",
                },
            })

    # Duration footer
    if session.duration_ms:
        duration_str = _format_duration(session.duration_ms)
        blocks.append({
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": f"⏱ {duration_str} total"}],
        })

    return blocks


def format_error(message: str) -> list[dict[str, Any]]:
    """Format error message.

    Args:
        message: Error message to display.

    Returns:
        List of Block Kit blocks.
    """
    return [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"❌ {_escape_mrkdwn(message)}"},
        },
    ]


# ---------------------------------------------------------------------------
# SlackCommandHandler
# ---------------------------------------------------------------------------


@dataclass
class SlackCommandHandler:
    """Handles Slack /search command and interactions.

    Processes slash commands, formats results as Block Kit messages,
    and handles button interactions for watch/preview/pagination.
    """

    search_engine: SearchEngine
    search_state_manager: SearchStateManager
    rate_limiter: RateLimiter
    slack_publisher: SlackPublisher | None = None
    attach_callback: Any = None  # Callback to attach session to destination

    # HTTP session for response_url posts
    _http_session: aiohttp.ClientSession | None = field(default=None, repr=False)

    async def _get_http_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session for response_url posts."""
        if self._http_session is None or self._http_session.closed:
            self._http_session = aiohttp.ClientSession()
        return self._http_session

    async def close(self) -> None:
        """Close the HTTP session."""
        if self._http_session is not None and not self._http_session.closed:
            await self._http_session.close()
            self._http_session = None

    async def handle_search(
        self,
        command: str,
        text: str,
        user_id: str,
        channel_id: str,
        response_url: str,
    ) -> dict[str, Any] | None:
        """Handle /search slash command.

        Args:
            command: The command name ("/search").
            text: The query text.
            user_id: Slack user ID.
            channel_id: Slack channel ID.
            response_url: URL to post results to.

        Returns:
            Immediate response dict if rate limited, None for async processing.
        """
        # Check rate limit
        rate_key = f"slack:{user_id}"
        allowed, retry_after = self.rate_limiter.check(rate_key)
        if not allowed:
            # Return immediate rate limit response
            return {
                "response_type": "ephemeral",
                "blocks": format_rate_limited(retry_after),
                "text": f"Too many searches. Please wait {retry_after} seconds.",
            }

        # Process search in background
        asyncio.create_task(
            self._process_search_and_respond(text, channel_id, response_url)
        )

        # Return None for immediate 200 OK (Slack requires response within 3s)
        return None

    async def _process_search_and_respond(
        self,
        query_text: str,
        channel_id: str,
        response_url: str,
    ) -> None:
        """Process search and post results to response_url.

        Args:
            query_text: The search query.
            channel_id: Slack channel ID (for state tracking).
            response_url: URL to post results to.
        """
        try:
            # Parse and execute search
            params = self.search_engine.parse_query(query_text)
            results = await self.search_engine.search(params)

            # Create search state
            chat_key = f"slack:{channel_id}"
            state = SearchState(
                query=params.query,
                filters=params.filters,
                results=results.results,
                current_offset=0,
                message_id="",  # Will be set when we get the response
                created_at=datetime.now(timezone.utc),
            )

            # Format response
            if results.total == 0:
                blocks = format_empty_results(params.query)
                fallback_text = f"No sessions found matching \"{params.query}\""
            else:
                blocks = format_search_results(results, state)
                fallback_text = f"Found {results.total} sessions matching \"{params.query}\""

            # Post to response_url
            response_data = {
                "response_type": "in_channel",
                "blocks": blocks,
                "text": fallback_text,
            }

            session = await self._get_http_session()
            async with session.post(response_url, json=response_data) as resp:
                if resp.status != 200:
                    logger.warning(
                        "Failed to post search results to response_url: %s",
                        await resp.text(),
                    )
                else:
                    # Save state (message_id will be set on interaction)
                    self.search_state_manager.save(chat_key, state)

        except Exception as e:
            logger.exception("Error processing search: %s", e)
            # Try to post error message
            try:
                error_data = {
                    "response_type": "ephemeral",
                    "blocks": format_error("An error occurred while searching."),
                    "text": "An error occurred while searching.",
                }
                session = await self._get_http_session()
                await session.post(response_url, json=error_data)
            except Exception:
                pass

    async def handle_watch(
        self,
        action_id: str,
        value: str | None,
        payload: dict[str, Any],
    ) -> None:
        """Handle Watch button click from overflow menu.

        Args:
            action_id: The action ID (e.g., "session_menu:0").
            value: The selected value (e.g., "watch:0").
            payload: Full Slack interaction payload.
        """
        if not value or not value.startswith("watch:"):
            return

        try:
            session_index = int(value.split(":")[1])
        except (ValueError, IndexError):
            logger.warning("Invalid watch value: %s", value)
            return

        channel_id = payload.get("channel", {}).get("id", "")
        chat_key = f"slack:{channel_id}"

        # Get search state
        state = self.search_state_manager.get(chat_key)
        if state is None:
            await self._respond_ephemeral(
                payload, "Search results expired. Please search again."
            )
            return

        # Get session
        session = state.session_at_index(session_index)
        if session is None:
            await self._respond_ephemeral(payload, "Session not found.")
            return

        # Attach session via callback
        if self.attach_callback:
            try:
                await self.attach_callback(
                    session_id=session.session_id,
                    file_path=str(session.file_path),
                    destination={"type": "slack", "channel": channel_id},
                    replay_count=5,
                )
            except Exception as e:
                logger.exception("Failed to attach session: %s", e)
                await self._respond_ephemeral(
                    payload, f"Failed to attach session: {e}"
                )
                return

        # Post confirmation
        if self.slack_publisher:
            try:
                blocks = format_watch_confirmation(session)
                await self.slack_publisher.send_message(
                    channel=channel_id,
                    text=f'Now watching: "{session.summary}"',
                    blocks=blocks,
                )
            except Exception as e:
                logger.warning("Failed to post watch confirmation: %s", e)

    async def handle_preview(
        self,
        action_id: str,
        value: str | None,
        payload: dict[str, Any],
    ) -> None:
        """Handle Preview button click from overflow menu.

        Args:
            action_id: The action ID (e.g., "session_menu:0").
            value: The selected value (e.g., "preview:0").
            payload: Full Slack interaction payload.
        """
        if not value or not value.startswith("preview:"):
            return

        try:
            session_index = int(value.split(":")[1])
        except (ValueError, IndexError):
            logger.warning("Invalid preview value: %s", value)
            return

        channel_id = payload.get("channel", {}).get("id", "")
        message_ts = payload.get("message", {}).get("ts", "")
        chat_key = f"slack:{channel_id}"

        # Get search state
        state = self.search_state_manager.get(chat_key)
        if state is None:
            await self._respond_ephemeral(
                payload, "Search results expired. Please search again."
            )
            return

        # Get session
        session = state.session_at_index(session_index)
        if session is None:
            await self._respond_ephemeral(payload, "Session not found.")
            return

        # Get preview events (simplified - just show basic info for now)
        # In a full implementation, this would call a preview API
        preview_events = self._generate_preview_events(session)

        # Post preview as thread reply
        if self.slack_publisher:
            try:
                blocks = format_preview(session, preview_events)
                # Post as reply in thread
                await self.slack_publisher._client.chat_postMessage(
                    channel=channel_id,
                    thread_ts=message_ts,
                    text=f'Preview: "{session.summary}"',
                    blocks=blocks,
                )
            except Exception as e:
                logger.warning("Failed to post preview: %s", e)
                await self._respond_ephemeral(
                    payload, f"Failed to get preview: {e}"
                )

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

    async def handle_pagination(
        self,
        action_id: str,
        value: str | None,
        payload: dict[str, Any],
    ) -> None:
        """Handle Prev/Next/Refresh pagination buttons.

        Args:
            action_id: The action ID (search_prev, search_next, search_refresh).
            value: The action value (not used for pagination).
            payload: Full Slack interaction payload.
        """
        channel_id = payload.get("channel", {}).get("id", "")
        message_ts = payload.get("message", {}).get("ts", "")
        chat_key = f"slack:{channel_id}"

        # Handle disabled buttons
        if action_id in ("search_prev_disabled", "search_next_disabled", "search_page_indicator"):
            return

        # Get search state
        state = self.search_state_manager.get(chat_key)
        if state is None:
            await self._respond_ephemeral(
                payload, "Search results expired. Please search again."
            )
            return

        if action_id == "search_next":
            new_offset = state.current_offset + PAGE_SIZE
            state = self.search_state_manager.update_offset(chat_key, new_offset)
        elif action_id == "search_prev":
            new_offset = max(0, state.current_offset - PAGE_SIZE)
            state = self.search_state_manager.update_offset(chat_key, new_offset)
        elif action_id == "search_refresh":
            # Re-run search
            await self._refresh_search(chat_key, state, channel_id, message_ts)
            return

        if state is None:
            return

        # Update message with new page
        await self._update_search_message(state, channel_id, message_ts)

    async def _refresh_search(
        self,
        chat_key: str,
        old_state: SearchState,
        channel_id: str,
        message_ts: str,
    ) -> None:
        """Re-run search and update the message.

        Args:
            chat_key: The chat key for state tracking.
            old_state: The previous search state.
            channel_id: Slack channel ID.
            message_ts: Message timestamp to update.
        """
        try:
            # Re-execute search with same query
            params = self.search_engine.parse_query(old_state.query)
            params.filters = old_state.filters
            results = await self.search_engine.search(params)

            # Create new state
            new_state = SearchState(
                query=old_state.query,
                filters=old_state.filters,
                results=results.results,
                current_offset=0,  # Reset to first page
                message_id=message_ts,
                created_at=datetime.now(timezone.utc),
            )

            # Save new state
            self.search_state_manager.save(chat_key, new_state)

            # Update message
            await self._update_search_message(new_state, channel_id, message_ts)

        except Exception as e:
            logger.exception("Error refreshing search: %s", e)

    async def _update_search_message(
        self,
        state: SearchState,
        channel_id: str,
        message_ts: str,
    ) -> None:
        """Update the search results message with current state.

        Args:
            state: Current search state.
            channel_id: Slack channel ID.
            message_ts: Message timestamp to update.
        """
        if self.slack_publisher is None:
            return

        # Create mock SearchResults for formatting
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
            blocks = format_empty_results(state.query)
            fallback_text = f"No sessions found matching \"{state.query}\""
        else:
            blocks = format_search_results(results, state)
            fallback_text = f"Found {results.total} sessions"

        try:
            await self.slack_publisher.update_message(
                channel=channel_id,
                ts=message_ts,
                text=fallback_text,
                blocks=blocks,
            )
        except Exception as e:
            logger.warning("Failed to update search message: %s", e)

    async def _respond_ephemeral(
        self,
        payload: dict[str, Any],
        message: str,
    ) -> None:
        """Send an ephemeral response to the user.

        Args:
            payload: Slack interaction payload containing response_url.
            message: Message to send.
        """
        response_url = payload.get("response_url")
        if not response_url:
            return

        try:
            response_data = {
                "response_type": "ephemeral",
                "text": message,
                "replace_original": False,
            }
            session = await self._get_http_session()
            await session.post(response_url, json=response_data)
        except Exception as e:
            logger.warning("Failed to send ephemeral response: %s", e)

    async def handle_question_button_interaction(
        self,
        action_id: str,
        value: str,
        payload: dict[str, Any],
    ) -> None:
        """Handle question button click interaction.

        Sends an ephemeral message directing users to respond in the CLI.
        Buttons are display-only and do not trigger any action.

        Args:
            action_id: The action ID (e.g., "question_opt_0_0").
            value: The button value (e.g., "tool_use_id:0:0").
            payload: Full Slack interaction payload.
        """
        await self._respond_ephemeral(
            payload,
            "Please respond to this question in the Claude Code CLI.",
        )
