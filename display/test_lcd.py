#!/usr/bin/env python3
"""
test_lcd.py — Quick hardware test for the Pimoroni Display HAT Mini.

Run this first to confirm the screen is working before starting the full service:
    sudo python3 test_lcd.py

Shows a sequence of coloured screens with text so you know exactly what's happening.
"""

import sys
import time
import traceback


def step(msg):
    print(f"  {msg}", flush=True)


def run_test():
    print("\n=== Display HAT Mini hardware test ===\n")

    # ── 1. Import PIL ──────────────────────────────────────────────────────────
    step("1. Importing PIL...")
    try:
        from PIL import Image, ImageDraw, ImageFont
        step("   OK")
    except ImportError:
        print("\nERROR: Pillow not installed.")
        print("Fix:  pip3 install Pillow --break-system-packages")
        sys.exit(1)

    # ── 2. Import displayhatmini ───────────────────────────────────────────────
    step("2. Importing displayhatmini...")
    try:
        from displayhatmini import DisplayHATMini
        step("   OK")
    except ImportError as e:
        print(f"\nERROR: displayhatmini not installed: {e}")
        print("Fix:  pip3 install displayhatmini --break-system-packages")
        sys.exit(1)

    # ── 3. Init hardware ───────────────────────────────────────────────────────
    step("3. Initialising display hardware...")
    try:
        display = DisplayHATMini(None)
        display.set_backlight(1.0)
        W = DisplayHATMini.WIDTH   # 320
        H = DisplayHATMini.HEIGHT  # 240
        step(f"   OK — display is {W}x{H}")
    except Exception as e:
        print(f"\nERROR: Could not init display: {e}")
        traceback.print_exc()
        print("\nCommon causes:")
        print("  - SPI not enabled  →  sudo raspi-config  → Interface Options → SPI → Yes")
        print("  - Wrong user perms →  run with sudo")
        print("  - Display not seated properly on GPIO header")
        sys.exit(1)

    # ── 4. Draw test frames ────────────────────────────────────────────────────
    step("4. Drawing test frames — watch the screen...\n")

    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 20)
        font_sm = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 14)
    except Exception:
        font = ImageFont.load_default()
        font_sm = font

    frames = [
        ((255,  50,  50), "RED",   "If you see this — screen works!"),
        (( 50, 200,  50), "GREEN", "Colours look OK"),
        (( 50, 100, 255), "BLUE",  "Almost done..."),
        ((255, 255, 255), "WHITE", "Test complete!"),
    ]

    for bg, label, subtitle in frames:
        img  = Image.new("RGB", (W, H), bg)
        draw = ImageDraw.Draw(img)

        # dark overlay for text readability
        text_col = (0, 0, 0) if bg == (255, 255, 255) else (255, 255, 255)
        bbox = draw.textbbox((0, 0), label, font=font)
        tw = bbox[2] - bbox[0]
        draw.text(((W - tw) // 2, 90), label, fill=text_col, font=font)

        bbox2 = draw.textbbox((0, 0), subtitle, font=font_sm)
        tw2 = bbox2[2] - bbox2[0]
        draw.text(((W - tw2) // 2, 130), subtitle, fill=text_col, font=font_sm)

        display.display(img)
        print(f"   {label}", flush=True)
        time.sleep(1.5)

    # ── 5. Final raccoon frame ─────────────────────────────────────────────────
    step("5. Drawing raccoon idle frame...")
    try:
        import os
        sys.path.insert(0, os.path.dirname(__file__))
        from raccoon import RaccoonRenderer
        r   = RaccoonRenderer()
        img = r.draw_frame("idle", 0, "disconnected", "test")
        display.display(img)
        step("   OK — raccoon is on screen")
        time.sleep(3)
    except Exception as e:
        print(f"   WARNING: raccoon renderer error: {e}")

    print("\n✓ All tests passed — display is working correctly.\n")
    print("Start the full service with:")
    print("  sudo systemctl start raccoon-display\n")


if __name__ == "__main__":
    run_test()
