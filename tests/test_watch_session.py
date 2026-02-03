"""Tests for the watch-session.py script."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

# Add the bin directory to path to import watch-session
bin_dir = Path(__file__).parent.parent / "bin"
sys.path.insert(0, str(bin_dir))


class TestSessionWatcher:
    """Tests for SessionWatcher class."""

    @pytest.fixture
    def temp_files(self, tmp_path: Path) -> tuple[Path, Path]:
        """Create temporary input and output files."""
        input_path = tmp_path / "session.jsonl"
        output_path = tmp_path / "output.md"
        return input_path, output_path

    @pytest.fixture
    def sample_user_line(self) -> dict:
        """A sample user input JSONL line."""
        return {
            "type": "user",
            "message": {"content": "Hello, Claude", "role": "user"},
        }

    @pytest.fixture
    def sample_assistant_line(self) -> dict:
        """A sample assistant response JSONL line."""
        return {
            "type": "assistant",
            "message": {
                "content": [{"type": "text", "text": "Hi there!"}],
                "role": "assistant",
            },
            "requestId": "req-123",
        }

    def test_initial_processing(
        self,
        temp_files: tuple[Path, Path],
        sample_user_line: dict,
        sample_assistant_line: dict,
    ) -> None:
        """Test that initial lines are processed and markdown is written."""
        # Import here to avoid issues with module loading
        from importlib.util import module_from_spec, spec_from_file_location

        spec = spec_from_file_location(
            "watch_session", bin_dir / "watch-session.py"
        )
        assert spec is not None
        assert spec.loader is not None
        watch_session = module_from_spec(spec)
        spec.loader.exec_module(watch_session)

        input_path, output_path = temp_files

        # Write initial content to JSONL
        with input_path.open("w") as f:
            f.write(json.dumps(sample_user_line) + "\n")
            f.write(json.dumps(sample_assistant_line) + "\n")

        # Create watcher and process initial lines (without starting the watch loop)
        watcher = watch_session.SessionWatcher(input_path, output_path)

        # Process initial lines manually
        lines, _ = watcher.reader.read_new_lines()
        watcher._process_lines(lines)
        watcher._write_markdown()

        # Verify output was written
        assert output_path.exists()
        content = output_path.read_text()
        assert "Hello, Claude" in content
        assert "Hi there!" in content

    @pytest.mark.asyncio
    async def test_watcher_detects_appended_line(
        self,
        temp_files: tuple[Path, Path],
        sample_user_line: dict,
        sample_assistant_line: dict,
    ) -> None:
        """Test that watcher detects and processes appended lines."""
        from importlib.util import module_from_spec, spec_from_file_location

        spec = spec_from_file_location(
            "watch_session", bin_dir / "watch-session.py"
        )
        assert spec is not None
        assert spec.loader is not None
        watch_session = module_from_spec(spec)
        spec.loader.exec_module(watch_session)

        input_path, output_path = temp_files

        # Write initial content
        with input_path.open("w") as f:
            f.write(json.dumps(sample_user_line) + "\n")

        # Create watcher
        watcher = watch_session.SessionWatcher(input_path, output_path)

        # Start watcher in background
        watcher_task = asyncio.create_task(watcher.run())

        # Give watcher time to start and process initial content
        await asyncio.sleep(0.2)

        # Verify initial content was processed
        assert output_path.exists()
        initial_content = output_path.read_text()
        assert "Hello, Claude" in initial_content
        assert "Hi there!" not in initial_content

        # Append a new line
        with input_path.open("a") as f:
            f.write(json.dumps(sample_assistant_line) + "\n")

        # Give watcher time to detect and process the change
        await asyncio.sleep(0.3)

        # Verify updated content
        updated_content = output_path.read_text()
        assert "Hello, Claude" in updated_content
        assert "Hi there!" in updated_content

        # Stop watcher
        watcher.stop()
        watcher_task.cancel()
        try:
            await watcher_task
        except asyncio.CancelledError:
            pass

    def test_empty_file_produces_empty_output(
        self, temp_files: tuple[Path, Path]
    ) -> None:
        """Test that an empty JSONL file produces empty markdown."""
        from importlib.util import module_from_spec, spec_from_file_location

        spec = spec_from_file_location(
            "watch_session", bin_dir / "watch-session.py"
        )
        assert spec is not None
        assert spec.loader is not None
        watch_session = module_from_spec(spec)
        spec.loader.exec_module(watch_session)

        input_path, output_path = temp_files

        # Create empty file
        input_path.touch()

        watcher = watch_session.SessionWatcher(input_path, output_path)
        lines, _ = watcher.reader.read_new_lines()
        watcher._process_lines(lines)
        watcher._write_markdown()

        assert output_path.exists()
        assert output_path.read_text() == ""

    def test_tool_call_and_result(self, temp_files: tuple[Path, Path]) -> None:
        """Test that tool calls and results are properly rendered."""
        from importlib.util import module_from_spec, spec_from_file_location

        spec = spec_from_file_location(
            "watch_session", bin_dir / "watch-session.py"
        )
        assert spec is not None
        assert spec.loader is not None
        watch_session = module_from_spec(spec)
        spec.loader.exec_module(watch_session)

        input_path, output_path = temp_files

        tool_call = {
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "id": "tool-abc",
                        "name": "Read",
                        "input": {"file_path": "/test/file.txt"},
                    }
                ],
                "role": "assistant",
            },
            "requestId": "req-456",
        }

        tool_result = {
            "type": "user",
            "message": {
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "tool-abc",
                        "content": "File contents here",
                    }
                ],
                "role": "user",
            },
        }

        with input_path.open("w") as f:
            f.write(json.dumps(tool_call) + "\n")
            f.write(json.dumps(tool_result) + "\n")

        watcher = watch_session.SessionWatcher(input_path, output_path)
        lines, _ = watcher.reader.read_new_lines()
        watcher._process_lines(lines)
        watcher._write_markdown()

        content = output_path.read_text()
        assert "Read(file.txt)" in content
        assert "File contents here" in content
