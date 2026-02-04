"""End-to-end tests for question presentation in messaging.

These tests verify the complete question presentation flow from JSONL session
events through to Telegram/Slack message output, including:
- Question JSONL parsing and event generation
- MessageStateTracker action generation
- Telegram inline keyboard formatting
- Slack Block Kit button formatting
- Answer update handling with keyboard removal
- Option truncation for questions with many options
"""

from __future__ import annotations

import pytest

from claude_session_player.events import (
    AddBlock,
    BlockType,
    ProcessingContext,
    QuestionContent,
    UpdateBlock,
)
from claude_session_player.parser import LineType, classify_line
from claude_session_player.processor import process_line
from claude_session_player.watcher.message_state import (
    MessageStateTracker,
    SendNewMessage,
    UpdateExistingMessage,
)
from claude_session_player.watcher.slack_publisher import (
    MAX_QUESTION_BUTTONS,
    format_answered_question_blocks,
    format_question_blocks,
)
from claude_session_player.watcher.telegram_publisher import (
    MAX_QUESTION_BUTTONS as TELEGRAM_MAX_BUTTONS,
    format_question_keyboard,
    format_question_text,
)


# -----------------------------------------------------------------------------
# TestQuestionPipelineE2E
# -----------------------------------------------------------------------------


class TestQuestionPipelineE2E:
    """E2E tests for complete question pipeline from JSONL to messaging output."""

    def test_question_jsonl_to_telegram_keyboard(
        self,
        question_jsonl_line: dict,
    ) -> None:
        """Full pipeline: JSONL -> Event -> MessageAction -> Telegram keyboard.

        Verifies that a question JSONL line is:
        1. Correctly classified as TOOL_USE
        2. Processed into an AddBlock with QUESTION BlockType
        3. Produces a SendNewMessage with correct content
        4. Generates Telegram inline keyboard with correct callback data
        """
        # Step 1: Classify the line
        line_type = classify_line(question_jsonl_line)
        assert line_type == LineType.TOOL_USE

        # Step 2: Process the line into events
        context = ProcessingContext()
        events = process_line(context, question_jsonl_line)

        assert len(events) == 1
        event = events[0]
        assert isinstance(event, AddBlock)
        assert event.block.type == BlockType.QUESTION

        # Verify content is QuestionContent
        content = event.block.content
        assert isinstance(content, QuestionContent)
        assert content.tool_use_id == "toolu_q123"
        assert len(content.questions) == 1
        assert len(content.questions[0].options) == 3

        # Step 3: Process through MessageStateTracker
        tracker = MessageStateTracker()
        action = tracker.handle_event("test-session", event)

        assert isinstance(action, SendNewMessage)
        assert action.message_type == "question"
        assert action.metadata.get("tool_use_id") == "toolu_q123"

        # Step 4: Generate Telegram keyboard
        keyboard = format_question_keyboard(content)
        assert keyboard is not None

        # Verify keyboard has correct structure
        buttons = keyboard.inline_keyboard
        assert len(buttons) == 3  # 3 options = 3 rows

        # Verify callback data format: q:{tool_use_id}:{question_idx}:{option_idx}
        for i, row in enumerate(buttons):
            assert len(row) == 1
            button = row[0]
            expected_callback = f"q:toolu_q123:0:{i}"
            assert button.callback_data == expected_callback

        # Verify button labels
        assert buttons[0][0].text == "Option A"
        assert buttons[1][0].text == "Option B"
        assert buttons[2][0].text == "Option C"

        # Verify Telegram text includes question header and text
        text = format_question_text(content)
        assert "Implementation Strategy" in text
        assert "Which approach should I use?" in text
        assert "respond in CLI" in text

    def test_question_jsonl_to_slack_blocks(
        self,
        question_jsonl_line: dict,
    ) -> None:
        """Full pipeline: JSONL -> Event -> MessageAction -> Slack blocks.

        Verifies that a question JSONL line produces correct Slack Block Kit
        blocks with action buttons.
        """
        # Process through pipeline
        context = ProcessingContext()
        events = process_line(context, question_jsonl_line)

        assert len(events) == 1
        event = events[0]
        assert isinstance(event, AddBlock)

        content = event.block.content
        assert isinstance(content, QuestionContent)

        # Process through MessageStateTracker
        tracker = MessageStateTracker()
        action = tracker.handle_event("test-session", event)

        assert isinstance(action, SendNewMessage)
        # Slack blocks should be present
        assert len(action.blocks) > 0

        # Generate Slack blocks directly for detailed verification
        blocks = format_question_blocks(content)

        # Find section blocks with question text
        section_blocks = [b for b in blocks if b.get("type") == "section"]
        assert len(section_blocks) >= 1

        # First section should contain question header and text
        first_section = section_blocks[0]
        section_text = first_section["text"]["text"]
        assert "Implementation Strategy" in section_text
        assert "Which approach should I use?" in section_text

        # Find actions block with buttons
        actions_blocks = [b for b in blocks if b.get("type") == "actions"]
        assert len(actions_blocks) == 1

        actions = actions_blocks[0]
        elements = actions["elements"]
        assert len(elements) == 3  # 3 option buttons

        # Verify action_id format
        for i, button in enumerate(elements):
            assert button["type"] == "button"
            assert button["action_id"] == f"question_opt_0_{i}"
            assert button["value"] == f"toolu_q123:0:{i}"

        # Verify button labels
        assert elements[0]["text"]["text"] == "Option A"
        assert elements[1]["text"]["text"] == "Option B"
        assert elements[2]["text"]["text"] == "Option C"

        # Check for context block with CLI prompt
        context_blocks = [b for b in blocks if b.get("type") == "context"]
        assert len(context_blocks) >= 1
        cli_prompt = context_blocks[-1]["elements"][0]["text"]
        assert "respond in CLI" in cli_prompt

    def test_answer_updates_remove_keyboard(
        self,
        question_jsonl_line: dict,
        question_answer_jsonl_line: dict,
    ) -> None:
        """Answer event produces UpdateExistingMessage with remove_keyboard flag.

        Verifies that when a question is answered:
        1. The answer JSONL line updates the question state
        2. MessageStateTracker produces UpdateExistingMessage
        3. The metadata includes remove_keyboard flag
        """
        context = ProcessingContext()
        tracker = MessageStateTracker()

        # First, process the question
        question_events = process_line(context, question_jsonl_line)
        assert len(question_events) == 1
        question_action = tracker.handle_event("test-session", question_events[0])

        # Simulate sending the message and recording the ID
        assert isinstance(question_action, SendNewMessage)
        tracker.record_question_message_id(
            "test-session",
            "toolu_q123",
            "telegram",
            "123456789",
            12345,
        )
        tracker.record_question_message_id(
            "test-session",
            "toolu_q123",
            "slack",
            "C123",
            "1234567890.000001",
        )

        # Now process the answer
        answer_events = process_line(context, question_answer_jsonl_line)

        # Should have an UpdateBlock for the question
        question_updates = [
            e for e in answer_events
            if isinstance(e, UpdateBlock) and isinstance(e.content, QuestionContent)
        ]
        assert len(question_updates) == 1

        update_event = question_updates[0]
        assert isinstance(update_event.content, QuestionContent)
        assert update_event.content.answers is not None
        assert update_event.content.answers.get("Which approach should I use?") == "Option B"

        # Process through MessageStateTracker
        update_action = tracker.handle_event("test-session", update_event)

        # Should be an update with remove_keyboard metadata
        assert isinstance(update_action, UpdateExistingMessage)
        assert update_action.metadata.get("answered") is True
        assert update_action.metadata.get("remove_keyboard") is True

        # Verify the content no longer has keyboard
        keyboard = format_question_keyboard(update_event.content)
        assert keyboard is None  # No keyboard for answered questions

        # Verify answered blocks show the selected answer
        answered_blocks = format_answered_question_blocks(update_event.content)
        block_texts = " ".join(
            b["text"]["text"] for b in answered_blocks
            if b.get("type") == "section" and "text" in b.get("text", {})
        )
        assert "Option B" in block_texts

    def test_multiple_questions_single_message(
        self,
        multi_question_jsonl_line: dict,
    ) -> None:
        """Multiple questions render with dividers.

        Verifies that a question block with multiple questions:
        1. Is processed as a single QUESTION block
        2. Produces a single SendNewMessage
        3. Has dividers between questions in Slack blocks
        4. Has all questions in Telegram text
        """
        context = ProcessingContext()
        events = process_line(context, multi_question_jsonl_line)

        assert len(events) == 1
        event = events[0]
        assert isinstance(event, AddBlock)

        content = event.block.content
        assert isinstance(content, QuestionContent)
        assert len(content.questions) == 2

        # Process through MessageStateTracker
        tracker = MessageStateTracker()
        action = tracker.handle_event("test-session", event)

        assert isinstance(action, SendNewMessage)

        # Generate Slack blocks
        blocks = format_question_blocks(content)

        # Should have dividers between questions
        divider_blocks = [b for b in blocks if b.get("type") == "divider"]
        assert len(divider_blocks) >= 1  # At least one divider between 2 questions

        # Should have 2 actions blocks (one per question)
        actions_blocks = [b for b in blocks if b.get("type") == "actions"]
        assert len(actions_blocks) == 2

        # Verify each question has its own action block
        for i, actions in enumerate(actions_blocks):
            # Action IDs should reference the correct question index
            for button in actions["elements"]:
                assert button["action_id"].startswith(f"question_opt_{i}_")

        # Generate Telegram text
        text = format_question_text(content)

        # Should include both questions
        assert "Language Selection" in text
        assert "Which language?" in text
        assert "Framework Selection" in text
        assert "Which framework?" in text

        # Generate Telegram keyboard
        keyboard = format_question_keyboard(content)
        assert keyboard is not None

        # Should have buttons for all options from both questions
        total_options = sum(len(q.options) for q in content.questions)
        assert len(keyboard.inline_keyboard) == total_options

    def test_many_options_truncated(
        self,
        many_options_jsonl_line: dict,
    ) -> None:
        """Options >5 are truncated with overflow message.

        Verifies that when a question has more than MAX_QUESTION_BUTTONS options:
        1. Only the first MAX_QUESTION_BUTTONS are shown as buttons
        2. An overflow message indicates additional options
        3. The overflow count is correct
        """
        context = ProcessingContext()
        events = process_line(context, many_options_jsonl_line)

        assert len(events) == 1
        event = events[0]

        content = event.block.content
        assert isinstance(content, QuestionContent)
        assert len(content.questions[0].options) == 8

        # Telegram keyboard should be truncated
        keyboard = format_question_keyboard(content)
        assert keyboard is not None
        assert len(keyboard.inline_keyboard) == TELEGRAM_MAX_BUTTONS  # 5 buttons max

        # Verify only first 5 options are in keyboard
        for i, row in enumerate(keyboard.inline_keyboard):
            button = row[0]
            assert button.text == f"file{i+1}.py"

        # Telegram text should have overflow notice
        text = format_question_text(content)
        overflow_count = 8 - TELEGRAM_MAX_BUTTONS
        assert f"...and {overflow_count} more option" in text
        assert "in CLI" in text

        # Slack blocks should also be truncated
        blocks = format_question_blocks(content)

        # Actions block should have MAX_QUESTION_BUTTONS buttons
        actions_blocks = [b for b in blocks if b.get("type") == "actions"]
        assert len(actions_blocks) == 1
        assert len(actions_blocks[0]["elements"]) == MAX_QUESTION_BUTTONS

        # Should have context block with overflow notice
        context_blocks = [b for b in blocks if b.get("type") == "context"]
        overflow_texts = [
            b["elements"][0]["text"]
            for b in context_blocks
            if "more option" in b["elements"][0]["text"]
        ]
        assert len(overflow_texts) >= 1
        assert f"{overflow_count} more option" in overflow_texts[0]


# -----------------------------------------------------------------------------
# TestTelegramCallbackE2E
# -----------------------------------------------------------------------------


class TestTelegramCallbackE2E:
    """E2E tests for Telegram callback data format verification."""

    def test_callback_data_format(
        self,
        question_jsonl_line: dict,
    ) -> None:
        """Verify callback_data format "q:{tool_use_id}:{question_idx}:{option_idx}".

        The callback data must follow this exact format for the callback
        handler to correctly identify which option was selected.
        """
        context = ProcessingContext()
        events = process_line(context, question_jsonl_line)

        content = events[0].block.content
        assert isinstance(content, QuestionContent)

        keyboard = format_question_keyboard(content)
        assert keyboard is not None

        # Verify all callback_data strings follow the expected format
        for q_idx, question in enumerate(content.questions):
            for opt_idx, _option in enumerate(question.options[:TELEGRAM_MAX_BUTTONS]):
                expected_callback = f"q:{content.tool_use_id}:{q_idx}:{opt_idx}"

                # Find the button with this callback
                button_row = keyboard.inline_keyboard[q_idx * len(question.options[:TELEGRAM_MAX_BUTTONS]) + opt_idx]
                button = button_row[0]

                assert button.callback_data == expected_callback
                assert button.callback_data.startswith("q:")
                parts = button.callback_data.split(":")
                assert len(parts) == 4
                assert parts[0] == "q"
                assert parts[1] == content.tool_use_id
                assert parts[2] == str(q_idx)
                assert parts[3] == str(opt_idx)

    def test_callback_data_with_multiple_questions(
        self,
        multi_question_jsonl_line: dict,
    ) -> None:
        """Verify callback data correctly indexes multiple questions."""
        context = ProcessingContext()
        events = process_line(context, multi_question_jsonl_line)

        content = events[0].block.content
        assert isinstance(content, QuestionContent)

        keyboard = format_question_keyboard(content)
        assert keyboard is not None

        # Track all callback data strings
        callbacks = []
        for row in keyboard.inline_keyboard:
            callbacks.append(row[0].callback_data)

        # First question (Language) has 2 options: indices 0, 1
        assert callbacks[0] == "q:toolu_multi:0:0"
        assert callbacks[1] == "q:toolu_multi:0:1"

        # Second question (Framework) has 2 options: indices 0, 1
        assert callbacks[2] == "q:toolu_multi:1:0"
        assert callbacks[3] == "q:toolu_multi:1:1"

        # All should be unique
        assert len(callbacks) == len(set(callbacks))


# -----------------------------------------------------------------------------
# TestSlackInteractionE2E
# -----------------------------------------------------------------------------


class TestSlackInteractionE2E:
    """E2E tests for Slack interaction action_id format verification."""

    def test_action_id_format(
        self,
        question_jsonl_line: dict,
    ) -> None:
        """Verify action_id starts with "question_opt_".

        The action_id must follow this format for the interaction handler
        to correctly route button clicks to the question handler.
        """
        context = ProcessingContext()
        events = process_line(context, question_jsonl_line)

        content = events[0].block.content
        assert isinstance(content, QuestionContent)

        blocks = format_question_blocks(content)

        # Find actions block
        actions_blocks = [b for b in blocks if b.get("type") == "actions"]
        assert len(actions_blocks) == 1

        actions = actions_blocks[0]

        # Verify all action_ids follow the expected format
        for i, button in enumerate(actions["elements"]):
            action_id = button["action_id"]
            assert action_id.startswith("question_opt_")
            assert action_id == f"question_opt_0_{i}"

            # Verify value format matches
            value = button["value"]
            assert value == f"toolu_q123:0:{i}"

    def test_action_id_with_multiple_questions(
        self,
        multi_question_jsonl_line: dict,
    ) -> None:
        """Verify action_id correctly indexes multiple questions."""
        context = ProcessingContext()
        events = process_line(context, multi_question_jsonl_line)

        content = events[0].block.content
        assert isinstance(content, QuestionContent)

        blocks = format_question_blocks(content)

        # Find all actions blocks (one per question)
        actions_blocks = [b for b in blocks if b.get("type") == "actions"]
        assert len(actions_blocks) == 2

        # Collect all action IDs
        action_ids = []
        for actions in actions_blocks:
            for button in actions["elements"]:
                action_ids.append(button["action_id"])

        # First question: question_opt_0_0, question_opt_0_1
        assert action_ids[0] == "question_opt_0_0"
        assert action_ids[1] == "question_opt_0_1"

        # Second question: question_opt_1_0, question_opt_1_1
        assert action_ids[2] == "question_opt_1_0"
        assert action_ids[3] == "question_opt_1_1"

        # All should be unique
        assert len(action_ids) == len(set(action_ids))

    def test_block_id_contains_tool_use_id(
        self,
        question_jsonl_line: dict,
    ) -> None:
        """Verify actions block_id contains tool_use_id for state tracking."""
        context = ProcessingContext()
        events = process_line(context, question_jsonl_line)

        content = events[0].block.content
        assert isinstance(content, QuestionContent)

        blocks = format_question_blocks(content)

        # Find actions block
        actions_blocks = [b for b in blocks if b.get("type") == "actions"]
        assert len(actions_blocks) == 1

        block_id = actions_blocks[0]["block_id"]
        assert content.tool_use_id in block_id
        assert block_id.startswith("q_")
