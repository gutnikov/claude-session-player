"""CLI entry point for running the watcher service.

Usage:
    python -m claude_session_player.watcher [options]

Options:
    --host HOST          Host to bind to (default: 127.0.0.1)
    --port PORT          Port to bind to (default: 8080)
    --config PATH        Path to config.yaml (default: ./config.yaml)
    --state-dir PATH     Path to state directory (default: ./state)
    --log-level LEVEL    Log level (default: INFO)
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys
from pathlib import Path

from claude_session_player.watcher.service import WatcherService


def parse_args(args: list[str] | None = None) -> argparse.Namespace:
    """Parse command line arguments.

    Args:
        args: Command line arguments (defaults to sys.argv[1:]).

    Returns:
        Parsed arguments namespace.
    """
    parser = argparse.ArgumentParser(
        description="Claude Session Player - Watcher Service",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Start with defaults
    python -m claude_session_player.watcher

    # Specify config and state directories
    python -m claude_session_player.watcher --config /etc/watcher/config.yaml --state-dir /var/lib/watcher/state

    # Bind to all interfaces on port 9000
    python -m claude_session_player.watcher --host 0.0.0.0 --port 9000
""",
    )

    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Host to bind to (default: 127.0.0.1)",
    )

    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Port to bind to (default: 8080)",
    )

    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config.yaml"),
        help="Path to config.yaml (default: ./config.yaml)",
    )

    parser.add_argument(
        "--state-dir",
        type=Path,
        default=Path("state"),
        help="Path to state directory (default: ./state)",
    )

    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Log level (default: INFO)",
    )

    return parser.parse_args(args)


def setup_logging(level: str) -> None:
    """Configure logging.

    Args:
        level: Log level name (DEBUG, INFO, WARNING, ERROR, CRITICAL).
    """
    logging.basicConfig(
        level=getattr(logging, level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


async def run_service(service: WatcherService, shutdown_event: asyncio.Event) -> None:
    """Run the service until shutdown event is set.

    Args:
        service: The WatcherService instance.
        shutdown_event: Event to signal shutdown.
    """
    await service.start()

    try:
        # Wait for shutdown signal
        await shutdown_event.wait()
    finally:
        await service.stop()


def main(args: list[str] | None = None) -> int:
    """Main entry point.

    Args:
        args: Command line arguments (defaults to sys.argv[1:]).

    Returns:
        Exit code (0 for success, non-zero for error).
    """
    parsed = parse_args(args)
    setup_logging(parsed.log_level)

    logger = logging.getLogger(__name__)

    # Create shutdown event
    shutdown_event = asyncio.Event()

    # Create service
    service = WatcherService(
        config_path=parsed.config.absolute(),
        state_dir=parsed.state_dir.absolute(),
        host=parsed.host,
        port=parsed.port,
    )

    # Set up signal handlers
    def signal_handler(signum: int, frame: object) -> None:
        sig_name = signal.Signals(signum).name
        logger.info(f"Received {sig_name}, initiating shutdown...")
        shutdown_event.set()

    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    logger.info(f"Config path: {parsed.config.absolute()}")
    logger.info(f"State directory: {parsed.state_dir.absolute()}")
    logger.info(f"Server will listen on http://{parsed.host}:{parsed.port}")

    try:
        asyncio.run(run_service(service, shutdown_event))
        return 0
    except Exception as e:
        logger.error(f"Service error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
