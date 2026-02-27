"""Tests for the Perception processor (Feature 4).

Covers: Perception dataclass, PerceptionProcessor.classify(),
factory methods, immutability.
"""

import pytest

from engine.perception import Perception, PerceptionProcessor, processor


# ---------------------------------------------------------------------------
# Perception dataclass
# ---------------------------------------------------------------------------

class TestPerceptionDataclass:
    def test_frozen(self):
        """Perception should be immutable."""
        p = Perception(
            action="userMessage", content="hi", user_id="u1",
            channel="ch", thread_ts="ts",
        )
        with pytest.raises(AttributeError):
            p.action = "other"

    def test_defaults(self):
        """Check default values for optional fields."""
        p = Perception(
            action="userMessage", content="hi", user_id="u1",
            channel="ch", thread_ts="ts",
        )
        assert p.display_name == ""
        assert p.internal is False
        assert p.metadata == {}
        assert p.created_at > 0

    def test_internal_flag(self):
        """Internal perceptions should have internal=True."""
        p = Perception(
            action="scheduledEvent", content="check in", user_id="system",
            channel="scheduler", thread_ts="scheduled", internal=True,
        )
        assert p.internal is True


# ---------------------------------------------------------------------------
# PerceptionProcessor.classify
# ---------------------------------------------------------------------------

class TestClassify:
    def test_user_message(self):
        """Normal text should classify as userMessage."""
        p = processor.classify("hello there", "u1", "ch", "ts")
        assert p.action == "userMessage"
        assert p.content == "hello there"

    def test_empty_message(self):
        """Empty text should classify as skip."""
        p = processor.classify("", "u1", "ch", "ts")
        assert p.action == "skip"

    def test_whitespace_only(self):
        """Whitespace-only text should classify as skip."""
        p = processor.classify("   \n  ", "u1", "ch", "ts")
        assert p.action == "skip"

    def test_slash_command(self):
        """Slash commands should classify as command."""
        p = processor.classify("/help", "u1", "ch", "ts")
        assert p.action == "command"
        assert p.content == "/help"

    def test_display_name_passed_through(self):
        """Display name should be preserved in the Perception."""
        p = processor.classify("hi", "u1", "ch", "ts", display_name="Tom")
        assert p.display_name == "Tom"

    def test_content_stripped(self):
        """Content should be stripped of leading/trailing whitespace."""
        p = processor.classify("  hello  ", "u1", "ch", "ts")
        assert p.content == "hello"

    def test_none_text(self):
        """None text should classify as skip."""
        p = processor.classify(None, "u1", "ch", "ts")
        assert p.action == "skip"


# ---------------------------------------------------------------------------
# Factory methods
# ---------------------------------------------------------------------------

class TestFactoryMethods:
    def test_from_scheduled_event(self):
        """Scheduled events should be internal=True."""
        p = processor.from_scheduled_event(
            action="followUp", content="check in",
            channel="C123", thread_ts="ts123",
            metadata={"event_id": "e1"},
        )
        assert p.action == "followUp"
        assert p.internal is True
        assert p.user_id == "system"
        assert p.metadata == {"event_id": "e1"}

    def test_from_system(self):
        """System notifications should be internal=True."""
        p = processor.from_system(
            action="systemNotification",
            content="Server restarted",
        )
        assert p.action == "systemNotification"
        assert p.internal is True
        assert p.user_id == "system"
        assert p.channel == "system"


# ---------------------------------------------------------------------------
# Module singleton
# ---------------------------------------------------------------------------

class TestModuleSingleton:
    def test_processor_is_instance(self):
        """Module-level processor should be a PerceptionProcessor."""
        assert isinstance(processor, PerceptionProcessor)
