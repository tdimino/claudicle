#!/usr/bin/env python3
"""Manage the WhatsApp Gateway lifecycle.

Usage:
    python3 whatsapp_listen.py --start    # Start gateway in background
    python3 whatsapp_listen.py --stop     # Stop gateway
    python3 whatsapp_listen.py --status   # Check gateway status
    python3 whatsapp_listen.py --pair     # First-time QR pairing (foreground)
"""

import argparse
import json
import os
import signal
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
import _whatsapp_utils as utils

ADAPTER_DIR = utils.adapter_dir()
GATEWAY_JS  = os.path.join(ADAPTER_DIR, "gateway.js")
PID_FILE    = os.path.join(utils.daemon_dir(), "whatsapp-gateway.pid")
LOG_DIR     = os.path.join(utils.daemon_dir(), "logs")
LOG_FILE    = os.path.join(LOG_DIR, "whatsapp.log")


def _read_pid():
    """Read PID from file, return int or None."""
    if not os.path.exists(PID_FILE):
        return None
    try:
        pid = int(open(PID_FILE).read().strip())
        os.kill(pid, 0)  # Check if process exists
        return pid
    except (ValueError, ProcessLookupError, PermissionError):
        try:
            os.unlink(PID_FILE)
        except OSError:
            pass
        return None


def cmd_status():
    """Check gateway status."""
    pid = _read_pid()
    if pid:
        health = utils.health_check()
        status = health.get("status", "unknown")
        uptime = health.get("uptime", 0)
        print(f"WhatsApp Gateway: running (PID {pid}, status={status}, uptime={uptime:.0f}s)")
    else:
        print("WhatsApp Gateway: not running")


def cmd_start():
    """Start gateway in background."""
    pid = _read_pid()
    if pid:
        print(f"WhatsApp Gateway already running (PID {pid})")
        return

    # Check node_modules
    node_modules = os.path.join(ADAPTER_DIR, "node_modules")
    if not os.path.exists(node_modules):
        print("Installing dependencies...")
        subprocess.run(["npm", "install"], cwd=ADAPTER_DIR, check=True)

    # Ensure log directory exists
    os.makedirs(LOG_DIR, exist_ok=True)

    # Start gateway as background process
    log_fd = open(LOG_FILE, "a")
    proc = subprocess.Popen(
        ["node", GATEWAY_JS],
        cwd=ADAPTER_DIR,
        stdout=log_fd,
        stderr=log_fd,
        start_new_session=True,
    )

    # Wait briefly to check it started
    time.sleep(2)
    if proc.poll() is not None:
        print(f"Gateway failed to start (exit code {proc.returncode})")
        print(f"Check logs: {LOG_FILE}")
        sys.exit(1)

    print(f"WhatsApp Gateway started (PID {proc.pid})")
    print(f"Logs: {LOG_FILE}")


def cmd_stop():
    """Stop the gateway."""
    pid = _read_pid()
    if not pid:
        print("WhatsApp Gateway is not running")
        return

    try:
        os.kill(pid, signal.SIGTERM)
        # Wait for graceful shutdown
        stopped = False
        for _ in range(10):
            time.sleep(0.5)
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                stopped = True
                break
        if not stopped:
            # SIGKILL fallback if SIGTERM didn't work
            try:
                os.kill(pid, signal.SIGKILL)
                time.sleep(0.5)
            except ProcessLookupError:
                pass
        print(f"WhatsApp Gateway stopped (PID {pid})")
    except ProcessLookupError:
        print("Gateway process already gone")

    try:
        os.unlink(PID_FILE)
    except OSError:
        pass


def cmd_pair():
    """Run gateway in foreground for QR code pairing."""
    pid = _read_pid()
    if pid:
        print(f"Gateway already running (PID {pid}). Stop it first: --stop")
        sys.exit(1)

    # Check node_modules
    node_modules = os.path.join(ADAPTER_DIR, "node_modules")
    if not os.path.exists(node_modules):
        print("Installing dependencies...")
        subprocess.run(["npm", "install"], cwd=ADAPTER_DIR, check=True)

    print("Starting WhatsApp Gateway in pairing mode...")
    print("Scan the QR code with WhatsApp → Settings → Linked Devices → Link a Device")
    print("Press Ctrl+C after pairing to stop.\n")

    try:
        subprocess.run(["node", GATEWAY_JS], cwd=ADAPTER_DIR)
    except KeyboardInterrupt:
        print("\nPairing session ended.")


def main():
    parser = argparse.ArgumentParser(description="WhatsApp Gateway lifecycle manager")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--start",  action="store_true", help="Start gateway in background")
    group.add_argument("--stop",   action="store_true", help="Stop gateway")
    group.add_argument("--status", action="store_true", help="Check gateway status")
    group.add_argument("--pair",   action="store_true", help="First-time QR pairing (foreground)")
    args = parser.parse_args()

    if args.start:
        cmd_start()
    elif args.stop:
        cmd_stop()
    elif args.status:
        cmd_status()
    elif args.pair:
        cmd_pair()


if __name__ == "__main__":
    main()
