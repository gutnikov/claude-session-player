"""JSONL session file reading and parsing."""

from __future__ import annotations

import json


def read_session(path: str) -> list[dict]:
    """Read a JSONL file and return list of parsed dicts.

    Each non-empty line is parsed as a JSON object. Blank lines and
    malformed lines are skipped.
    """
    lines: list[dict] = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                parsed = json.loads(line)
                if isinstance(parsed, dict):
                    lines.append(parsed)
            except json.JSONDecodeError:
                continue
    return lines
