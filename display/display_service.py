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
import subprocess
import threading
import time

from PIL import Image

from raccoon import RaccoonRenderer

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
SOCKET_PATH        = "/tmp/raccoon.sock"
FPS                = 6
FRAME_SLEEP        = 1.0 / FPS
IDLE_SLEEP_TIMEOUT = 120   # seconds of idle before raccoon falls asleep (2 min)
STRETCH_FRAMES     = 18    # frames to show "stretching" on wakeup (~3 s)

# Display HAT Mini button GPIO pins (BCM numbering, active-low)
BUTTON_A = 5
BUTTON_B = 6
BUTTON_X = 16
BUTTON_Y = 24


# ---------------------------------------------------------------------------
# Display backend — real hardware or debug fallback
# ---------------------------------------------------------------------------
def _init_display():
    """Return (display_obj, use_hardware) — retries on EBUSY, falls back gracefully."""
    try:
        from displayhatmini import DisplayHATMini   # type: ignore
    except ImportError as exc:
        print(f"[display] displayhatmini not installed: {exc}", flush=True)
        print("[display] Run: pip3 install rpi-lgpio displayhatmini", flush=True)
        return None, False

    for attempt in range(5):
        try:
            disp = DisplayHATMini(None)
            disp.set_backlight(1.0)
            print("[display] Hardware display initialised.", flush=True)
            return disp, True
        except OSError as exc:
            if exc.errno == 16 and attempt < 4:  # EBUSY — previous process still holds GPIO
                print(f"[display] GPIO busy, retrying in 2s (attempt {attempt + 1}/5)…", flush=True)
                time.sleep(2)
            else:
                print(f"[display] Hardware init failed: {type(exc).__name__}: {exc}", flush=True)
                import traceback; traceback.print_exc()
                break
        except Exception as exc:
            print(f"[display] Hardware init failed: {type(exc).__name__}: {exc}", flush=True)
            import traceback; traceback.print_exc()
            break

    return None, False


def _push_frame(disp, use_hardware: bool, img: Image.Image):
    """Send a rendered frame to the display (or save it for debugging)."""
    if use_hardware:
        disp.st7789.display(img)
    else:
        img.save("/tmp/raccoon_frame.png")


# ---------------------------------------------------------------------------
# System stats collector — updates every 2 s in a background thread
# ---------------------------------------------------------------------------
class SysInfoCollector:
    def __init__(self):
        self._lock     = threading.Lock()
        self._stats    = {}
        self._prev_cpu = None

    def get(self) -> dict:
        with self._lock:
            return dict(self._stats)

    def _collect(self):
        s = {}

        # CPU %
        try:
            with open('/proc/stat') as f:
                parts = f.readline().split()
            idle  = int(parts[4])
            total = sum(int(x) for x in parts[1:8])
            if self._prev_cpu:
                pi, pt = self._prev_cpu
                d_idle  = idle  - pi
                d_total = total - pt
                s['cpu'] = max(0, min(100, int(100 * (1 - d_idle / max(d_total, 1)))))
            else:
                s['cpu'] = 0
            self._prev_cpu = (idle, total)
        except Exception:
            s['cpu'] = 0

        # Memory
        try:
            mem = {}
            with open('/proc/meminfo') as f:
                for line in f:
                    k, v = line.split(':', 1)
                    mem[k.strip()] = int(v.split()[0])
            total_mb = mem['MemTotal']     // 1024
            avail_mb = mem['MemAvailable'] // 1024
            used_mb  = total_mb - avail_mb
            s['mem_pct']   = max(0, min(100, int(100 * used_mb / max(total_mb, 1))))
            s['mem_used']  = used_mb
            s['mem_total'] = total_mb
        except Exception:
            s['mem_pct'] = s['mem_used'] = s['mem_total'] = 0

        # Temperature
        try:
            with open('/sys/class/thermal/thermal_zone0/temp') as f:
                s['temp'] = int(f.read().strip()) // 1000
        except Exception:
            s['temp'] = 0

        # Uptime
        try:
            with open('/proc/uptime') as f:
                up = int(float(f.read().split()[0]))
            days = up // 86400
            hrs  = (up % 86400) // 3600
            mins = (up % 3600)  // 60
            s['uptime'] = (f"{days}d {hrs}h {mins}m" if days else
                           f"{hrs}h {mins}m"          if hrs  else
                           f"{mins}m")
        except Exception:
            s['uptime'] = '?'

        # IP address
        try:
            _s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            _s.connect(('8.8.8.8', 80))
            s['ip'] = _s.getsockname()[0]
            _s.close()
        except Exception:
            s['ip'] = ''

        # WiFi SSID
        try:
            r = subprocess.run(['iwgetid', '-r'],
                               capture_output=True, text=True, timeout=2)
            s['ssid'] = r.stdout.strip()
        except Exception:
            s['ssid'] = ''

        # Tailscale IP
        try:
            r = subprocess.run(['tailscale', 'ip', '-4'],
                               capture_output=True, text=True, timeout=3)
            s['tailscale_ip'] = r.stdout.strip()
        except Exception:
            try:
                r = subprocess.run(['ip', 'addr', 'show', 'tailscale0'],
                                   capture_output=True, text=True, timeout=2)
                for line in r.stdout.splitlines():
                    line = line.strip()
                    if line.startswith('inet '):
                        s['tailscale_ip'] = line.split()[1].split('/')[0]
                        break
                else:
                    s['tailscale_ip'] = ''
            except Exception:
                s['tailscale_ip'] = ''

        with self._lock:
            self._stats = s

    def run(self):
        while True:
            try:
                self._collect()
            except Exception:
                pass
            time.sleep(2)


# ---------------------------------------------------------------------------
# Shared mutable state — protected by a lock
# ---------------------------------------------------------------------------
class DisplayState:
    def __init__(self):
        self._lock          = threading.Lock()
        self.state          = "network"
        self.connectivity   = "disconnected"
        self.provider       = "starting"
        self.qr_data        = ""
        self.ip             = ""
        self.ssid           = ""
        self.hostname       = ""
        self._frame         = 0
        self._last_activity = time.monotonic()
        self._was_sleeping  = False
        self._stretch_count = 0
        # 0 = raccoon  1 = network info  2 = sysinfo
        self._button_mode   = 0

    def update(self, **kwargs):
        with self._lock:
            if "state" in kwargs and kwargs["state"] != self.state:
                incoming = kwargs["state"]
                # Waking from sleep → play stretch first
                if self.state == "sleeping" or self._was_sleeping:
                    self._was_sleeping  = True
                    self._stretch_count = 0
                self.state  = incoming
                self._frame = 0
                # Any bot activity snaps back to raccoon view
                if self._button_mode != 0:
                    self._button_mode = 0
                    print("[display] Button mode: raccoon (auto-reset)", flush=True)
            self._last_activity = time.monotonic()
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

    def cycle_display(self):
        """Button A: cycle raccoon → network → sysinfo → raccoon."""
        with self._lock:
            self._button_mode = (self._button_mode + 1) % 3
            labels = ["raccoon", "network", "sysinfo"]
            print(f"[display] Button mode: {labels[self._button_mode]}", flush=True)

    def idle_seconds(self) -> float:
        with self._lock:
            return time.monotonic() - self._last_activity

    def tick_frame(self) -> tuple:
        with self._lock:
            # Button cycle overrides everything
            if self._button_mode == 2:
                snap = ("sysinfo", self._frame, self.connectivity,
                        self.provider, self.qr_data, self.ip, self.ssid, self.hostname)
                self._frame = (self._frame + 1) % 120
                return snap
            if self._button_mode == 1:
                snap = ("network", self._frame, self.connectivity,
                        self.provider, self.qr_data, self.ip, self.ssid, self.hostname)
                self._frame = (self._frame + 1) % 120
                return snap

            state = self.state

            # In raccoon mode, never show the startup network screen
            if state == "network":
                state = "idle"

            # Auto-sleep when idle long enough
            if state == "idle" and (time.monotonic() - self._last_activity) > IDLE_SLEEP_TIMEOUT:
                state = "sleeping"

            # Wakeup stretch — play for STRETCH_FRAMES then let real state show
            if self._was_sleeping:
                if self._stretch_count < STRETCH_FRAMES:
                    state = "stretching"
                    self._stretch_count += 1
                else:
                    self._was_sleeping  = False
                    self._stretch_count = 0

            snap = (state, self._frame, self.connectivity,
                    self.provider, self.qr_data, self.ip, self.ssid, self.hostname)
            self._frame = (self._frame + 1) % 120
        return snap


# ---------------------------------------------------------------------------
# Render / display loop thread
# ---------------------------------------------------------------------------
def display_loop(shared: DisplayState, disp, use_hardware: bool,
                 renderer: RaccoonRenderer, stop_event: threading.Event,
                 sysinfo: SysInfoCollector):
    print("[display] Display loop started.", flush=True)
    while not stop_event.is_set():
        t0 = time.monotonic()

        state, frame, connectivity, provider, qr_data, ip, ssid, hostname = shared.tick_frame()

        try:
            stats = sysinfo.get() if state in ("sysinfo", "network") else None
            tailscale_ip = (stats or {}).get('tailscale_ip', '')
            img = renderer.draw_frame(state, frame, connectivity, provider,
                                      qr_data, ip, ssid, hostname, stats,
                                      tailscale_ip=tailscale_ip)
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
# Button polling thread — GPIO A toggles sysinfo, others reserved
# ---------------------------------------------------------------------------
def button_thread(shared: DisplayState, stop_event: threading.Event):
    try:
        import RPi.GPIO as GPIO
        GPIO.setmode(GPIO.BCM)
        for pin in (BUTTON_A, BUTTON_B, BUTTON_X, BUTTON_Y):
            GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        print("[buttons] GPIO button polling started.", flush=True)

        prev = {BUTTON_A: 1, BUTTON_B: 1, BUTTON_X: 1, BUTTON_Y: 1}
        while not stop_event.is_set():
            for pin in (BUTTON_A, BUTTON_B, BUTTON_X, BUTTON_Y):
                cur = GPIO.input(pin)
                if prev[pin] and not cur:      # falling edge = press
                    if pin == BUTTON_A:
                        shared.cycle_display()
                    # B / X / Y reserved for future use
                prev[pin] = cur
            time.sleep(0.05)
    except Exception as exc:
        print(f"[buttons] GPIO unavailable: {exc}", flush=True)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main():
    renderer     = RaccoonRenderer()
    shared       = DisplayState()
    sysinfo      = SysInfoCollector()
    disp, use_hw = _init_display()
    stop_event   = threading.Event()

    # Render one initial frame immediately so the display isn't blank
    try:
        img = renderer.draw_frame(shared.state, 0, shared.connectivity, shared.provider,
                                  shared.qr_data, shared.ip, shared.ssid, shared.hostname)
        _push_frame(disp, use_hw, img)
    except Exception as exc:
        print(f"[display] Initial frame error: {exc}", flush=True)

    # Background threads
    for name, target, args in [
        ("display-loop",  display_loop,   (shared, disp, use_hw, renderer, stop_event, sysinfo)),
        ("sysinfo",       sysinfo.run,    ()),
        ("buttons",       button_thread,  (shared, stop_event)),
    ]:
        t = threading.Thread(target=target, args=args, daemon=True, name=name)
        t.start()

    # Run the socket server in the main thread
    try:
        socket_server(shared, stop_event)
    except KeyboardInterrupt:
        print("\n[main] Interrupted — shutting down.", flush=True)
    finally:
        stop_event.set()
        print("[main] Goodbye.", flush=True)


if __name__ == "__main__":
    main()
