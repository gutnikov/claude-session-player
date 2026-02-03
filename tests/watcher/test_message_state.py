"""Tests for MessageStateTracker."""

from __future__ import annotations

import pytest

from claude_session_player.events import (
    AddBlock,
    AssistantContent,
    Block,
    BlockType,
    ClearAll,
    DurationContent,
    SystemContent,
    ThinkingContent,
    ToolCallContent,
    UpdateBlock,
    UserContent,
)
from claude_session_player.watcher.message_state import (
    MessageAction,
    MessageStateTracker,
    NoAction,
    SendNewMessage,
    SessionMessageState,
    TurnState,
    UpdateExistingMessage,
)


# ---------------------------------------------------------------------------
# Test Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tracker() -> MessageStateTracker:
    """Create a fresh MessageStateTracker for each test."""
    return MessageStateTracker()


def make_user_block(block_id: str = "u1", text: str = "Hello") -> Block:
    """Create a user block for testing."""
    return Block(
        id=block_id,
        type=BlockType.USER,
        content=UserContent(text=text),
    )


def make_assistant_block(block_id: str = "a1", text: str = "Hi there") -> Block:
    """Create an assistant block for testing."""
    return Block(
        id=block_id,
        type=BlockType.ASSISTANT,
        content=AssistantContent(text=text),
    )


def make_tool_call_block(
    block_id: str = "t1",
    tool_name: str = "Read",
    tool_use_id: str = "tu1",
    label: str = "src/main.py",
    result: str | None = None,
    is_error: bool = False,
) -> Block:
    """Create a tool call block for testing."""
    return Block(
        id=block_id,
        type=BlockType.TOOL_CALL,
        content=ToolCallContent(
            tool_name=tool_name,
            tool_use_id=tool_use_id,
            label=label,
            result=result,
            is_error=is_error,
        ),
    )


def make_duration_block(block_id: str = "d1", duration_ms: int = 5000) -> Block:
    """Create a duration block for testing."""
    return Block(
        id=block_id,
        type=BlockType.DURATION,
        content=DurationContent(duration_ms=duration_ms),
    )


def make_system_block(block_id: str = "s1", text: str = "System message") -> Block:
    """Create a system block for testing."""
    return Block(
        id=block_id,
        type=BlockType.SYSTEM,
        content=SystemContent(text=text),
    )


def make_thinking_block(block_id: str = "th1") -> Block:
    """Create a thinking block for testing."""
    return Block(
        id=block_id,
        type=BlockType.THINKING,
        content=ThinkingContent(),
    )


# ---------------------------------------------------------------------------
# Test TurnState
# ---------------------------------------------------------------------------


class TestTurnState:
    """Tests for TurnState dataclass."""

    def test_create_default(self) -> None:
        """Test creating TurnState with defaults."""
        turn = TurnState(turn_id="turn-1")
        assert turn.turn_id == "turn-1"
        assert turn.assistant_text == ""
        assert turn.tool_calls == []
        assert turn.duration_ms is None
        assert turn.finalized is False
        assert turn.telegram_messages == {}
        assert turn.slack_messages == {}
        assert turn.tool_use_id_to_index == {}

    def test_create_with_values(self) -> None:
        """Test creating TurnState with values."""
        from claude_session_player.watcher.telegram_publisher import ToolCallInfo

        turn = TurnState(
            turn_id="turn-1",
            assistant_text="Hello",
            tool_calls=[ToolCallInfo(name="Read", label="test.py", icon="📖")],
            duration_ms=5000,
            finalized=True,
            telegram_messages={"123": 456},
            slack_messages={"C123": "ts123"},
        )
        assert turn.turn_id == "turn-1"
        assert turn.assistant_text == "Hello"
        assert len(turn.tool_calls) == 1
        assert turn.duration_ms == 5000
        assert turn.finalized is True
        assert turn.telegram_messages == {"123": 456}
        assert turn.slack_messages == {"C123": "ts123"}


class TestSessionMessageState:
    """Tests for SessionMessageState dataclass."""

    def test_create_default(self) -> None:
        """Test creating SessionMessageState with defaults."""
        state = SessionMessageState(session_id="sess-1")
        assert state.session_id == "sess-1"
        assert state.current_turn is None

    def test_create_with_turn(self) -> None:
        """Test creating SessionMessageState with a turn."""
        turn = TurnState(turn_id="turn-1")
        state = SessionMessageState(session_id="sess-1", current_turn=turn)
        assert state.current_turn is turn


# ---------------------------------------------------------------------------
# Test MessageAction Types
# ---------------------------------------------------------------------------


class TestMessageActionTypes:
    """Tests for MessageAction types."""

    def test_send_new_message(self) -> None:
        """Test SendNewMessage creation."""
        action = SendNewMessage(
            turn_id="turn-1",
            message_type="turn",
            content="Hello",
            blocks=[{"type": "section", "text": {"type": "mrkdwn", "text": "Hello"}}],
            text_fallback="Hello fallback",
        )
        assert action.turn_id == "turn-1"
        assert action.message_type == "turn"
        assert action.content == "Hello"
        assert len(action.blocks) == 1
        assert action.text_fallback == "Hello fallback"

    def test_update_existing_message(self) -> None:
        """Test UpdateExistingMessage creation."""
        action = UpdateExistingMessage(
            turn_id="turn-1",
            content="Updated",
            blocks=[],
            text_fallback="Updated fallback",
        )
        assert action.turn_id == "turn-1"
        assert action.content == "Updated"

    def test_no_action(self) -> None:
        """Test NoAction creation."""
        action = NoAction(reason="No reason")
        assert action.reason == "No reason"


# ---------------------------------------------------------------------------
# Test MessageStateTracker - Basic Operations
# ---------------------------------------------------------------------------


class TestMessageStateTrackerBasic:
    """Tests for basic MessageStateTracker operations."""

    def test_get_session_state_creates_new(self, tracker: MessageStateTracker) -> None:
        """Test get_session_state creates new state if not exists."""
        state = tracker.get_session_state("sess-1")
        assert state.session_id == "sess-1"
        assert state.current_turn is None

    def test_get_session_state_returns_existing(
        self, tracker: MessageStateTracker
    ) -> None:
        """Test get_session_state returns existing state."""
        state1 = tracker.get_session_state("sess-1")
        state1.current_turn = TurnState(turn_id="turn-1")
        state2 = tracker.get_session_state("sess-1")
        assert state2.current_turn is not None
        assert state2.current_turn.turn_id == "turn-1"

    def test_clear_session(self, tracker: MessageStateTracker) -> None:
        """Test clear_session removes session state."""
        tracker.get_session_state("sess-1")
        tracker.clear_session("sess-1")
        # Getting state again should create fresh state
        state = tracker.get_session_state("sess-1")
        assert state.current_turn is None

    def test_clear_session_nonexistent(self, tracker: MessageStateTracker) -> None:
        """Test clear_session on non-existent session is safe."""
        tracker.clear_session("nonexistent")  # Should not raise


# ---------------------------------------------------------------------------
# Test MessageStateTracker - USER Block Handling
# ---------------------------------------------------------------------------


class TestHandleUserBlock:
    """Tests for USER block handling."""

    def test_user_block_sends_new_message(self, tracker: MessageStateTracker) -> None:
        """Test USER block creates SendNewMessage."""
        block = make_user_block(text="Hello world")
        event = AddBlock(block=block)
        action = tracker.handle_event("sess-1", event)

        assert isinstance(action, SendNewMessage)
        assert action.message_type == "user"
        assert action.turn_id == "user-u1"
        assert "Hello world" in action.content
        assert "👤" in action.content
        assert len(action.blocks) == 1

    def test_user_block_finalizes_previous_turn(
        self, tracker: MessageStateTracker
    ) -> None:
        """Test USER block finalizes the previous turn."""
        # Start a turn
        assistant_block = make_assistant_block()
        tracker.handle_event("sess-1", AddBlock(block=assistant_block))

        state = tracker.get_session_state("sess-1")
        assert state.current_turn is not None
        assert not state.current_turn.finalized

        # User block should finalize it
        user_block = make_user_block()
        tracker.handle_event("sess-1", AddBlock(block=user_block))

        assert state.current_turn.finalized

    def test_user_block_with_empty_text(self, tracker: MessageStateTracker) -> None:
        """Test USER block with empty text."""
        block = make_user_block(text="")
        event = AddBlock(block=block)
        action = tracker.handle_event("sess-1", event)

        assert isinstance(action, SendNewMessage)
        assert action.text_fallback == "User message"


# ---------------------------------------------------------------------------
# Test MessageStateTracker - ASSISTANT Block Handling
# ---------------------------------------------------------------------------


class TestHandleAssistantBlock:
    """Tests for ASSISTANT block handling."""

    def test_assistant_block_starts_new_turn(
        self, tracker: MessageStateTracker
    ) -> None:
        """Test ASSISTANT block starts a new turn."""
        block = make_assistant_block(text="Hello!")
        event = AddBlock(block=block)
        action = tracker.handle_event("sess-1", event)

        assert isinstance(action, SendNewMessage)
        assert action.message_type == "turn"
        assert "Hello!" in action.content
        assert "🤖" in action.content

    def test_assistant_block_continues_turn(
        self, tracker: MessageStateTracker
    ) -> None:
        """Test multiple ASSISTANT blocks continue the same turn."""
        block1 = make_assistant_block(block_id="a1", text="First part")
        block2 = make_assistant_block(block_id="a2", text="Second part")

        action1 = tracker.handle_event("sess-1", AddBlock(block=block1))
        assert isinstance(action1, SendNewMessage)

        # Record message ID so next action is an update
        tracker.record_message_id("sess-1", action1.turn_id, "telegram", "123", 456)

        action2 = tracker.handle_event("sess-1", AddBlock(block=block2))
        assert isinstance(action2, UpdateExistingMessage)
        assert "First part" in action2.content
        assert "Second part" in action2.content

    def test_assistant_block_after_finalized_turn(
        self, tracker: MessageStateTracker
    ) -> None:
        """Test ASSISTANT block after finalized turn starts new turn."""
        # First turn
        block1 = make_assistant_block(block_id="a1", text="First turn")
        tracker.handle_event("sess-1", AddBlock(block=block1))

        # Finalize with user block
        user_block = make_user_block()
        tracker.handle_event("sess-1", AddBlock(block=user_block))

        # New assistant block should start new turn
        block2 = make_assistant_block(block_id="a2", text="Second turn")
        action = tracker.handle_event("sess-1", AddBlock(block=block2))

        assert isinstance(action, SendNewMessage)
        assert action.turn_id == "turn-a2"
        assert "Second turn" in action.content
        assert "First turn" not in action.content


# ---------------------------------------------------------------------------
# Test MessageStateTracker - TOOL_CALL Block Handling
# ---------------------------------------------------------------------------


class TestHandleToolCallBlock:
    """Tests for TOOL_CALL block handling."""

    def test_tool_call_starts_turn_if_none(
        self, tracker: MessageStateTracker
    ) -> None:
        """Test TOOL_CALL block starts a turn if none exists."""
        block = make_tool_call_block(tool_name="Read", label="test.py")
        action = tracker.handle_event("sess-1", AddBlock(block=block))

        assert isinstance(action, SendNewMessage)
        assert action.message_type == "turn"
        assert "📖" in action.content  # Read icon
        assert "test.py" in action.content

    def test_tool_call_added_to_existing_turn(
        self, tracker: MessageStateTracker
    ) -> None:
        """Test TOOL_CALL block is added to existing turn."""
        # Start turn with assistant
        assistant_block = make_assistant_block(text="Let me check")
        action1 = tracker.handle_event("sess-1", AddBlock(block=assistant_block))
        tracker.record_message_id("sess-1", action1.turn_id, "telegram", "123", 456)

        # Add tool call
        tool_block = make_tool_call_block(tool_name="Read", label="test.py")
        action2 = tracker.handle_event("sess-1", AddBlock(block=tool_block))

        assert isinstance(action2, UpdateExistingMessage)
        assert "Let me check" in action2.content
        assert "📖" in action2.content
        assert "test.py" in action2.content

    def test_tool_call_with_result(self, tracker: MessageStateTracker) -> None:
        """Test TOOL_CALL block with result."""
        block = make_tool_call_block(
            tool_name="Read", label="test.py", result="file contents here"
        )
        action = tracker.handle_event("sess-1", AddBlock(block=block))

        assert isinstance(action, SendNewMessage)
        assert "file contents here" in action.content

    def test_tool_call_with_error(self, tracker: MessageStateTracker) -> None:
        """Test TOOL_CALL block with error."""
        block = make_tool_call_block(
            tool_name="Read", label="test.py", is_error=True
        )
        action = tracker.handle_event("sess-1", AddBlock(block=block))

        assert isinstance(action, SendNewMessage)
        assert "Error" in action.content

    def test_multiple_tool_calls_in_turn(self, tracker: MessageStateTracker) -> None:
        """Test multiple tool calls in the same turn."""
        # Start with assistant
        assistant_block = make_assistant_block(text="Checking files")
        action1 = tracker.handle_event("sess-1", AddBlock(block=assistant_block))
        tracker.record_message_id("sess-1", action1.turn_id, "telegram", "123", 456)

        # Add first tool
        tool1 = make_tool_call_block(
            block_id="t1", tool_name="Read", tool_use_id="tu1", label="file1.py"
        )
        tracker.handle_event("sess-1", AddBlock(block=tool1))

        # Add second tool
        tool2 = make_tool_call_block(
            block_id="t2", tool_name="Bash", tool_use_id="tu2", label="ls -la"
        )
        action3 = tracker.handle_event("sess-1", AddBlock(block=tool2))

        assert isinstance(action3, UpdateExistingMessage)
        assert "file1.py" in action3.content
        assert "ls -la" in action3.content


# ---------------------------------------------------------------------------
# Test MessageStateTracker - DURATION Block Handling
# ---------------------------------------------------------------------------


class TestHandleDurationBlock:
    """Tests for DURATION block handling."""

    def test_duration_block_added_to_turn(self, tracker: MessageStateTracker) -> None:
        """Test DURATION block is added to current turn."""
        # Start turn
        assistant_block = make_assistant_block(text="Done!")
        action1 = tracker.handle_event("sess-1", AddBlock(block=assistant_block))
        tracker.record_message_id("sess-1", action1.turn_id, "telegram", "123", 456)

        # Add duration
        duration_block = make_duration_block(duration_ms=12300)
        action2 = tracker.handle_event("sess-1", AddBlock(block=duration_block))

        assert isinstance(action2, UpdateExistingMessage)
        assert "12.3s" in action2.content

    def test_duration_block_without_turn(self, tracker: MessageStateTracker) -> None:
        """Test DURATION block without current turn returns NoAction."""
        duration_block = make_duration_block()
        action = tracker.handle_event("sess-1", AddBlock(block=duration_block))

        assert isinstance(action, NoAction)
        assert "Duration without turn" in action.reason


# ---------------------------------------------------------------------------
# Test MessageStateTracker - SYSTEM Block Handling
# ---------------------------------------------------------------------------


class TestHandleSystemBlock:
    """Tests for SYSTEM block handling."""

    def test_system_block_sends_new_message(
        self, tracker: MessageStateTracker
    ) -> None:
        """Test SYSTEM block creates SendNewMessage."""
        block = make_system_block(text="Session started")
        action = tracker.handle_event("sess-1", AddBlock(block=block))

        assert isinstance(action, SendNewMessage)
        assert action.message_type == "system"
        assert action.turn_id == "system-s1"
        assert "Session started" in action.content
        assert "⚡" in action.content

    def test_system_block_does_not_affect_turn(
        self, tracker: MessageStateTracker
    ) -> None:
        """Test SYSTEM block does not affect current turn."""
        # Start turn
        assistant_block = make_assistant_block(text="Working...")
        tracker.handle_event("sess-1", AddBlock(block=assistant_block))

        state = tracker.get_session_state("sess-1")
        turn = state.current_turn

        # System block should not change the turn
        system_block = make_system_block(text="Note")
        tracker.handle_event("sess-1", AddBlock(block=system_block))

        assert state.current_turn is turn


# ---------------------------------------------------------------------------
# Test MessageStateTracker - UpdateBlock Handling
# ---------------------------------------------------------------------------


class TestHandleUpdateBlock:
    """Tests for UpdateBlock handling."""

    def test_update_block_updates_tool_result(
        self, tracker: MessageStateTracker
    ) -> None:
        """Test UpdateBlock updates tool result in turn."""
        # Start turn with tool call
        tool_block = make_tool_call_block(
            tool_name="Read", tool_use_id="tu1", label="test.py"
        )
        action1 = tracker.handle_event("sess-1", AddBlock(block=tool_block))
        tracker.record_message_id("sess-1", action1.turn_id, "telegram", "123", 456)

        # Update with result
        update = UpdateBlock(
            block_id="t1",
            content=ToolCallContent(
                tool_name="Read",
                tool_use_id="tu1",
                label="test.py",
                result="file contents",
                is_error=False,
            ),
        )
        action2 = tracker.handle_event("sess-1", update)

        assert isinstance(action2, UpdateExistingMessage)
        assert "file contents" in action2.content

    def test_update_block_updates_tool_error(
        self, tracker: MessageStateTracker
    ) -> None:
        """Test UpdateBlock updates tool error status."""
        # Start turn with tool call
        tool_block = make_tool_call_block(
            tool_name="Bash", tool_use_id="tu1", label="ls -la"
        )
        action1 = tracker.handle_event("sess-1", AddBlock(block=tool_block))
        tracker.record_message_id("sess-1", action1.turn_id, "telegram", "123", 456)

        # Update with error
        update = UpdateBlock(
            block_id="t1",
            content=ToolCallContent(
                tool_name="Bash",
                tool_use_id="tu1",
                label="ls -la",
                result=None,
                is_error=True,
            ),
        )
        action2 = tracker.handle_event("sess-1", update)

        assert isinstance(action2, UpdateExistingMessage)
        assert "Error" in action2.content

    def test_update_block_without_turn(self, tracker: MessageStateTracker) -> None:
        """Test UpdateBlock without current turn returns NoAction."""
        update = UpdateBlock(
            block_id="t1",
            content=ToolCallContent(
                tool_name="Read",
                tool_use_id="tu1",
                label="test.py",
                result="result",
            ),
        )
        action = tracker.handle_event("sess-1", update)

        assert isinstance(action, NoAction)
        assert "Update without current turn" in action.reason

    def test_update_block_unknown_tool_use_id(
        self, tracker: MessageStateTracker
    ) -> None:
        """Test UpdateBlock with unknown tool_use_id returns NoAction."""
        # Start turn with tool call
        tool_block = make_tool_call_block(
            tool_name="Read", tool_use_id="tu1", label="test.py"
        )
        tracker.handle_event("sess-1", AddBlock(block=tool_block))

        # Update with different tool_use_id
        update = UpdateBlock(
            block_id="t2",
            content=ToolCallContent(
                tool_name="Read",
                tool_use_id="tu-unknown",
                label="other.py",
                result="result",
            ),
        )
        action = tracker.handle_event("sess-1", update)

        assert isinstance(action, NoAction)
        assert "unknown block" in action.reason


# ---------------------------------------------------------------------------
# Test MessageStateTracker - ClearAll Handling
# ---------------------------------------------------------------------------


class TestHandleClearAll:
    """Tests for ClearAll handling."""

    def test_clear_all_sends_compaction_message(
        self, tracker: MessageStateTracker
    ) -> None:
        """Test ClearAll creates SendNewMessage for compaction."""
        action = tracker.handle_event("sess-1", ClearAll())

        assert isinstance(action, SendNewMessage)
        assert action.message_type == "system"
        assert action.turn_id.startswith("clear-")
        assert "Context compacted" in action.content
        assert action.text_fallback == "Context compacted"

    def test_clear_all_finalizes_current_turn(
        self, tracker: MessageStateTracker
    ) -> None:
        """Test ClearAll finalizes the current turn."""
        # Start turn
        assistant_block = make_assistant_block(text="Working...")
        tracker.handle_event("sess-1", AddBlock(block=assistant_block))

        state = tracker.get_session_state("sess-1")
        assert state.current_turn is not None
        assert not state.current_turn.finalized

        # Clear all
        tracker.handle_event("sess-1", ClearAll())

        # Current turn should be None now
        assert state.current_turn is None

    def test_clear_all_without_turn(self, tracker: MessageStateTracker) -> None:
        """Test ClearAll without current turn still sends message."""
        action = tracker.handle_event("sess-1", ClearAll())

        assert isinstance(action, SendNewMessage)
        assert "Context compacted" in action.content


# ---------------------------------------------------------------------------
# Test MessageStateTracker - Message ID Tracking
# ---------------------------------------------------------------------------


class TestMessageIdTracking:
    """Tests for message ID tracking."""

    def test_record_telegram_message_id(self, tracker: MessageStateTracker) -> None:
        """Test recording Telegram message ID."""
        # Start turn
        assistant_block = make_assistant_block()
        action = tracker.handle_event("sess-1", AddBlock(block=assistant_block))

        # Record message ID
        tracker.record_message_id(
            "sess-1", action.turn_id, "telegram", "12345", 67890
        )

        # Verify
        msg_id = tracker.get_message_id(
            "sess-1", action.turn_id, "telegram", "12345"
        )
        assert msg_id == 67890

    def test_record_slack_message_id(self, tracker: MessageStateTracker) -> None:
        """Test recording Slack message ID."""
        # Start turn
        assistant_block = make_assistant_block()
        action = tracker.handle_event("sess-1", AddBlock(block=assistant_block))

        # Record message ID
        tracker.record_message_id(
            "sess-1", action.turn_id, "slack", "C12345", "ts123.456"
        )

        # Verify
        msg_id = tracker.get_message_id(
            "sess-1", action.turn_id, "slack", "C12345"
        )
        assert msg_id == "ts123.456"

    def test_get_message_id_wrong_turn(self, tracker: MessageStateTracker) -> None:
        """Test getting message ID for wrong turn returns None."""
        # Start turn
        assistant_block = make_assistant_block()
        action = tracker.handle_event("sess-1", AddBlock(block=assistant_block))

        tracker.record_message_id(
            "sess-1", action.turn_id, "telegram", "12345", 67890
        )

        # Try to get with wrong turn_id
        msg_id = tracker.get_message_id(
            "sess-1", "wrong-turn", "telegram", "12345"
        )
        assert msg_id is None

    def test_get_message_id_wrong_identifier(
        self, tracker: MessageStateTracker
    ) -> None:
        """Test getting message ID for wrong identifier returns None."""
        # Start turn
        assistant_block = make_assistant_block()
        action = tracker.handle_event("sess-1", AddBlock(block=assistant_block))

        tracker.record_message_id(
            "sess-1", action.turn_id, "telegram", "12345", 67890
        )

        # Try to get with wrong identifier
        msg_id = tracker.get_message_id(
            "sess-1", action.turn_id, "telegram", "99999"
        )
        assert msg_id is None

    def test_message_id_enables_update_action(
        self, tracker: MessageStateTracker
    ) -> None:
        """Test that recording message ID makes next action an update."""
        # Start turn
        assistant_block = make_assistant_block(block_id="a1", text="First")
        action1 = tracker.handle_event("sess-1", AddBlock(block=assistant_block))
        assert isinstance(action1, SendNewMessage)

        # Record message ID
        tracker.record_message_id(
            "sess-1", action1.turn_id, "telegram", "12345", 67890
        )

        # Next block should trigger update
        tool_block = make_tool_call_block()
        action2 = tracker.handle_event("sess-1", AddBlock(block=tool_block))
        assert isinstance(action2, UpdateExistingMessage)


# ---------------------------------------------------------------------------
# Test MessageStateTracker - Replay Rendering
# ---------------------------------------------------------------------------


class TestReplayRendering:
    """Tests for replay rendering."""

    def test_render_replay_empty_events(self, tracker: MessageStateTracker) -> None:
        """Test render_replay with empty events list."""
        text, blocks = tracker.render_replay("sess-1", [])
        assert text == ""
        assert blocks == []

    def test_render_replay_with_events(self, tracker: MessageStateTracker) -> None:
        """Test render_replay with various events."""
        events = [
            AddBlock(block=make_user_block(block_id="u1", text="Hello")),
            AddBlock(block=make_assistant_block(block_id="a1", text="Hi")),
            AddBlock(block=make_tool_call_block(block_id="t1")),
            AddBlock(block=make_tool_call_block(block_id="t2")),
        ]

        text, blocks = tracker.render_replay("sess-1", events)

        assert "Catching up" in text
        assert "(4 events)" in text
        assert "User messages: 1" in text
        assert "Assistant turns: 1" in text
        assert "Tool calls: 2" in text

        assert len(blocks) >= 1
        assert "Catching up" in blocks[0]["text"]["text"]

    def test_render_replay_only_user_messages(
        self, tracker: MessageStateTracker
    ) -> None:
        """Test render_replay with only user messages."""
        events = [
            AddBlock(block=make_user_block(block_id="u1", text="Hello")),
            AddBlock(block=make_user_block(block_id="u2", text="World")),
        ]

        text, blocks = tracker.render_replay("sess-1", events)

        assert "User messages: 2" in text
        assert "Assistant turns" not in text
        assert "Tool calls" not in text


# ---------------------------------------------------------------------------
# Test MessageStateTracker - Other Block Types
# ---------------------------------------------------------------------------


class TestOtherBlockTypes:
    """Tests for other block types."""

    def test_thinking_block_returns_no_action(
        self, tracker: MessageStateTracker
    ) -> None:
        """Test THINKING block returns NoAction."""
        block = make_thinking_block()
        action = tracker.handle_event("sess-1", AddBlock(block=block))

        assert isinstance(action, NoAction)
        assert "Thinking blocks" in action.reason


# ---------------------------------------------------------------------------
# Test MessageStateTracker - Turn Grouping Integration
# ---------------------------------------------------------------------------


class TestTurnGroupingIntegration:
    """Integration tests for turn grouping."""

    def test_full_turn_cycle(self, tracker: MessageStateTracker) -> None:
        """Test a complete turn cycle: user -> assistant -> tools -> duration -> user."""
        session = "sess-1"

        # User message
        action1 = tracker.handle_event(
            session, AddBlock(block=make_user_block(text="Do something"))
        )
        assert isinstance(action1, SendNewMessage)
        assert action1.message_type == "user"

        # Assistant response
        action2 = tracker.handle_event(
            session, AddBlock(block=make_assistant_block(text="I'll help"))
        )
        assert isinstance(action2, SendNewMessage)
        assert action2.message_type == "turn"
        turn_id = action2.turn_id

        # Record message IDs
        tracker.record_message_id(session, turn_id, "telegram", "123", 456)
        tracker.record_message_id(session, turn_id, "slack", "C123", "ts123")

        # Tool call
        action3 = tracker.handle_event(
            session, AddBlock(block=make_tool_call_block(tool_name="Read", label="f.py"))
        )
        assert isinstance(action3, UpdateExistingMessage)
        assert action3.turn_id == turn_id

        # Duration
        action4 = tracker.handle_event(
            session, AddBlock(block=make_duration_block(duration_ms=5000))
        )
        assert isinstance(action4, UpdateExistingMessage)
        assert "5.0s" in action4.content

        # Next user message
        action5 = tracker.handle_event(
            session, AddBlock(block=make_user_block(block_id="u2", text="Thanks"))
        )
        assert isinstance(action5, SendNewMessage)
        assert action5.message_type == "user"

        # Verify turn was finalized
        state = tracker.get_session_state(session)
        # Current turn should be the old finalized one, not None
        # (only cleared on ClearAll)
        assert state.current_turn.finalized

    def test_multiple_sessions_isolated(self, tracker: MessageStateTracker) -> None:
        """Test that multiple sessions are isolated."""
        # Session 1: start turn
        tracker.handle_event(
            "sess-1", AddBlock(block=make_assistant_block(text="Session 1"))
        )

        # Session 2: start different turn
        tracker.handle_event(
            "sess-2", AddBlock(block=make_assistant_block(text="Session 2"))
        )

        state1 = tracker.get_session_state("sess-1")
        state2 = tracker.get_session_state("sess-2")

        assert state1.current_turn.assistant_text == "Session 1"
        assert state2.current_turn.assistant_text == "Session 2"


# ---------------------------------------------------------------------------
# Test Module Imports
# ---------------------------------------------------------------------------


class TestModuleImports:
    """Tests for module imports."""

    def test_import_from_message_state(self) -> None:
        """Test imports from message_state module."""
        from claude_session_player.watcher.message_state import (
            MessageAction,
            MessageStateTracker,
            NoAction,
            SendNewMessage,
            SessionMessageState,
            TurnState,
            UpdateExistingMessage,
        )

        assert MessageAction is not None
        assert MessageStateTracker is not None
        assert NoAction is not None
        assert SendNewMessage is not None
        assert SessionMessageState is not None
        assert TurnState is not None
        assert UpdateExistingMessage is not None

    def test_import_from_watcher_init(self) -> None:
        """Test imports from watcher __init__."""
        from claude_session_player.watcher import (
            MessageAction,
            MessageStateTracker,
            NoAction,
            SendNewMessage,
            SessionMessageState,
            TurnState,
            UpdateExistingMessage,
        )

        assert MessageAction is not None
        assert MessageStateTracker is not None
        assert NoAction is not None
        assert SendNewMessage is not None
        assert SessionMessageState is not None
        assert TurnState is not None
        assert UpdateExistingMessage is not None

    def test_all_exports(self) -> None:
        """Test that all exports are in __all__."""
        from claude_session_player.watcher import __all__

        expected = [
            "MessageAction",
            "MessageStateTracker",
            "NoAction",
            "SendNewMessage",
            "SessionMessageState",
            "TurnState",
            "UpdateExistingMessage",
        ]
        for name in expected:
            assert name in __all__, f"{name} not in __all__"
