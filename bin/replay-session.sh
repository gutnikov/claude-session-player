#!/usr/bin/env bash
set -euo pipefail

# Replay a Claude session file (optionally limiting the number of lines)
# Usage: replay-session.sh <session.jsonl> [num_lines]

if [ $# -lt 1 ]; then
    echo "Usage: $0 <session.jsonl> [num_lines]"
    exit 1
fi

SESSION_FILE="$1"
NUM_LINES="${2:-}"

if [ ! -f "$SESSION_FILE" ]; then
    echo "Error: File not found: $SESSION_FILE"
    exit 1
fi

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if [ -n "$NUM_LINES" ]; then
    head -n "$NUM_LINES" "$SESSION_FILE" | python3 -c "
import sys
sys.path.insert(0, '$REPO_ROOT')
from claude_session_player.models import ScreenState
from claude_session_player.renderer import render
from claude_session_player.formatter import to_markdown

lines = [__import__('json').loads(line) for line in sys.stdin if line.strip()]
state = ScreenState()
for line in lines:
    state = render(state, line)
print(to_markdown(state))
"
else
    python3 -m claude_session_player.cli "$SESSION_FILE"
fi
