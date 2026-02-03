"""Tests for AskUserQuestion tool rendering (Issue #31)."""

from __future__ import annotations

import pytest

from claude_session_player import (
    AddBlock,
    Block,
    BlockType,
    ProcessingContext,
    Question,
    QuestionContent,
    QuestionOption,
    ScreenStateConsumer,
    UpdateBlock,
    process_line,
)
from claude_session_player.consumer import format_question
from claude_session_player.parser import (
    get_ask_user_question_data,
    get_tool_use_result_answers,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def ask_user_question_line() -> dict:
    """AskUserQuestion tool_use message."""
    return {
        "type": "assistant",
        "uuid": "q-001",
        "parentUuid": "aaa-111",
        "requestId": "req_q_001",
        "message": {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": "toolu_q_001",
                    "name": "AskUserQuestion",
                    "input": {
                        "questions": [
                            {
                                "question": "How should we manage dependencies?",
                                "header": "Pkg manager",
                                "options": [
                                    {
                                        "label": "uv (Recommended)",
                                        "description": "Fast, modern Python package manager",
                                    },
                                    {
                                        "label": "poetry",
                                        "description": "Popular dependency management",
                                    },
                                    {
                                        "label": "pip + requirements.txt",
                                        "description": "Simple, classic approach",
                                    },
                                ],
                                "multiSelect": False,
                            }
                        ]
                    },
                }
            ],
        },
    }


@pytest.fixture
def ask_user_question_answer_line() -> dict:
    """Tool result with AskUserQuestion answer."""
    return {
        "type": "user",
        "isMeta": False,
        "uuid": "q-ans-001",
        "parentUuid": "q-001",
        "sessionId": "sess-001",
        "toolUseResult": {
            "questions": [
                {
                    "question": "How should we manage dependencies?",
                    "header": "Pkg manager",
                    "options": [
                        {
                            "label": "uv (Recommended)",
                            "description": "Fast, modern...",
                        },
                    ],
                    "multiSelect": False,
                }
            ],
            "answers": {"How should we manage dependencies?": "uv (Recommended)"},
        },
        "message": {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "toolu_q_001",
                    "content": "User has answered your questions: ...",
                    "is_error": False,
                }
            ],
        },
    }


@pytest.fixture
def multi_question_line() -> dict:
    """AskUserQuestion with multiple questions."""
    return {
        "type": "assistant",
        "uuid": "q-002",
        "parentUuid": "aaa-111",
        "requestId": "req_q_002",
        "message": {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": "toolu_q_002",
                    "name": "AskUserQuestion",
                    "input": {
                        "questions": [
                            {
                                "question": "How should we manage dependencies?",
                                "header": "Pkg manager",
                                "options": [
                                    {"label": "uv", "description": "Fast"},
                                    {"label": "poetry", "description": "Popular"},
                                ],
                                "multiSelect": False,
                            },
                            {
                                "question": "How should the client send messages?",
                                "header": "Approach",
                                "options": [
                                    {
                                        "label": "CLI in tmux (Recommended)",
                                        "description": "Run in terminal",
                                    },
                                    {
                                        "label": "WebSocket",
                                        "description": "Real-time connection",
                                    },
                                ],
                                "multiSelect": False,
                            },
                        ]
                    },
                }
            ],
        },
    }


@pytest.fixture
def multi_question_answer_line() -> dict:
    """Tool result with multiple question answers."""
    return {
        "type": "user",
        "isMeta": False,
        "uuid": "q-ans-002",
        "parentUuid": "q-002",
        "sessionId": "sess-001",
        "toolUseResult": {
            "questions": [],
            "answers": {
                "How should we manage dependencies?": "uv",
                "How should the client send messages?": "CLI in tmux (Recommended)",
            },
        },
        "message": {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "toolu_q_002",
                    "content": "User answered",
                    "is_error": False,
                }
            ],
        },
    }


@pytest.fixture
def multiselect_question_line() -> dict:
    """AskUserQuestion with multiSelect=true."""
    return {
        "type": "assistant",
        "uuid": "q-003",
        "parentUuid": "aaa-111",
        "requestId": "req_q_003",
        "message": {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": "toolu_q_003",
                    "name": "AskUserQuestion",
                    "input": {
                        "questions": [
                            {
                                "question": "Which features do you want?",
                                "header": "Features",
                                "options": [
                                    {"label": "Auth", "description": "Authentication"},
                                    {"label": "Cache", "description": "Caching"},
                                    {"label": "Logging", "description": "Log output"},
                                ],
                                "multiSelect": True,
                            }
                        ]
                    },
                }
            ],
        },
    }


@pytest.fixture
def orphan_answer_line() -> dict:
    """Tool result for AskUserQuestion without matching question block."""
    return {
        "type": "user",
        "isMeta": False,
        "uuid": "orphan-001",
        "parentUuid": "unknown",
        "sessionId": "sess-001",
        "toolUseResult": {
            "questions": [],
            "answers": {"Some question?": "Some answer"},
        },
        "message": {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "toolu_orphan",
                    "content": "User answered orphan question",
                    "is_error": False,
                }
            ],
        },
    }


# ---------------------------------------------------------------------------
# Parser tests
# ---------------------------------------------------------------------------


class TestParserHelpers:
    """Tests for parser extraction helpers."""

    def test_get_ask_user_question_data_returns_questions(
        self, ask_user_question_line: dict
    ) -> None:
        """Should extract questions from AskUserQuestion tool_use."""
        result = get_ask_user_question_data(ask_user_question_line)
        assert result is not None
        assert len(result) == 1
        assert result[0]["question"] == "How should we manage dependencies?"
        assert result[0]["header"] == "Pkg manager"
        assert len(result[0]["options"]) == 3

    def test_get_ask_user_question_data_returns_none_for_other_tools(self) -> None:
        """Should return None for non-AskUserQuestion tools."""
        tool_use_line = {
            "type": "assistant",
            "uuid": "bbb-222",
            "parentUuid": "aaa-111",
            "requestId": "req_001",
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_001",
                        "name": "Bash",
                        "input": {"command": "ls -la"},
                    }
                ],
            },
        }
        result = get_ask_user_question_data(tool_use_line)
        assert result is None

    def test_get_tool_use_result_answers(
        self, ask_user_question_answer_line: dict
    ) -> None:
        """Should extract answers from toolUseResult."""
        result = get_tool_use_result_answers(ask_user_question_answer_line)
        assert result is not None
        assert result["How should we manage dependencies?"] == "uv (Recommended)"

    def test_get_tool_use_result_answers_returns_none_without_answers(self) -> None:
        """Should return None when toolUseResult has no answers."""
        tool_result_line = {
            "type": "user",
            "isMeta": False,
            "uuid": "aaa-300",
            "parentUuid": "bbb-222",
            "sessionId": "sess-001",
            "message": {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_001",
                        "content": "file1.py\nfile2.py",
                        "is_error": False,
                    }
                ],
            },
        }
        result = get_tool_use_result_answers(tool_result_line)
        assert result is None


# ---------------------------------------------------------------------------
# Processor tests
# ---------------------------------------------------------------------------


class TestProcessorAskUserQuestion:
    """Tests for AskUserQuestion event processing."""

    def test_ask_user_question_creates_add_block_question(
        self, ask_user_question_line: dict
    ) -> None:
        """AskUserQuestion tool_use should create AddBlock(QUESTION)."""
        context = ProcessingContext()
        events = process_line(context, ask_user_question_line)

        assert len(events) == 1
        event = events[0]
        assert isinstance(event, AddBlock)
        assert event.block.type == BlockType.QUESTION
        assert isinstance(event.block.content, QuestionContent)

    def test_question_content_has_correct_fields(
        self, ask_user_question_line: dict
    ) -> None:
        """QuestionContent should have correct questions, no answers initially."""
        context = ProcessingContext()
        events = process_line(context, ask_user_question_line)

        content = events[0].block.content
        assert isinstance(content, QuestionContent)
        assert content.tool_use_id == "toolu_q_001"
        assert len(content.questions) == 1
        assert content.answers is None

        q = content.questions[0]
        assert q.question == "How should we manage dependencies?"
        assert q.header == "Pkg manager"
        assert len(q.options) == 3
        assert q.multi_select is False

    def test_question_options_parsed_correctly(
        self, ask_user_question_line: dict
    ) -> None:
        """Question options should be parsed into QuestionOption objects."""
        context = ProcessingContext()
        events = process_line(context, ask_user_question_line)

        content = events[0].block.content
        assert isinstance(content, QuestionContent)
        opts = content.questions[0].options

        assert opts[0].label == "uv (Recommended)"
        assert "Fast" in opts[0].description
        assert opts[1].label == "poetry"
        assert opts[2].label == "pip + requirements.txt"

    def test_answer_updates_question_block(
        self, ask_user_question_line: dict, ask_user_question_answer_line: dict
    ) -> None:
        """Tool result with answers should create UpdateBlock with answers."""
        context = ProcessingContext()

        # First process the question
        events = process_line(context, ask_user_question_line)
        assert len(events) == 1

        # Then process the answer
        events = process_line(context, ask_user_question_answer_line)
        assert len(events) == 1
        event = events[0]

        assert isinstance(event, UpdateBlock)
        assert isinstance(event.content, QuestionContent)
        assert event.content.answers is not None
        assert event.content.answers["How should we manage dependencies?"] == "uv (Recommended)"

    def test_multiple_questions_processed(self, multi_question_line: dict) -> None:
        """AskUserQuestion with multiple questions should parse all."""
        context = ProcessingContext()
        events = process_line(context, multi_question_line)

        content = events[0].block.content
        assert isinstance(content, QuestionContent)
        assert len(content.questions) == 2
        assert content.questions[0].header == "Pkg manager"
        assert content.questions[1].header == "Approach"

    def test_multiselect_question_parsed(self, multiselect_question_line: dict) -> None:
        """multiSelect=true should be preserved in Question."""
        context = ProcessingContext()
        events = process_line(context, multiselect_question_line)

        content = events[0].block.content
        assert isinstance(content, QuestionContent)
        assert content.questions[0].multi_select is True

    def test_orphan_answer_creates_system_block(
        self, orphan_answer_line: dict
    ) -> None:
        """Answer without matching question should create SystemOutput."""
        context = ProcessingContext()
        events = process_line(context, orphan_answer_line)

        assert len(events) == 1
        event = events[0]
        assert isinstance(event, AddBlock)
        assert event.block.type == BlockType.SYSTEM


# ---------------------------------------------------------------------------
# Consumer/Rendering tests
# ---------------------------------------------------------------------------


class TestQuestionRendering:
    """Tests for QuestionContent markdown rendering."""

    def test_format_question_pending_single(self) -> None:
        """Pending question should show options and awaiting response."""
        content = QuestionContent(
            tool_use_id="toolu_001",
            questions=[
                Question(
                    question="How should we manage dependencies?",
                    header="Pkg manager",
                    options=[
                        QuestionOption("uv (Recommended)", "Fast package manager"),
                        QuestionOption("poetry", "Popular choice"),
                        QuestionOption("pip + requirements.txt", "Simple"),
                    ],
                    multi_select=False,
                )
            ],
            answers=None,
        )

        result = format_question(content)

        assert "● Question: Pkg manager" in result
        assert "├ How should we manage dependencies?" in result
        assert "│ ○ uv (Recommended)" in result
        assert "│ ○ poetry" in result
        assert "│ ○ pip + requirements.txt" in result
        assert "└ (awaiting response)" in result

    def test_format_question_answered_single(self) -> None:
        """Answered question should show checkmark and answer."""
        content = QuestionContent(
            tool_use_id="toolu_001",
            questions=[
                Question(
                    question="How should we manage dependencies?",
                    header="Pkg manager",
                    options=[
                        QuestionOption("uv (Recommended)", "Fast"),
                        QuestionOption("poetry", "Popular"),
                    ],
                    multi_select=False,
                )
            ],
            answers={"How should we manage dependencies?": "uv (Recommended)"},
        )

        result = format_question(content)

        assert "● Question: Pkg manager" in result
        assert "├ How should we manage dependencies?" in result
        assert "└ ✓ uv (Recommended)" in result
        # Should not show options when answered
        assert "○" not in result
        assert "(awaiting response)" not in result

    def test_format_question_multiple_questions(self) -> None:
        """Multiple questions should render as separate blocks."""
        content = QuestionContent(
            tool_use_id="toolu_002",
            questions=[
                Question(
                    question="Q1?",
                    header="First",
                    options=[QuestionOption("A", "desc")],
                    multi_select=False,
                ),
                Question(
                    question="Q2?",
                    header="Second",
                    options=[QuestionOption("B", "desc")],
                    multi_select=False,
                ),
            ],
            answers={"Q1?": "A", "Q2?": "B"},
        )

        result = format_question(content)

        assert "● Question: First" in result
        assert "● Question: Second" in result
        assert "├ Q1?" in result
        assert "├ Q2?" in result
        assert "└ ✓ A" in result
        assert "└ ✓ B" in result

    def test_format_question_empty_header_defaults(self) -> None:
        """Empty header should default to 'Question'."""
        content = QuestionContent(
            tool_use_id="toolu_003",
            questions=[
                Question(
                    question="Test?",
                    header="",
                    options=[QuestionOption("Yes", "y")],
                    multi_select=False,
                )
            ],
            answers=None,
        )

        result = format_question(content)
        assert "● Question: Question" in result


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------


class TestQuestionIntegration:
    """Integration tests for full question flow."""

    def test_full_flow_question_and_answer(
        self, ask_user_question_line: dict, ask_user_question_answer_line: dict
    ) -> None:
        """Full flow: question → answer should render correctly."""
        context = ProcessingContext()
        consumer = ScreenStateConsumer()

        # Process question
        for event in process_line(context, ask_user_question_line):
            consumer.handle(event)

        # Check pending state
        md = consumer.to_markdown()
        assert "● Question: Pkg manager" in md
        assert "(awaiting response)" in md

        # Process answer
        for event in process_line(context, ask_user_question_answer_line):
            consumer.handle(event)

        # Check answered state
        md = consumer.to_markdown()
        assert "● Question: Pkg manager" in md
        assert "✓ uv (Recommended)" in md
        assert "(awaiting response)" not in md

    def test_multiple_questions_answered(
        self, multi_question_line: dict, multi_question_answer_line: dict
    ) -> None:
        """Multiple questions should all be answered."""
        context = ProcessingContext()
        consumer = ScreenStateConsumer()

        for event in process_line(context, multi_question_line):
            consumer.handle(event)
        for event in process_line(context, multi_question_answer_line):
            consumer.handle(event)

        md = consumer.to_markdown()
        assert "● Question: Pkg manager" in md
        assert "● Question: Approach" in md
        assert "✓ uv" in md
        assert "✓ CLI in tmux (Recommended)" in md

    def test_question_with_other_blocks(
        self, ask_user_question_line: dict
    ) -> None:
        """Questions should render correctly mixed with other blocks."""
        context = ProcessingContext()
        consumer = ScreenStateConsumer()

        user_input_line = {
            "type": "user",
            "isMeta": False,
            "uuid": "aaa-111",
            "parentUuid": None,
            "sessionId": "sess-001",
            "message": {"role": "user", "content": "hello world"},
        }

        for event in process_line(context, user_input_line):
            consumer.handle(event)
        for event in process_line(context, ask_user_question_line):
            consumer.handle(event)

        md = consumer.to_markdown()
        # User message comes first
        assert md.startswith("❯ hello world")
        # Then question block
        assert "● Question: Pkg manager" in md


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestQuestionEdgeCases:
    """Edge case tests for AskUserQuestion handling."""

    def test_question_with_no_options(self) -> None:
        """Question with no options should still render."""
        content = QuestionContent(
            tool_use_id="toolu_edge",
            questions=[
                Question(
                    question="Open-ended question?",
                    header="Input",
                    options=[],
                    multi_select=False,
                )
            ],
            answers=None,
        )

        result = format_question(content)
        assert "● Question: Input" in result
        assert "├ Open-ended question?" in result
        assert "└ (awaiting response)" in result

    def test_question_partial_answers(self) -> None:
        """Some questions answered, some pending."""
        content = QuestionContent(
            tool_use_id="toolu_partial",
            questions=[
                Question(
                    question="Q1?",
                    header="First",
                    options=[QuestionOption("A", "a")],
                    multi_select=False,
                ),
                Question(
                    question="Q2?",
                    header="Second",
                    options=[QuestionOption("B", "b")],
                    multi_select=False,
                ),
            ],
            answers={"Q1?": "A"},  # Only Q1 answered
        )

        result = format_question(content)
        # Q1 should show answer
        assert "✓ A" in result
        # Q2 should show options and awaiting
        assert "○ B" in result
        assert "(awaiting response)" in result

    def test_long_option_description_truncation(self) -> None:
        """Long option labels should not be truncated in current impl."""
        long_label = "A" * 100
        content = QuestionContent(
            tool_use_id="toolu_long",
            questions=[
                Question(
                    question="Pick one?",
                    header="Long",
                    options=[QuestionOption(long_label, "description")],
                    multi_select=False,
                )
            ],
            answers=None,
        )

        result = format_question(content)
        # Currently labels are not truncated
        assert long_label in result
