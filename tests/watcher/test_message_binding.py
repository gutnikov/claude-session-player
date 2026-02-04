"""Tests for MessageBinding and MessageBindingManager."""

from __future__ import annotations

from datetime import datetime

import pytest

from claude_session_player.watcher.destinations import AttachedDestination
from claude_session_player.watcher.message_binding import (
    MessageBinding,
    MessageBindingManager,
    Preset,
)


# ---------------------------------------------------------------------------
# MessageBinding tests
# ---------------------------------------------------------------------------


class TestMessageBinding:
    """Tests for MessageBinding dataclass."""

    def test_create_telegram_binding(self) -> None:
        """Can create binding for telegram destination."""
        now = datetime.now()
        dest = AttachedDestination(
            type="telegram", identifier="123456789", attached_at=now
        )
        binding = MessageBinding(
            session_id="test-session",
            preset="desktop",
            destination=dest,
            message_id="999",
        )
        assert binding.session_id == "test-session"
        assert binding.preset == "desktop"
        assert binding.destination.type == "telegram"
        assert binding.destination.identifier == "123456789"
        assert binding.message_id == "999"
        assert binding.last_content == ""  # Default

    def test_create_slack_binding(self) -> None:
        """Can create binding for slack destination."""
        now = datetime.now()
        dest = AttachedDestination(
            type="slack", identifier="C0123456789", attached_at=now
        )
        binding = MessageBinding(
            session_id="test-session",
            preset="mobile",
            destination=dest,
            message_id="1234567890.123456",
            last_content="initial content",
        )
        assert binding.session_id == "test-session"
        assert binding.preset == "mobile"
        assert binding.destination.type == "slack"
        assert binding.destination.identifier == "C0123456789"
        assert binding.message_id == "1234567890.123456"
        assert binding.last_content == "initial content"

    def test_preset_type_literal(self) -> None:
        """Preset type accepts only desktop and mobile."""
        # This is a type check - at runtime any string works
        # but the Preset type hints to static analyzers
        now = datetime.now()
        dest = AttachedDestination(type="telegram", identifier="123", attached_at=now)

        # Valid presets
        binding1 = MessageBinding(
            session_id="s1", preset="desktop", destination=dest, message_id="1"
        )
        binding2 = MessageBinding(
            session_id="s2", preset="mobile", destination=dest, message_id="2"
        )

        assert binding1.preset == "desktop"
        assert binding2.preset == "mobile"


# ---------------------------------------------------------------------------
# MessageBindingManager fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def manager() -> MessageBindingManager:
    """Create a fresh MessageBindingManager."""
    return MessageBindingManager()


@pytest.fixture
def telegram_dest() -> AttachedDestination:
    """Create a telegram destination."""
    return AttachedDestination(
        type="telegram", identifier="123456789", attached_at=datetime.now()
    )


@pytest.fixture
def slack_dest() -> AttachedDestination:
    """Create a slack destination."""
    return AttachedDestination(
        type="slack", identifier="C0123456789", attached_at=datetime.now()
    )


@pytest.fixture
def telegram_binding(telegram_dest: AttachedDestination) -> MessageBinding:
    """Create a telegram binding."""
    return MessageBinding(
        session_id="test-session",
        preset="desktop",
        destination=telegram_dest,
        message_id="999",
    )


@pytest.fixture
def slack_binding(slack_dest: AttachedDestination) -> MessageBinding:
    """Create a slack binding."""
    return MessageBinding(
        session_id="test-session",
        preset="mobile",
        destination=slack_dest,
        message_id="1234567890.123456",
    )


# ---------------------------------------------------------------------------
# MessageBindingManager.add_binding tests
# ---------------------------------------------------------------------------


class TestAddBinding:
    """Tests for MessageBindingManager.add_binding()."""

    def test_add_single_binding(
        self, manager: MessageBindingManager, telegram_binding: MessageBinding
    ) -> None:
        """Can add a single binding."""
        manager.add_binding(telegram_binding)
        bindings = manager.get_bindings_for_session("test-session")
        assert len(bindings) == 1
        assert bindings[0] == telegram_binding

    def test_add_multiple_bindings_same_session(
        self,
        manager: MessageBindingManager,
        telegram_binding: MessageBinding,
        slack_binding: MessageBinding,
    ) -> None:
        """Can add multiple bindings to the same session."""
        manager.add_binding(telegram_binding)
        manager.add_binding(slack_binding)
        bindings = manager.get_bindings_for_session("test-session")
        assert len(bindings) == 2

    def test_add_bindings_different_sessions(
        self, manager: MessageBindingManager, telegram_dest: AttachedDestination
    ) -> None:
        """Can add bindings to different sessions."""
        binding1 = MessageBinding(
            session_id="session-1",
            preset="desktop",
            destination=telegram_dest,
            message_id="1",
        )
        binding2 = MessageBinding(
            session_id="session-2",
            preset="desktop",
            destination=telegram_dest,
            message_id="2",
        )
        manager.add_binding(binding1)
        manager.add_binding(binding2)

        assert len(manager.get_bindings_for_session("session-1")) == 1
        assert len(manager.get_bindings_for_session("session-2")) == 1


# ---------------------------------------------------------------------------
# MessageBindingManager.remove_binding tests
# ---------------------------------------------------------------------------


class TestRemoveBinding:
    """Tests for MessageBindingManager.remove_binding()."""

    def test_remove_existing_binding(
        self,
        manager: MessageBindingManager,
        telegram_binding: MessageBinding,
        telegram_dest: AttachedDestination,
    ) -> None:
        """Can remove an existing binding."""
        manager.add_binding(telegram_binding)
        removed = manager.remove_binding("test-session", telegram_dest)
        assert removed == telegram_binding
        assert len(manager.get_bindings_for_session("test-session")) == 0

    def test_remove_nonexistent_binding_returns_none(
        self, manager: MessageBindingManager, telegram_dest: AttachedDestination
    ) -> None:
        """Removing nonexistent binding returns None."""
        removed = manager.remove_binding("unknown-session", telegram_dest)
        assert removed is None

    def test_remove_binding_wrong_destination(
        self,
        manager: MessageBindingManager,
        telegram_binding: MessageBinding,
        slack_dest: AttachedDestination,
    ) -> None:
        """Removing with wrong destination returns None."""
        manager.add_binding(telegram_binding)
        removed = manager.remove_binding("test-session", slack_dest)
        assert removed is None
        assert len(manager.get_bindings_for_session("test-session")) == 1

    def test_remove_one_of_multiple_bindings(
        self,
        manager: MessageBindingManager,
        telegram_binding: MessageBinding,
        slack_binding: MessageBinding,
        telegram_dest: AttachedDestination,
    ) -> None:
        """Can remove one binding while leaving others."""
        manager.add_binding(telegram_binding)
        manager.add_binding(slack_binding)

        removed = manager.remove_binding("test-session", telegram_dest)

        assert removed == telegram_binding
        bindings = manager.get_bindings_for_session("test-session")
        assert len(bindings) == 1
        assert bindings[0] == slack_binding


# ---------------------------------------------------------------------------
# MessageBindingManager.get_bindings_for_session tests
# ---------------------------------------------------------------------------


class TestGetBindingsForSession:
    """Tests for MessageBindingManager.get_bindings_for_session()."""

    def test_get_bindings_empty(self, manager: MessageBindingManager) -> None:
        """Returns empty list for unknown session."""
        bindings = manager.get_bindings_for_session("unknown-session")
        assert bindings == []

    def test_get_bindings_returns_copy(
        self, manager: MessageBindingManager, telegram_binding: MessageBinding
    ) -> None:
        """Returns a copy of the bindings list."""
        manager.add_binding(telegram_binding)

        bindings1 = manager.get_bindings_for_session("test-session")
        bindings2 = manager.get_bindings_for_session("test-session")

        assert bindings1 == bindings2
        assert bindings1 is not bindings2

    def test_get_bindings_modification_does_not_affect_manager(
        self, manager: MessageBindingManager, telegram_binding: MessageBinding
    ) -> None:
        """Modifying returned list does not affect manager state."""
        manager.add_binding(telegram_binding)
        bindings = manager.get_bindings_for_session("test-session")
        bindings.clear()

        # Original bindings should still exist
        assert len(manager.get_bindings_for_session("test-session")) == 1


# ---------------------------------------------------------------------------
# MessageBindingManager.get_all_bindings tests
# ---------------------------------------------------------------------------


class TestGetAllBindings:
    """Tests for MessageBindingManager.get_all_bindings()."""

    def test_get_all_bindings_empty(self, manager: MessageBindingManager) -> None:
        """Returns empty list when no bindings exist."""
        assert manager.get_all_bindings() == []

    def test_get_all_bindings_multiple_sessions(
        self, manager: MessageBindingManager, telegram_dest: AttachedDestination
    ) -> None:
        """Returns bindings from all sessions."""
        binding1 = MessageBinding(
            session_id="session-1",
            preset="desktop",
            destination=telegram_dest,
            message_id="1",
        )
        binding2 = MessageBinding(
            session_id="session-2",
            preset="mobile",
            destination=telegram_dest,
            message_id="2",
        )

        manager.add_binding(binding1)
        manager.add_binding(binding2)

        all_bindings = manager.get_all_bindings()
        assert len(all_bindings) == 2
        assert binding1 in all_bindings
        assert binding2 in all_bindings


# ---------------------------------------------------------------------------
# MessageBindingManager.update_last_content tests
# ---------------------------------------------------------------------------


class TestUpdateLastContent:
    """Tests for MessageBindingManager.update_last_content()."""

    def test_update_last_content(
        self,
        manager: MessageBindingManager,
        telegram_binding: MessageBinding,
        telegram_dest: AttachedDestination,
    ) -> None:
        """Can update last_content for a binding."""
        manager.add_binding(telegram_binding)
        manager.update_last_content("test-session", telegram_dest, "new content")

        binding = manager.get_bindings_for_session("test-session")[0]
        assert binding.last_content == "new content"

    def test_update_last_content_nonexistent_session(
        self, manager: MessageBindingManager, telegram_dest: AttachedDestination
    ) -> None:
        """Updating nonexistent session is a no-op (no exception)."""
        # Should not raise
        manager.update_last_content("unknown-session", telegram_dest, "content")

    def test_update_last_content_wrong_destination(
        self,
        manager: MessageBindingManager,
        telegram_binding: MessageBinding,
        slack_dest: AttachedDestination,
    ) -> None:
        """Updating with wrong destination is a no-op."""
        manager.add_binding(telegram_binding)
        manager.update_last_content("test-session", slack_dest, "content")

        # Original binding should be unchanged
        binding = manager.get_bindings_for_session("test-session")[0]
        assert binding.last_content == ""

    def test_update_correct_binding_among_multiple(
        self,
        manager: MessageBindingManager,
        telegram_binding: MessageBinding,
        slack_binding: MessageBinding,
        telegram_dest: AttachedDestination,
    ) -> None:
        """Updates only the matching binding."""
        manager.add_binding(telegram_binding)
        manager.add_binding(slack_binding)

        manager.update_last_content("test-session", telegram_dest, "telegram update")

        bindings = manager.get_bindings_for_session("test-session")
        telegram_b = next(b for b in bindings if b.destination.type == "telegram")
        slack_b = next(b for b in bindings if b.destination.type == "slack")

        assert telegram_b.last_content == "telegram update"
        assert slack_b.last_content == ""  # Unchanged


# ---------------------------------------------------------------------------
# MessageBindingManager.find_binding tests
# ---------------------------------------------------------------------------


class TestFindBinding:
    """Tests for MessageBindingManager.find_binding()."""

    def test_find_existing_binding(
        self,
        manager: MessageBindingManager,
        telegram_binding: MessageBinding,
        telegram_dest: AttachedDestination,
    ) -> None:
        """Can find an existing binding."""
        manager.add_binding(telegram_binding)
        found = manager.find_binding("test-session", telegram_dest)
        assert found == telegram_binding

    def test_find_nonexistent_binding(
        self, manager: MessageBindingManager, telegram_dest: AttachedDestination
    ) -> None:
        """Returns None for nonexistent binding."""
        found = manager.find_binding("unknown-session", telegram_dest)
        assert found is None

    def test_find_binding_wrong_destination(
        self,
        manager: MessageBindingManager,
        telegram_binding: MessageBinding,
        slack_dest: AttachedDestination,
    ) -> None:
        """Returns None when destination doesn't match."""
        manager.add_binding(telegram_binding)
        found = manager.find_binding("test-session", slack_dest)
        assert found is None


# ---------------------------------------------------------------------------
# MessageBindingManager.has_bindings tests
# ---------------------------------------------------------------------------


class TestHasBindings:
    """Tests for MessageBindingManager.has_bindings()."""

    def test_has_bindings_true(
        self, manager: MessageBindingManager, telegram_binding: MessageBinding
    ) -> None:
        """Returns True when session has bindings."""
        manager.add_binding(telegram_binding)
        assert manager.has_bindings("test-session") is True

    def test_has_bindings_false_unknown_session(
        self, manager: MessageBindingManager
    ) -> None:
        """Returns False for unknown session."""
        assert manager.has_bindings("unknown-session") is False

    def test_has_bindings_false_after_remove(
        self,
        manager: MessageBindingManager,
        telegram_binding: MessageBinding,
        telegram_dest: AttachedDestination,
    ) -> None:
        """Returns False after all bindings removed."""
        manager.add_binding(telegram_binding)
        manager.remove_binding("test-session", telegram_dest)
        assert manager.has_bindings("test-session") is False


# ---------------------------------------------------------------------------
# MessageBindingManager.clear_session tests
# ---------------------------------------------------------------------------


class TestClearSession:
    """Tests for MessageBindingManager.clear_session()."""

    def test_clear_session_removes_all_bindings(
        self,
        manager: MessageBindingManager,
        telegram_binding: MessageBinding,
        slack_binding: MessageBinding,
    ) -> None:
        """Clears all bindings for a session."""
        manager.add_binding(telegram_binding)
        manager.add_binding(slack_binding)

        removed = manager.clear_session("test-session")

        assert len(removed) == 2
        assert telegram_binding in removed
        assert slack_binding in removed
        assert manager.get_bindings_for_session("test-session") == []

    def test_clear_session_unknown_returns_empty(
        self, manager: MessageBindingManager
    ) -> None:
        """Clearing unknown session returns empty list."""
        removed = manager.clear_session("unknown-session")
        assert removed == []

    def test_clear_session_does_not_affect_other_sessions(
        self, manager: MessageBindingManager, telegram_dest: AttachedDestination
    ) -> None:
        """Clearing one session does not affect others."""
        binding1 = MessageBinding(
            session_id="session-1",
            preset="desktop",
            destination=telegram_dest,
            message_id="1",
        )
        binding2 = MessageBinding(
            session_id="session-2",
            preset="desktop",
            destination=telegram_dest,
            message_id="2",
        )
        manager.add_binding(binding1)
        manager.add_binding(binding2)

        manager.clear_session("session-1")

        assert manager.get_bindings_for_session("session-1") == []
        assert len(manager.get_bindings_for_session("session-2")) == 1


# ---------------------------------------------------------------------------
# Module imports tests
# ---------------------------------------------------------------------------


class TestModuleImports:
    """Tests for module imports and __all__."""

    def test_import_message_binding(self) -> None:
        """Can import MessageBinding from watcher package."""
        from claude_session_player.watcher import MessageBinding as MB

        assert MB is MessageBinding

    def test_import_message_binding_manager(self) -> None:
        """Can import MessageBindingManager from watcher package."""
        from claude_session_player.watcher import MessageBindingManager as MBM

        assert MBM is MessageBindingManager

    def test_in_all(self) -> None:
        """MessageBinding and MessageBindingManager are in __all__."""
        from claude_session_player import watcher

        assert "MessageBinding" in watcher.__all__
        assert "MessageBindingManager" in watcher.__all__
