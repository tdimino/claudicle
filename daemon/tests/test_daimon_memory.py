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
from memory.daimon_output_parser import parse_and_store
from memory.snapshot import CognitiveOutput


class TestMakeContext:
    def test_default_context(self):
        ctx = make_context("mnemon")
        assert ctx.agent_name == "mnemon"
        assert ctx.soul_id == "default"
        assert ctx.user_id == ""
        assert ctx.project == "global"
        assert ctx.channel == "daimon:mnemon"
        assert ctx.thread_ts == "default::global"

    def test_custom_context(self):
        ctx = make_context("scholiast", soul_id="claudius", user_id="tom", project="claudicle")
        assert ctx.channel == "daimon:scholiast"
        assert ctx.thread_ts == "claudius:tom:claudicle"

    def test_context_is_frozen(self):
        ctx = make_context("mnemon")
        try:
            ctx.agent_name = "hacked"
            assert False, "Should have raised FrozenInstanceError"
        except AttributeError:
            pass


class TestStoreAndLoad:
    def test_store_invocation_and_load(self):
        ctx = make_context("mnemon")
        store_invocation(ctx, "Reflected on session abc123", trace_id="t1")

        snap = load_memory(ctx, limit=10)
        assert len(snap.entries) == 1
        assert "Reflected on session" in snap.entries[0].content
        assert snap.channel == "daimon:mnemon"

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
        ctx = make_context("mnemon", user_id="tom", project="claudicle")
        store_invocation(ctx, "default region entry")
        store_lesson("mnemon", "A lesson learned")

        # Load only lessons region from project-scoped thread (should be empty—
        # lessons go to the global thread, not the project thread)
        snap = load_memory(ctx, limit=10, regions=["lessons"])
        assert len(snap.entries) == 0

    def test_load_empty_memory(self):
        ctx = make_context("phantasos")
        snap = load_memory(ctx)
        assert len(snap.entries) == 0


class TestLessons:
    def test_store_and_load_lesson(self):
        store_lesson("mnemon", "Users prefer concise reflections")
        snap = load_lessons("mnemon")
        assert len(snap.entries) == 1
        assert snap.entries[0].content == "Users prefer concise reflections"

    def test_lessons_are_cross_project(self):
        store_lesson("mnemon", "Lesson from project A", project="proj-a")
        store_lesson("mnemon", "Lesson from project B", project="proj-b")
        snap = load_lessons("mnemon")
        assert len(snap.entries) == 2

    def test_lessons_scoped_by_agent(self):
        store_lesson("mnemon", "Mnemon lesson")
        store_lesson("eikon", "Eikon lesson")

        mnemon_lessons = load_lessons("mnemon")
        eikon_lessons = load_lessons("eikon")

        assert len(mnemon_lessons.entries) == 1
        assert mnemon_lessons.entries[0].content == "Mnemon lesson"
        assert len(eikon_lessons.entries) == 1
        assert eikon_lessons.entries[0].content == "Eikon lesson"


class TestCommunication:
    def test_store_outbound(self):
        ctx = make_context("mnemon")
        store_communication(ctx, "outbound", "team-lead", "Analysis complete")

        snap = load_memory(ctx, limit=10, regions=["comms"])
        assert len(snap.entries) == 1
        assert "[outbound]" in snap.entries[0].content
        assert "team-lead" in snap.entries[0].content

    def test_store_inbound(self):
        ctx = make_context("mnemon")
        store_communication(ctx, "inbound", "researcher", "Found 3 PRs")

        snap = load_memory(ctx, limit=10, regions=["comms"])
        assert len(snap.entries) == 1
        assert "[inbound]" in snap.entries[0].content
        assert snap.entries[0].user_id == "researcher"


class TestFormatForBoot:
    def test_format_empty(self):
        ctx = make_context("mnemon")
        memory = load_memory(ctx)
        lessons = load_lessons("mnemon")
        result = format_for_boot(ctx, memory, lessons)
        assert result == ""

    def test_format_with_invocations(self):
        ctx = make_context("mnemon")
        store_invocation(ctx, "First invocation summary")
        memory = load_memory(ctx)
        lessons = load_lessons("mnemon")
        result = format_for_boot(ctx, memory, lessons)
        assert "Prior Invocations" in result

    def test_format_with_lessons(self):
        ctx = make_context("mnemon")
        store_lesson("mnemon", "Important lesson")
        memory = load_memory(ctx)
        lessons = load_lessons("mnemon")
        result = format_for_boot(ctx, memory, lessons)
        assert "Lessons Learned" in result
        assert "Important lesson" in result


class TestProcessMemoryWrappers:
    def test_get_set_state(self):
        set_state("mnemon", "invocation_count", 5)
        assert get_state("mnemon", "invocation_count") == 5

    def test_get_default(self):
        assert get_state("mnemon", "nonexistent") is None
        assert get_state("mnemon", "nonexistent", default=0) == 0


class TestOutputParser:
    def test_parse_lessons(self):
        ctx = make_context("mnemon")
        output = """## Mnemon Reflection

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

        lessons = load_lessons("mnemon")
        assert len(lessons.entries) == 2

    def test_parse_communications(self):
        ctx = make_context("mnemon")
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
        ctx = make_context("mnemon")
        output = """## Mnemon Reflection

### Internal Monologue
Just some reflection, no memory updates.
"""
        result = parse_and_store(output, ctx)
        assert result["lessons_stored"] == 0
        assert result["comms_stored"] == 0

    def test_parse_empty_output(self):
        ctx = make_context("mnemon")
        result = parse_and_store("", ctx)
        assert result["lessons_stored"] == 0
        assert result["comms_stored"] == 0

    def test_parse_unknown_subsection_ignored(self):
        ctx = make_context("mnemon")
        output = """## Memory Updates

### Unknown Section
- Some data here

### Lessons Learned
- Real lesson
"""
        result = parse_and_store(output, ctx)
        assert result["lessons_stored"] == 1
