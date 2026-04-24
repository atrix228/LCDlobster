#!/usr/bin/env python3
"""
diagnose_lcd.py — Step-by-step diagnostic for the Display HAT Mini on Pi Zero.

Run with:  sudo python3 diagnose_lcd.py
"""

import sys
import os
import subprocess


PASS = "\033[32m[PASS]\033[0m"
FAIL = "\033[31m[FAIL]\033[0m"
WARN = "\033[33m[WARN]\033[0m"
INFO = "\033[34m[INFO]\033[0m"


def section(title):
    print(f"\n{'─' * 52}")
    print(f"  {title}")
    print('─' * 52)


def check(label, ok, detail=""):
    mark = PASS if ok else FAIL
    print(f"  {mark}  {label}")
    if detail:
        for line in detail.splitlines():
            print(f"         {line}")
    return ok


def cmd_out(args):
    try:
        return subprocess.check_output(args, stderr=subprocess.STDOUT,
                                       text=True).strip()
    except Exception:
        return ""


# ── 1. Platform ───────────────────────────────────────────────────────────────
section("1 / Platform")

import platform
arch   = platform.machine()
pyver  = sys.version.split()[0]
is_pi  = os.path.exists("/proc/device-tree/model")
model  = open("/proc/device-tree/model").read().rstrip("\x00") if is_pi else "Not a Raspberry Pi"

check(f"Architecture: {arch}",  True)
check(f"Python: {pyver}",        True)
check(f"Model: {model}",         is_pi,
      "" if is_pi else "Not running on a Raspberry Pi — hardware tests will fail.")

os_id = cmd_out(["lsb_release", "-sd"]) or cmd_out(["cat", "/etc/os-release"]).split('\n')[0]
check(f"OS: {os_id}", True)

# ── 2. SPI ────────────────────────────────────────────────────────────────────
section("2 / SPI interface")

spi_dev  = os.path.exists("/dev/spidev0.0") or os.path.exists("/dev/spidev0.1")
spi_mod  = "spi_bcm2835" in cmd_out(["lsmod"])
boot_cfg = "/boot/firmware/config.txt" if os.path.exists("/boot/firmware/config.txt") \
           else "/boot/config.txt"
spi_cfg  = False
try:
    spi_cfg = "dtparam=spi=on" in open(boot_cfg).read()
except OSError:
    pass

check(f"SPI in {boot_cfg}", spi_cfg,
      f"Fix: add  dtparam=spi=on  to {boot_cfg}, then reboot")
check("SPI kernel module loaded (spi_bcm2835)", spi_mod,
      "Fix: reboot after enabling SPI, or run: sudo modprobe spi_bcm2835")
check("/dev/spidev0.0 or /dev/spidev0.1 present", spi_dev,
      "Fix: SPI not active — enable via raspi-config → Interface Options → SPI")

# ── 3. GPIO permissions ───────────────────────────────────────────────────────
section("3 / GPIO & permissions")

is_root  = os.geteuid() == 0
gpio_dev = os.path.exists("/dev/gpiomem")

check("Running as root or with GPIO access", is_root or gpio_dev,
      "Fix: run with sudo, or add your user to the gpio/spi groups")
check("/dev/gpiomem present", gpio_dev,
      "Fix: install raspi-gpio package; /dev/gpiomem is Pi-specific")

# ── 4. Python packages ────────────────────────────────────────────────────────
section("4 / Python packages")

def try_import(pkg, pip_name=None):
    try:
        __import__(pkg)
        mod = sys.modules[pkg]
        ver = getattr(mod, "__version__", "?")
        check(f"{pkg}  ({ver})", True)
        return True
    except ImportError as e:
        fix = f"Fix: pip3 install {pip_name or pkg} --break-system-packages"
        check(f"{pkg}", False, f"{e}\n{fix}")
        return False

pil_ok  = try_import("PIL",        "Pillow")
spi_ok  = try_import("spidev",     "spidev")

# Try rpi-lgpio first (Bookworm replacement for RPi.GPIO), then fall back
lgpio_ok = False
rpigpio_ok = False
try:
    import lgpio
    ver = getattr(lgpio, "__version__", "?")
    check(f"lgpio  ({ver})  [preferred on Bookworm]", True)
    lgpio_ok = True
except ImportError:
    print(f"  {WARN}  lgpio not installed (needed on Pi OS Bookworm)")
    print(f"         Fix: pip3 install rpi-lgpio --break-system-packages")

if not lgpio_ok:
    try:
        import RPi.GPIO as GPIO
        ver = getattr(GPIO, "VERSION", "?")
        check(f"RPi.GPIO  ({ver})  [legacy, may fail on Bookworm]", True)
        rpigpio_ok = True
    except ImportError:
        check("RPi.GPIO", False,
              "Fix: pip3 install RPi.GPIO --break-system-packages\n"
              "     OR (preferred on Bookworm): pip3 install rpi-lgpio --break-system-packages")

disp_ok = try_import("displayhatmini", "displayhatmini")

# ── 5. Hardware init ──────────────────────────────────────────────────────────
section("5 / Hardware init (Display HAT Mini)")

if not (spi_dev and disp_ok and pil_ok):
    print(f"  {WARN}  Skipping hardware test — prerequisites not met (see above).")
else:
    try:
        from displayhatmini import DisplayHATMini
        from PIL import Image, ImageDraw

        disp = DisplayHATMini(None)
        disp.set_backlight(1.0)
        W, H = DisplayHATMini.WIDTH, DisplayHATMini.HEIGHT

        check(f"DisplayHATMini init  ({W}x{H})", True)

        # Draw a simple test frame
        img  = Image.new("RGB", (W, H), (0, 80, 160))
        draw = ImageDraw.Draw(img)
        draw.text((10, 10), "LCD OK", fill=(255, 255, 255))
        disp.st7789.display(img)
        check("Frame pushed to display", True,
              "A blue screen with 'LCD OK' should be visible now.")

        import time; time.sleep(2)

        # Black out
        disp.st7789.display(Image.new("RGB", (W, H), (0, 0, 0)))
        disp.set_backlight(0)

    except Exception as exc:
        import traceback
        check("Hardware init", False, traceback.format_exc().strip())

# ── 6. Summary ────────────────────────────────────────────────────────────────
section("6 / Summary & quick-fix commands")

if not (lgpio_ok or rpigpio_ok):
    print(f"""
  {WARN}  GPIO library missing — most likely cause of your failure.

  On Pi OS Bookworm run:
    sudo pip3 install rpi-lgpio --break-system-packages
    sudo pip3 install displayhatmini --break-system-packages

  On Pi OS Bullseye run:
    sudo pip3 install RPi.GPIO --break-system-packages
    sudo pip3 install displayhatmini --break-system-packages
""")
elif not spi_dev:
    print(f"""
  {WARN}  SPI not active.

  Option A (raspi-config):
    sudo raspi-config
    → Interface Options → SPI → Yes → Finish → Reboot

  Option B (manual):
    echo "dtparam=spi=on" | sudo tee -a {boot_cfg}
    sudo reboot
""")
elif not disp_ok:
    print(f"""
  {WARN}  displayhatmini not installed.
    sudo pip3 install displayhatmini --break-system-packages
""")
else:
    print(f"  {PASS}  Everything looks good — run test_lcd.py to see the raccoon.\n")
