"""Message state tracking for turn-based message grouping.

This module tracks message state across Telegram and Slack destinations,
handling turn-based grouping of events into messages.

Turn grouping rules:
- A turn starts with an ASSISTANT block (after a USER block)
- A turn includes all ASSISTANT, TOOL_CALL, and DURATION blocks until the next USER block
- USER blocks get their own message
- SYSTEM blocks and ClearAll get their own messages
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Union
from uuid import uuid4

from claude_session_player.events import (
    AddBlock,
    AssistantContent,
    Block,
    BlockType,
    ClearAll,
    DurationContent,
    Event,
    SystemContent,
    ToolCallContent,
    UpdateBlock,
    UserContent,
)
from claude_session_player.watcher.telegram_publisher import (
    ToolCallInfo,
    format_context_compacted,
    format_system_message,
    format_turn_message,
    format_user_message,
    get_tool_icon,
)
from claude_session_player.watcher.slack_publisher import (
    ToolCallInfo as SlackToolCallInfo,
    format_context_compacted_blocks,
    format_system_message_blocks,
    format_turn_message_blocks,
    format_user_message_blocks,
    get_tool_icon as slack_get_tool_icon,
)


# ---------------------------------------------------------------------------
# Data Structures
# ---------------------------------------------------------------------------


@dataclass
class TurnState:
    """State of a single turn being built."""

    turn_id: str
    assistant_text: str = ""
    tool_calls: list[ToolCallInfo] = field(default_factory=list)
    duration_ms: int | None = None
    finalized: bool = False

    # Message IDs per destination (ephemeral, not persisted)
    telegram_messages: dict[str, int] = field(default_factory=dict)  # chat_id -> message_id
    slack_messages: dict[str, str] = field(default_factory=dict)  # channel -> ts

    # Track tool_use_id to tool_call index for updates
    tool_use_id_to_index: dict[str, int] = field(default_factory=dict)


@dataclass
class SessionMessageState:
    """Message state for a single session."""

    session_id: str
    current_turn: TurnState | None = None


# ---------------------------------------------------------------------------
# MessageAction Types
# ---------------------------------------------------------------------------


@dataclass
class SendNewMessage:
    """Send a new message to all destinations."""

    turn_id: str
    message_type: Literal["user", "turn", "system"]
    content: str  # For Telegram
    blocks: list[dict]  # For Slack
    text_fallback: str  # For Slack notifications


@dataclass
class UpdateExistingMessage:
    """Update an existing message at all destinations."""

    turn_id: str
    content: str  # For Telegram
    blocks: list[dict]  # For Slack
    text_fallback: str  # For Slack notifications


@dataclass
class NoAction:
    """No messaging action needed."""

    reason: str


MessageAction = Union[SendNewMessage, UpdateExistingMessage, NoAction]


# ---------------------------------------------------------------------------
# MessageStateTracker
# ---------------------------------------------------------------------------


class MessageStateTracker:
    """Tracks message state for turn-based message grouping.

    This class processes events and determines what messaging action to take
    (send new message, update existing, or no action). It also tracks message
    IDs per destination so updates can be sent to the correct messages.

    State is ephemeral - not persisted across restarts. On restart, we lose
    ability to update old messages and start fresh.
    """

    def __init__(self) -> None:
        """Initialize the tracker."""
        self._sessions: dict[str, SessionMessageState] = {}

    def get_session_state(self, session_id: str) -> SessionMessageState:
        """Get or create session state.

        Args:
            session_id: The session identifier.

        Returns:
            SessionMessageState for the session.
        """
        if session_id not in self._sessions:
            self._sessions[session_id] = SessionMessageState(session_id=session_id)
        return self._sessions[session_id]

    def handle_event(
        self,
        session_id: str,
        event: Event,
    ) -> MessageAction:
        """Process an event and determine the messaging action.

        Args:
            session_id: The session identifier.
            event: The event to process.

        Returns:
            MessageAction indicating what to do (send new, update existing, etc.)
        """
        state = self.get_session_state(session_id)

        if isinstance(event, AddBlock):
            return self._handle_add_block(state, event.block)
        elif isinstance(event, UpdateBlock):
            return self._handle_update_block(state, event)
        elif isinstance(event, ClearAll):
            return self._handle_clear_all(state)
        else:
            return NoAction(reason=f"Unknown event type: {type(event)}")

    def record_message_id(
        self,
        session_id: str,
        turn_id: str,
        destination_type: str,
        identifier: str,
        message_id: int | str,
    ) -> None:
        """Record the message ID after sending to a destination.

        Args:
            session_id: The session identifier.
            turn_id: The turn identifier.
            destination_type: "telegram" or "slack".
            identifier: chat_id for Telegram, channel for Slack.
            message_id: The message ID (int for Telegram, str for Slack).
        """
        state = self.get_session_state(session_id)
        if state.current_turn and state.current_turn.turn_id == turn_id:
            if destination_type == "telegram":
                state.current_turn.telegram_messages[identifier] = int(message_id)
            elif destination_type == "slack":
                state.current_turn.slack_messages[identifier] = str(message_id)

    def get_message_id(
        self,
        session_id: str,
        turn_id: str,
        destination_type: str,
        identifier: str,
    ) -> int | str | None:
        """Get the message ID for a turn at a destination.

        Args:
            session_id: The session identifier.
            turn_id: The turn identifier.
            destination_type: "telegram" or "slack".
            identifier: chat_id for Telegram, channel for Slack.

        Returns:
            The message ID if found, None otherwise.
        """
        state = self.get_session_state(session_id)
        if state.current_turn and state.current_turn.turn_id == turn_id:
            if destination_type == "telegram":
                return state.current_turn.telegram_messages.get(identifier)
            elif destination_type == "slack":
                return state.current_turn.slack_messages.get(identifier)
        return None

    def clear_session(self, session_id: str) -> None:
        """Clear all state for a session.

        Args:
            session_id: The session identifier.
        """
        if session_id in self._sessions:
            del self._sessions[session_id]

    def render_replay(
        self,
        session_id: str,
        events: list[Event],
    ) -> tuple[str, list[dict]]:
        """Render multiple events as a single catch-up message.

        Used when replay_count > 0 on attach.

        Args:
            session_id: The session identifier.
            events: List of events to render.

        Returns:
            Tuple of (telegram_text, slack_blocks).
        """
        if not events:
            return "", []

        # Count events by type
        user_count = 0
        assistant_count = 0
        tool_count = 0

        for event in events:
            if isinstance(event, AddBlock):
                if event.block.type == BlockType.USER:
                    user_count += 1
                elif event.block.type == BlockType.ASSISTANT:
                    assistant_count += 1
                elif event.block.type == BlockType.TOOL_CALL:
                    tool_count += 1

        # Build Telegram text
        text_parts = [f"📜 *Catching up* ({len(events)} events)\n"]
        if user_count:
            text_parts.append(f"\n👤 User messages: {user_count}")
        if assistant_count:
            text_parts.append(f"\n🤖 Assistant turns: {assistant_count}")
        if tool_count:
            text_parts.append(f"\n🔧 Tool calls: {tool_count}")

        telegram_text = "".join(text_parts)

        # Build Slack blocks
        blocks: list[dict] = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"📜 *Catching up* ({len(events)} events)",
                },
            }
        ]

        summary_parts = []
        if user_count:
            summary_parts.append(f"👤 User messages: {user_count}")
        if assistant_count:
            summary_parts.append(f"🤖 Assistant turns: {assistant_count}")
        if tool_count:
            summary_parts.append(f"🔧 Tool calls: {tool_count}")

        if summary_parts:
            blocks.append({"type": "divider"})
            blocks.append(
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": "\n".join(summary_parts)},
                }
            )

        return telegram_text, blocks

    # -------------------------------------------------------------------------
    # Private Methods
    # -------------------------------------------------------------------------

    def _handle_add_block(
        self, state: SessionMessageState, block: Block
    ) -> MessageAction:
        """Handle an AddBlock event."""
        if block.type == BlockType.USER:
            return self._handle_user_block(state, block)
        elif block.type == BlockType.ASSISTANT:
            return self._handle_assistant_block(state, block)
        elif block.type == BlockType.TOOL_CALL:
            return self._handle_tool_call_block(state, block)
        elif block.type == BlockType.DURATION:
            return self._handle_duration_block(state, block)
        elif block.type == BlockType.SYSTEM:
            return self._handle_system_block(state, block)
        elif block.type == BlockType.THINKING:
            # Thinking blocks don't produce messages
            return NoAction(reason="Thinking blocks are not displayed")
        elif block.type == BlockType.QUESTION:
            # Questions are handled like tool calls but we don't have special formatting yet
            return NoAction(reason="Question blocks not yet supported in messaging")
        else:
            return NoAction(reason=f"Unhandled block type: {block.type}")

    def _handle_user_block(
        self, state: SessionMessageState, block: Block
    ) -> MessageAction:
        """Handle a USER block - creates new message and finalizes previous turn."""
        # Finalize current turn (if any)
        if state.current_turn and not state.current_turn.finalized:
            state.current_turn.finalized = True

        # Get user text
        if isinstance(block.content, UserContent):
            text = block.content.text
        else:
            text = ""

        # Format for Telegram and Slack
        content = format_user_message(text)
        blocks = format_user_message_blocks(text)
        text_fallback = f"User: {text[:100]}" if text else "User message"

        return SendNewMessage(
            turn_id=f"user-{block.id}",
            message_type="user",
            content=content,
            blocks=blocks,
            text_fallback=text_fallback,
        )

    def _handle_assistant_block(
        self, state: SessionMessageState, block: Block
    ) -> MessageAction:
        """Handle an ASSISTANT block - starts or continues a turn."""
        # Start new turn if none exists or previous is finalized
        if state.current_turn is None or state.current_turn.finalized:
            state.current_turn = TurnState(turn_id=f"turn-{block.id}")

        # Add assistant text
        if isinstance(block.content, AssistantContent):
            if state.current_turn.assistant_text:
                state.current_turn.assistant_text += "\n\n"
            state.current_turn.assistant_text += block.content.text

        return self._render_turn_action(state.current_turn)

    def _handle_tool_call_block(
        self, state: SessionMessageState, block: Block
    ) -> MessageAction:
        """Handle a TOOL_CALL block - adds to current turn."""
        # Start new turn if none exists
        if state.current_turn is None:
            state.current_turn = TurnState(turn_id=f"turn-{block.id}")

        if isinstance(block.content, ToolCallContent):
            tool_info = ToolCallInfo(
                name=block.content.tool_name,
                label=block.content.label or "",
                icon=get_tool_icon(block.content.tool_name),
                result=block.content.result,
                is_error=block.content.is_error,
            )
            # Track tool_use_id -> index for updates
            idx = len(state.current_turn.tool_calls)
            state.current_turn.tool_use_id_to_index[block.content.tool_use_id] = idx
            state.current_turn.tool_calls.append(tool_info)

        return self._render_turn_action(state.current_turn)

    def _handle_duration_block(
        self, state: SessionMessageState, block: Block
    ) -> MessageAction:
        """Handle a DURATION block - adds footer to current turn."""
        if state.current_turn:
            if isinstance(block.content, DurationContent):
                state.current_turn.duration_ms = block.content.duration_ms
            return self._render_turn_action(state.current_turn)
        return NoAction(reason="Duration without turn")

    def _handle_system_block(
        self, state: SessionMessageState, block: Block
    ) -> MessageAction:
        """Handle a SYSTEM block - creates standalone message."""
        if isinstance(block.content, SystemContent):
            text = block.content.text
        else:
            text = ""

        content = format_system_message(text)
        blocks = format_system_message_blocks(text)
        text_fallback = f"System: {text}"

        return SendNewMessage(
            turn_id=f"system-{block.id}",
            message_type="system",
            content=content,
            blocks=blocks,
            text_fallback=text_fallback,
        )

    def _handle_update_block(
        self, state: SessionMessageState, event: UpdateBlock
    ) -> MessageAction:
        """Handle an UpdateBlock event - update tool result in current turn."""
        if not state.current_turn:
            return NoAction(reason="Update without current turn")

        # UpdateBlock contains updated content, usually ToolCallContent with result
        if isinstance(event.content, ToolCallContent):
            tool_use_id = event.content.tool_use_id
            if tool_use_id in state.current_turn.tool_use_id_to_index:
                idx = state.current_turn.tool_use_id_to_index[tool_use_id]
                tool = state.current_turn.tool_calls[idx]
                # Update the result
                tool.result = event.content.result
                tool.is_error = event.content.is_error
                return self._render_turn_action(state.current_turn)

        return NoAction(reason="Update for unknown block")

    def _handle_clear_all(self, state: SessionMessageState) -> MessageAction:
        """Handle a ClearAll event - context compaction."""
        # Finalize current turn
        if state.current_turn:
            state.current_turn.finalized = True
        state.current_turn = None

        # Send context compacted message
        content = format_context_compacted()
        blocks = format_context_compacted_blocks()

        return SendNewMessage(
            turn_id=f"clear-{uuid4().hex[:8]}",
            message_type="system",
            content=content,
            blocks=blocks,
            text_fallback="Context compacted",
        )

    def _render_turn_action(self, turn: TurnState) -> MessageAction:
        """Render the turn as a message action."""
        # Convert ToolCallInfo to SlackToolCallInfo for Slack formatting
        slack_tool_calls = [
            SlackToolCallInfo(
                name=t.name,
                label=t.label,
                icon=slack_get_tool_icon(t.name),
                result=t.result,
                is_error=t.is_error,
            )
            for t in turn.tool_calls
        ]

        content = format_turn_message(
            turn.assistant_text or None,
            turn.tool_calls,
            turn.duration_ms,
        )
        blocks = format_turn_message_blocks(
            turn.assistant_text or None,
            slack_tool_calls,
            turn.duration_ms,
        )
        text_fallback = (
            f"Assistant: {turn.assistant_text[:100]}..."
            if turn.assistant_text
            else "Assistant response"
        )

        # If we have message IDs, it's an update; otherwise it's new
        if turn.telegram_messages or turn.slack_messages:
            return UpdateExistingMessage(
                turn_id=turn.turn_id,
                content=content,
                blocks=blocks,
                text_fallback=text_fallback,
            )
        else:
            return SendNewMessage(
                turn_id=turn.turn_id,
                message_type="turn",
                content=content,
                blocks=blocks,
                text_fallback=text_fallback,
            )
