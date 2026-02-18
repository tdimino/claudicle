"""
Inter-soul conversation — Claudius and a daimon speak to each other.

Orchestrates a multi-turn conversation between Claudius and a registered
daimon. Claudius speaks via the providers system (Groq or Claude CLI),
and the daimon speaks via its own WS daemon or Groq fallback.

Transcript is stored in working_memory for persistence.
"""

import logging
from typing import Callable, Optional

import daimon_speak
import daimonic
import soul_engine
import working_memory
from daimon_registry import DaimonConfig

log = logging.getLogger("claudius.daimon_converse")


async def converse(
    daimon: DaimonConfig,
    channel: str,
    thread_ts: str,
    topic: str = "",
    max_turns: int = 4,
    post_fn: Optional[Callable] = None,
) -> list[dict]:
    """Run a multi-turn conversation between Claudius and a daimon.

    Args:
        daimon: The daimon to converse with.
        channel: Slack channel (or "terminal") for working_memory scoping.
        thread_ts: Thread timestamp for working_memory scoping.
        topic: Optional topic to seed the conversation.
        max_turns: Total number of messages (alternating speakers).
        post_fn: Optional async callable to post each message (e.g. to Slack).

    Returns:
        Transcript as list of {"speaker": str, "content": str} dicts.
    """
    from providers import get_provider

    transcript = []
    context = daimonic.read_context(channel, thread_ts)

    # Build Claudius's opener prompt
    opener_system = soul_engine.load_soul()
    opener_user = (
        f"You are about to converse with {daimon.display_name}, a fellow soul. "
        f"{'Topic: ' + topic + '. ' if topic else ''}"
        "Begin a genuine exchange. Speak directly to them. 2-3 sentences."
    )
    opener_prompt = f"{opener_system}\n\n{opener_user}"

    # Use Groq for Claudius's side if available, else default provider
    try:
        provider = get_provider("groq")
    except KeyError:
        provider = get_provider()

    claudius_msg = await provider.agenerate(opener_prompt)
    claudius_msg = claudius_msg.strip()[:1500]

    transcript.append({"speaker": "Claudius", "content": claudius_msg})
    if post_fn:
        await post_fn(f"*Claudius:* {claudius_msg}")

    last_msg = claudius_msg

    for turn in range(max_turns - 1):
        # Daimon responds to Claudius's last message
        daimon_response = await daimon_speak.generate_response(
            daimon, last_msg, context, claudius_response="",
        )
        if not daimon_response:
            log.info("Daimon %s ended conversation at turn %d", daimon.name, turn + 1)
            break

        transcript.append({"speaker": daimon.display_name, "content": daimon_response})
        if post_fn:
            await post_fn(f"*{daimon.display_name}:* {daimon_response}")

        # Claudius responds to the daimon
        reply_prompt = (
            f"{opener_system}\n\n"
            f"{daimon.display_name} said: \"{daimon_response}\"\n\n"
            "Respond to your fellow soul. Stay in character. 2-3 sentences."
        )
        claudius_reply = await provider.agenerate(reply_prompt)
        claudius_reply = claudius_reply.strip()[:1500]

        transcript.append({"speaker": "Claudius", "content": claudius_reply})
        if post_fn:
            await post_fn(f"*Claudius:* {claudius_reply}")

        last_msg = claudius_reply

    # Store full transcript in working_memory
    transcript_text = "\n".join(
        f"{t['speaker']}: {t['content']}" for t in transcript
    )
    working_memory.add(
        channel=channel,
        thread_ts=thread_ts,
        user_id="claudius",
        entry_type="interSoulConversation",
        content=transcript_text,
        metadata={"daimon": daimon.name, "turns": len(transcript)},
    )

    log.info(
        "Inter-soul conversation with %s: %d turns in %s/%s",
        daimon.name, len(transcript), channel, thread_ts,
    )

    return transcript
