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
import json
sys.path.insert(0, '$REPO_ROOT')
from claude_session_player.consumer import replay_session

lines = [json.loads(line) for line in sys.stdin if line.strip()]
print(replay_session(lines))
"
else
    python3 -m claude_session_player.cli "$SESSION_FILE"
fi
