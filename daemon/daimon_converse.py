"""
Inter-soul conversation — Claudicle and a daimon speak to each other.

Orchestrates a multi-turn conversation between Claudicle and a registered
daimon. Claudicle speaks via the providers system (Groq or Claude CLI),
and the daimon speaks via its own WS daemon or Groq fallback.

Transcript is stored in working_memory for persistence.
"""

import logging
from typing import Callable, Optional

import context
import daimon_speak
import daimonic
import working_memory
from daimon_registry import DaimonConfig

log = logging.getLogger("claudicle.daimon_converse")


async def converse(
    daimon: DaimonConfig,
    channel: str,
    thread_ts: str,
    topic: str = "",
    max_turns: int = 4,
    post_fn: Optional[Callable] = None,
) -> list[dict]:
    """Run a multi-turn conversation between Claudicle and a daimon.

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
    conv_context = daimonic.read_context(channel, thread_ts)

    # Build Claudicle's opener prompt
    opener_system = context.load_soul()
    opener_user = (
        f"You are about to converse with {daimon.display_name}, a fellow soul. "
        f"{'Topic: ' + topic + '. ' if topic else ''}"
        "Begin a genuine exchange. Speak directly to them. 2-3 sentences."
    )
    opener_prompt = f"{opener_system}\n\n{opener_user}"

    # Use Groq for Claudicle's side if available, else default provider
    try:
        provider = get_provider("groq")
    except KeyError:
        provider = get_provider()

    claudicle_msg = await provider.agenerate(opener_prompt)
    claudicle_msg = claudicle_msg.strip()[:1500]

    transcript.append({"speaker": "Claudicle", "content": claudicle_msg})
    if post_fn:
        await post_fn(f"*Claudicle:* {claudicle_msg}")

    last_msg = claudicle_msg

    for turn in range(max_turns - 1):
        # Daimon responds to Claudicle's last message
        daimon_response = await daimon_speak.generate_response(
            daimon, last_msg, conv_context, claudicle_response="",
        )
        if not daimon_response:
            log.info("Daimon %s ended conversation at turn %d", daimon.name, turn + 1)
            break

        transcript.append({"speaker": daimon.display_name, "content": daimon_response})
        if post_fn:
            await post_fn(f"*{daimon.display_name}:* {daimon_response}")

        # Claudicle responds to the daimon
        reply_prompt = (
            f"{opener_system}\n\n"
            f"{daimon.display_name} said: \"{daimon_response}\"\n\n"
            "Respond to your fellow soul. Stay in character. 2-3 sentences."
        )
        claudicle_reply = await provider.agenerate(reply_prompt)
        claudicle_reply = claudicle_reply.strip()[:1500]

        transcript.append({"speaker": "Claudicle", "content": claudicle_reply})
        if post_fn:
            await post_fn(f"*Claudicle:* {claudicle_reply}")

        last_msg = claudicle_reply

    # Store full transcript in working_memory
    transcript_text = "\n".join(
        f"{t['speaker']}: {t['content']}" for t in transcript
    )
    working_memory.add(
        channel=channel,
        thread_ts=thread_ts,
        user_id="claudicle",
        entry_type="interSoulConversation",
        content=transcript_text,
        metadata={"daimon": daimon.name, "turns": len(transcript)},
    )

    log.info(
        "Inter-soul conversation with %s: %d turns in %s/%s",
        daimon.name, len(transcript), channel, thread_ts,
    )

    return transcript
