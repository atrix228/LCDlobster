#!/usr/bin/env python3
"""
lobster_status.py — Universal display status sender for LCDlobster.

Installed as `lobster-status` in PATH. Sends state updates to the
display service socket so any AI tool can animate the raccoon.

─── Direct usage (any tool, shell scripts, cron, etc.) ─────────────
  lobster-status idle
  lobster-status thinking
  lobster-status responding
  lobster-status working
  lobster-status building
  lobster-status error

  Extra fields:
  lobster-status thinking --provider "Gemini 1.5"
  lobster-status error    --message  "API timeout"

─── Claude Code / OpenClaw hook mode ───────────────────────────────
  Reads the JSON hook payload from stdin automatically.

  PreToolUse  → maps tool name to working / building state
  PostToolUse → switches back to thinking (model is composing reply)
  Stop        → idle

  The hooks config at display/hooks/openclaw.json wires this up.

─── Pipe raw JSON ───────────────────────────────────────────────────
  echo '{"state":"thinking","provider":"GPT-4o"}' | lobster-status
"""

import sys
import json
import socket
import os
import argparse

SOCKET_PATH = os.environ.get("LOBSTER_SOCKET", "/tmp/raccoon.sock")

VALID_STATES = {
    "idle", "thinking", "responding", "listening",
    "working", "building", "error", "network", "qr",
}

# Map Claude Code tool names → display states
_TOOL_STATE = {
    "Bash":        "working",
    "computer":    "working",
    "Edit":        "building",
    "Write":       "building",
    "MultiEdit":   "building",
    "Read":        "thinking",
    "Glob":        "thinking",
    "Grep":        "thinking",
    "WebSearch":   "working",
    "WebFetch":    "working",
    "Agent":       "working",
    "TodoWrite":   "thinking",
    "TodoRead":    "thinking",
}


def _send(payload: dict) -> None:
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(2.0)
            s.connect(SOCKET_PATH)
            s.sendall((json.dumps(payload) + "\n").encode())
    except (OSError, ConnectionRefusedError, TimeoutError):
        pass  # display service not running — silent, never block the AI tool


def _read_stdin_json() -> dict:
    try:
        raw = sys.stdin.read()
        if raw.strip():
            return json.loads(raw)
    except Exception:
        pass
    return {}


def main() -> None:
    # ── No args: try to read raw JSON from stdin ──────────────────────────────
    if len(sys.argv) == 1:
        data = _read_stdin_json()
        if data:
            _send(data)
        return

    first = sys.argv[1]

    # ── Hook modes (stdin carries the Claude Code event payload) ──────────────
    if first == "--hook-pretool":
        hook = _read_stdin_json()
        tool = hook.get("tool_name", "")
        state = _TOOL_STATE.get(tool, "working")
        _send({"state": state})
        return

    if first == "--hook-posttool":
        _read_stdin_json()  # consume stdin even if unused
        _send({"state": "thinking"})
        return

    if first == "--hook-stop":
        _read_stdin_json()
        _send({"state": "idle"})
        return

    if first == "--hook-notification":
        _read_stdin_json()
        # Don't change animation state for notifications — they're informational
        return

    # ── Direct state name ─────────────────────────────────────────────────────
    parser = argparse.ArgumentParser(
        prog="lobster-status",
        description="Send a display state to the LCDlobster raccoon.",
        add_help=True,
    )
    parser.add_argument(
        "state",
        choices=sorted(VALID_STATES),
        help="Animation state to display",
    )
    parser.add_argument("--provider", default=None, help="Provider label for status bar")
    parser.add_argument("--message",  default=None, help="Error message (for error state)")

    args = parser.parse_args()

    payload: dict = {"state": args.state}
    if args.provider:
        payload["provider"] = args.provider
    if args.message and args.state == "error":
        payload["message"] = args.message

    _send(payload)


if __name__ == "__main__":
    main()
