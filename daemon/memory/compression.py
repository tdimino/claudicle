"""Working-memory compression helpers."""

from __future__ import annotations

from typing import Any

import config
from engine import llm_client
from memory import working_memory

_ALWAYS_PRESERVE_TYPES = {"daimonicIntuition", "onboardingStep", "memorySummary"}
_RESULT_PRESERVE_TYPES = {"decision", "mentalQuery"}
_TOPIC_ENTRY_TYPES = {
    "userMessage",
    "externalDialog",
    "internalMonologue",
    "toolAction",
    "decision",
    "mentalQuery",
}
_VERBATIM_ENTRY_TYPES = {"decision", "mentalQuery", "daimonicIntuition"}


def _parse_metadata(entry: dict) -> dict:
    """Normalize metadata field to a dictionary."""
    import json as _json

    meta = entry.get("metadata")
    if isinstance(meta, dict):
        return meta
    if isinstance(meta, str) and meta:
        try:
            parsed = _json.loads(meta)
            return parsed if isinstance(parsed, dict) else {}
        except _json.JSONDecodeError:
            return {}
    return {}


def _normalize_text(text: str) -> str:
    return " ".join((text or "").split())


def partition_by_priority(entries: list[dict]) -> tuple[list[dict], list[dict]]:
    """Split entries into must-preserve and compressible groups."""
    must_preserve: list[dict] = []
    compressible: list[dict] = []

    for entry in entries:
        entry_type = entry.get("entry_type", "")
        if entry_type in _ALWAYS_PRESERVE_TYPES:
            must_preserve.append(entry)
            continue

        if entry_type in _RESULT_PRESERVE_TYPES:
            if bool(_parse_metadata(entry).get("result")):
                must_preserve.append(entry)
            else:
                compressible.append(entry)
            continue

        compressible.append(entry)

    return must_preserve, compressible


def heuristic_compress(entries: list[dict], soul_name: str = "Claudius") -> str:
    """Build a lightweight template summary (~400 chars target)."""
    if not entries:
        return f"Memory compression summary for {soul_name}: no compressible entries."

    speakers: list[str] = []
    speaker_seen: set[str] = set()
    topics: list[str] = []
    topic_seen: set[str] = set()
    verbatim: list[str] = []

    for entry in entries:
        entry_type = entry.get("entry_type", "")
        content = _normalize_text(entry.get("content", ""))
        if not content:
            continue

        if entry_type == "userMessage":
            speaker = entry.get("display_name") or entry.get("user_id") or "User"
            if speaker not in speaker_seen:
                speaker_seen.add(speaker)
                speakers.append(speaker)

        if entry_type in _TOPIC_ENTRY_TYPES:
            topic = content[:50]
            if topic and topic not in topic_seen:
                topic_seen.add(topic)
                topics.append(topic)

        if entry_type in _VERBATIM_ENTRY_TYPES:
            result = _parse_metadata(entry).get("result")
            if result is None:
                verbatim.append(f'"{content}"')
            else:
                verbatim.append(f'"{content}" (result={result})')

    parts: list[str] = [f"Memory compression summary for {soul_name}."]
    if verbatim:
        parts.append("Verbatim decisions/intuitions: " + " | ".join(verbatim) + ".")
    if speakers:
        parts.append("Speakers: " + ", ".join(speakers) + ".")
    if topics:
        parts.append("Topics: " + " | ".join(topics) + ".")

    summary = " ".join(parts)
    target = 400
    hard_cap = 480

    if len(summary) <= target:
        return summary

    # Trim topics first to keep verbatim sections untouched.
    while topics and len(summary) > hard_cap:
        topics.pop()
        parts = [p for p in parts if not p.startswith("Topics: ")]
        if topics:
            parts.append("Topics: " + " | ".join(topics) + ".")
        summary = " ".join(parts)

    if len(summary) > hard_cap and speakers:
        summary = " ".join([p for p in parts if not p.startswith("Speakers: ")])

    return summary


def llm_compress(
    entries: list[dict],
    soul_name: str,
    provider: str,
    model: str,
) -> str:
    """Compress entries using LLM summarization."""
    lines = []
    for entry in entries:
        meta = _parse_metadata(entry)
        result = meta.get("result")
        result_suffix = f" result={result}" if result is not None else ""
        speaker = entry.get("display_name") or entry.get("user_id") or ""
        speaker_suffix = f" speaker={speaker}" if speaker else ""
        lines.append(
            f"[{entry.get('entry_type', '')}{result_suffix}{speaker_suffix}] {entry.get('content', '')}"
        )

    prompt = (
        f"You are {soul_name}, reflecting on a conversation segment that is about "
        f"to leave your active memory. Before it fades, distill what matters.\n\n"
        "Ask yourself:\n"
        "- What did I learn about the people I was speaking with?\n"
        "- What decisions were made, and what was my reasoning?\n"
        "- What threads remain open that I should remember?\n"
        "- What would I need to know to continue this conversation seamlessly?\n\n"
        "Write a first-person reflection (~400 characters). "
        "Preserve any decisions or intuitions verbatim. "
        "Name the speakers. Plain text only.\n\n"
        "Conversation segment:\n"
        + "\n".join(lines)
    )
    return llm_client.call_llm(prompt=prompt, provider=provider, model=model).strip()


def store_summary(
    channel: str,
    thread_ts: str,
    summary: str,
    original_count: int,
    time_range: dict[str, Any],
    method: str,
) -> None:
    """Replace prior summary entry with a fresh summary-region record.

    Atomic: DELETE old + INSERT new in a single transaction so a crash
    between the two cannot leave the thread without a summary.
    """
    import json as _json

    working_memory.replace_region(
        channel=channel,
        thread_ts=thread_ts,
        region="summary",
        entries=[
            {
                "user_id": "claudicle",
                "entry_type": "memorySummary",
                "content": summary,
                "metadata": _json.dumps(
                    {
                        "original_count": original_count,
                        "time_range": time_range,
                        "method": method,
                    }
                ),
            }
        ],
    )


def archive_and_delete(
    entries: list[dict],
    channel: str,
    thread_ts: str,
    time_range: dict[str, Any],
    compression_trace_id: str,
) -> int:
    """Archive + delete entries in one transaction.

    Caller is responsible for trimming (compress_thread handles keep-recent).
    All entries passed here will be archived and deleted.
    """
    if not entries:
        return 0
    return working_memory.archive_entries(
        entries=list(entries),
        channel=channel,
        thread_ts=thread_ts,
        compression_trace_id=compression_trace_id,
        archive=config.COMPRESSION_ARCHIVE,
    )


def compress_thread(
    channel: str,
    thread_ts: str,
    trace_id: str | None = None,
) -> dict[str, Any]:
    """Compress one thread's default-region working memory."""
    entries = working_memory.get_region(channel, thread_ts, "default", limit=5000)
    threshold = max(config.COMPRESSION_THRESHOLD, 1)
    if len(entries) < threshold:
        return {"compressed_count": 0, "reason": "threshold_not_met"}

    _, compressible = partition_by_priority(entries)
    if not compressible:
        return {"compressed_count": 0, "reason": "nothing_compressible"}

    keep_recent = max(config.COMPRESSION_KEEP_RECENT, 0)
    to_compress = compressible[:-keep_recent] if keep_recent and len(compressible) > keep_recent else []
    if keep_recent == 0:
        to_compress = list(compressible)

    if not to_compress:
        return {"compressed_count": 0, "reason": "keep_recent_guard"}

    method = "heuristic"
    if config.COMPRESSION_USE_LLM:
        try:
            summary = llm_compress(
                to_compress,
                soul_name=config.SOUL_NAME,
                provider=config.COMPRESSION_PROVIDER,
                model=config.COMPRESSION_MODEL,
            )
            method = "llm"
        except Exception:
            summary = heuristic_compress(to_compress, soul_name=config.SOUL_NAME)
            method = "heuristic_fallback"
    else:
        summary = heuristic_compress(to_compress, soul_name=config.SOUL_NAME)

    created_values = [float(e.get("created_at", 0.0)) for e in to_compress]
    time_range = {
        "start": min(created_values) if created_values else None,
        "end": max(created_values) if created_values else None,
    }
    compression_trace_id = trace_id or working_memory.new_trace_id()

    store_summary(
        channel=channel,
        thread_ts=thread_ts,
        summary=summary,
        original_count=len(to_compress),
        time_range=time_range,
        method=method,
    )
    compressed_count = archive_and_delete(
        entries=to_compress,
        channel=channel,
        thread_ts=thread_ts,
        time_range=time_range,
        compression_trace_id=compression_trace_id,
    )

    return {
        "compressed_count": compressed_count,
        "method": method,
        "summary": summary,
        "time_range": time_range,
        "trace_id": compression_trace_id,
    }
