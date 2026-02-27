"""Tests for the mental process state machine (Feature 1 + Hardenings).

Covers: process loading, routing, transitions, executeNow depth limit,
process memory auto-clear, soul_memory defaults, process name validation,
params forwarding, target_process override, and internal flag threading.
"""

import asyncio
import types

import pytest

from engine.process_base import ProcessResult, ProcessTransition
from engine.process_router import (
    MAX_EXECUTE_NOW_DEPTH,
    _DEFAULT_PROCESS,
    _discover_valid_processes,
    _validate_process,
    _load_process,
    route,
)
from memory import soul_memory
from memory.process_memory import get as pm_get, set as pm_set, clear as pm_clear
from memory.snapshot import CognitiveOutput, WorkingMemorySnapshot, load_snapshot


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def snapshot(tmp_path):
    """Minimal snapshot for testing."""
    return WorkingMemorySnapshot(
        channel="test-ch", thread_ts="test-ts", trace_id="abc123",
    )


@pytest.fixture
def mock_main_process(monkeypatch):
    """Mock processes.main_process with a controllable run()."""
    results = []

    async def mock_run(text, user_id, channel, thread_ts, snapshot, display_name=None, params=None):
        if results:
            return results.pop(0)
        return ProcessResult(
            dialogue="hello from main",
            output=CognitiveOutput(),
        )

    mod = types.ModuleType("processes.main_process")
    mod.run = mock_run
    mod._results = results

    import sys
    monkeypatch.setitem(sys.modules, "processes.main_process", mod)
    return mod


@pytest.fixture
def mock_focused_process(monkeypatch):
    """Mock processes.focused_process."""
    async def mock_run(text, user_id, channel, thread_ts, snapshot, display_name=None, params=None):
        return ProcessResult(
            dialogue="hello from focused",
            output=CognitiveOutput(),
        )

    mod = types.ModuleType("processes.focused_process")
    mod.run = mock_run

    import sys
    monkeypatch.setitem(sys.modules, "processes.focused_process", mod)
    return mod


# ---------------------------------------------------------------------------
# Process loading
# ---------------------------------------------------------------------------

class TestLoadProcess:
    def test_loads_existing_module(self):
        """Loading main_process should return a module with run()."""
        mod = _load_process("main_process")
        assert hasattr(mod, "run")

    def test_unknown_module_falls_back_to_main(self):
        """Unknown process name should fall back to main_process."""
        mod = _load_process("nonexistent_process_xyz")
        assert hasattr(mod, "run")


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------

class TestRoute:
    def test_routes_to_current_process(self, snapshot, mock_main_process):
        """Route should call the current process from soul_memory."""
        soul_memory.set("currentProcess", "main_process")
        result = asyncio.get_event_loop().run_until_complete(
            route("hi", "user1", "ch", "ts", snapshot)
        )
        assert result.dialogue == "hello from main"

    def test_routes_to_focused_process(self, snapshot, mock_main_process, mock_focused_process):
        """Route should follow soul_memory currentProcess."""
        soul_memory.set("currentProcess", "focused_process")
        result = asyncio.get_event_loop().run_until_complete(
            route("hi", "user1", "ch", "ts", snapshot)
        )
        assert result.dialogue == "hello from focused"

    def test_default_process_when_not_set(self, snapshot, mock_main_process):
        """When currentProcess is not set, should use main_process."""
        # Don't set currentProcess — should default
        result = asyncio.get_event_loop().run_until_complete(
            route("hi", "user1", "ch", "ts", snapshot)
        )
        assert result.dialogue == "hello from main"


# ---------------------------------------------------------------------------
# Transitions
# ---------------------------------------------------------------------------

class TestTransitions:
    def test_transition_updates_soul_memory(self, snapshot, mock_main_process, mock_focused_process, monkeypatch):
        """Transition should update currentProcess and previousProcess."""
        soul_memory.set("currentProcess", "main_process")

        # Make main_process return a transition
        mock_main_process._results.append(ProcessResult(
            dialogue="transitioning",
            output=CognitiveOutput(),
            transition=ProcessTransition(target="focused_process"),
        ))

        asyncio.get_event_loop().run_until_complete(
            route("hi", "user1", "ch", "ts", snapshot)
        )

        assert soul_memory.get("currentProcess") == "focused_process"
        assert soul_memory.get("previousProcess") == "main_process"

    def test_transition_clears_process_memory(self, snapshot, mock_main_process, mock_focused_process, monkeypatch):
        """Process memory for the old process should be cleared on transition."""
        soul_memory.set("currentProcess", "main_process")

        # Store some process memory
        pm_set("main_process", "stage", 2)
        assert pm_get("main_process", "stage") == 2

        mock_main_process._results.append(ProcessResult(
            dialogue="bye",
            output=CognitiveOutput(),
            transition=ProcessTransition(target="focused_process"),
        ))

        asyncio.get_event_loop().run_until_complete(
            route("hi", "user1", "ch", "ts", snapshot)
        )

        # Process memory should be cleared
        assert pm_get("main_process", "stage") is None

    def test_execute_now_chains(self, snapshot, monkeypatch):
        """executeNow should chain immediately to the target process."""
        call_log = []

        async def main_run(text, user_id, channel, thread_ts, snapshot, display_name=None, params=None):
            call_log.append("main")
            return ProcessResult(
                dialogue="chain me",
                output=CognitiveOutput(),
                transition=ProcessTransition(target="focused_process", execute_now=True),
            )

        async def focused_run(text, user_id, channel, thread_ts, snapshot, display_name=None, params=None):
            call_log.append("focused")
            return ProcessResult(dialogue="focused result", output=CognitiveOutput())

        import sys
        main_mod = types.ModuleType("processes.main_process")
        main_mod.run = main_run
        monkeypatch.setitem(sys.modules, "processes.main_process", main_mod)

        focused_mod = types.ModuleType("processes.focused_process")
        focused_mod.run = focused_run
        monkeypatch.setitem(sys.modules, "processes.focused_process", focused_mod)

        soul_memory.set("currentProcess", "main_process")
        result = asyncio.get_event_loop().run_until_complete(
            route("hi", "user1", "ch", "ts", snapshot)
        )

        assert call_log == ["main", "focused"]
        assert result.dialogue == "focused result"

    def test_execute_now_depth_limit(self, snapshot, monkeypatch):
        """executeNow should stop at MAX_EXECUTE_NOW_DEPTH."""
        call_count = [0]

        async def looping_run(text, user_id, channel, thread_ts, snapshot, display_name=None, params=None):
            call_count[0] += 1
            # Always try to chain — should be capped
            target = f"loop_process_{call_count[0]}"
            return ProcessResult(
                dialogue=f"loop {call_count[0]}",
                output=CognitiveOutput(),
                transition=ProcessTransition(target="main_process", execute_now=True),
            )

        import sys
        mod = types.ModuleType("processes.main_process")
        mod.run = looping_run
        monkeypatch.setitem(sys.modules, "processes.main_process", mod)

        soul_memory.set("currentProcess", "main_process")
        result = asyncio.get_event_loop().run_until_complete(
            route("hi", "user1", "ch", "ts", snapshot)
        )

        # Should be capped at MAX_EXECUTE_NOW_DEPTH + 1 calls
        assert call_count[0] <= MAX_EXECUTE_NOW_DEPTH + 1


# ---------------------------------------------------------------------------
# Soul memory defaults
# ---------------------------------------------------------------------------

class TestSoulMemoryDefaults:
    def test_process_defaults_exist(self):
        """soul_memory should have currentProcess, previousProcess, processTurnCount."""
        from memory.soul_memory import SOUL_MEMORY_DEFAULTS
        assert "currentProcess" in SOUL_MEMORY_DEFAULTS
        assert "previousProcess" in SOUL_MEMORY_DEFAULTS
        assert "processTurnCount" in SOUL_MEMORY_DEFAULTS

    def test_default_current_process(self):
        """Default currentProcess should be main_process."""
        assert soul_memory.get("currentProcess") == "main_process"

    def test_default_process_turn_count(self):
        """Default processTurnCount should be '0'."""
        assert soul_memory.get("processTurnCount") == "0"


# ---------------------------------------------------------------------------
# Process base types
# ---------------------------------------------------------------------------

class TestProcessBaseTypes:
    def test_process_result_frozen(self):
        """ProcessResult should be immutable."""
        result = ProcessResult(dialogue="hi", output=CognitiveOutput())
        with pytest.raises(AttributeError):
            result.dialogue = "bye"

    def test_process_transition_frozen(self):
        """ProcessTransition should be immutable."""
        t = ProcessTransition(target="focused_process")
        with pytest.raises(AttributeError):
            t.target = "main_process"

    def test_process_transition_defaults(self):
        """ProcessTransition defaults: params={}, execute_now=False."""
        t = ProcessTransition(target="x")
        assert t.params == {}
        assert t.execute_now is False

    def test_process_result_defaults(self):
        """ProcessResult default output should be empty CognitiveOutput."""
        result = ProcessResult(dialogue="hi")
        assert result.output.is_empty
        assert result.transition is None


# ---------------------------------------------------------------------------
# H4: Process name validation
# ---------------------------------------------------------------------------

class TestProcessValidation:
    def test_discover_valid_processes(self, monkeypatch):
        """Should discover at least main, focused, frustrated processes."""
        import engine.process_router as pr
        monkeypatch.setattr(pr, "_valid_processes", None)  # Reset cache
        valid = _discover_valid_processes()
        assert "main_process" in valid
        assert "focused_process" in valid
        assert "frustrated_process" in valid

    def test_validate_process_accepts_valid(self, monkeypatch):
        """Known process names should validate."""
        import engine.process_router as pr
        monkeypatch.setattr(pr, "_valid_processes", None)
        assert _validate_process("main_process") is True

    def test_validate_process_rejects_invalid(self, monkeypatch):
        """Unknown process names should fail validation."""
        import engine.process_router as pr
        monkeypatch.setattr(pr, "_valid_processes", None)
        assert _validate_process("nonexistent_evil_process") is False

    def test_invalid_transition_target_rejected(self, snapshot, mock_main_process, monkeypatch):
        """Transition to invalid process should be ignored — currentProcess stays."""
        import engine.process_router as pr
        monkeypatch.setattr(pr, "_valid_processes", {"main_process", "focused_process", "frustrated_process"})

        soul_memory.set("currentProcess", "main_process")

        mock_main_process._results.append(ProcessResult(
            dialogue="bad transition",
            output=CognitiveOutput(),
            transition=ProcessTransition(target="nonexistent_xyz"),
        ))

        asyncio.get_event_loop().run_until_complete(
            route("hi", "user1", "ch", "ts", snapshot)
        )

        # currentProcess should NOT have changed
        assert soul_memory.get("currentProcess") == "main_process"


# ---------------------------------------------------------------------------
# H3: Params forwarding
# ---------------------------------------------------------------------------

class TestParamsForwarding:
    def test_params_forwarded_to_process_run(self, snapshot, monkeypatch):
        """Params passed to route() should reach process_module.run()."""
        received_params = []

        async def capturing_run(text, user_id, channel, thread_ts, snapshot, display_name=None, params=None):
            received_params.append(params)
            return ProcessResult(dialogue="got params", output=CognitiveOutput())

        import sys
        mod = types.ModuleType("processes.main_process")
        mod.run = capturing_run
        monkeypatch.setitem(sys.modules, "processes.main_process", mod)

        soul_memory.set("currentProcess", "main_process")
        asyncio.get_event_loop().run_until_complete(
            route("hi", "user1", "ch", "ts", snapshot, params={"topic": "test"})
        )

        assert received_params == [{"topic": "test"}]

    def test_execute_now_forwards_transition_params(self, snapshot, monkeypatch):
        """executeNow should pass transition.params to the target process."""
        received_params = []

        async def main_run(text, user_id, channel, thread_ts, snapshot, display_name=None, params=None):
            return ProcessResult(
                dialogue="chaining",
                output=CognitiveOutput(),
                transition=ProcessTransition(
                    target="focused_process",
                    params={"reason": "deep focus"},
                    execute_now=True,
                ),
            )

        async def focused_run(text, user_id, channel, thread_ts, snapshot, display_name=None, params=None):
            received_params.append(params)
            return ProcessResult(dialogue="focused", output=CognitiveOutput())

        import sys
        main_mod = types.ModuleType("processes.main_process")
        main_mod.run = main_run
        monkeypatch.setitem(sys.modules, "processes.main_process", main_mod)

        focused_mod = types.ModuleType("processes.focused_process")
        focused_mod.run = focused_run
        monkeypatch.setitem(sys.modules, "processes.focused_process", focused_mod)

        import engine.process_router as pr
        monkeypatch.setattr(pr, "_valid_processes", {"main_process", "focused_process", "frustrated_process"})

        soul_memory.set("currentProcess", "main_process")
        asyncio.get_event_loop().run_until_complete(
            route("hi", "user1", "ch", "ts", snapshot)
        )

        assert received_params == [{"reason": "deep focus"}]


# ---------------------------------------------------------------------------
# H2: Target process override
# ---------------------------------------------------------------------------

class TestTargetProcess:
    def test_route_respects_target_process(self, snapshot, mock_main_process, mock_focused_process):
        """target_process should override soul_memory currentProcess."""
        soul_memory.set("currentProcess", "main_process")

        result = asyncio.get_event_loop().run_until_complete(
            route("hi", "user1", "ch", "ts", snapshot, target_process="focused_process")
        )

        assert result.dialogue == "hello from focused"

    def test_route_empty_target_uses_soul_memory(self, snapshot, mock_main_process):
        """Empty target_process should fall through to soul_memory."""
        soul_memory.set("currentProcess", "main_process")

        result = asyncio.get_event_loop().run_until_complete(
            route("hi", "user1", "ch", "ts", snapshot, target_process="")
        )

        assert result.dialogue == "hello from main"


# ---------------------------------------------------------------------------
# H1: Internal flag threading
# ---------------------------------------------------------------------------

class TestInternalFlag:
    def test_apply_output_internal_suppresses_scheduling(self, isolate_databases, monkeypatch):
        """apply_output(internal=True) should NOT schedule events."""
        from memory.snapshot import apply_output, CognitiveOutput
        import scheduler

        output = CognitiveOutput().with_scheduled_event(
            action="reminder", content="test", delay_seconds=60,
        )

        monkeypatch.setattr("config.SCHEDULER_ENABLED", True)
        apply_output(output, "ch", "ts", internal=True)

        assert scheduler.count_pending() == 0

    def test_apply_output_external_allows_scheduling(self, isolate_databases, monkeypatch):
        """apply_output(internal=False) should schedule events."""
        from memory.snapshot import apply_output, CognitiveOutput
        import scheduler

        output = CognitiveOutput().with_scheduled_event(
            action="reminder", content="test", delay_seconds=60,
        )

        monkeypatch.setattr("config.SCHEDULER_ENABLED", True)
        apply_output(output, "ch", "ts", internal=False)

        assert scheduler.count_pending() == 1

    def test_route_threads_internal_to_apply_output(self, snapshot, mock_main_process, monkeypatch):
        """route(internal=True) should pass internal=True to apply_output()."""
        apply_calls = []
        original_apply = __import__("memory.snapshot", fromlist=["apply_output"]).apply_output

        def tracking_apply(output, channel, thread_ts, internal=False):
            apply_calls.append({"internal": internal})
            return original_apply(output, channel, thread_ts, internal=internal)

        monkeypatch.setattr("engine.process_router.apply_output", tracking_apply)

        soul_memory.set("currentProcess", "main_process")
        asyncio.get_event_loop().run_until_complete(
            route("hi", "user1", "ch", "ts", snapshot, internal=True)
        )

        assert apply_calls[0]["internal"] is True
