#!/usr/bin/env python3
"""
zeroclaw_bridge.py — Bridge between ZeroClaw daemon and the raccoon display.

Tails the ZeroClaw daemon log file and maps log events to raccoon states.
Also polls /health every 5 s to keep connectivity indicator up to date.

Run as a systemd user service (see setup-zeroclaw-bridge.sh).
"""

import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
import urllib.request

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
LOG_FILE       = os.path.expanduser("~/.zeroclaw/daemon.log")
RACCOON_SOCK   = "/tmp/raccoon.sock"
GATEWAY_HEALTH = "http://127.0.0.1:42617/health"
HEALTH_INTERVAL = 5      # seconds between health polls
IDLE_TIMEOUT    = 20     # seconds of log silence before going idle
PROVIDER_LABEL  = "ZeroClaw / DeepSeek"

# ---------------------------------------------------------------------------
# Log pattern → raccoon state
# Each entry: (compiled_regex, state_name, revert_after_secs or None)
# Patterns are checked in order; first match wins.
# ---------------------------------------------------------------------------
_P = re.compile
PATTERNS = [
    # ------ error ------
    (_P(r"ERROR|panicked|panic!|FATAL"),           "error",      None),

    # ------ incoming Telegram message ------
    (_P(r"zeroclaw_channels::telegram.*(receiv|update|inbound|dispatch|new message)",
        re.I),                                      "listening",  None),
    (_P(r"zeroclaw_channels::orchestrator.*(dispatch|queue|enqueue)",
        re.I),                                      "listening",  None),

    # ------ LLM thinking ------
    (_P(r"zeroclaw_runtime::agent"),                "thinking",   None),
    (_P(r"zeroclaw_providers"),                     "thinking",   None),
    (_P(r"zeroclaw_runtime::context|zeroclaw_runtime::memory.*load",
        re.I),                                      "thinking",   None),

    # ------ tool execution ------
    (_P(r"tool_execution|executing.*tool|tool.*dispatch|tool_call",
        re.I),                                      "working",    None),
    (_P(r"zeroclaw_runtime::tools"),                "working",    None),
    (_P(r"shell_tool|file_read|file_write|web_search|web_fetch",
        re.I),                                      "working",    None),

    # ------ response sent back ------
    (_P(r"zeroclaw_channels::telegram.*(send|sent|reply|respond)",
        re.I),                                      "responding", 4),
    (_P(r"zeroclaw_channels::orchestrator.*(send|sent|reply|respond|done|complete)",
        re.I),                                      "responding", 4),
]


# ---------------------------------------------------------------------------
# Raccoon socket helpers
# ---------------------------------------------------------------------------
def _send(payload: dict):
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(2)
        s.connect(RACCOON_SOCK)
        s.sendall(json.dumps(payload).encode() + b"\n")
        s.close()
    except Exception as exc:
        print(f"[bridge] socket error: {exc}", flush=True)


_current_state = "idle"
_revert_timer  = None
_state_lock    = threading.Lock()


def set_state(state: str, revert_after: float = None):
    global _current_state, _revert_timer
    with _state_lock:
        if _revert_timer:
            _revert_timer.cancel()
            _revert_timer = None
        if state == _current_state and not revert_after:
            return
        _current_state = state
        _send({"state": state, "provider": PROVIDER_LABEL})
        print(f"[bridge] → {state}", flush=True)

        if revert_after:
            def _revert():
                with _state_lock:
                    global _current_state, _revert_timer
                    _revert_timer = None
                    if _current_state not in ("idle", "sleeping"):
                        _current_state = "idle"
                        _send({"state": "idle", "provider": PROVIDER_LABEL})
                        print("[bridge] → idle (revert)", flush=True)
            _revert_timer = threading.Timer(revert_after, _revert)
            _revert_timer.daemon = True
            _revert_timer.start()


# ---------------------------------------------------------------------------
# Log tailer
# ---------------------------------------------------------------------------
def _classify(line: str):
    for pattern, state, revert in PATTERNS:
        if pattern.search(line):
            return state, revert
    return None, None


def tail_log(stop_event: threading.Event):
    """Follow LOG_FILE with tail -F; classify each line."""
    print(f"[bridge] Tailing {LOG_FILE}", flush=True)
    last_activity = time.monotonic()

    # Wait for log file to appear (daemon may not have started yet)
    while not stop_event.is_set() and not os.path.exists(LOG_FILE):
        time.sleep(2)

    proc = subprocess.Popen(
        ["tail", "-F", "-n", "0", LOG_FILE],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        bufsize=1,
    )

    idle_check = threading.Event()

    def _idle_watcher():
        while not stop_event.is_set():
            time.sleep(5)
            with _state_lock:
                cur = _current_state
            if cur not in ("idle", "sleeping", "network"):
                elapsed = time.monotonic() - last_activity
                if elapsed > IDLE_TIMEOUT:
                    set_state("idle")

    watcher = threading.Thread(target=_idle_watcher, daemon=True)
    watcher.start()

    try:
        for raw_line in proc.stdout:
            if stop_event.is_set():
                break
            line = raw_line.strip()
            if not line:
                continue

            state, revert = _classify(line)
            if state:
                last_activity = time.monotonic()
                set_state(state, revert_after=revert)
    finally:
        proc.terminate()
        proc.wait()


# ---------------------------------------------------------------------------
# Health poller — keeps connectivity dot accurate
# ---------------------------------------------------------------------------
def poll_health(stop_event: threading.Event):
    while not stop_event.is_set():
        try:
            with urllib.request.urlopen(GATEWAY_HEALTH, timeout=3) as resp:
                data = json.loads(resp.read())
            # "ok" from daemon and telegram channel = connected
            comps = data.get("runtime", {}).get("components", {})
            tg    = comps.get("channel:telegram", {}).get("status", "")
            conn  = "connected" if tg == "ok" else "disconnected"
            _send({"connectivity": conn})
        except Exception:
            _send({"connectivity": "disconnected"})
        time.sleep(HEALTH_INTERVAL)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main():
    print(f"[bridge] ZeroClaw raccoon bridge starting", flush=True)
    print(f"[bridge] Log file: {LOG_FILE}", flush=True)
    print(f"[bridge] Socket:   {RACCOON_SOCK}", flush=True)

    # Announce provider on the display
    _send({"provider": PROVIDER_LABEL})

    stop = threading.Event()

    threads = [
        threading.Thread(target=tail_log,    args=(stop,), daemon=True, name="log-tailer"),
        threading.Thread(target=poll_health, args=(stop,), daemon=True, name="health-poller"),
    ]
    for t in threads:
        t.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[bridge] Interrupted.", flush=True)
    finally:
        stop.set()


if __name__ == "__main__":
    main()
