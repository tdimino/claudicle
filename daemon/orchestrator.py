"""
Orchestrator HTTP API — allows Kothar and external systems to spawn
Claude Code sessions and inject perceptions.

Endpoints:
  POST /api/orchestrate  — spawn a Claude Code session with bypassPermissions
  POST /api/perception   — inject a perception into the Claudicle message queue
  GET  /api/health       — liveness check

Registers with portless as `claudicle-api` so Kothar and other services
can reach it at http://claudicle-api.localhost:1355/api/orchestrate.
"""

import asyncio
import json
import logging
import os
import subprocess
from uuid import uuid4

from aiohttp import web

import claude_handler
from config import CLAUDE_ALLOWED_TOOLS, CLAUDE_CWD

log = logging.getLogger("claudicle.orchestrator")

PORTLESS_NAME = "claudicle-api"

# Auth token -- loaded from CLAUDICLE_API_TOKEN env var or config.
# Any local process calling /api/orchestrate or /api/perception must
# include this as a Bearer token. Without it, endpoints return 401.
_AUTH_TOKEN = os.environ.get("CLAUDICLE_API_TOKEN", "")


def _check_auth(request: web.Request) -> bool:
    """Verify Bearer token. Returns True if auth passes or no token configured."""
    if not _AUTH_TOKEN:
        return True  # No token configured -- loopback-only trust
    auth = request.headers.get("Authorization", "")
    return auth == f"Bearer {_AUTH_TOKEN}"


def _find_free_port() -> int:
    """Find an available port in the 4000-4999 range (portless convention)."""
    import socket
    for port in range(4000, 5000):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("127.0.0.1", port))
                return port
        except OSError:
            continue
    raise RuntimeError("No free port in 4000-4999 range")


class OrchestratorServer:
    """Lightweight HTTP gateway for Kothar → Claude Code orchestration."""

    def __init__(self, enqueue_fn=None):
        """
        Args:
            enqueue_fn: async callable to inject messages into Claudicle's queue.
                        Signature: async (msg_dict) -> None
        """
        self._enqueue = enqueue_fn
        self._port = None
        self._portless_url = None
        self._app = web.Application()
        self._app.router.add_post("/api/orchestrate", self._handle_orchestrate)
        self._app.router.add_post("/api/perception", self._handle_perception)
        self._app.router.add_get("/api/health", self._handle_health)
        self._runner = None

    async def start(self):
        """Start the HTTP server and register with portless."""
        self._port = _find_free_port()

        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, "127.0.0.1", self._port)
        await site.start()

        # Register with portless as a static alias
        try:
            result = subprocess.run(
                ["portless", "alias", PORTLESS_NAME, str(self._port), "--force"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                self._portless_url = f"http://{PORTLESS_NAME}.localhost:1355"
                log.info("Orchestrator API: %s (port %d)", self._portless_url, self._port)
            else:
                self._portless_url = f"http://127.0.0.1:{self._port}"
                log.warning(
                    "portless alias failed (rc=%d): %s",
                    result.returncode, result.stderr.strip(),
                )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            self._portless_url = f"http://127.0.0.1:{self._port}"
            log.warning(
                "portless not available, orchestrator at %s", self._portless_url,
            )

    async def stop(self):
        """Graceful shutdown — unregister from portless."""
        try:
            subprocess.run(
                ["portless", "alias", "--remove", PORTLESS_NAME],
                capture_output=True, timeout=5,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        if self._runner:
            await self._runner.cleanup()

    @property
    def url(self) -> str:
        """Public URL for this server (portless or direct)."""
        return self._portless_url or f"http://127.0.0.1:{self._port}"

    async def _handle_health(self, request: web.Request) -> web.Response:
        return web.json_response({"status": "ok"})

    async def _handle_orchestrate(self, request: web.Request) -> web.Response:
        """
        Spawn a Claude Code session with bypassPermissions.

        Request body:
            {
                "task": "Natural language task description",
                "cwd": "/optional/working/directory",
                "tools": "optional,comma,separated,tools",
                "soul_enabled": false
            }

        Response:
            {"result": "Claude's response text", "session_id": "..."}
        """
        if not _check_auth(request):
            return web.json_response({"error": "Unauthorized"}, status=401)

        try:
            body = await request.json()
        except (json.JSONDecodeError, Exception):
            return web.json_response(
                {"error": "Invalid JSON body"}, status=400,
            )

        task = body.get("task", "").strip()
        if not task:
            return web.json_response(
                {"error": "Missing required field: task"}, status=400,
            )

        cwd = body.get("cwd", str(CLAUDE_CWD))
        tools = body.get("tools", CLAUDE_ALLOWED_TOOLS)
        soul_enabled = body.get("soul_enabled", False)
        thread_id = f"orch-{uuid4().hex[:12]}"

        log.info(
            "Orchestrate request: task=%s cwd=%s soul=%s",
            task[:80], cwd, soul_enabled,
        )

        try:
            response = await claude_handler.async_process(
                text=task,
                channel="kothar:orchestrator",
                thread_ts=thread_id,
                user_id="kothar",
                soul_enabled=soul_enabled,
                allowed_tools=tools,
                origin="orchestrator",
            )
        except Exception as e:
            log.error("Orchestrate failed: %s", e)
            return web.json_response(
                {"error": str(e)}, status=500,
            )

        return web.json_response({
            "result": response,
            "thread_id": thread_id,
        })

    async def _handle_perception(self, request: web.Request) -> web.Response:
        """
        Inject a perception into the Claudicle message queue.

        Request body:
            {
                "action": "orchestrate",
                "content": {
                    "task": "Research the latest Three.js release notes",
                    "cwd": "/path/to/project",
                    "report_to": "slack:#general"
                }
            }

        This enqueues a message as if it came from an adapter,
        allowing Kothar or external systems to trigger Claudicle work.
        """
        if not _check_auth(request):
            return web.json_response({"error": "Unauthorized"}, status=401)

        if not self._enqueue:
            return web.json_response(
                {"error": "No message queue configured"}, status=503,
            )

        try:
            body = await request.json()
        except (json.JSONDecodeError, Exception):
            return web.json_response(
                {"error": "Invalid JSON body"}, status=400,
            )

        action = body.get("action", "")
        content = body.get("content", {})

        if not action:
            return web.json_response(
                {"error": "Missing required field: action"}, status=400,
            )

        # Build a message that the process loop can handle
        msg = {
            "source": "orchestrator",
            "action": action,
            "text": content.get("task", json.dumps(content)),
            "channel": content.get("report_to", "kothar:perception"),
            "thread_ts": f"perc-{uuid4().hex[:12]}",
            "user": "kothar",
            "display_name": "Kothar",
            "channel_name": "orchestrator",
            "content": content,
        }

        log.info("Perception injected: action=%s", action)
        await self._enqueue(msg)

        return web.json_response({"status": "queued", "action": action})
