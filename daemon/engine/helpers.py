import re
from typing import Callable, Optional

from memory import working_memory
from monitoring import soul_log


def extract_tag(text: str, tag: str) -> tuple[str, Optional[str]]:
    """Extract content and optional verb attribute from an XML tag.

    Returns (content, verb) or ("", None) if not found.
    """
    pattern = rf'<{tag}(?:\s+verb="([^"]*)")?\s*>(.*?)</{tag}>'
    match = re.search(pattern, text, re.DOTALL)
    if match:
        verb = match.group(1) if match.group(1) else None
        content = match.group(2).strip()
        return content, verb
    return "", None


def extract_tag_with_attrs(text: str, tag: str) -> tuple[str, dict[str, str]]:
    """Extract content and all attributes from an XML tag.

    Returns (content, attrs_dict) or ("", {}) if not found.
    Handles tags like <brainstorm count="3">...</brainstorm>
    and <decision options="a,b,c" reasoning="...">...</decision>.
    """
    pattern = rf'<{tag}([^>]*)>(.*?)</{tag}>'
    match = re.search(pattern, text, re.DOTALL)
    if not match:
        return "", {}
    attrs_str = match.group(1)
    content = match.group(2).strip()
    # Parse attributes
    attrs = dict(re.findall(r'(\w+)="([^"]*)"', attrs_str))
    return content, attrs


def strip_all_tags(text: str) -> str:
    """Remove all XML tags from text, keeping only content."""
    return re.sub(r"<[^>]+>", "", text)


def store_and_emit(
    channel,
    thread_ts,
    trace_id,
    entry_type,
    content,
    verb=None,
    metadata=None,
    display_name=None,
    phase: str = "cognition",
    step: Optional[str] = None,
    emit_verb: bool = True,
    log_fields: Optional[dict] = None,
    postprocess: Optional[Callable[[str], None]] = None,
):
    working_memory.add(
        channel=channel,
        thread_ts=thread_ts,
        user_id="claudicle",
        entry_type=entry_type,
        content=content,
        verb=verb,
        metadata=metadata,
        trace_id=trace_id,
        display_name=display_name,
    )
    emit_payload = {
        "channel": channel,
        "thread_ts": thread_ts,
    }
    if log_fields is not None:
        emit_payload.update(log_fields)
    else:
        emit_payload.update(
            step=step or entry_type,
            content=content,
            content_length=len(content),
        )
        if emit_verb and verb:
            emit_payload["verb"] = verb

    soul_log.emit(phase, trace_id, **emit_payload)
    if postprocess is not None:
        postprocess(content)
