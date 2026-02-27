"""Tests for the scheduled events store (Feature 6).

Covers: schedule, cancel, get_due_events, mark_fired,
overdue auto-expire, batch cap, cleanup, count_pending,
and schedule_event XML extraction in parse_cognitive_response.
"""

import time

import pytest

import scheduler
from memory.snapshot import CognitiveOutput


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clean_scheduler(isolate_databases):
    """Ensure a clean scheduled_events table for each test."""
    conn = scheduler._get_conn()
    conn.execute("DELETE FROM scheduled_events")
    conn.commit()


# ---------------------------------------------------------------------------
# schedule / cancel
# ---------------------------------------------------------------------------

class TestSchedule:
    def test_schedule_returns_id(self):
        eid = scheduler.schedule("followUp", "check in", delay_seconds=60)
        assert isinstance(eid, str)
        assert len(eid) > 0

    def test_schedule_creates_pending_event(self):
        scheduler.schedule("followUp", "check in", delay_seconds=60)
        pending = scheduler.pending()
        assert len(pending) == 1
        assert pending[0]["perception_action"] == "followUp"
        assert pending[0]["perception_content"] == "check in"
        assert pending[0]["fired"] == 0

    def test_cancel_removes_event(self):
        eid = scheduler.schedule("test", "content", delay_seconds=300)
        assert scheduler.cancel(eid) is True
        assert scheduler.count_pending() == 0

    def test_cancel_nonexistent_returns_false(self):
        assert scheduler.cancel("nonexistent") is False

    def test_cancel_already_fired_returns_false(self):
        eid = scheduler.schedule("test", delay_seconds=0)
        scheduler.mark_fired(eid)
        assert scheduler.cancel(eid) is False


# ---------------------------------------------------------------------------
# get_due_events
# ---------------------------------------------------------------------------

class TestGetDueEvents:
    def test_due_event_returned(self):
        """Events with fire_at in the past are due."""
        scheduler.schedule("followUp", "check in", delay_seconds=0)
        due = scheduler.get_due_events()
        assert len(due) == 1
        assert due[0]["perception_action"] == "followUp"

    def test_future_event_not_returned(self):
        """Events with fire_at in the future are not due."""
        scheduler.schedule("followUp", "check in", delay_seconds=9999)
        due = scheduler.get_due_events()
        assert len(due) == 0

    def test_batch_cap(self):
        """get_due_events respects max_batch."""
        for i in range(10):
            scheduler.schedule(f"event_{i}", delay_seconds=0)
        due = scheduler.get_due_events(max_batch=3)
        assert len(due) == 3

    def test_already_fired_not_returned(self):
        eid = scheduler.schedule("test", delay_seconds=0)
        scheduler.mark_fired(eid)
        due = scheduler.get_due_events()
        assert len(due) == 0

    def test_metadata_parsed(self):
        """Metadata should be parsed from JSON string to dict."""
        scheduler.schedule("test", metadata={"key": "value"}, delay_seconds=0)
        due = scheduler.get_due_events()
        assert due[0]["metadata"] == {"key": "value"}


# ---------------------------------------------------------------------------
# Overdue auto-expire
# ---------------------------------------------------------------------------

class TestOverdueExpiry:
    def test_massively_overdue_auto_expired(self):
        """Events overdue by >2x their intended delay are auto-expired."""
        conn = scheduler._get_conn()
        now = time.time()
        # Event intended to fire 10s after creation, but 100s overdue
        conn.execute(
            """INSERT INTO scheduled_events
               (id, fire_at, perception_action, created_at, fired)
               VALUES (?, ?, ?, ?, 0)""",
            ("overdue1", now - 100, "test", now - 110),
        )
        conn.commit()
        due = scheduler.get_due_events(max_overdue_ratio=2.0)
        assert len(due) == 0
        # Should be marked as fired
        row = conn.execute(
            "SELECT fired FROM scheduled_events WHERE id = 'overdue1'"
        ).fetchone()
        assert row["fired"] == 1

    def test_slightly_overdue_not_expired(self):
        """Events slightly overdue should still fire."""
        conn = scheduler._get_conn()
        now = time.time()
        # Event intended to fire 100s after creation, only 5s overdue
        conn.execute(
            """INSERT INTO scheduled_events
               (id, fire_at, perception_action, created_at, fired)
               VALUES (?, ?, ?, ?, 0)""",
            ("ok1", now - 5, "test", now - 105),
        )
        conn.commit()
        due = scheduler.get_due_events(max_overdue_ratio=2.0)
        assert len(due) == 1


# ---------------------------------------------------------------------------
# mark_fired / count_pending / cleanup
# ---------------------------------------------------------------------------

class TestMarkFired:
    def test_mark_fired(self):
        eid = scheduler.schedule("test", delay_seconds=0)
        scheduler.mark_fired(eid)
        assert scheduler.count_pending() == 0


class TestCleanup:
    def test_cleanup_removes_old_fired(self):
        conn = scheduler._get_conn()
        old_time = time.time() - (40 * 86400)  # 40 days ago
        conn.execute(
            """INSERT INTO scheduled_events
               (id, fire_at, perception_action, created_at, fired)
               VALUES (?, ?, ?, ?, 1)""",
            ("old1", old_time, "test", old_time),
        )
        conn.commit()
        deleted = scheduler.cleanup(max_age_days=30)
        assert deleted == 1

    def test_cleanup_keeps_recent_fired(self):
        eid = scheduler.schedule("test", delay_seconds=0)
        scheduler.mark_fired(eid)
        deleted = scheduler.cleanup(max_age_days=30)
        assert deleted == 0


class TestCountPending:
    def test_count_pending(self):
        assert scheduler.count_pending() == 0
        scheduler.schedule("a", delay_seconds=60)
        scheduler.schedule("b", delay_seconds=60)
        assert scheduler.count_pending() == 2


# ---------------------------------------------------------------------------
# CognitiveOutput.with_scheduled_event
# ---------------------------------------------------------------------------

class TestCognitiveOutputScheduledEvents:
    def test_with_scheduled_event(self):
        output = CognitiveOutput().with_scheduled_event(
            action="followUp", content="check in", delay_seconds=3600,
        )
        assert len(output.scheduled_events) == 1
        assert output.scheduled_events[0]["action"] == "followUp"
        assert output.scheduled_events[0]["delay_seconds"] == 3600

    def test_multiple_scheduled_events(self):
        output = (CognitiveOutput()
            .with_scheduled_event(action="a", delay_seconds=60)
            .with_scheduled_event(action="b", delay_seconds=120))
        assert len(output.scheduled_events) == 2

    def test_scheduled_events_in_is_empty(self):
        empty = CognitiveOutput()
        assert empty.is_empty is True
        with_event = empty.with_scheduled_event(action="test")
        assert with_event.is_empty is False

    def test_merge_combines_events(self):
        a = CognitiveOutput().with_scheduled_event(action="a")
        b = CognitiveOutput().with_scheduled_event(action="b")
        merged = a.merge(b)
        assert len(merged.scheduled_events) == 2


# ---------------------------------------------------------------------------
# schedule_event XML extraction in parse_cognitive_response
# ---------------------------------------------------------------------------

class TestScheduleEventExtraction:
    def test_single_schedule_event(self):
        from engine.soul_engine import parse_cognitive_response
        raw = (
            '<internal_monologue>thinking</internal_monologue>'
            '<external_dialogue>hello</external_dialogue>'
            '<schedule_event action="followUp" delay="3600">Check in later.</schedule_event>'
        )
        dialogue, output = parse_cognitive_response(raw, "u1", "trace1")
        assert len(output.scheduled_events) == 1
        assert output.scheduled_events[0]["action"] == "followUp"
        assert output.scheduled_events[0]["delay_seconds"] == 3600.0
        assert output.scheduled_events[0]["content"] == "Check in later."

    def test_multiple_schedule_events(self):
        from engine.soul_engine import parse_cognitive_response
        raw = (
            '<external_dialogue>ok</external_dialogue>'
            '<schedule_event action="reminder" delay="60">First</schedule_event>'
            '<schedule_event action="followUp" delay="3600" process="focused_process">Second</schedule_event>'
        )
        _, output = parse_cognitive_response(raw, "u1", "trace1")
        assert len(output.scheduled_events) == 2
        assert output.scheduled_events[0]["action"] == "reminder"
        assert output.scheduled_events[1]["target_process"] == "focused_process"

    def test_no_schedule_event(self):
        from engine.soul_engine import parse_cognitive_response
        raw = '<external_dialogue>hello</external_dialogue>'
        _, output = parse_cognitive_response(raw, "u1", "trace1")
        assert len(output.scheduled_events) == 0

    def test_schedule_event_default_action(self):
        from engine.soul_engine import parse_cognitive_response
        raw = (
            '<external_dialogue>ok</external_dialogue>'
            '<schedule_event delay="30">quick check</schedule_event>'
        )
        _, output = parse_cognitive_response(raw, "u1", "trace1")
        assert output.scheduled_events[0]["action"] == "scheduledEvent"

    def test_schedule_event_bad_delay(self):
        from engine.soul_engine import parse_cognitive_response
        raw = (
            '<external_dialogue>ok</external_dialogue>'
            '<schedule_event action="test" delay="notanumber">content</schedule_event>'
        )
        _, output = parse_cognitive_response(raw, "u1", "trace1")
        assert output.scheduled_events[0]["delay_seconds"] == 0

    def test_schedule_event_creates_tool_action_entry(self):
        from engine.soul_engine import parse_cognitive_response
        raw = (
            '<external_dialogue>ok</external_dialogue>'
            '<schedule_event action="followUp" delay="60">check</schedule_event>'
        )
        _, output = parse_cognitive_response(raw, "u1", "trace1")
        tool_entries = [e for e in output.entries if e.entry_type == "toolAction"]
        assert any("scheduled event" in e.content for e in tool_entries)
