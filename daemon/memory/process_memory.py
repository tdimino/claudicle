"""Per-subprocess persistent state. Maps to Open Souls useProcessMemory hook. Backed by soul_memory with namespaced keys — zero migration, automatic test isolation."""

import json
from typing import Any, Optional

from memory import soul_memory


def _make_key(subprocess_name: str, key: str, channel: Optional[str] = None, thread_ts: Optional[str] = None) -> str:
    if channel and thread_ts:
        return f"proc:{subprocess_name}:{channel}:{thread_ts}:{key}"
    return f"proc:{subprocess_name}:{key}"


def get(
    subprocess_name: str,
    key: str,
    default: Any = None,
    *,
    channel: Optional[str] = None,
    thread_ts: Optional[str] = None,
) -> Any:
    namespaced_key = _make_key(subprocess_name, key, channel=channel, thread_ts=thread_ts)
    value = soul_memory.get(namespaced_key)
    if value is None or value == "":
        return default
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return value


def set(
    subprocess_name: str,
    key: str,
    value: Any,
    *,
    channel: Optional[str] = None,
    thread_ts: Optional[str] = None,
) -> None:
    namespaced_key = _make_key(subprocess_name, key, channel=channel, thread_ts=thread_ts)
    soul_memory.set(namespaced_key, json.dumps(value))


def clear(
    subprocess_name: str,
    *,
    channel: Optional[str] = None,
    thread_ts: Optional[str] = None,
) -> int:
    prefix = (
        f"proc:{subprocess_name}:{channel}:{thread_ts}:"
        if channel and thread_ts
        else f"proc:{subprocess_name}:"
    )
    state = soul_memory.get_all()
    to_clear = [key for key in state if key.startswith(prefix)]
    for key in to_clear:
        soul_memory.delete(key)
    return len(to_clear)
