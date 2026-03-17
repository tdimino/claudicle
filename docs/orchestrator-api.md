# Orchestrator API

HTTP gateway that allows daimones (Kothar, or any soul) to autonomously spawn Claude Code sessions and inject perceptions into Claudicle's message queue.

## Overview

```
Daimon (e.g. Kothar)
  → POST /api/orchestrate  (Bearer token)
    → claude_handler.async_process()
      → Claude Agent SDK query() with permission_mode="bypassPermissions"
      → smart-auto-approve.py deny list still enforced
    → returns result text
```

The spawned Claude Code session is full Opus 4.6 with all tools and skills. The daimon is the architect; Opus is the builder.

## Endpoints

### `POST /api/orchestrate`

Spawn a Claude Code session with `bypassPermissions`.

**Request**:
```json
{
  "task": "Implement the user authentication module",
  "cwd": "/Users/you/project",
  "tools": "Bash,Read,Write,Edit,Glob,Grep",
  "soul_enabled": false
}
```

| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `task` | Yes | — | Natural language task for Claude Code |
| `cwd` | No | `CLAUDE_CWD` | Working directory for the session |
| `tools` | No | `CLAUDE_ALLOWED_TOOLS` | Comma-separated tool whitelist |
| `soul_enabled` | No | `false` | Whether to wrap with Claudius's cognitive pipeline |

**Response**:
```json
{
  "result": "I've implemented the auth module in src/auth/...",
  "thread_id": "orch-a1b2c3d4e5f6"
}
```

### `POST /api/perception`

Inject a perception into Claudicle's message queue.

**Request**:
```json
{
  "action": "orchestrate",
  "content": {
    "task": "Research the latest Three.js release notes",
    "cwd": "/Users/you/project",
    "report_to": "slack:#general"
  }
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `action` | Yes | Perception type (e.g. `orchestrate`, `systemAlert`) |
| `content` | Yes | Perception payload (string or object) |

**Response**:
```json
{
  "status": "queued",
  "action": "orchestrate"
}
```

### `GET /api/health`

Liveness check. Returns `{"status": "ok"}`.

## Authentication

All mutating endpoints require a Bearer token via the `Authorization` header:

```
Authorization: Bearer <CLAUDICLE_API_TOKEN>
```

The token is loaded from the `CLAUDICLE_API_TOKEN` environment variable. If no token is configured, endpoints accept all requests (loopback-only trust).

**Setup**:
```bash
# Generate token
openssl rand -hex 32

# Add to ~/.config/env/secrets.env
export CLAUDICLE_API_TOKEN="<generated-token>"
```

The same token must be available to both the Claudicle daemon (reads via `os.environ`) and the daimon (reads via `process.env`).

## Portless Registration

The orchestrator registers itself with portless as `claudicle-api`:

```
http://claudicle-api.localhost:1355/api/orchestrate
```

If portless is unavailable, it falls back to a direct port in the 4000-4999 range. The `url` property on `OrchestratorServer` always returns the correct address.

## Permission Model

Spawned sessions use `permission_mode="bypassPermissions"`, but the `smart-auto-approve.py` hook still fires on every Bash command. Safety is enforced by the deny list in `config/auto-approve-whitelist.template.json`.

**What this means**: commands not explicitly denied are permitted without human approval. The deny list is the critical safety layer for daemon-spawned sessions.

See `config/INDEX.md` for the full deny category reference.

## Integration with Daimones

### From a Mental Process (TypeScript)

```typescript
const ORCHESTRATOR_URL = 'http://claudicle-api.localhost:1355';
const ORCHESTRATOR_TOKEN = process.env.CLAUDICLE_API_TOKEN || '';

async function spawnSession(task: string, cwd?: string): Promise<string> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (ORCHESTRATOR_TOKEN) headers['Authorization'] = `Bearer ${ORCHESTRATOR_TOKEN}`;

  const response = await fetch(`${ORCHESTRATOR_URL}/api/orchestrate`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ task, cwd }),
  });

  const data = await response.json();
  return data.result;
}
```

### From a Script (curl)

```bash
curl -X POST http://claudicle-api.localhost:1355/api/orchestrate \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $CLAUDICLE_API_TOKEN" \
  -d '{"task": "List files in ~/Desktop/Programming"}'
```

## Lifecycle

The orchestrator starts and stops with the Claudicle unified launcher (`claudicle.py`):

1. **Start**: after all channel adapters, before the terminal input loop
2. **Stop**: during `_shutdown()`, unregisters portless alias

No separate daemon management needed.
