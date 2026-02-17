# Streaming Patterns — Extension Pattern

## Open Souls Pattern

The Open Souls Engine supports **real-time token streaming** from cognitive steps to the frontend. This enables character-by-character display of responses, typing indicators, and reactive UIs. Streaming is a first-class concept woven into the cognitive step architecture.

### Core Streaming API

```typescript
// Non-streaming: collect full response
const [memory, response] = await externalDialog(workingMemory, "Respond");
speak(response);  // Send complete string

// Streaming: forward token-by-token
const [memory, stream] = await externalDialog(
  workingMemory, "Respond", { stream: true }
);
speak(stream);           // Forward AsyncIterable directly to frontend
await memory.finished;   // Wait for stream consumption
```

### `memory.finished` — Stream Synchronization

When streaming is enabled, the returned `WorkingMemory` is not yet complete—the LLM is still generating tokens. The `memory.finished` promise resolves when the stream has been fully consumed.

```typescript
const [memory, stream] = await externalDialog(
  workingMemory, "Think deeply", { stream: true }
);

// ❌ WRONG: memory is incomplete here
// const thought = memory.memories.at(-1)?.content;  // May be partial

speak(stream);
await memory.finished;  // ✅ Wait for completion

// ✅ Now memory is complete
return memory;
```

**Critical rule**: Always `await memory.finished` before returning memory or using its contents. The `finished` property returns `Promise<void>`, NOT `WorkingMemory`.

### Stream Forwarding Pattern

The backend never consumes the stream—it forwards the `AsyncIterable` directly:

```typescript
// speak() forwards stream to frontend
const [memory, stream] = await externalDialog(wm, "Respond", { stream: true });
speak(stream);  // AsyncIterable<string> sent directly

// dispatch() also supports streams
dispatch({
  name: memory.soulName,
  action: "answers",
  content: stream  // Stream forwarded in dispatch payload
});
```

### Stream Processing (Custom Transformations)

Cognitive steps can define `streamProcessor` for real-time token transformation:

```typescript
const customStep = createCognitiveStep((instructions: string) => ({
  command: ({ soulName }) => ({
    role: ChatMessageRoleEnum.System,
    content: `${soulName}: ${instructions}`
  }),
  streamProcessor: async function* (stream: AsyncIterable<string>) {
    for await (const chunk of stream) {
      // Transform tokens in real-time
      yield chunk.toUpperCase();
    }
  },
  postProcess: async (memory, response) => {
    return [{
      role: ChatMessageRoleEnum.Assistant,
      content: response
    }, response];
  }
}));
```

### Internal Monologue Streaming

Internal monologue can also stream—useful for showing "thinking" indicators:

```typescript
const [memory, stream] = await internalMonologue(
  workingMemory, "Analyze the emotional tone",
  { stream: true }
);

// Forward thinking to UI (separate from speech)
dispatch({ action: "thinks", content: stream });
await memory.finished;
```

### Multi-Step Streaming

When chaining streaming steps, await `finished` between each:

```typescript
// Step 1: Internal reasoning (streamed to debug UI)
const [mem1, thinkStream] = await internalMonologue(
  workingMemory, "Think about response", { stream: true }
);
dispatch({ action: "thinks", content: thinkStream });
await mem1.finished;

// Step 2: External response (streamed to user)
const [mem2, respondStream] = await externalDialog(
  mem1, "Respond to user", { stream: true }
);
speak(respondStream);
await mem2.finished;

return mem2;
```

---

## Current Claudius Implementation

Claudius **does not stream responses**. The cognitive pipeline collects the full response before posting:

```
build_prompt() → LLM call (blocking) → parse_response() → post to channel
```

### Where Responses Are Collected

- **Session Bridge** (`bot.py`): `subprocess.run(["claude", "-p", ...])` — blocks until complete, returns `stdout` as string
- **Unified Launcher** (`claude_handler.py:75-139`): `async for message in query(...)` — iterates through SDK messages but collects all `TextBlock` content into `full_response` string before processing
- **`/slack-respond`**: Processes messages through `soul_engine.build_prompt()` → `claude -p` → `soul_engine.parse_response()` → `slack_post.py`

### Hourglass Pattern (Current UX)

Instead of streaming, Claudius uses a hourglass reaction to indicate processing:

```
1. Message received → add ⏳ reaction
2. Process (blocking) → collect full response
3. Post response → remove ⏳ reaction
```

This is in `bot.py:268-295` and `claudius.py:135-180`.

---

## Extension Blueprint

### Goal

Add streaming support so responses appear character-by-character in Slack (via message editing) or terminal (via stdout).

### Approach 1: Slack Message Editing (Incremental)

Post an initial message, then edit it as tokens arrive:

```python
# daemon/streaming.py
"""Streaming response handler for Slack and terminal."""

import asyncio
import logging
from slack_sdk.web.async_client import AsyncWebClient

log = logging.getLogger("claudius.streaming")

class SlackStreamer:
    """Stream tokens to Slack by editing a message."""

    def __init__(self, client: AsyncWebClient, channel: str, thread_ts: str):
        self.client = client
        self.channel = channel
        self.thread_ts = thread_ts
        self.message_ts = None
        self.buffer = ""
        self.min_edit_interval = 0.5  # Rate limit: max 2 edits/sec

    async def start(self, initial_text: str = "..."):
        """Post initial placeholder message."""
        result = await self.client.chat_postMessage(
            channel=self.channel,
            thread_ts=self.thread_ts,
            text=initial_text,
        )
        self.message_ts = result["ts"]

    async def update(self, text: str):
        """Edit message with accumulated text."""
        if not self.message_ts:
            return
        self.buffer = text
        await self.client.chat_update(
            channel=self.channel,
            ts=self.message_ts,
            text=text,
        )

    async def finish(self, final_text: str):
        """Final edit with complete response."""
        await self.update(final_text)
```

### Approach 2: SDK Streaming (Direct)

Use the Agent SDK's streaming capability directly:

```python
# claude_handler.py — streaming version of async_process()
async def async_process_streaming(prompt, channel, thread_ts, slack_streamer=None):
    """Process with real-time streaming to Slack."""
    session_id = session_store.get(channel, thread_ts)

    streamer = slack_streamer
    full_response = ""

    async for message in query(prompt, options=ClaudeAgentOptions(
        allowed_tools=config.CLAUDE_ALLOWED_TOOLS.split(","),
        resume=session_id,
        permission_mode="bypassPermissions",
    )):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    full_response += block.text
                    if streamer:
                        await streamer.update(full_response)

        elif isinstance(message, ResultMessage):
            session_store.save(channel, thread_ts, message.session_id)

    # Final update with complete text
    if streamer:
        await streamer.finish(full_response)

    return full_response
```

### Approach 3: Terminal Streaming (Simplest)

Stream to terminal stdout without Slack complexity:

```python
# terminal_ui.py — streaming display
import sys

async def stream_response(text_generator):
    """Display streaming response in terminal."""
    async for chunk in text_generator:
        sys.stdout.write(chunk)
        sys.stdout.flush()
    print()  # Final newline
```

### Streaming + Cognitive Pipeline

The main challenge: `parse_response()` needs the **complete** response to extract XML tags. Options:

1. **Buffer then parse**: Stream to UI, but still parse after completion (simplest)
2. **Streaming parser**: Detect XML tag boundaries in the token stream, extract `<external_dialogue>` content as it arrives (complex but enables real-time dialogue streaming)
3. **Two-phase**: Stream raw response, then parse and replace the message with just the dialogue (good UX compromise)

### Rate Limiting

Slack's API limits message edits to ~1/second. The streamer must batch tokens:

```python
# Batch tokens and update at intervals
MIN_EDIT_INTERVAL = 0.5  # seconds
last_edit = 0

async def throttled_update(streamer, text):
    nonlocal last_edit
    now = time.time()
    if now - last_edit >= MIN_EDIT_INTERVAL:
        await streamer.update(text)
        last_edit = now
```

### Estimated Effort

- **Terminal streaming**: ~30 LOC in `terminal_ui.py`
- **Slack streaming**: ~80 LOC in new `streaming.py`
- **SDK integration**: ~40 LOC modified in `claude_handler.py`
- **Streaming parser** (optional): ~100 LOC in `soul_engine.py`
- Tests: ~50 LOC
