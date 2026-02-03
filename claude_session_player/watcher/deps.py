"""Dependency availability checks for optional messaging integrations."""

from __future__ import annotations


def check_telegram_available() -> bool:
    """Check if aiogram is installed."""
    try:
        import aiogram  # noqa: F401

        return True
    except ImportError:
        return False


def check_slack_available() -> bool:
    """Check if slack-sdk is installed."""
    try:
        import slack_sdk  # noqa: F401

        return True
    except ImportError:
        return False
