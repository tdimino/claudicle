"""Tests for daimon_memory and daimon_output_parser.

Subdaimon persistent memory: context creation, memory load/store,
lesson persistence, communication logging, output protocol parsing.
DB isolation comes from conftest.py's isolate_databases fixture.
"""

from memory.daimon_memory import (
    DaimonContext,
    make_context,
    load_memory,
    load_lessons,
    store_output,
    store_invocation,
    store_lesson,
    store_communication,
    format_for_boot,
    get_state,
    set_state,
)
from memory.daimon_output_parser import parse_and_store, parse_output
from memory.snapshot import CognitiveOutput
from memory import process_memory, soul_memory


class TestMakeContext:
    def test_default_context(self):
        ctx = make_context("leb")
        assert ctx.agent_name == "leb"
        assert ctx.soul_id == "default"
        assert ctx.user_id == ""
        assert ctx.project == "global"
        assert ctx.channel == "daimon:leb"
        assert ctx.thread_ts == "default::global"

    def test_custom_context(self):
        ctx = make_context("scholiast", soul_id="claudius", user_id="tom", project="claudicle")
        assert ctx.channel == "daimon:scholiast"
        assert ctx.thread_ts == "claudius:tom:claudicle"

    def test_context_is_frozen(self):
        ctx = make_context("leb")
        try:
            ctx.agent_name = "hacked"
            assert False, "Should have raised FrozenInstanceError"
        except AttributeError:
            pass


class TestStoreAndLoad:
    def test_store_invocation_and_load(self):
        ctx = make_context("leb")
        store_invocation(ctx, "Reflected on session abc123", trace_id="t1")

        snap = load_memory(ctx, limit=10)
        assert len(snap.entries) == 1
        assert "Reflected on session" in snap.entries[0].content
        assert snap.channel == "daimon:leb"

    def test_store_output(self):
        ctx = make_context("eikon")
        output = CognitiveOutput().with_entry(
            "daimonicIntuition",
            "User prefers explicit confirmation",
            verb="observed",
            user_id="eikon",
        )
        store_output(ctx, output)

        snap = load_memory(ctx, limit=10)
        assert len(snap.entries) == 1
        assert snap.entries[0].content == "User prefers explicit confirmation"

    def test_load_memory_with_regions(self):
        # Use a project-scoped context so thread differs from global lesson thread
        ctx = make_context("leb", user_id="tom", project="claudicle")
        store_invocation(ctx, "default region entry")
        store_lesson("leb", "A lesson learned")

        # Load only lessons region from project-scoped thread (should be empty—
        # lessons go to the global thread, not the project thread)
        snap = load_memory(ctx, limit=10, regions=["lessons"])
        assert len(snap.entries) == 0

    def test_load_empty_memory(self):
        ctx = make_context("rapu")
        snap = load_memory(ctx)
        assert len(snap.entries) == 0


class TestLessons:
    def test_store_and_load_lesson(self):
        store_lesson("leb", "Users prefer concise reflections")
        snap = load_lessons("leb")
        assert len(snap.entries) == 1
        assert snap.entries[0].content == "Users prefer concise reflections"

    def test_lessons_are_cross_project(self):
        store_lesson("leb", "Lesson from project A", project="proj-a")
        store_lesson("leb", "Lesson from project B", project="proj-b")
        snap = load_lessons("leb")
        assert len(snap.entries) == 2

    def test_lessons_scoped_by_agent(self):
        store_lesson("leb", "Leb lesson")
        store_lesson("eikon", "Eikon lesson")

        leb_lessons = load_lessons("leb")
        eikon_lessons = load_lessons("eikon")

        assert len(leb_lessons.entries) == 1
        assert leb_lessons.entries[0].content == "Leb lesson"
        assert len(eikon_lessons.entries) == 1
        assert eikon_lessons.entries[0].content == "Eikon lesson"


class TestCommunication:
    def test_store_outbound(self):
        ctx = make_context("leb")
        store_communication(ctx, "outbound", "team-lead", "Analysis complete")

        snap = load_memory(ctx, limit=10, regions=["comms"])
        assert len(snap.entries) == 1
        assert "[outbound]" in snap.entries[0].content
        assert "team-lead" in snap.entries[0].content

    def test_store_inbound(self):
        ctx = make_context("leb")
        store_communication(ctx, "inbound", "researcher", "Found 3 PRs")

        snap = load_memory(ctx, limit=10, regions=["comms"])
        assert len(snap.entries) == 1
        assert "[inbound]" in snap.entries[0].content
        assert snap.entries[0].user_id == "researcher"


class TestFormatForBoot:
    def test_format_empty(self):
        ctx = make_context("leb")
        memory = load_memory(ctx)
        lessons = load_lessons("leb")
        result = format_for_boot(ctx, memory, lessons)
        assert result == ""

    def test_format_with_invocations(self):
        ctx = make_context("leb")
        store_invocation(ctx, "First invocation summary")
        memory = load_memory(ctx)
        lessons = load_lessons("leb")
        result = format_for_boot(ctx, memory, lessons)
        assert "Prior Invocations" in result

    def test_format_with_lessons(self):
        ctx = make_context("leb")
        store_lesson("leb", "Important lesson")
        memory = load_memory(ctx)
        lessons = load_lessons("leb")
        result = format_for_boot(ctx, memory, lessons)
        assert "Lessons Learned" in result
        assert "Important lesson" in result


class TestProcessMemoryWrappers:
    def test_get_set_state(self):
        set_state("leb", "invocation_count", 5)
        assert get_state("leb", "invocation_count") == 5

    def test_get_default(self):
        assert get_state("leb", "nonexistent") is None
        assert get_state("leb", "nonexistent", default=0) == 0


class TestOutputParser:
    def test_parse_lessons(self):
        ctx = make_context("leb")
        output = """## Leb Reflection

### Internal Monologue
Some reflection here.

## Memory Updates

### Lessons Learned
- Pattern: user prefers explicit confirmation before large refactors
- Insight: Slack threads with >10 messages need compression
"""
        result = parse_and_store(output, ctx)
        assert result["lessons_stored"] == 2
        assert result["comms_stored"] == 0

        lessons = load_lessons("leb")
        assert len(lessons.entries) == 2

    def test_parse_communications(self):
        ctx = make_context("leb")
        output = """## Memory Updates

### Communication Log
- [outbound] to team-lead: Completed analysis
- [inbound] from researcher: Found 3 related PRs
"""
        result = parse_and_store(output, ctx)
        assert result["lessons_stored"] == 0
        assert result["comms_stored"] == 2

    def test_parse_mixed(self):
        ctx = make_context("scholiast")
        output = """## Research Findings

Some findings here.

## Memory Updates

### Lessons Learned
- Always use --no-text for initial Exa searches

### Communication Log
- [outbound] to team-lead: Research complete
"""
        result = parse_and_store(output, ctx)
        assert result["lessons_stored"] == 1
        assert result["comms_stored"] == 1

    def test_parse_no_memory_section(self):
        ctx = make_context("leb")
        output = """## Leb Reflection

### Internal Monologue
Just some reflection, no memory updates.
"""
        result = parse_and_store(output, ctx)
        assert result["lessons_stored"] == 0
        assert result["comms_stored"] == 0

    def test_parse_empty_output(self):
        ctx = make_context("leb")
        result = parse_and_store("", ctx)
        assert result["lessons_stored"] == 0
        assert result["comms_stored"] == 0

    def test_parse_unknown_subsection_ignored(self):
        ctx = make_context("leb")
        output = """## Memory Updates

### Unknown Section
- Some data here

### Lessons Learned
- Real lesson
"""
        result = parse_and_store(output, ctx)
        assert result["lessons_stored"] == 1


class TestParseOutput:
    """Tests for parse_output() — pure path returning CognitiveOutput."""

    def test_returns_cognitive_output(self):
        ctx = make_context("leb")
        output = """## Memory Updates

### Lessons Learned
- Pattern: user prefers concise responses
"""
        result = parse_output(output, ctx)
        assert isinstance(result, CognitiveOutput)
        assert len(result.entries) == 1

    def test_no_db_writes(self):
        """parse_output() should not write to the DB — pure function."""
        ctx = make_context("leb")
        output = """## Memory Updates

### Lessons Learned
- A lesson
"""
        result = parse_output(output, ctx)
        # No entries should exist in DB yet
        lessons = load_lessons("leb")
        assert len(lessons.entries) == 0
        # But the CognitiveOutput should have the entry
        assert len(result.entries) == 1

    def test_lesson_entries_have_correct_targets(self):
        ctx = make_context("scholiast", soul_id="claudius")
        output = """## Memory Updates

### Lessons Learned
- Always cite primary sources
"""
        result = parse_output(output, ctx)
        entry = result.entries[0]
        assert entry.entry_type == "daimonicIntuition"
        assert entry.verb == "learned"
        assert entry.region == "lessons"
        assert entry.target_channel == "daimon:scholiast"
        assert entry.target_thread_ts == "claudius::global"

    def test_comm_entries_have_correct_targets(self):
        ctx = make_context("leb", soul_id="default", user_id="tom", project="proj")
        output = """## Memory Updates

### Communication Log
- [outbound] to team-lead: Analysis complete
"""
        result = parse_output(output, ctx)
        entry = result.entries[0]
        assert entry.entry_type == "toolAction"
        assert entry.region == "comms"
        assert entry.target_channel == "daimon:leb"
        assert entry.target_thread_ts == "default:tom:proj"
        assert "[outbound]" in entry.content

    def test_empty_input_returns_empty_output(self):
        ctx = make_context("leb")
        result = parse_output("", ctx)
        assert result.is_empty

    def test_mixed_lessons_and_comms(self):
        ctx = make_context("leb")
        output = """## Memory Updates

### Lessons Learned
- Lesson one

### Communication Log
- [inbound] from researcher: Found data
"""
        result = parse_output(output, ctx)
        assert len(result.entries) == 2
        lessons = [e for e in result.entries if e.region == "lessons"]
        comms = [e for e in result.entries if e.region == "comms"]
        assert len(lessons) == 1
        assert len(comms) == 1


class TestProcessMemoryClear:
    """Tests for process_memory.clear() using delete() instead of tombstoning."""

    def test_clear_removes_keys_entirely(self):
        process_memory.set("leb", "counter", 5)
        process_memory.set("leb", "last_run", "2026-03-05")

        cleared = process_memory.clear("leb")
        assert cleared == 2

        # Keys should be gone from get_all(), not tombstoned
        all_state = soul_memory.get_all()
        proc_keys = [k for k in all_state if k.startswith("proc:leb:")]
        assert len(proc_keys) == 0

    def test_clear_leaves_other_agents_intact(self):
        process_memory.set("leb", "key1", "val1")
        process_memory.set("eikon", "key2", "val2")

        process_memory.clear("leb")

        # eikon's key should still exist
        assert process_memory.get("eikon", "key2") == "val2"
        # leb's key should be gone
        assert process_memory.get("leb", "key1") is None
