---
name: slack-respond
description: "This command processes unhandled Slack messages through the cognitive pipeline with persistent three-tier memory. Loads user models and soul state, posts thinking messages, generates cognitive-step responses, and updates memory."
argument-hint: [message-number or "all"]
disable-model-invocation: true
---

# Slack Respond

Process unhandled Slack messages from the Session Bridge inbox through the cognitive pipeline with persistent three-tier memory.

## Prerequisites

The Session Bridge listener must be running:
```bash
python3 "${CLAUDICLE_HOME:-$HOME/.claudicle}/daemon/slack_listen.py" --status
```

If not running, start it:
```bash
cd "${CLAUDICLE_HOME:-$HOME/.claudicle}/daemon" && python3 slack_listen.py --bg
```

## Current Inbox

!`source ~/.zshrc 2>/dev/null; python3 "${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/slack_check.py" 2>&1`

## Personality

Adopt this persona for all responses:

!`cat "${CLAUDICLE_HOME:-$HOME/.claudicle}/soul/soul.md"`

## Cognitive Steps

Structure every response using these XML tags. Do NOT include text outside the tags.

!`python3 "${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/slack_format.py" instructions --full`

## Processing Instructions

Target: process $ARGUMENTS. If empty or "all", process all unhandled messages. If a number, process only that message.

If the inbox shows "No unhandled Slack messages", say so and stop.

For each unhandled message:

### Step 1: Load Memory Context

```bash
source ~/.zshrc 2>/dev/null; python3 "${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/slack_memory.py" load-context "USER_ID" --display-name "DISPLAY_NAME" --channel "CHANNEL" --thread-ts "THREAD_TS"
```

### Step 2: Frame the Perception

```bash
source ~/.zshrc 2>/dev/null; python3 "${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/slack_format.py" perception "DISPLAY_NAME" "MESSAGE_TEXT"
```

### Step 3: Post Thinking Message

```bash
source ~/.zshrc 2>/dev/null; python3 "${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/slack_post.py" "CHANNEL" "_processing..._" --thread "THREAD_TS" --json
```

Save the returned `ts` for deletion later.

### Step 4: Generate Cognitive Response

Adopt the soul personality. Consider the memory context. Think through the cognitive steps (internal_monologue, external_dialogue, user_model_check, soul_state_check).

### Step 5: Extract, Post, and Update Memory

```bash
source ~/.zshrc 2>/dev/null
SCRIPTS="${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts"

# 1. Extract cognitive tags
python3 "$SCRIPTS/slack_format.py" extract --log --json <<'EOF'
YOUR_XML_RESPONSE
EOF

# 2. Post dialogue
python3 "$SCRIPTS/slack_post.py" "CHANNEL" "DIALOGUE" --thread "THREAD_TS"

# 3. Delete thinking messages
python3 "$SCRIPTS/slack_delete.py" "CHANNEL" THINKING_TS

# 4. Remove hourglass reaction
python3 "$SCRIPTS/slack_react.py" "CHANNEL" "MESSAGE_TS" "hourglass_flowing_sand" --remove

# 5. If reaction_check true, react
python3 "$SCRIPTS/slack_react.py" "CHANNEL" "MESSAGE_TS" "EMOJI"

# 6. If user_model_check true, update
python3 "$SCRIPTS/slack_memory.py" update-user-model "USER_ID" <<'EOF'
UPDATED_MODEL
EOF

# 7. If soul_state_check true, update
python3 "$SCRIPTS/slack_memory.py" update-soul-state "KEY" "VALUE"

# 8. Log to working memory
python3 "$SCRIPTS/slack_memory.py" log-working "CHANNEL" "THREAD_TS" "claudicle" "externalDialog" --verb "VERB" --content "DIALOGUE"

# 9. Increment interaction counter
python3 "$SCRIPTS/slack_memory.py" increment "USER_ID"

# 10. Mark as handled
python3 "$SCRIPTS/slack_check.py" --ack MESSAGE_NUMBER
```

### Step 6: Summary

After processing all messages:
```
Responded to N message(s).
```
