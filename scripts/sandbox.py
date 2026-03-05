#!/usr/bin/env python3
"""Claudicle Cognitive Sandbox — isolated pipeline testing.

Run the full Claudicle cognitive pipeline in a sandbox environment where
you can watch every step fire, every working memory entry form, and every
gate decision — without touching production databases.

Generalizes the isolation pattern from test-reflect.py to the full
forward pipeline (both unified and split modes).

Usage:
    uv run scripts/sandbox.py --message "Hello, who are you?"
    uv run scripts/sandbox.py --message "Hello" --user-id U_TEST --user-name "TestUser"
    uv run scripts/sandbox.py --message "Hello" --mode split
    uv run scripts/sandbox.py --message "Hello" --provider groq --model moonshotai/kimi-k2-instruct
    uv run scripts/sandbox.py --message "Hello" --keep
    uv run scripts/sandbox.py --message "Hello" --soul /path/to/custom-soul.md
    uv run scripts/sandbox.py --message "Hello" --daimonic
    uv run scripts/sandbox.py --scenario first-meeting
    uv run scripts/sandbox.py --repl
"""

import argparse
import json
import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

# ---------------------------------------------------------------------------
# 1. Create temp dir and set env vars BEFORE any daemon imports
# ---------------------------------------------------------------------------

_temp_dir: str = ""
_keep: bool = False
_daimonic_enabled: bool = False
_soul_file: str = ""  # Custom soul.md path (empty = use default)
_prev_um_sizes: dict[str, int] = {}  # Track user model size deltas


def _init_sandbox(keep: bool = False) -> str:
    """Create isolated sandbox directory and set env vars before daemon imports."""
    global _temp_dir, _keep
    _keep = keep
    _temp_dir = tempfile.mkdtemp(prefix="claudicle-sandbox-")

    # Set env vars BEFORE importing anything from daemon
    os.environ["CLAUDICLE_SOUL_LOG"] = os.path.join(_temp_dir, "soul-stream.jsonl")
    os.environ["CLAUDICLE_WM_STREAM_PATH"] = os.path.join(_temp_dir, "wm-stream.jsonl")

    # Memory subdirectories
    memory_dir = os.path.join(_temp_dir, "memory")
    os.makedirs(os.path.join(memory_dir, "users"), exist_ok=True)
    os.makedirs(os.path.join(memory_dir, "dossiers", "people"), exist_ok=True)
    os.makedirs(os.path.join(memory_dir, "dossiers", "subjects"), exist_ok=True)

    return _temp_dir


def _apply_patches(soul_path: str = "", daimonic_enabled: bool = False):
    """Monkeypatch daemon modules to use sandbox storage.

    Must be called AFTER _init_sandbox() and AFTER adding daemon to sys.path.
    Follows the same pattern as scripts/test-reflect.py.
    """
    global _daimonic_enabled, _soul_file
    _daimonic_enabled = daimonic_enabled
    _soul_file = soul_path

    temp_db = os.path.join(_temp_dir, "memory.db")
    temp_sessions_db = os.path.join(_temp_dir, "sessions.db")
    memory_dir = os.path.join(_temp_dir, "memory")

    # Patch ConnectionPool instances — the only live DB path.
    # Module-level DB_PATH attrs are dead exports; the pool owns the path.
    import threading
    from memory.db import memory_pool, session_pool
    memory_pool.db_path = temp_db
    memory_pool.reset_local()
    session_pool.db_path = temp_sessions_db
    session_pool.reset_local()

    # Reset soul_memory migration flag so fresh DB gets schema
    from memory import soul_memory
    if hasattr(soul_memory, "_migrated"):
        soul_memory._migrated = False

    # Reset trace_id stash to prevent bleed across cycles
    from engine import soul_engine
    soul_engine._trace_local = threading.local()

    # Disable onboarding and git-backed memory versioning
    import config
    config.ONBOARDING_ENABLED = False
    config.MEMORY_GIT_ENABLED = False

    # Patch git tracker to temp dir
    from memory import git_tracker
    git_tracker.MEMORY_DIR = Path(memory_dir)
    git_tracker.USERS_DIR = Path(memory_dir) / "users"
    git_tracker.DOSSIERS_PEOPLE_DIR = Path(memory_dir) / "dossiers" / "people"
    git_tracker.DOSSIERS_SUBJECTS_DIR = Path(memory_dir) / "dossiers" / "subjects"
    git_tracker._repo_initialized = False

    # Patch stream paths
    from monitoring import soul_log, wm_stream
    soul_log.LOG_PATH = os.path.join(_temp_dir, "soul-stream.jsonl")
    wm_stream.WM_STREAM_PATH = os.path.join(_temp_dir, "wm-stream.jsonl")

    # Daimonic: mock or initialize based on --daimonic flag
    if not daimonic_enabled:
        import daimonic
        daimonic.format_for_prompt = lambda: ""
        daimonic.consume_all_whispers = lambda: None
    else:
        from daimonic import registry as daimon_registry
        daimon_registry.load_from_config()
        # Force-enable all registered daimons in Groq-only mode
        for daimon in daimon_registry._registry.values():
            daimon.enabled = True
            daimon.daemon_host = ""
            daimon.daemon_port = 0
            daimon.groq_enabled = True

    # Reset context caches so sandbox gets fresh state
    from engine import context
    context._soul_cache = None
    context._skills_cache = None
    context._interaction_count = 0

    # Custom soul override
    if soul_path:
        abs_soul = os.path.abspath(soul_path)
        if not os.path.isfile(abs_soul):
            print(f"{_RED}Warning: soul file not found: {abs_soul}{_RESET}")
        else:
            context._SOUL_MD_PATH = abs_soul


# ---------------------------------------------------------------------------
# 2. Structured output rendering
# ---------------------------------------------------------------------------

# ANSI color codes (no Rich dependency needed)
_BOLD = "\033[1m"
_DIM = "\033[2m"
_RESET = "\033[0m"
_CYAN = "\033[36m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_RED = "\033[31m"
_MAGENTA = "\033[35m"
_BLUE = "\033[34m"

_BOX_TL = "\u256d"
_BOX_TR = "\u256e"
_BOX_BL = "\u2570"
_BOX_BR = "\u256f"
_BOX_H = "\u2500"
_BOX_V = "\u2502"


def _box(title: str, lines: list[str], width: int = 70) -> str:
    """Render a bordered box with title."""
    top = f"{_BOX_TL}{_BOX_H} {_BOLD}{title}{_RESET} {_BOX_H * (width - len(title) - 4)}{_BOX_TR}"
    bottom = f"{_BOX_BL}{_BOX_H * (width - 1)}{_BOX_BR}"
    body = []
    for line in lines:
        # Truncate visible content but allow ANSI codes
        body.append(f"{_BOX_V} {line}")
    return "\n".join([top] + body + [bottom])


def _render_step(label: str, icon: str, content: str, color: str = _CYAN) -> str:
    """Render a single cognitive step."""
    preview = content[:200].replace("\n", " ")
    if len(content) > 200:
        preview += "..."
    return f"  {icon} {color}{_BOLD}{label}{_RESET}: {preview}"


def _render_gate(name: str, result: bool, detail: str = "") -> str:
    """Render a gate decision."""
    status = f"{_GREEN}true{_RESET}" if result else f"{_DIM}false (skipped){_RESET}"
    line = f"  {_YELLOW}GATE{_RESET}: {name} -> {status}"
    if result and detail:
        preview = detail[:150].replace("\n", " ")
        line += f"\n    {_DIM}-> {preview}{_RESET}"
    return line


def render_cycle(cycle_num: int, trace_id: str, parsed: dict, stats: dict) -> str:
    """Render a full cognitive cycle as structured terminal output."""
    lines = []

    # Core steps
    if parsed.get("stimulus_verb"):
        lines.append(_render_step("stimulus_verb", "*", f'"{parsed["stimulus_verb"]}"', _MAGENTA))
    if parsed.get("internal_monologue"):
        verb = parsed.get("monologue_verb", "thought")
        lines.append(_render_step(f"internal_monologue ({verb})", "#", parsed["internal_monologue"]))
    if parsed.get("external_dialogue"):
        verb = parsed.get("dialogue_verb", "said")
        lines.append(_render_step(f"external_dialogue ({verb})", ">", parsed["external_dialogue"], _GREEN))
    lines.append("")

    # Context decisions (Samantha-Dreams, skills injection, dossiers)
    decisions = stats.get("decisions", [])
    if decisions:
        for content, result in decisions:
            status = f"{_GREEN}true{_RESET}" if result else f"{_DIM}false{_RESET}"
            lines.append(f"  {_BLUE}CONTEXT{_RESET}: {content} -> {status}")
        lines.append("")

    # Whispers (daimonic mode)
    whispers = parsed.get("whispers", [])
    if whispers:
        for source, whisper in whispers:
            preview = whisper[:150].replace("\n", " ")
            lines.append(f"  {_MAGENTA}WHISPER{_RESET} ({source}): {preview}")
        lines.append("")

    # Gates
    model_check = parsed.get("user_model_check", False)
    lines.append(_render_gate("user_model_check", model_check, parsed.get("user_model_update", "")))
    if parsed.get("user_model_reflection"):
        lines.append(f"    {_DIM}reflection: {parsed['user_model_reflection'][:100]}{_RESET}")

    if "dossier_check" in parsed:
        lines.append(_render_gate("dossier_check", parsed["dossier_check"], parsed.get("dossier_update", "")))

    if "soul_state_check" in parsed:
        lines.append(_render_gate("soul_state_check", parsed["soul_state_check"], parsed.get("soul_state_update", "")))

    lines.append("")

    # Stats
    wm_count = stats.get("wm_entries", 0)
    um_size = stats.get("user_model_size", 0)
    um_delta = stats.get("user_model_delta", 0)
    ss_keys = stats.get("soul_state_keys", 0)
    interaction = stats.get("interaction_count", 0)

    lines.append(f"  {_BLUE}Working Memory{_RESET}: {wm_count} entries")
    delta_str = f" ({_GREEN}+{um_delta}{_RESET})" if um_delta > 0 else (f" ({_RED}{um_delta}{_RESET})" if um_delta < 0 else "")
    lines.append(f"  {_BLUE}User Model{_RESET}: {um_size:,} bytes{delta_str}")
    lines.append(f"  {_BLUE}Soul State{_RESET}: {ss_keys} keys")
    lines.append(f"  {_BLUE}Interaction{_RESET}: #{interaction}")

    title = f"Cognitive Cycle #{cycle_num} -- trace: {trace_id}"
    return _box(title, lines)


# ---------------------------------------------------------------------------
# 3. Pipeline runners
# ---------------------------------------------------------------------------

def _get_db_stats(user_id: str, trace_id: str = "") -> dict:
    """Read sandbox DB for current stats."""
    temp_db = os.path.join(_temp_dir, "memory.db")
    stats = {"wm_entries": 0, "user_model_size": 0, "user_model_delta": 0,
             "soul_state_keys": 0, "decisions": [], "interaction_count": 0}
    try:
        conn = sqlite3.connect(temp_db)
        stats["wm_entries"] = conn.execute("SELECT count(*) FROM working_memory").fetchone()[0]
        row = conn.execute("SELECT model_md FROM user_models WHERE user_id = ?", (user_id,)).fetchone()
        if row:
            stats["user_model_size"] = len(row[0])
        stats["soul_state_keys"] = conn.execute("SELECT count(*) FROM soul_memory").fetchone()[0]

        # User model size delta
        prev = _prev_um_sizes.get(user_id, 0)
        stats["user_model_delta"] = stats["user_model_size"] - prev
        _prev_um_sizes[user_id] = stats["user_model_size"]

        # Context decisions (Samantha-Dreams, skills, dossiers) from this trace
        if trace_id:
            decision_rows = conn.execute(
                "SELECT content, metadata FROM working_memory WHERE entry_type='decision' AND trace_id=?",
                (trace_id,),
            ).fetchall()
            for content, meta_raw in decision_rows:
                result = False
                if meta_raw:
                    try:
                        m = json.loads(meta_raw) if isinstance(meta_raw, str) else meta_raw
                        result = bool(m.get("result", False))
                    except (json.JSONDecodeError, TypeError):
                        pass
                stats["decisions"].append((content, result))

        conn.close()
    except Exception:
        pass

    # Interaction count from context module
    try:
        from engine import context
        stats["interaction_count"] = context._interaction_count
    except Exception:
        pass

    return stats


def _parse_output_to_dict(dialogue: str, output, whisper_results: list = None) -> dict:
    """Extract parsed fields from CognitiveOutput for rendering."""
    parsed = {}

    # Walk the entries in the output
    for entry in output.entries:
        et = entry.entry_type
        if et == "internalMonologue":
            parsed["internal_monologue"] = entry.content
            parsed["monologue_verb"] = entry.verb or "thought"
        elif et == "externalDialog":
            parsed["external_dialogue"] = entry.content
            parsed["dialogue_verb"] = entry.verb or "said"
        elif et == "mentalQuery":
            content_lower = (entry.content or "").lower()
            if "user model" in content_lower:
                parsed["user_model_check"] = bool((entry.metadata or {}).get("result", False))
            elif "dossier" in content_lower:
                parsed["dossier_check"] = bool((entry.metadata or {}).get("result", False))
            elif "soul state" in content_lower:
                parsed["soul_state_check"] = bool((entry.metadata or {}).get("result", False))

    # User model update
    if output.user_model_update:
        parsed["user_model_update"] = output.user_model_update[:200]

    # User model reflection
    for entry in output.entries:
        if entry.entry_type == "internalMonologue" and "reflection" in (entry.verb or "").lower():
            parsed["user_model_reflection"] = entry.content

    # Soul state updates
    if output.soul_state_updates:
        parsed["soul_state_update"] = "\n".join(
            f"{k}: {v}" for k, v in output.soul_state_updates.items()
        )

    # Stimulus verb
    for entry in output.entries:
        if entry.entry_type == "decision" and "stimulus" in (entry.content or "").lower():
            parsed["stimulus_verb"] = (entry.metadata or {}).get("verb", "")

    if dialogue and "external_dialogue" not in parsed:
        parsed["external_dialogue"] = dialogue

    # Whisper results (daimonic mode)
    if whisper_results:
        parsed["whispers"] = whisper_results

    return parsed


def run_unified(
    text: str,
    user_id: str,
    channel: str,
    thread_ts: str,
    display_name: str = "",
    provider: str = "",
    model: str = "",
) -> tuple[str, dict, str]:
    """Run a single message through the unified pipeline.

    Returns (dialogue, parsed_dict, trace_id).
    """
    from engine import soul_engine
    from engine.llm_client import call_llm
    from memory import working_memory

    # Pre-cycle whisper invocation (daimonic mode)
    whisper_results = []
    if _daimonic_enabled:
        try:
            import asyncio
            from daimonic.whispers import invoke_all_whisperers, store_whisper
            context_for_whispers = {"message": text, "user_id": user_id, "channel": channel}
            results = asyncio.run(invoke_all_whisperers(context_for_whispers))
            for display, whisper in results:
                store_whisper(whisper, source=display, channel=channel, thread_ts=thread_ts)
                whisper_results.append((display, whisper))
        except Exception as e:
            print(f"  {_YELLOW}Daimonic whisper error: {e}{_RESET}")

    trace_id = working_memory.new_trace_id()
    prompt = soul_engine.build_prompt(
        text, user_id, channel, thread_ts,
        display_name=display_name or None,
        trace_id=trace_id,
    )

    # Call LLM
    provider = provider or "groq"
    model = model or "moonshotai/kimi-k2-instruct"
    raw_response = call_llm(prompt, provider=provider, model=model)

    # Parse cognitive response (pure) then apply side effects
    dialogue, output = soul_engine.parse_cognitive_response(
        raw_response, user_id, trace_id,
    )
    from memory.snapshot import apply_output
    apply_output(output, channel, thread_ts)

    parsed = _parse_output_to_dict(dialogue, output, whisper_results)
    return dialogue, parsed, trace_id


def run_message(
    text: str,
    user_id: str = "U_SANDBOX",
    user_name: str = "SandboxUser",
    channel: str = "sandbox:test",
    mode: str = "unified",
    provider: str = "",
    model: str = "",
    cycle_num: int = 1,
) -> str:
    """Run a single message and return rendered output."""
    thread_ts = "sandbox-session"

    if mode != "unified":
        print(f"{_YELLOW}Note: split mode not yet wired — using unified pipeline{_RESET}")
    dialogue, parsed, trace_id = run_unified(
        text, user_id, channel, thread_ts,
        display_name=user_name,
        provider=provider, model=model,
    )

    stats = _get_db_stats(user_id, trace_id)
    output = render_cycle(cycle_num, trace_id, parsed, stats)
    return output


# ---------------------------------------------------------------------------
# 4. REPL commands
# ---------------------------------------------------------------------------

def _cmd_wm(args: str = "") -> str:
    """Show working memory entries."""
    temp_db = os.path.join(_temp_dir, "memory.db")
    conn = sqlite3.connect(temp_db)
    conn.row_factory = sqlite3.Row

    query = "SELECT entry_type, verb, content, trace_id, user_id FROM working_memory ORDER BY created_at"
    params: list = []

    # Filter by type
    if args.startswith("--type "):
        entry_type = args.split("--type ", 1)[1].strip()
        query = "SELECT entry_type, verb, content, trace_id, user_id FROM working_memory WHERE entry_type = ? ORDER BY created_at"
        params = [entry_type]

    rows = conn.execute(query, params).fetchall()
    conn.close()

    if not rows:
        return f"{_DIM}No working memory entries.{_RESET}"

    lines = [f"{_BOLD}Working Memory ({len(rows)} entries){_RESET}", ""]
    for row in rows:
        label = row["entry_type"]
        if row["verb"]:
            label += f" ({row['verb']})"
        preview = (row["content"] or "")[:150].replace("\n", " ")
        trace = row["trace_id"] or "?"
        lines.append(f"  [{_CYAN}{label}{_RESET}] {_DIM}trace:{trace}{_RESET}")
        lines.append(f"    {preview}")
        lines.append("")

    return "\n".join(lines)


def _cmd_user_model(user_id: str = "U_SANDBOX") -> str:
    """Show current user model with frontmatter parsing."""
    temp_db = os.path.join(_temp_dir, "memory.db")
    conn = sqlite3.connect(temp_db)
    row = conn.execute("SELECT model_md FROM user_models WHERE user_id = ?", (user_id,)).fetchone()
    conn.close()
    if not row:
        return f"{_DIM}No user model for {user_id}.{_RESET}"

    model_md = row[0]
    lines = [f"{_BOLD}User Model: {user_id}{_RESET}", ""]

    # Parse YAML frontmatter if present
    if model_md.startswith("---"):
        parts = model_md.split("---", 2)
        if len(parts) >= 3:
            frontmatter = parts[1].strip()
            lines.append(f"  {_CYAN}Frontmatter:{_RESET}")
            for fm_line in frontmatter.split("\n"):
                fm_line = fm_line.strip()
                if fm_line:
                    lines.append(f"    {fm_line}")
            lines.append("")

    lines.append(model_md)
    return "\n".join(lines)


def _cmd_user_model_history() -> str:
    """Show user model check history across all cycles."""
    temp_db = os.path.join(_temp_dir, "memory.db")
    conn = sqlite3.connect(temp_db)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT trace_id, content, metadata FROM working_memory "
        "WHERE entry_type='mentalQuery' AND content LIKE '%user model%' "
        "ORDER BY created_at",
    ).fetchall()
    conn.close()

    if not rows:
        return f"{_DIM}No user model checks recorded.{_RESET}"

    lines = [f"{_BOLD}User Model Check History ({len(rows)} checks){_RESET}", ""]
    for row in rows:
        trace = row["trace_id"] or "?"
        meta_raw = row["metadata"]
        result = False
        if meta_raw:
            try:
                m = json.loads(meta_raw) if isinstance(meta_raw, str) else meta_raw
                result = bool(m.get("result", False))
            except (json.JSONDecodeError, TypeError):
                pass
        status = f"{_GREEN}true (updated){_RESET}" if result else f"{_DIM}false (skipped){_RESET}"
        lines.append(f"  {_DIM}trace:{trace}{_RESET}  {status}")

    return "\n".join(lines)


def _cmd_soul_state() -> str:
    """Show soul state."""
    temp_db = os.path.join(_temp_dir, "memory.db")
    conn = sqlite3.connect(temp_db)
    try:
        rows = conn.execute("SELECT key, value FROM soul_memory ORDER BY key").fetchall()
    except sqlite3.OperationalError:
        conn.close()
        return f"{_DIM}No soul state table.{_RESET}"
    conn.close()
    if not rows:
        return f"{_DIM}Soul state is empty.{_RESET}"
    lines = [f"{_BOLD}Soul State ({len(rows)} keys){_RESET}", ""]
    for key, value in rows:
        lines.append(f"  {_CYAN}{key}{_RESET}: {value}")
    return "\n".join(lines)


def _cmd_soul_log() -> str:
    """Show soul stream JSONL."""
    stream_path = os.path.join(_temp_dir, "soul-stream.jsonl")
    if not os.path.exists(stream_path) or os.path.getsize(stream_path) == 0:
        return f"{_DIM}No soul stream entries.{_RESET}"
    lines = [f"{_BOLD}Soul Stream{_RESET}", ""]
    with open(stream_path) as f:
        for raw_line in f:
            entry = json.loads(raw_line)
            phase = entry.get("phase", "?")
            summary = json.dumps({k: v for k, v in entry.items() if k != "phase"}, default=str)[:120]
            lines.append(f"  {_MAGENTA}{phase}{_RESET}: {summary}")
    return "\n".join(lines)


def _cmd_trace(trace_id: str) -> str:
    """Show all entries for a specific trace_id."""
    temp_db = os.path.join(_temp_dir, "memory.db")
    conn = sqlite3.connect(temp_db)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT entry_type, verb, content FROM working_memory WHERE trace_id = ? ORDER BY created_at",
        (trace_id,),
    ).fetchall()
    conn.close()
    if not rows:
        return f"{_DIM}No entries for trace {trace_id}.{_RESET}"
    lines = [f"{_BOLD}Trace: {trace_id} ({len(rows)} entries){_RESET}", ""]
    for row in rows:
        label = row["entry_type"]
        if row["verb"]:
            label += f" ({row['verb']})"
        preview = (row["content"] or "")[:200].replace("\n", " ")
        lines.append(f"  [{_CYAN}{label}{_RESET}]")
        lines.append(f"    {preview}")
        lines.append("")
    return "\n".join(lines)


def _cmd_soul() -> str:
    """Show active soul path and first 10 lines."""
    try:
        from engine import context
        soul_path = context._SOUL_MD_PATH
    except Exception:
        return f"{_DIM}Cannot determine soul path.{_RESET}"

    is_custom = bool(_soul_file)
    label = "custom" if is_custom else "default"
    lines = [f"{_BOLD}Soul ({label}){_RESET}: {soul_path}", ""]

    try:
        with open(soul_path) as f:
            for i, line in enumerate(f):
                if i >= 10:
                    lines.append(f"  {_DIM}... (truncated){_RESET}")
                    break
                lines.append(f"  {line.rstrip()}")
    except FileNotFoundError:
        lines.append(f"  {_RED}File not found{_RESET}")

    return "\n".join(lines)


def _cmd_soul_switch(new_path: str) -> str:
    """Hot-swap soul mid-REPL session."""
    abs_path = os.path.abspath(new_path)
    if not os.path.isfile(abs_path):
        return f"{_RED}File not found: {abs_path}{_RESET}"

    global _soul_file
    _soul_file = abs_path

    from engine import context
    context._SOUL_MD_PATH = abs_path
    context._soul_cache = None  # Force re-read

    return f"{_GREEN}Soul switched to: {abs_path}{_RESET}"


def _cmd_daimonic() -> str:
    """Show daimon registry status."""
    if not _daimonic_enabled:
        return f"{_DIM}Daimonic mode is disabled. Use --daimonic flag to enable.{_RESET}"

    try:
        from daimonic import registry as daimon_registry
        enabled = daimon_registry.get_enabled()
        if not enabled:
            return f"{_DIM}No enabled daimons.{_RESET}"

        lines = [f"{_BOLD}Daimon Registry ({len(enabled)} enabled){_RESET}", ""]
        for d in enabled:
            lines.append(f"  {_CYAN}{d.display_name}{_RESET} ({d.name})")
            lines.append(f"    Mode: {d.mode}, Groq: {d.groq_enabled}, Model: {d.groq_model}")
            if d.whisper_suffix:
                preview = d.whisper_suffix[:100].replace("\n", " ").strip()
                lines.append(f"    Suffix: {_DIM}{preview}...{_RESET}")
            lines.append("")
        return "\n".join(lines)
    except Exception as e:
        return f"{_RED}Error reading registry: {e}{_RESET}"


def _cmd_whispers() -> str:
    """Show all active whispers from soul_memory."""
    temp_db = os.path.join(_temp_dir, "memory.db")
    try:
        conn = sqlite3.connect(temp_db)
        rows = conn.execute(
            "SELECT key, value FROM soul_memory WHERE key LIKE 'daimonic_whisper%' ORDER BY key"
        ).fetchall()
        conn.close()
    except Exception:
        return f"{_DIM}No soul memory table.{_RESET}"

    whispers = [(k, v) for k, v in rows if v and v.strip()]
    if not whispers:
        return f"{_DIM}No active whispers.{_RESET}"

    lines = [f"{_BOLD}Active Whispers{_RESET}", ""]
    for key, value in whispers:
        source = key.replace("daimonic_whisper_", "").replace("daimonic_whisper", "legacy")
        lines.append(f"  {_MAGENTA}{source}{_RESET}: {value}")
        lines.append("")
    return "\n".join(lines)


def _cmd_subdaimones() -> str:
    """List subdaimon definitions from /subdaimones/*.md."""
    # Find subdaimones directory relative to the repo
    script_dir = os.path.dirname(os.path.abspath(__file__))
    repo_dir = os.path.dirname(script_dir)
    subdaimones_dir = os.path.join(repo_dir, "subdaimones")

    if not os.path.isdir(subdaimones_dir):
        return f"{_DIM}No subdaimones directory found at {subdaimones_dir}.{_RESET}"

    lines = [f"{_BOLD}Subdaimones{_RESET} (informational — cannot run in sandbox)", ""]

    for fname in sorted(os.listdir(subdaimones_dir)):
        if not fname.endswith(".md") or fname == "README.md":
            continue
        name = fname.replace(".md", "")
        fpath = os.path.join(subdaimones_dir, fname)
        # Read first few lines for description
        description = ""
        tier = ""
        with open(fpath) as f:
            for line in f:
                line = line.strip()
                if line.startswith("tier:"):
                    tier = line.split(":", 1)[1].strip()
                elif line.startswith("description:"):
                    description = line.split(":", 1)[1].strip().strip('"')
                if tier and description:
                    break

        tier_label = f" [{tier}]" if tier else ""
        desc_label = f" — {description}" if description else ""
        lines.append(f"  {_CYAN}{name}{_RESET}{tier_label}{desc_label}")

    return "\n".join(lines)


def _cmd_reset():
    """Wipe sandbox memory and start fresh."""
    import threading

    temp_db = os.path.join(_temp_dir, "memory.db")
    temp_sessions_db = os.path.join(_temp_dir, "sessions.db")
    for db_path in [temp_db, temp_sessions_db]:
        if os.path.exists(db_path):
            os.unlink(db_path)

    # Clear streams
    for stream in ["soul-stream.jsonl", "wm-stream.jsonl"]:
        path = os.path.join(_temp_dir, stream)
        if os.path.exists(path):
            os.unlink(path)

    # Reset ConnectionPools so they reconnect to the (now fresh) DBs
    from memory.db import memory_pool, session_pool
    memory_pool.reset_local()
    session_pool.reset_local()

    # Reset soul_memory migration flag so schema gets recreated
    from memory import soul_memory
    if hasattr(soul_memory, "_migrated"):
        soul_memory._migrated = False

    # Reset trace_id stash to prevent bleed
    from engine import soul_engine
    soul_engine._trace_local = threading.local()

    # Reset context caches
    from engine import context
    context._soul_cache = None
    context._skills_cache = None
    context._interaction_count = 0

    # Reset user model size tracking
    _prev_um_sizes.clear()

    return f"{_GREEN}Sandbox reset.{_RESET}"


def _cmd_export() -> str:
    """Copy sandbox dir to a named location."""
    dest = os.path.join(os.path.expanduser("~"), ".claudicle", "sandbox-exports", os.path.basename(_temp_dir))
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    shutil.copytree(_temp_dir, dest)
    return f"{_GREEN}Exported to: {dest}{_RESET}"


# ---------------------------------------------------------------------------
# 5. Interactive REPL
# ---------------------------------------------------------------------------

def run_repl(
    user_id: str = "U_SANDBOX",
    user_name: str = "SandboxUser",
    channel: str = "sandbox:test",
    mode: str = "unified",
    provider: str = "",
    model: str = "",
):
    """Interactive REPL for sandbox testing."""
    cycle_num = 0

    # Resolve active soul path for banner
    try:
        from engine import context
        soul_display = context._SOUL_MD_PATH
    except Exception:
        soul_display = "unknown"
    soul_label = "custom" if _soul_file else "default"

    print(f"\n{_BOLD}Claudicle Cognitive Sandbox{_RESET}")
    print(f"  Temp dir: {_DIM}{_temp_dir}{_RESET}")
    print(f"  User: {user_name} ({user_id})")
    print(f"  Channel: {channel}")
    print(f"  Mode: {mode}")
    print(f"  Provider: {provider or 'groq'} / {model or 'moonshotai/kimi-k2-instruct'}")
    print(f"  Soul: {_DIM}{soul_display}{_RESET} ({soul_label})")
    print(f"  Daimonic: {'enabled' if _daimonic_enabled else 'disabled'}")
    print(f"\n  Commands: /wm, /user-model, /user-model-history, /soul-state, /soul-log,")
    print(f"           /trace <id>, /scenario <name>, /reset, /mode <mode>, /export,")
    print(f"           /soul, /soul-switch <path>, /daimonic, /whispers, /subdaimones, /quit")
    print(f"  Type a message to run a cognitive cycle.\n")

    while True:
        try:
            text = input(f"{_CYAN}sandbox>{_RESET} ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not text:
            continue

        if text == "/quit" or text == "/exit":
            break
        elif text == "/wm" or text.startswith("/wm "):
            args = text[3:].strip() if len(text) > 3 else ""
            print(_cmd_wm(args))
        elif text == "/user-model":
            print(_cmd_user_model(user_id))
        elif text == "/user-model-history":
            print(_cmd_user_model_history())
        elif text == "/soul-state":
            print(_cmd_soul_state())
        elif text == "/soul-log":
            print(_cmd_soul_log())
        elif text.startswith("/trace "):
            tid = text.split("/trace ", 1)[1].strip()
            print(_cmd_trace(tid))
        elif text.startswith("/scenario "):
            scenario_name = text.split("/scenario ", 1)[1].strip()
            _run_scenario(scenario_name, user_id, user_name, channel, mode, provider, model)
        elif text == "/reset":
            print(_cmd_reset())
            cycle_num = 0
        elif text.startswith("/mode "):
            mode = text.split("/mode ", 1)[1].strip()
            print(f"  Mode set to: {_BOLD}{mode}{_RESET}")
        elif text == "/export":
            print(_cmd_export())
        elif text == "/soul":
            print(_cmd_soul())
        elif text.startswith("/soul-switch "):
            new_path = text.split("/soul-switch ", 1)[1].strip()
            print(_cmd_soul_switch(new_path))
        elif text == "/daimonic":
            print(_cmd_daimonic())
        elif text == "/whispers":
            print(_cmd_whispers())
        elif text == "/subdaimones":
            print(_cmd_subdaimones())
        elif text.startswith("/"):
            print(f"  {_RED}Unknown command: {text}{_RESET}")
        else:
            cycle_num += 1
            try:
                output = run_message(
                    text, user_id=user_id, user_name=user_name,
                    channel=channel, mode=mode,
                    provider=provider, model=model,
                    cycle_num=cycle_num,
                )
                print(output)
            except Exception as e:
                print(f"  {_RED}Error: {e}{_RESET}")
                import traceback
                traceback.print_exc()


# ---------------------------------------------------------------------------
# 6. Scenario runner
# ---------------------------------------------------------------------------

def _run_scenario(
    name: str,
    user_id: str = "U_SANDBOX",
    user_name: str = "SandboxUser",
    channel: str = "sandbox:test",
    mode: str = "unified",
    provider: str = "",
    model: str = "",
):
    """Run a canned multi-turn scenario."""
    try:
        from sandbox_scenarios import SCENARIOS
    except ImportError:
        # Try relative import
        scenario_dir = os.path.dirname(os.path.abspath(__file__))
        sys.path.insert(0, scenario_dir)
        from sandbox_scenarios import SCENARIOS

    if name not in SCENARIOS:
        print(f"  {_RED}Unknown scenario: {name}{_RESET}")
        print(f"  Available: {', '.join(SCENARIOS.keys())}")
        return

    scenario = SCENARIOS[name]
    print(f"\n{_BOLD}Scenario: {name}{_RESET}")
    print(f"  {_DIM}{scenario['description']}{_RESET}\n")

    # Apply soul_path override if scenario specifies one
    if "soul_path" in scenario:
        result = _cmd_soul_switch(scenario["soul_path"])
        print(f"  {_DIM}{result}{_RESET}")

    # Apply setup if present (pre-seed user model, etc.)
    if "setup" in scenario:
        setup = scenario["setup"]
        from memory import user_models
        uid = setup.get("user_id", user_id)
        uname = setup.get("user_name", user_name)
        if "model_md" in setup:
            user_models.save(uid, setup["model_md"], uname)
            print(f"  {_DIM}Pre-seeded user model for {uid}{_RESET}")

    scenario_channel = scenario.get("channel", channel)

    for i, msg in enumerate(scenario["messages"], 1):
        msg_text = msg["text"]
        msg_uid = msg.get("user_id", user_id)
        msg_name = msg.get("user_name", user_name)

        print(f"  {_DIM}--- Message {i}: {msg_name}: {msg_text[:60]} ---{_RESET}\n")

        try:
            output = run_message(
                msg_text, user_id=msg_uid, user_name=msg_name,
                channel=scenario_channel, mode=mode,
                provider=provider, model=model,
                cycle_num=i,
            )
            print(output)
            print()
        except Exception as e:
            print(f"  {_RED}Error on message {i}: {e}{_RESET}")
            import traceback
            traceback.print_exc()
            break

    print(f"{_GREEN}Scenario '{name}' complete.{_RESET}\n")


# ---------------------------------------------------------------------------
# 7. CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Claudicle Cognitive Sandbox — isolated pipeline testing",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--message", "-m", type=str, help="Single message to process")
    parser.add_argument("--scenario", "-s", type=str, help="Run a canned scenario by name")
    parser.add_argument("--repl", action="store_true", help="Start interactive REPL")
    parser.add_argument("--user-id", default="U_SANDBOX", help="User ID (default: U_SANDBOX)")
    parser.add_argument("--user-name", default="SandboxUser", help="Display name (default: SandboxUser)")
    parser.add_argument("--channel", default="sandbox:test", help="Channel ID (default: sandbox:test)")
    parser.add_argument("--mode", choices=["unified", "split"], default="unified", help="Pipeline mode")
    parser.add_argument("--provider", default="", help="LLM provider (default: groq)")
    parser.add_argument("--model", default="", help="LLM model (default: moonshotai/kimi-k2-instruct)")
    parser.add_argument("--keep", action="store_true", help="Keep sandbox dir after exit")
    parser.add_argument("--soul", type=str, default="", help="Custom soul.md file path")
    parser.add_argument("--daimonic", action="store_true", help="Enable daimonic whispers via Groq")
    parser.add_argument("--list-scenarios", action="store_true", help="List available scenarios")

    args = parser.parse_args()

    # List scenarios without sandbox setup
    if args.list_scenarios:
        scripts_dir = os.path.dirname(os.path.abspath(__file__))
        sys.path.insert(0, scripts_dir)
        try:
            from sandbox_scenarios import SCENARIOS
            print(f"\n{_BOLD}Available Scenarios{_RESET}\n")
            for name, scenario in SCENARIOS.items():
                n_msgs = len(scenario.get("messages", []))
                print(f"  {_CYAN}{name}{_RESET}: {scenario['description']} ({n_msgs} messages)")
            print()
        except ImportError:
            print("No sandbox_scenarios.py found.")
        return

    if not args.message and not args.scenario and not args.repl:
        parser.print_help()
        return

    # Initialize sandbox
    _init_sandbox(keep=args.keep)

    # Add daemon to path
    claudicle_home = os.environ.get("CLAUDICLE_HOME", os.path.expanduser("~/.claudicle"))
    daemon_dir = os.path.join(claudicle_home, "daemon")
    if not os.path.isdir(daemon_dir):
        # Try relative path from script location
        daemon_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "daemon")
    sys.path.insert(0, daemon_dir)

    # Apply isolation patches
    _apply_patches(soul_path=args.soul, daimonic_enabled=args.daimonic)

    # Resolve active soul for banner
    try:
        from engine import context
        soul_display = context._SOUL_MD_PATH
    except Exception:
        soul_display = "unknown"
    soul_label = "custom" if args.soul else "default"

    print(f"\n{_BOLD}Claudicle Cognitive Sandbox{_RESET}")
    print(f"  Temp dir: {_DIM}{_temp_dir}{_RESET}")
    print(f"  Soul: {_DIM}{soul_display}{_RESET} ({soul_label})")
    if args.daimonic:
        print(f"  Daimonic: {_GREEN}enabled{_RESET}")

    try:
        if args.message:
            output = run_message(
                args.message,
                user_id=args.user_id,
                user_name=args.user_name,
                channel=args.channel,
                mode=args.mode,
                provider=args.provider,
                model=args.model,
            )
            print(output)

        elif args.scenario:
            _run_scenario(
                args.scenario,
                user_id=args.user_id,
                user_name=args.user_name,
                channel=args.channel,
                mode=args.mode,
                provider=args.provider,
                model=args.model,
            )

        elif args.repl:
            run_repl(
                user_id=args.user_id,
                user_name=args.user_name,
                channel=args.channel,
                mode=args.mode,
                provider=args.provider,
                model=args.model,
            )

    except KeyboardInterrupt:
        print(f"\n{_DIM}Interrupted.{_RESET}")
    except Exception as e:
        print(f"\n{_RED}Error: {e}{_RESET}")
        import traceback
        traceback.print_exc()
    finally:
        if args.keep or _keep:
            print(f"\n  Sandbox preserved: {_BOLD}{_temp_dir}{_RESET}")
            print(f"  Inspect: sqlite3 {_temp_dir}/memory.db '.tables'")
            print(f"  Stream:  cat {_temp_dir}/soul-stream.jsonl | python3 -m json.tool")
        else:
            shutil.rmtree(_temp_dir, ignore_errors=True)
            print(f"\n  {_DIM}Sandbox cleaned up. Use --keep to preserve.{_RESET}")


if __name__ == "__main__":
    main()
