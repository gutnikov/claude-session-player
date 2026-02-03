#!/usr/bin/env python3
"""CLI entry point for Claude Session Player.

Replay a Claude Code session as ASCII terminal output (markdown format).
"""

from __future__ import annotations

import sys
from pathlib import Path

from .models import ScreenState
from .parser import read_session
from .renderer import render


def main() -> None:
    """Run the Claude Session Player CLI.

    Usage: claude-session-player <session.jsonl>

    Reads the JSONL session file, processes all lines through the render
    function, and prints the final markdown output to stdout.
    """
    if len(sys.argv) != 2:
        print("Usage: claude-session-player <session.jsonl>", file=sys.stderr)
        sys.exit(1)

    path = sys.argv[1]

    if not Path(path).exists():
        print(f"Error: File not found: {path}", file=sys.stderr)
        sys.exit(1)

    lines = read_session(path)
    state = ScreenState()
    for line in lines:
        render(state, line)
    print(state.to_markdown())


if __name__ == "__main__":
    main()
