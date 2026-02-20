"""
Claude Code invocation handler.

Two modes:
  1. process()       — subprocess `claude -p` (legacy, used by bot.py)
  2. async_process() — Claude Agent SDK `query()` (used by claudicle.py)

Thread-level sessions are stored in SQLite so multi-turn conversations
resume the same Claude context.

When the soul engine is enabled, prompts are wrapped with cognitive
instructions and responses are parsed for structured output.
"""

import json
import logging
import os
import subprocess
import time
from typing import Optional

from memory import session_store, session_index, working_memory
from engine import soul_engine
from monitoring import soul_log
import session_title
from config import (
    CLAUDE_ALLOWED_TOOLS,
    CLAUDE_CWD,
    CLAUDE_TIMEOUT,
    MAX_RESPONSE_LENGTH,
    SOUL_ENGINE_ENABLED,
)

log = logging.getLogger("slack-daemon.handler")

# Path to soul-registry.py (for session registration + Slack binding)
_SOUL_REGISTRY = os.path.expanduser("~/.claude/hooks/soul-registry.py")


def _title_session(
    session_id: str,
    channel: str,
    text: str,
    channel_name: Optional[str] = None,
    thread_ts: Optional[str] = None,
    user_id: Optional[str] = None,
    display_name: Optional[str] = None,
    origin: str = "slack",
):
    """Auto-title a new session and register it in Claudicle's index."""
    # Build a descriptive title
    label = channel_name or channel
    snippet = text[:50].replace("\n", " ")
    if len(text) > 50:
        snippet += "..."
    title = f"Slack: #{label}\u2014{snippet}"

    # Write customTitle to Claude's sessions-index.json
    session_title.set_custom_title(session_id, title)

    # Register in Claudicle's own session index
    session_index.register(
        session_id=session_id,
        channel=channel,
        thread_ts=thread_ts or "",
        user_id=user_id or "",
        display_name=display_name,
        channel_name=channel_name,
        title=title,
        origin=origin,
    )

    # Register in soul registry + bind Slack channel (fire-and-forget)
    if os.path.exists(_SOUL_REGISTRY):
        log.debug("Spawning soul-registry register+bind for session %s", session_id[:8])
        try:
            subprocess.Popen(
                ["python3", _SOUL_REGISTRY, "register", session_id, str(CLAUDE_CWD)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            subprocess.Popen(
                ["python3", _SOUL_REGISTRY, "bind", session_id, channel, channel_name or channel],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError as e:
            log.warning("Failed to spawn soul-registry for session %s: %s", session_id[:8], e)


def process(
    text: str,
    channel: str,
    thread_ts: str,
    user_id: Optional[str] = None,
    channel_name: Optional[str] = None,
    display_name: Optional[str] = None,
) -> str:
    """
    Send text to Claude Code and return the response.

    Resumes a prior session if one exists for this thread.
    Saves the new session ID for future turns.
    When soul engine is enabled, wraps prompt with cognitive steps
    and parses structured output.
    """
    session_id = session_store.get(channel, thread_ts)

    stimulus_ts = time.time()
    trace_id = None

    # Build the prompt — stimulus emitted first so phase ordering is correct
    if SOUL_ENGINE_ENABLED and user_id:
        trace_id = working_memory.new_trace_id()
        soul_engine.store_user_message(text, user_id, channel, thread_ts, display_name=display_name or user_id)
        soul_log.emit(
            "stimulus", trace_id, channel=channel, thread_ts=thread_ts,
            origin="slack", user_id=user_id, display_name=display_name or user_id,
            text=text, text_length=len(text),
        )
        prompt = soul_engine.build_prompt(
            text, user_id=user_id, channel=channel, thread_ts=thread_ts,
            trace_id=trace_id,
        )
    else:
        prompt = text

    cmd = [
        "claude",
        "-p", prompt,
        "--output-format", "json",
        "--allowedTools", CLAUDE_ALLOWED_TOOLS,
    ]
    if session_id:
        cmd.extend(["--resume", session_id])

    log.info(
        "Invoking claude: channel=%s thread=%s resume=%s len=%d soul=%s",
        channel, thread_ts, session_id or "new", len(prompt),
        "on" if SOUL_ENGINE_ENABLED else "off",
    )

    # Build env with guaranteed PATH for launchd contexts
    env = os.environ.copy()
    env["PATH"] = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:" + env.get("PATH", "")
    # Remove all Claude Code session vars so claude -p doesn't detect a nested session
    for key in list(env):
        if key.startswith("CLAUDE_CODE_") or key == "CLAUDECODE":
            env.pop(key)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=CLAUDE_TIMEOUT,
            cwd=CLAUDE_CWD,
            env=env,
        )
    except subprocess.TimeoutExpired:
        log.warning("Claude timed out after %ds", CLAUDE_TIMEOUT)
        if trace_id:
            soul_log.emit(
                "error", trace_id, channel=channel, thread_ts=thread_ts,
                source="claude_handler.process", error=f"Timed out after {CLAUDE_TIMEOUT}s",
                error_type="TimeoutExpired",
            )
        return f"Timed out after {CLAUDE_TIMEOUT}s. Try a simpler question or break it into steps."

    # Parse JSON output (Claude CLI returns JSON even on error)
    try:
        data = json.loads(result.stdout)
    except (json.JSONDecodeError, ValueError):
        if result.returncode != 0:
            stderr = result.stderr.strip()
            log.error("Claude failed (rc=%d) stderr: %s", result.returncode, stderr[:500])
            if trace_id:
                soul_log.emit(
                    "error", trace_id, channel=channel, thread_ts=thread_ts,
                    source="claude_handler.process", error=f"rc={result.returncode}: {stderr[:200]}",
                    error_type="SubprocessError",
                )
            return f"Error running Claude (exit {result.returncode}): {stderr[:200] or 'unknown error'}"
        log.error("Failed to parse Claude output: %s", result.stdout[:200])
        if trace_id:
            soul_log.emit(
                "error", trace_id, channel=channel, thread_ts=thread_ts,
                source="claude_handler.process", error="Failed to parse JSON output",
                error_type="JSONDecodeError",
            )
        return result.stdout.strip()[:MAX_RESPONSE_LENGTH] or "No response from Claude."

    # Handle structured errors (e.g. credit balance, auth failures)
    if data.get("is_error"):
        error_msg = data.get("result", "Unknown error")
        log.error("Claude returned error: %s", error_msg)
        if trace_id:
            soul_log.emit(
                "error", trace_id, channel=channel, thread_ts=thread_ts,
                source="claude_handler.process", error=error_msg[:500],
                error_type="ClaudeError",
            )
        return f"Claude error: {error_msg}"

    if result.returncode != 0:
        log.error("Claude failed (rc=%d): %s", result.returncode, data.get("result", "")[:500])
        if trace_id:
            soul_log.emit(
                "error", trace_id, channel=channel, thread_ts=thread_ts,
                source="claude_handler.process", error=f"rc={result.returncode}",
                error_type="SubprocessError",
            )
        return f"Error running Claude (exit {result.returncode}). Check daemon logs."

    # Persist session for thread continuity (only on success)
    new_session_id = data.get("session_id")
    if new_session_id and new_session_id != session_id:
        session_store.save(channel, thread_ts, new_session_id)
        _title_session(
            new_session_id, channel, text,
            channel_name=channel_name, thread_ts=thread_ts,
            user_id=user_id, display_name=display_name,
        )
    elif (session_id or new_session_id) and result.returncode == 0:
        session_store.touch(channel, thread_ts)
        session_index.touch(session_id or new_session_id)

    raw_response = data.get("result", "")
    if not raw_response:
        if trace_id:
            soul_log.emit(
                "error", trace_id, channel=channel, thread_ts=thread_ts,
                source="claude_handler.process", error="Empty response",
                error_type="EmptyResponse",
            )
        return "Claude returned an empty response."

    # Parse through soul engine or return raw
    if SOUL_ENGINE_ENABLED and user_id:
        response = soul_engine.parse_response(
            raw_response, user_id=user_id, channel=channel, thread_ts=thread_ts,
            trace_id=trace_id,
        )
    else:
        response = raw_response

    was_truncated = len(response) > MAX_RESPONSE_LENGTH
    if was_truncated:
        response = response[:MAX_RESPONSE_LENGTH] + "\n\n_(truncated)_"

    if trace_id:
        elapsed_ms = int((time.time() - stimulus_ts) * 1000)
        soul_log.emit(
            "response", trace_id, channel=channel, thread_ts=thread_ts,
            text=response, text_length=len(response),
            truncated=was_truncated, elapsed_ms=elapsed_ms,
        )

    return response


# ------------------------------------------------------------------
# SDK-based async handler (used by unified launcher)
# ------------------------------------------------------------------

async def async_process(
    text: str,
    channel: str,
    thread_ts: str,
    user_id: Optional[str] = None,
    soul_enabled: bool = True,
    allowed_tools: Optional[str] = None,
    origin: str = "slack",
    display_name: Optional[str] = None,
    channel_name: Optional[str] = None,
) -> str:
    """
    Process via Claude Agent SDK query() instead of subprocess.

    Uses resume= for session continuity. Soul engine wrapping is optional.
    """
    from claude_agent_sdk import (
        query,
        ClaudeAgentOptions,
        AssistantMessage,
        ResultMessage,
        TextBlock,
    )

    stimulus_ts = time.time()
    trace_id = None

    session_id = session_store.get(channel, thread_ts)
    tools = allowed_tools or CLAUDE_ALLOWED_TOOLS

    # Build the prompt
    use_soul = soul_enabled and SOUL_ENGINE_ENABLED and user_id

    # Split-mode pipeline: per-step routing to different providers
    if use_soul:
        from engine import pipeline
        if pipeline.is_split_mode():
            soul_engine.store_user_message(text, user_id, channel, thread_ts, display_name=display_name)
            split_trace_id = working_memory.new_trace_id()
            soul_log.emit(
                "stimulus", split_trace_id, channel=channel, thread_ts=thread_ts,
                origin=origin, user_id=user_id, display_name=display_name or user_id,
                text=text, text_length=len(text),
            )
            result = await pipeline.run_pipeline(
                text, user_id, channel, thread_ts,
            )
            response = result.dialogue
            was_truncated = len(response) > MAX_RESPONSE_LENGTH
            if was_truncated:
                response = response[:MAX_RESPONSE_LENGTH] + "\n\n_(truncated)_"
            elapsed_ms = int((time.time() - stimulus_ts) * 1000)
            soul_log.emit(
                "response", split_trace_id, channel=channel, thread_ts=thread_ts,
                text=response, text_length=len(response),
                truncated=was_truncated, elapsed_ms=elapsed_ms,
            )
            return response

    # Invoke daimon whispers before building prompt (so they're available in build_prompt)
    if use_soul:
        try:
            import daimonic
            context = daimonic.read_context(channel, thread_ts)
            whispers = await daimonic.invoke_all_whisperers(context)
            for name, whisper in whispers:
                daimonic.store_whisper(whisper, source=name, channel=channel, thread_ts=thread_ts)
        except Exception as e:
            log.debug("Daimonic invocation failed: %s", e)

    if use_soul:
        trace_id = working_memory.new_trace_id()
        soul_engine.store_user_message(text, user_id, channel, thread_ts, display_name=display_name)
        soul_log.emit(
            "stimulus", trace_id, channel=channel, thread_ts=thread_ts,
            origin=origin, user_id=user_id, display_name=display_name or user_id,
            text=text, text_length=len(text),
        )
        prompt = soul_engine.build_prompt(
            text, user_id=user_id, channel=channel, thread_ts=thread_ts,
            trace_id=trace_id,
        )
    else:
        prompt = text

    log.info(
        "SDK query: channel=%s thread=%s resume=%s len=%d soul=%s",
        channel, thread_ts, session_id or "new", len(prompt),
        "on" if use_soul else "off",
    )

    # Override env vars that trigger nested-session detection.
    # SDK merges: {**os.environ, **options.env}, so we blank them out.
    env_overrides = {
        "CLAUDECODE": "",
        "CLAUDE_CODE_SSE_PORT": "",
        "CLAUDE_CODE_ENTRYPOINT": "",
        "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "",
        "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:" + os.environ.get("PATH", ""),
    }

    options = ClaudeAgentOptions(
        allowed_tools=tools.split(","),
        cwd=str(CLAUDE_CWD),
        permission_mode="bypassPermissions",
        env=env_overrides,
    )
    if session_id:
        options.resume = session_id

    full_response = ""
    new_session_id = None

    try:
        async for message in query(prompt=prompt, options=options):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        full_response += block.text
            elif isinstance(message, ResultMessage):
                new_session_id = message.session_id
                if message.is_error:
                    log.error("SDK query error: %s", message.result)
                    if trace_id:
                        soul_log.emit(
                            "error", trace_id, channel=channel, thread_ts=thread_ts,
                            source="claude_handler.async_process",
                            error=str(message.result)[:500], error_type="SDKError",
                        )
                    return f"Claude error: {message.result}"
                if message.result and not full_response:
                    full_response = message.result
    except Exception as e:
        log.error("SDK query failed: %s", e)
        if trace_id:
            soul_log.emit(
                "error", trace_id, channel=channel, thread_ts=thread_ts,
                source="claude_handler.async_process",
                error=str(e)[:500], error_type=type(e).__name__,
            )
        return f"Error invoking Claude: {e}"

    # Persist session
    if new_session_id and new_session_id != session_id:
        session_store.save(channel, thread_ts, new_session_id)
        _title_session(
            new_session_id, channel, text,
            channel_name=channel_name, thread_ts=thread_ts,
            user_id=user_id, display_name=display_name,
            origin=origin,
        )
    elif session_id or new_session_id:
        session_store.touch(channel, thread_ts)
        session_index.touch(session_id or new_session_id)

    if not full_response:
        if trace_id:
            soul_log.emit(
                "error", trace_id, channel=channel, thread_ts=thread_ts,
                source="claude_handler.async_process", error="Empty response",
                error_type="EmptyResponse",
            )
        return "Claude returned an empty response."

    # Parse through soul engine or return raw
    if use_soul:
        response = soul_engine.parse_response(
            full_response, user_id=user_id, channel=channel, thread_ts=thread_ts,
            trace_id=trace_id,
        )
    else:
        response = full_response

    was_truncated = len(response) > MAX_RESPONSE_LENGTH
    if was_truncated:
        response = response[:MAX_RESPONSE_LENGTH] + "\n\n_(truncated)_"

    if trace_id:
        elapsed_ms = int((time.time() - stimulus_ts) * 1000)
        soul_log.emit(
            "response", trace_id, channel=channel, thread_ts=thread_ts,
            text=response, text_length=len(response),
            truncated=was_truncated, elapsed_ms=elapsed_ms,
        )

    return response
