"""Tests for MessageBinding and MessageBindingManager."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from claude_session_player.watcher.destinations import AttachedDestination
from claude_session_player.watcher.message_binding import (
    DEFAULT_TTL_SECONDS,
    MAX_TTL_SECONDS,
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


# ---------------------------------------------------------------------------
# MessageBinding TTL tests
# ---------------------------------------------------------------------------


class TestMessageBindingTTL:
    """Tests for MessageBinding TTL fields and methods."""

    def test_default_ttl_fields(self, telegram_dest: AttachedDestination) -> None:
        """Binding has default TTL fields."""
        binding = MessageBinding(
            session_id="test-session",
            preset="desktop",
            destination=telegram_dest,
            message_id="999",
        )
        assert binding.ttl_seconds == DEFAULT_TTL_SECONDS
        assert binding.expired is False
        assert isinstance(binding.created_at, datetime)

    def test_custom_ttl(self, telegram_dest: AttachedDestination) -> None:
        """Can create binding with custom TTL."""
        binding = MessageBinding(
            session_id="test-session",
            preset="desktop",
            destination=telegram_dest,
            message_id="999",
            ttl_seconds=60,
        )
        assert binding.ttl_seconds == 60

    def test_is_expired_false_when_fresh(
        self, telegram_dest: AttachedDestination
    ) -> None:
        """is_expired returns False for fresh binding."""
        binding = MessageBinding(
            session_id="test-session",
            preset="desktop",
            destination=telegram_dest,
            message_id="999",
        )
        assert binding.is_expired() is False

    def test_is_expired_true_when_ttl_passed(
        self, telegram_dest: AttachedDestination
    ) -> None:
        """is_expired returns True when TTL has elapsed."""
        binding = MessageBinding(
            session_id="test-session",
            preset="desktop",
            destination=telegram_dest,
            message_id="999",
            created_at=datetime.now(timezone.utc) - timedelta(seconds=60),
            ttl_seconds=30,
        )
        assert binding.is_expired() is True

    def test_is_expired_true_when_marked_expired(
        self, telegram_dest: AttachedDestination
    ) -> None:
        """is_expired returns True when explicitly marked."""
        binding = MessageBinding(
            session_id="test-session",
            preset="desktop",
            destination=telegram_dest,
            message_id="999",
            expired=True,
        )
        assert binding.is_expired() is True

    def test_extend_ttl_adds_time(self, telegram_dest: AttachedDestination) -> None:
        """extend_ttl adds seconds to TTL."""
        binding = MessageBinding(
            session_id="test-session",
            preset="desktop",
            destination=telegram_dest,
            message_id="999",
            ttl_seconds=30,
        )
        binding.extend_ttl(30)
        assert binding.ttl_seconds == 60

    def test_extend_ttl_respects_max(self, telegram_dest: AttachedDestination) -> None:
        """extend_ttl caps at MAX_TTL_SECONDS."""
        binding = MessageBinding(
            session_id="test-session",
            preset="desktop",
            destination=telegram_dest,
            message_id="999",
            ttl_seconds=280,
        )
        binding.extend_ttl(100)  # Would be 380, should cap at 300
        assert binding.ttl_seconds == MAX_TTL_SECONDS

    def test_extend_ttl_clears_expired_flag(
        self, telegram_dest: AttachedDestination
    ) -> None:
        """extend_ttl clears the expired flag."""
        binding = MessageBinding(
            session_id="test-session",
            preset="desktop",
            destination=telegram_dest,
            message_id="999",
            expired=True,
        )
        binding.extend_ttl(30)
        assert binding.expired is False

    def test_extend_ttl_default_seconds(
        self, telegram_dest: AttachedDestination
    ) -> None:
        """extend_ttl uses default seconds when not specified."""
        binding = MessageBinding(
            session_id="test-session",
            preset="desktop",
            destination=telegram_dest,
            message_id="999",
            ttl_seconds=30,
        )
        binding.extend_ttl()
        assert binding.ttl_seconds == 60  # 30 + 30

    def test_time_remaining_positive(
        self, telegram_dest: AttachedDestination
    ) -> None:
        """time_remaining returns positive value for fresh binding."""
        binding = MessageBinding(
            session_id="test-session",
            preset="desktop",
            destination=telegram_dest,
            message_id="999",
            ttl_seconds=60,
        )
        remaining = binding.time_remaining()
        assert remaining > 0
        assert remaining <= 60

    def test_time_remaining_zero_when_expired(
        self, telegram_dest: AttachedDestination
    ) -> None:
        """time_remaining returns 0 when expired."""
        binding = MessageBinding(
            session_id="test-session",
            preset="desktop",
            destination=telegram_dest,
            message_id="999",
            created_at=datetime.now(timezone.utc) - timedelta(seconds=60),
            ttl_seconds=30,
        )
        assert binding.time_remaining() == 0

    def test_time_remaining_zero_when_marked_expired(
        self, telegram_dest: AttachedDestination
    ) -> None:
        """time_remaining returns 0 when explicitly marked expired."""
        binding = MessageBinding(
            session_id="test-session",
            preset="desktop",
            destination=telegram_dest,
            message_id="999",
            expired=True,
        )
        assert binding.time_remaining() == 0


# ---------------------------------------------------------------------------
# MessageBindingManager.find_binding_by_message_id tests
# ---------------------------------------------------------------------------


class TestFindBindingByMessageId:
    """Tests for MessageBindingManager.find_binding_by_message_id()."""

    def test_find_existing_telegram_binding(
        self, manager: MessageBindingManager, telegram_binding: MessageBinding
    ) -> None:
        """Can find telegram binding by message_id."""
        manager.add_binding(telegram_binding)
        found = manager.find_binding_by_message_id(
            destination_type="telegram",
            identifier="123456789",
            message_id="999",
        )
        assert found == telegram_binding

    def test_find_existing_slack_binding(
        self, manager: MessageBindingManager, slack_binding: MessageBinding
    ) -> None:
        """Can find slack binding by message_id."""
        manager.add_binding(slack_binding)
        found = manager.find_binding_by_message_id(
            destination_type="slack",
            identifier="C0123456789",
            message_id="1234567890.123456",
        )
        assert found == slack_binding

    def test_find_nonexistent_message_id(
        self, manager: MessageBindingManager, telegram_binding: MessageBinding
    ) -> None:
        """Returns None for nonexistent message_id."""
        manager.add_binding(telegram_binding)
        found = manager.find_binding_by_message_id(
            destination_type="telegram",
            identifier="123456789",
            message_id="wrong-message-id",
        )
        assert found is None

    def test_find_wrong_destination_type(
        self, manager: MessageBindingManager, telegram_binding: MessageBinding
    ) -> None:
        """Returns None for wrong destination type."""
        manager.add_binding(telegram_binding)
        found = manager.find_binding_by_message_id(
            destination_type="slack",
            identifier="123456789",
            message_id="999",
        )
        assert found is None

    def test_find_wrong_identifier(
        self, manager: MessageBindingManager, telegram_binding: MessageBinding
    ) -> None:
        """Returns None for wrong identifier."""
        manager.add_binding(telegram_binding)
        found = manager.find_binding_by_message_id(
            destination_type="telegram",
            identifier="wrong-chat-id",
            message_id="999",
        )
        assert found is None

    def test_find_among_multiple_bindings(
        self,
        manager: MessageBindingManager,
        telegram_binding: MessageBinding,
        slack_binding: MessageBinding,
        telegram_dest: AttachedDestination,
    ) -> None:
        """Can find specific binding among multiple."""
        # Add bindings for multiple sessions
        binding2 = MessageBinding(
            session_id="session-2",
            preset="desktop",
            destination=telegram_dest,
            message_id="888",
        )
        manager.add_binding(telegram_binding)
        manager.add_binding(slack_binding)
        manager.add_binding(binding2)

        # Find the specific one
        found = manager.find_binding_by_message_id(
            destination_type="telegram",
            identifier="123456789",
            message_id="888",
        )
        assert found == binding2
