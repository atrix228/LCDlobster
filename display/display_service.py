#!/usr/bin/env python3
"""
display_service.py — Raccoon display service for the Display HAT Mini (320x240).

Listens on /tmp/raccoon.sock for JSON state updates and animates the raccoon
character at ~6 FPS.

Expected JSON message format (newline-delimited):
    {"state": "thinking", "connectivity": "connected", "provider": "Claude 3"}

All fields are optional; missing fields keep their current values.
"""

import os
import sys
import json
import socket
import threading
import time

from PIL import Image

from raccoon import RaccoonRenderer

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
SOCKET_PATH = "/tmp/raccoon.sock"
FPS         = 6
FRAME_SLEEP = 1.0 / FPS


# ---------------------------------------------------------------------------
# Display backend — real hardware or debug fallback
# ---------------------------------------------------------------------------
def _init_display():
    """Return (display_obj, use_hardware) — falls back gracefully."""
    try:
        from displayhatmini import DisplayHATMini   # type: ignore
        disp = DisplayHATMini(None)
        disp.set_backlight(1.0)
        print("[display] Hardware display initialised.", flush=True)
        return disp, True
    except ImportError as exc:
        print(f"[display] displayhatmini not installed: {exc}", flush=True)
        print("[display] Run: pip3 install rpi-lgpio displayhatmini", flush=True)
    except Exception as exc:
        print(f"[display] Hardware init failed: {type(exc).__name__}: {exc}", flush=True)
        import traceback; traceback.print_exc()
    return None, False


def _push_frame(disp, use_hardware: bool, img: Image.Image):
    """Send a rendered frame to the display (or save it for debugging)."""
    if use_hardware:
        disp.display(img)
    else:
        img.save("/tmp/raccoon_frame.png")


# ---------------------------------------------------------------------------
# Shared mutable state — protected by a lock
# ---------------------------------------------------------------------------
class DisplayState:
    def __init__(self):
        self._lock        = threading.Lock()
        self.state        = "network"
        self.connectivity = "disconnected"
        self.provider     = "starting"
        self.qr_data      = ""
        self.ip           = ""
        self.ssid         = ""
        self.hostname     = ""
        self._frame       = 0

    def update(self, **kwargs):
        with self._lock:
            if "state" in kwargs and kwargs["state"] != self.state:
                self.state  = kwargs["state"]
                self._frame = 0
            if "connectivity" in kwargs:
                self.connectivity = kwargs["connectivity"]
            if "provider"     in kwargs:
                self.provider     = kwargs["provider"]
            if "qr_data"      in kwargs:
                self.qr_data      = kwargs["qr_data"]
            if "ip"           in kwargs:
                self.ip           = kwargs["ip"]
            if "ssid"         in kwargs:
                self.ssid         = kwargs["ssid"]
            if "hostname"     in kwargs:
                self.hostname     = kwargs["hostname"]

    def tick_frame(self) -> tuple:
        with self._lock:
            snap = (self.state, self._frame, self.connectivity,
                    self.provider, self.qr_data, self.ip, self.ssid, self.hostname)
            self._frame = (self._frame + 1) % 4
        return snap


# ---------------------------------------------------------------------------
# Render / display loop thread
# ---------------------------------------------------------------------------
def display_loop(shared: DisplayState, disp, use_hardware: bool,
                 renderer: RaccoonRenderer, stop_event: threading.Event):
    print("[display] Display loop started.", flush=True)
    while not stop_event.is_set():
        t0 = time.monotonic()

        state, frame, connectivity, provider, qr_data, ip, ssid, hostname = shared.tick_frame()

        try:
            img = renderer.draw_frame(state, frame, connectivity, provider,
                                      qr_data, ip, ssid, hostname)
            _push_frame(disp, use_hardware, img)
        except Exception as exc:
            print(f"[display] Render error: {exc}", flush=True)

        elapsed = time.monotonic() - t0
        sleep_t = FRAME_SLEEP - elapsed
        if sleep_t > 0:
            time.sleep(sleep_t)

    print("[display] Display loop stopped.", flush=True)


# ---------------------------------------------------------------------------
# Socket server (Unix domain, SOCK_STREAM, newline-delimited JSON)
# ---------------------------------------------------------------------------
def _handle_connection(conn: socket.socket, addr, shared: DisplayState):
    """Read newline-delimited JSON messages from a single client connection."""
    buf = b""
    try:
        conn.settimeout(30.0)
        while True:
            chunk = conn.recv(4096)
            if not chunk:
                break
            buf += chunk
            # Process all complete lines
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line.decode("utf-8"))
                    kwargs = {}
                    for field in ("state","connectivity","provider","qr_data","ip","ssid","hostname"):
                        if field in msg:
                            kwargs[field] = str(msg[field])
                    if kwargs:
                        shared.update(**kwargs)
                        print(f"[socket] State update: {kwargs}", flush=True)
                except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                    print(f"[socket] Bad message: {exc}", flush=True)
    except (OSError, socket.timeout):
        pass
    finally:
        try:
            conn.close()
        except OSError:
            pass


def socket_server(shared: DisplayState, stop_event: threading.Event):
    """Accept Unix-socket connections and spawn handler threads per client."""
    # Remove stale socket file
    try:
        os.unlink(SOCKET_PATH)
    except FileNotFoundError:
        pass

    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        srv.bind(SOCKET_PATH)
    except OSError as exc:
        print(f"[socket] Cannot bind {SOCKET_PATH}: {exc}", flush=True)
        stop_event.set()
        return

    os.chmod(SOCKET_PATH, 0o666)   # world-writable so node can talk to us
    srv.listen(8)
    srv.settimeout(1.0)            # allows periodic stop_event checks
    print(f"[socket] Listening on {SOCKET_PATH}", flush=True)

    threads = []

    try:
        while not stop_event.is_set():
            try:
                conn, addr = srv.accept()
            except socket.timeout:
                # Prune finished threads
                threads = [t for t in threads if t.is_alive()]
                continue
            except OSError:
                break

            t = threading.Thread(
                target=_handle_connection,
                args=(conn, addr, shared),
                daemon=True,
            )
            t.start()
            threads.append(t)
    finally:
        srv.close()
        try:
            os.unlink(SOCKET_PATH)
        except FileNotFoundError:
            pass
        print("[socket] Server stopped.", flush=True)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main():
    renderer     = RaccoonRenderer()
    shared       = DisplayState()
    disp, use_hw = _init_display()
    stop_event   = threading.Event()

    # Render one initial frame immediately so the display isn't blank
    try:
        img = renderer.draw_frame(shared.state, 0, shared.connectivity, shared.provider,
                                  shared.qr_data, shared.ip, shared.ssid, shared.hostname)
        _push_frame(disp, use_hw, img)
    except Exception as exc:
        print(f"[display] Initial frame error: {exc}", flush=True)

    # Start the animation loop in a background daemon thread
    loop_thread = threading.Thread(
        target=display_loop,
        args=(shared, disp, use_hw, renderer, stop_event),
        daemon=True,
        name="display-loop",
    )
    loop_thread.start()

    # Run the socket server in the main thread
    try:
        socket_server(shared, stop_event)
    except KeyboardInterrupt:
        print("\n[main] Interrupted — shutting down.", flush=True)
    finally:
        stop_event.set()
        loop_thread.join(timeout=2.0)
        print("[main] Goodbye.", flush=True)


if __name__ == "__main__":
    main()
