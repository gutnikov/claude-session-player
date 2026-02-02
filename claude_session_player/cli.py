"""CLI entry point for replaying Claude Code sessions."""

from __future__ import annotations

import argparse
import sys

from claude_session_player.models import ScreenState
from claude_session_player.parser import read_session
from claude_session_player.renderer import render


def main(argv: list[str] | None = None) -> None:
    """Replay a Claude Code JSONL session file and print markdown output."""
    parser = argparse.ArgumentParser(
        description="Replay a Claude Code JSONL session as markdown"
    )
    parser.add_argument("session_file", help="Path to JSONL session file")
    parser.add_argument(
        "--step",
        action="store_true",
        help="Print state after each line (step mode)",
    )
    args = parser.parse_args(argv)

    lines = read_session(args.session_file)
    state = ScreenState()

    if args.step:
        for i, line in enumerate(lines):
            state = render(state, line)
            print(f"--- After line {i} ({line.get('type', '?')}) ---")
            print(state.to_markdown())
            print()
    else:
        for line in lines:
            state = render(state, line)
        print(state.to_markdown())


if __name__ == "__main__":
    main()
