#!/usr/bin/env python3
"""Generate preview screenshots and animated GIFs for all raccoon states."""

import os
import sys
sys.path.insert(0, os.path.dirname(__file__))

from raccoon import RaccoonRenderer
from PIL import Image

OUT = os.path.join(os.path.dirname(__file__), "..", "assets")
os.makedirs(OUT, exist_ok=True)

r = RaccoonRenderer()

PROVIDER   = "ZeroClaw / Qwen3"
CONNECTED  = "connected"

# Best representative frame for each state (hand-picked for visual impact)
STILLS = {
    "idle":        1,   # tail right, eyes open
    "sleeping":    42,  # all 3 Zs fully visible
    "stretching":  0,   # arms raised, yawning
    "thinking":    2,   # paw raised, 3-dot bubble
    "responding":  1,   # mouth open
    "listening":   1,   # head tilted, ears up
    "working":     0,   # left paw up
    "building":    0,   # hard hat + wrench
    "error":       1,   # shaking, X eyes, drooping tail
    "celebrating": 2,   # bouncing, sparkles
    "confused":    24,  # 3 ? marks visible
    "searching":   3,   # magnifier swept right
    "reading":     0,   # glasses, laptop glow
    "excited":     2,   # star burst mid-burst
    "sneaky":      1,   # sunglasses, crouched
}

# Animated GIF states: state → list of frames to include
ANIMATIONS = {
    "thinking":    list(range(0, 12)),      # thought bubble cycling
    "sleeping":    list(range(24, 54)),     # Zzz full sequence
    "celebrating": list(range(0, 16)),      # bounce + sparkle loop
    "working":     list(range(0, 8)),       # typing paws
    "idle":        list(range(0, 8)),       # blink + wag
    "excited":     list(range(0, 12)),      # star burst spin
    "sneaky":      list(range(0, 8)),       # fast typing crouched
    "error":       list(range(0, 8)),       # shake + X eyes
}

# Sysinfo and network stills use dummy data
SYSINFO_STATS = {
    "cpu": 34, "mem_pct": 61, "mem_used": 312, "mem_total": 512,
    "temp": 52, "uptime": "2h 14m", "ssid": "HomeNetwork", "ip": "192.168.1.42",
}

print("Generating still frames...")
for state, frame in STILLS.items():
    img = r.draw_frame(state, frame, CONNECTED, PROVIDER)
    path = os.path.join(OUT, f"{state}.png")
    img.save(path)
    print(f"  {path}")

# Network and sysinfo screens
img = r.draw_frame("network", 0, CONNECTED, PROVIDER,
                   ip="192.168.1.42", ssid="HomeNetwork", hostname="lcdlobster")
img.save(os.path.join(OUT, "network.png"))
print(f"  {OUT}/network.png")

img = r.draw_frame("sysinfo", 0, CONNECTED, PROVIDER, stats=SYSINFO_STATS)
img.save(os.path.join(OUT, "sysinfo.png"))
print(f"  {OUT}/sysinfo.png")

print("\nGenerating animated GIFs...")
GIF_FPS = 6
FRAME_MS = int(1000 / GIF_FPS)

for state, frames in ANIMATIONS.items():
    imgs = [r.draw_frame(state, f, CONNECTED, PROVIDER) for f in frames]
    path = os.path.join(OUT, f"{state}.gif")
    imgs[0].save(
        path,
        save_all=True,
        append_images=imgs[1:],
        duration=FRAME_MS,
        loop=0,
        optimize=False,
    )
    print(f"  {path}  ({len(imgs)} frames @ {GIF_FPS} FPS)")

print("\nDone. All assets in:", OUT)
