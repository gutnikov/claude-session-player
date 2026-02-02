"""JSONL session file parsing."""

from pathlib import Path
from typing import Iterator


def read_session(path: Path) -> Iterator[dict]:
    """Read and parse a JSONL session file line by line.

    Args:
        path: Path to the JSONL session file.

    Yields:
        Parsed dict for each JSONL line.
    """
    raise NotImplementedError("Implemented in issue 05")
