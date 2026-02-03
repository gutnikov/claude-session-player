#!/usr/bin/env python3
"""CLI entry point for Claude Session Player.

Replay a Claude Code session as ASCII terminal output (markdown format).
Also provides index management commands for the session search index.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from .consumer import replay_session
from .parser import read_session

if TYPE_CHECKING:
    from .watcher.search_db import SearchDatabase
    from .watcher.indexer import SQLiteSessionIndexer


# ---------------------------------------------------------------------------
# Default Configuration
# ---------------------------------------------------------------------------

DEFAULT_PATHS = [Path("~/.claude/projects").expanduser()]
DEFAULT_STATE_DIR = Path("~/.claude-session-player/state").expanduser()


# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------


def _format_size(size_bytes: int) -> str:
    """Format byte size as human-readable string."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / 1024 / 1024:.1f} MB"
    else:
        return f"{size_bytes / 1024 / 1024 / 1024:.1f} GB"


def _format_duration(duration_ms: int | None) -> str:
    """Format duration in milliseconds as human-readable string."""
    if duration_ms is None:
        return "N/A"
    seconds = duration_ms // 1000
    if seconds < 60:
        return f"{seconds}s"
    minutes = seconds // 60
    remaining_seconds = seconds % 60
    if minutes < 60:
        return f"{minutes}m {remaining_seconds}s" if remaining_seconds else f"{minutes}m"
    hours = minutes // 60
    remaining_minutes = minutes % 60
    return f"{hours}h {remaining_minutes}m"


def _format_datetime(dt_str: str | None) -> str:
    """Format ISO datetime string as human-readable."""
    if not dt_str:
        return "Never"
    try:
        dt = datetime.fromisoformat(dt_str)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return dt_str


def _get_db_size(state_dir: Path) -> int:
    """Get the database file size in bytes."""
    db_path = state_dir / "search.db"
    if db_path.exists():
        return db_path.stat().st_size
    return 0


# ---------------------------------------------------------------------------
# Index Command Implementations
# ---------------------------------------------------------------------------


async def _rebuild(paths: list[Path], state_dir: Path) -> int:
    """Rebuild the search index from scratch."""
    from .watcher.indexer import SQLiteSessionIndexer, IndexConfig

    indexer = SQLiteSessionIndexer(
        paths=paths,
        state_dir=state_dir,
        config=IndexConfig(),
    )

    try:
        await indexer.initialize()
        print("Rebuilding search index...")
        count = await indexer.build_full_index()
        print(f"Indexed {count} sessions")
        return 0
    except Exception as e:
        print(f"Error rebuilding index: {e}", file=sys.stderr)
        return 1
    finally:
        await indexer.close()


async def _update(paths: list[Path], state_dir: Path) -> int:
    """Incremental update of the search index."""
    from .watcher.indexer import SQLiteSessionIndexer, IndexConfig

    indexer = SQLiteSessionIndexer(
        paths=paths,
        state_dir=state_dir,
        config=IndexConfig(),
    )

    try:
        await indexer.initialize()
        print("Updating search index...")
        added, updated, removed = await indexer.incremental_update()
        print(f"Added: {added}, Updated: {updated}, Removed: {removed}")
        return 0
    except Exception as e:
        print(f"Error updating index: {e}", file=sys.stderr)
        return 1
    finally:
        await indexer.close()


async def _stats(state_dir: Path) -> int:
    """Show index statistics."""
    from .watcher.search_db import SearchDatabase

    db = SearchDatabase(state_dir)

    try:
        await db.initialize()
        stats = await db.get_stats()

        db_size = _get_db_size(state_dir)

        print("Search Index Statistics")
        print("=" * 50)
        print(f"Sessions indexed: {stats['total_sessions']}")
        print(f"Projects: {stats['total_projects']}")
        print(f"Total size: {_format_size(stats['total_size_bytes'])}")
        print(f"FTS5 available: {'Yes' if stats['fts_available'] else 'No'}")
        print(f"Last full index: {_format_datetime(stats['last_full_index'])}")
        print(f"Last incremental: {_format_datetime(stats['last_incremental_index'])}")
        print(f"Database size: {_format_size(db_size)}")
        return 0
    except Exception as e:
        print(f"Error getting stats: {e}", file=sys.stderr)
        return 1
    finally:
        await db.close()


async def _verify(state_dir: Path) -> int:
    """Verify database integrity."""
    from .watcher.search_db import SearchDatabase

    db = SearchDatabase(state_dir)

    try:
        await db.initialize()
        print("Verifying database integrity...")
        is_valid = await db.verify_integrity()
        if is_valid:
            print("Database integrity check passed")
            return 0
        else:
            print("Database integrity check FAILED", file=sys.stderr)
            return 1
    except Exception as e:
        print(f"Error verifying database: {e}", file=sys.stderr)
        return 1
    finally:
        await db.close()


async def _vacuum(state_dir: Path) -> int:
    """Reclaim disk space."""
    from .watcher.search_db import SearchDatabase

    db = SearchDatabase(state_dir)

    try:
        await db.initialize()
        size_before = _get_db_size(state_dir)
        print("Running vacuum...")
        await db.vacuum()
        await db.checkpoint()
        size_after = _get_db_size(state_dir)
        saved = size_before - size_after
        print(f"Vacuum complete. Size: {_format_size(size_before)} -> {_format_size(size_after)}")
        if saved > 0:
            print(f"Reclaimed: {_format_size(saved)}")
        return 0
    except Exception as e:
        print(f"Error running vacuum: {e}", file=sys.stderr)
        return 1
    finally:
        await db.close()


async def _backup(output: Path, state_dir: Path) -> int:
    """Backup the search database."""
    from .watcher.search_db import SearchDatabase

    db = SearchDatabase(state_dir)

    try:
        await db.initialize()
        print(f"Backing up database to {output}...")
        await db.backup(output)
        size = output.stat().st_size
        print(f"Backup complete: {_format_size(size)}")
        return 0
    except Exception as e:
        print(f"Error creating backup: {e}", file=sys.stderr)
        return 1
    finally:
        await db.close()


async def _search(
    query: str,
    project: str | None,
    limit: int,
    state_dir: Path,
) -> int:
    """Search the index (for debugging)."""
    from .watcher.search_db import SearchDatabase, SearchFilters

    db = SearchDatabase(state_dir)

    try:
        await db.initialize()
        filters = SearchFilters(query=query, project=project)
        results, total = await db.search_ranked(filters, limit=limit)

        if not results:
            print(f'No results found for "{query}"')
            return 0

        print(f'Search results for "{query}" ({total} matches)')
        print()

        for i, result in enumerate(results, 1):
            session = result.session
            summary = session.summary or "(no summary)"
            if len(summary) > 60:
                summary = summary[:57] + "..."

            # Format date
            date_str = session.file_modified_at.strftime("%b %d, %Y")

            # Format size
            size_str = _format_size(session.size_bytes)

            # Format duration
            duration_str = _format_duration(session.duration_ms)

            print(f"{i}. {session.project_display_name}: {summary}")
            print(f"   \U0001F4C5 {date_str} \u2022 \U0001F4C4 {size_str} \u2022 \u23F1 {duration_str}")
            print(f"   Score: {result.score:.1f}")
            print()

        return 0
    except Exception as e:
        print(f"Error searching: {e}", file=sys.stderr)
        return 1
    finally:
        await db.close()


# ---------------------------------------------------------------------------
# CLI Argument Parsing
# ---------------------------------------------------------------------------


def _create_parser() -> argparse.ArgumentParser:
    """Create the argument parser."""
    parser = argparse.ArgumentParser(
        prog="claude-session-player",
        description="Replay Claude Code sessions as readable markdown output.",
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Replay command (default behavior when a file is passed)
    replay_parser = subparsers.add_parser(
        "replay",
        help="Replay a session file as markdown",
    )
    replay_parser.add_argument(
        "session_file",
        type=str,
        help="Path to session JSONL file",
    )

    # Index command group
    index_parser = subparsers.add_parser(
        "index",
        help="Manage the session search index",
    )
    index_subparsers = index_parser.add_subparsers(dest="index_command", help="Index commands")

    # Common options for index commands
    def add_common_options(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "--state-dir",
            type=Path,
            default=None,
            help=f"State directory (default: {DEFAULT_STATE_DIR})",
        )

    def add_paths_option(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "--paths",
            type=Path,
            nargs="*",
            default=None,
            help=f"Paths to scan (default: {DEFAULT_PATHS[0]})",
        )

    # index rebuild
    rebuild_parser = index_subparsers.add_parser(
        "rebuild",
        help="Rebuild the search index from scratch",
    )
    add_paths_option(rebuild_parser)
    add_common_options(rebuild_parser)

    # index update
    update_parser = index_subparsers.add_parser(
        "update",
        help="Incremental update of the search index",
    )
    add_paths_option(update_parser)
    add_common_options(update_parser)

    # index stats
    stats_parser = index_subparsers.add_parser(
        "stats",
        help="Show index statistics",
    )
    add_common_options(stats_parser)

    # index verify
    verify_parser = index_subparsers.add_parser(
        "verify",
        help="Verify database integrity",
    )
    add_common_options(verify_parser)

    # index vacuum
    vacuum_parser = index_subparsers.add_parser(
        "vacuum",
        help="Reclaim disk space",
    )
    add_common_options(vacuum_parser)

    # index backup
    backup_parser = index_subparsers.add_parser(
        "backup",
        help="Backup the search database",
    )
    backup_parser.add_argument(
        "-o",
        "--output",
        type=Path,
        required=True,
        help="Output path for backup",
    )
    add_common_options(backup_parser)

    # index search
    search_parser = index_subparsers.add_parser(
        "search",
        help="Search the index (for debugging)",
    )
    search_parser.add_argument(
        "query",
        type=str,
        help="Search query",
    )
    search_parser.add_argument(
        "-p",
        "--project",
        type=str,
        default=None,
        help="Filter by project",
    )
    search_parser.add_argument(
        "-l",
        "--limit",
        type=int,
        default=10,
        help="Max results (default: 10)",
    )
    add_common_options(search_parser)

    return parser


def _handle_index_command(args: argparse.Namespace) -> int:
    """Handle index subcommands."""
    if not args.index_command:
        print("Usage: claude-session-player index <command>", file=sys.stderr)
        print("Commands: rebuild, update, stats, verify, vacuum, backup, search", file=sys.stderr)
        return 1

    state_dir = getattr(args, "state_dir", None) or DEFAULT_STATE_DIR
    paths = getattr(args, "paths", None) or DEFAULT_PATHS

    if args.index_command == "rebuild":
        return asyncio.run(_rebuild(paths, state_dir))
    elif args.index_command == "update":
        return asyncio.run(_update(paths, state_dir))
    elif args.index_command == "stats":
        return asyncio.run(_stats(state_dir))
    elif args.index_command == "verify":
        return asyncio.run(_verify(state_dir))
    elif args.index_command == "vacuum":
        return asyncio.run(_vacuum(state_dir))
    elif args.index_command == "backup":
        return asyncio.run(_backup(args.output, state_dir))
    elif args.index_command == "search":
        return asyncio.run(_search(args.query, args.project, args.limit, state_dir))
    else:
        print("Usage: claude-session-player index <command>", file=sys.stderr)
        print("Commands: rebuild, update, stats, verify, vacuum, backup, search", file=sys.stderr)
        return 1


# ---------------------------------------------------------------------------
# Main Entry Point
# ---------------------------------------------------------------------------


def main() -> None:
    """Run the Claude Session Player CLI.

    Usage:
        claude-session-player <session.jsonl>       # Replay a session
        claude-session-player replay <session.jsonl>  # Explicit replay
        claude-session-player index <command>       # Index management
    """
    # Handle legacy usage: claude-session-player <file>
    if len(sys.argv) == 2 and not sys.argv[1].startswith("-"):
        # Check if it's a file path (not a command)
        arg = sys.argv[1]
        if arg not in ("replay", "index", "-h", "--help"):
            # Legacy mode: replay the file directly
            path = arg
            if not Path(path).exists():
                print(f"Error: File not found: {path}", file=sys.stderr)
                sys.exit(1)
            lines = read_session(path)
            print(replay_session(lines))
            return

    parser = _create_parser()
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    if args.command == "replay":
        path = args.session_file
        if not Path(path).exists():
            print(f"Error: File not found: {path}", file=sys.stderr)
            sys.exit(1)
        lines = read_session(path)
        print(replay_session(lines))
    elif args.command == "index":
        sys.exit(_handle_index_command(args))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
