#!/usr/bin/env python3
"""Watch a JSONL session file and render it to a markdown file in real-time.

Usage: watch-session.py <input.jsonl> <output.md>

The script:
1. Processes all existing lines in the JSONL file
2. Writes initial markdown to the output file
3. Watches for new lines being appended to the JSONL file
4. On each change, re-renders the full markdown and updates the output file
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

# Add the project root to sys.path for imports when running directly
script_dir = Path(__file__).parent.resolve()
project_root = script_dir.parent
sys.path.insert(0, str(project_root))

from claude_session_player.consumer import ScreenStateConsumer
from claude_session_player.events import ProcessingContext
from claude_session_player.processor import process_line
from claude_session_player.watcher.file_watcher import IncrementalReader

from watchfiles import awatch

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class SessionWatcher:
    """Watches a JSONL session file and renders to markdown on changes."""

    def __init__(self, input_path: Path, output_path: Path) -> None:
        self.input_path = input_path
        self.output_path = output_path
        self.reader = IncrementalReader(path=input_path)
        self.context = ProcessingContext()
        self.consumer = ScreenStateConsumer()
        self._stop_event = asyncio.Event()

    def _process_lines(self, lines: list[dict]) -> None:
        """Process a list of JSONL lines through the event pipeline."""
        for line in lines:
            events = process_line(self.context, line)
            for event in events:
                self.consumer.handle(event)

    def _write_markdown(self) -> None:
        """Write the current markdown state to the output file."""
        markdown = self.consumer.to_markdown()
        self.output_path.write_text(markdown, encoding="utf-8")
        logger.info(
            "wrote_markdown",
            extra={
                "output_path": str(self.output_path),
                "block_count": len(self.consumer.blocks),
            },
        )

    async def run(self) -> None:
        """Run the watcher loop."""
        # Step 1: Process all existing lines
        logger.info(
            "processing_initial_lines",
            extra={"input_path": str(self.input_path)},
        )
        lines, _ = self.reader.read_new_lines()
        if lines:
            self._process_lines(lines)
            logger.info(
                "processed_initial_lines",
                extra={"line_count": len(lines)},
            )

        # Step 2: Write initial markdown
        self._write_markdown()

        # Step 3: Watch for changes
        logger.info(
            "watching_for_changes",
            extra={"input_path": str(self.input_path)},
        )

        try:
            async for _changes in awatch(
                self.input_path.parent,
                stop_event=self._stop_event,
                debounce=100,
                recursive=False,
            ):
                # Check if our specific file was modified
                new_lines, _ = self.reader.read_new_lines()
                if new_lines:
                    logger.info(
                        "detected_new_lines",
                        extra={"line_count": len(new_lines)},
                    )
                    self._process_lines(new_lines)
                    self._write_markdown()

        except asyncio.CancelledError:
            logger.info("watcher_cancelled")
            raise

    def stop(self) -> None:
        """Signal the watcher to stop."""
        self._stop_event.set()


async def main(input_path: Path, output_path: Path) -> None:
    """Main entry point for the watcher."""
    if not input_path.exists():
        logger.error(
            "input_file_not_found",
            extra={"input_path": str(input_path)},
        )
        sys.exit(1)

    watcher = SessionWatcher(input_path, output_path)

    try:
        await watcher.run()
    except KeyboardInterrupt:
        logger.info("received_keyboard_interrupt")
        watcher.stop()


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: watch-session.py <input.jsonl> <output.md>", file=sys.stderr)
        sys.exit(1)

    input_path = Path(sys.argv[1]).resolve()
    output_path = Path(sys.argv[2]).resolve()

    asyncio.run(main(input_path, output_path))
