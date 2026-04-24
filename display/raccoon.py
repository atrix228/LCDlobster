#!/usr/bin/env python3
"""
raccoon.py — PIL-only raccoon character renderer for the 320x240 Display HAT Mini.

No external image files are used.  Everything is drawn with ImageDraw primitives.
"""

from PIL import Image, ImageDraw, ImageFont
import math

try:
    import qrcode  # type: ignore
    _HAS_QRCODE = True
except ImportError:
    _HAS_QRCODE = False


# ---------------------------------------------------------------------------
# Palette
# ---------------------------------------------------------------------------
WHITE      = (255, 255, 255)
LIGHT_GRAY = (204, 204, 204)
DARK_GRAY  = (136, 136, 136)
MID_GRAY   = (170, 170, 170)
BLACK      = (0,   0,   0)
YELLOW     = (255, 215,   0)
PINK       = (255, 200, 200)
GREEN      = ( 50, 200,  80)
RED        = (220,  50,  50)
LIGHT_BLUE = (140, 180, 255)
BG         = (10,   10,  10)   # near-black background


# ---------------------------------------------------------------------------
# RaccoonRenderer
# ---------------------------------------------------------------------------
class RaccoonRenderer:
    """Renders animation frames for a cartoon raccoon on a 320x240 canvas."""

    W = 320
    H = 240
    TOP_BAR    = 30
    BOTTOM_BAR = 30

    def __init__(self):
        try:
            ttf = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
            self._font_sm = ImageFont.truetype(ttf, 11)
            self._font_md = ImageFont.truetype(ttf, 13)
            self._font_lg = ImageFont.truetype(ttf, 22)
            self._font_xl = ImageFont.truetype(ttf, 30)
        except (IOError, OSError):
            self._font_sm = ImageFont.load_default()
            self._font_md = ImageFont.load_default()
            self._font_lg = ImageFont.load_default()
            self._font_xl = ImageFont.load_default()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def draw_frame(self, state: str, frame: int, connectivity: str,
                   provider: str = "", qr_data: str = "",
                   ip: str = "", ssid: str = "", hostname: str = "",
                   stats: dict = None) -> Image.Image:
        """Return a 320x240 RGB image for *state* at animation *frame*."""
        img  = Image.new("RGB", (self.W, self.H), BG)
        draw = ImageDraw.Draw(img)

        state = state.lower() if state else "idle"

        if state == "sysinfo":
            self._draw_sysinfo_screen(draw, stats or {}, connectivity)
            return img

        if state == "qr":
            self._draw_qr_screen(draw, img, qr_data, connectivity)
            return img

        if state == "network":
            self._draw_network_screen(draw, ip, ssid, hostname, connectivity)
            return img

        # Centre of the raccoon's world (inside the 180-px content band)
        cx = self.W // 2          # 160
        cy = self.TOP_BAR + 90    # 120  (centre of 30..210 band)

        if state == "idle":
            self._draw_idle(draw, cx, cy, frame)
        elif state == "sleeping":
            self._draw_sleeping(draw, cx, cy, frame)
        elif state == "stretching":
            self._draw_stretching(draw, cx, cy, frame)
        elif state == "thinking":
            self._draw_thinking(draw, cx, cy, frame)
        elif state == "responding":
            self._draw_responding(draw, cx, cy, frame)
        elif state == "listening":
            self._draw_listening(draw, cx, cy, frame)
        elif state == "working":
            self._draw_working(draw, cx, cy, frame)
        elif state == "building":
            self._draw_building(draw, cx, cy, frame)
        elif state == "error":
            self._draw_error(draw, cx, cy, frame)
        elif state == "celebrating":
            self._draw_celebrating(draw, cx, cy, frame)
        elif state == "confused":
            self._draw_confused(draw, cx, cy, frame)
        elif state == "searching":
            self._draw_searching(draw, cx, cy, frame)
        elif state == "reading":
            self._draw_reading(draw, cx, cy, frame)
        elif state == "excited":
            self._draw_excited(draw, cx, cy, frame)
        elif state == "sneaky":
            self._draw_sneaky(draw, cx, cy, frame)
        else:
            self._draw_idle(draw, cx, cy, frame)

        self._draw_status_bar(draw, state, connectivity, provider)
        return img

    def _draw_network_screen(self, draw: ImageDraw.ImageDraw,
                              ip: str, ssid: str, hostname: str, connectivity: str):
        """Full-screen network info: IP address, hostname, WiFi SSID, BT status."""
        # ── header bar ────────────────────────────────────────────────────────
        draw.rectangle([(0, 0), (self.W, 30)], fill=(15, 30, 60))
        self._text_centred(draw, 15, "LCDlobster", self._font_md, (100, 180, 255))

        # ── divider ───────────────────────────────────────────────────────────
        draw.line([(10, 32), (310, 32)], fill=(40, 80, 120), width=1)

        # ── IP label ──────────────────────────────────────────────────────────
        draw.text((16, 44), "IP Address", fill=DARK_GRAY, font=self._font_sm)

        ip_text = ip if ip and ip != "0.0.0.0" else "No network"
        ip_col  = WHITE if ip and ip != "0.0.0.0" else RED
        # Centre the large IP on screen
        bbox = draw.textbbox((0, 0), ip_text, font=self._font_xl)
        ip_w = bbox[2] - bbox[0]
        draw.text(((self.W - ip_w) // 2, 58), ip_text, fill=ip_col, font=self._font_xl)

        # ── divider ───────────────────────────────────────────────────────────
        draw.line([(10, 100), (310, 100)], fill=(40, 80, 120), width=1)

        # ── Hostname ──────────────────────────────────────────────────────────
        host_label = hostname if hostname else "lcdlobster"
        draw.text((16, 108), "Host:", fill=DARK_GRAY, font=self._font_sm)
        draw.text((70, 106), host_label, fill=LIGHT_GRAY, font=self._font_md)

        # ── WiFi SSID ─────────────────────────────────────────────────────────
        draw.text((16, 130), "WiFi:", fill=DARK_GRAY, font=self._font_sm)
        ssid_text = ssid if ssid else "—"
        ssid_col  = (100, 220, 100) if ssid else DARK_GRAY
        draw.text((70, 128), ssid_text[:24], fill=ssid_col, font=self._font_md)

        # ── SSH hint ──────────────────────────────────────────────────────────
        draw.line([(10, 152), (310, 152)], fill=(40, 80, 120), width=1)
        ssh_text = f"ssh pi@{ip}" if ip and ip != "0.0.0.0" else "waiting for network..."
        self._text_centred(draw, 164, ssh_text, self._font_sm, (80, 140, 200))

        # ── BT tether indicator ───────────────────────────────────────────────
        bt_col  = GREEN if connectivity == "connected" else (80, 80, 80)
        bt_text = "BT tether: ON" if connectivity == "connected" else "BT tether: OFF"
        draw.ellipse([(16, 182), (28, 194)], fill=bt_col)
        draw.text((36, 182), bt_text, fill=bt_col, font=self._font_sm)

        # ── bottom bar ────────────────────────────────────────────────────────
        draw.rectangle([(0, self.H - 22), (self.W, self.H)], fill=(15, 30, 60))
        self._text_centred(draw, self.H - 11, "starting up...", self._font_sm, DARK_GRAY)

    def _draw_qr_screen(self, draw: ImageDraw.ImageDraw, img: Image.Image,
                         qr_data: str, connectivity: str):
        """Render a scannable QR code centred on screen with instructions."""
        # Header
        draw.rectangle([(0, 0), (self.W, 26)], fill=(20, 20, 60))
        self._text_centred(draw, 13, "Scan with WhatsApp", self._font_md, WHITE)

        # BT indicator (top-right)
        dot_col = GREEN if connectivity == "connected" else RED
        draw.ellipse([(295, 8), (310, 22)], fill=dot_col)

        # Footer
        draw.rectangle([(0, self.H - 24), (self.W, self.H)], fill=(20, 20, 60))
        self._text_centred(draw, self.H - 12, "lcdlobster", self._font_sm, LIGHT_GRAY)

        if not _HAS_QRCODE or not qr_data:
            # Fallback: show placeholder box with message
            draw.rectangle([(80, 36), (240, 204)], outline=WHITE, width=2)
            self._text_centred(draw, 120, "QR unavailable", self._font_sm, RED)
            self._text_centred(draw, 136, "pip install qrcode", self._font_sm, LIGHT_GRAY)
            return

        # Generate QR matrix
        qr = qrcode.QRCode(
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=1,
            border=2,
        )
        qr.add_data(qr_data)
        qr.make(fit=True)

        # Render to a small PIL image (white on black for contrast)
        qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")

        # Scale to fit the available area (26..216 px vertically = 190px)
        avail_w = self.W - 20          # 300
        avail_h = self.H - 26 - 24    # 190
        scale   = min(avail_w // qr_img.width, avail_h // qr_img.height)
        scale   = max(scale, 1)

        scaled_w = qr_img.width  * scale
        scaled_h = qr_img.height * scale
        qr_img   = qr_img.resize((scaled_w, scaled_h), Image.NEAREST)

        # Centre the QR code in the available area
        paste_x = (self.W - scaled_w) // 2
        paste_y = 26 + (avail_h - scaled_h) // 2
        img.paste(qr_img, (paste_x, paste_y))

    def _text_centred(self, draw: ImageDraw.ImageDraw, y_centre: int,
                       text: str, font, colour):
        """Draw text horizontally centred at the given y centre coordinate."""
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        draw.text(((self.W - tw) // 2, y_centre - (bbox[3] - bbox[1]) // 2),
                  text, fill=colour, font=font)

    # ------------------------------------------------------------------
    # State-specific composition helpers
    # ------------------------------------------------------------------
    def _draw_idle(self, draw, cx, cy, frame):
        wag = 4 if (frame % 2 == 0) else -4
        self._draw_tail(draw, cx, cy, wag_offset=wag)
        blink = (frame % 4) >= 2          # half-close eyes on frames 2,3
        self._draw_raccoon_base(draw, cx, cy, blink=blink)

    def _draw_thinking(self, draw, cx, cy, frame):
        self._draw_tail(draw, cx, cy, wag_offset=0)
        self._draw_raccoon_base(draw, cx, cy)
        # Raised paw
        self._draw_raised_paw(draw, cx, cy)
        # Thought bubble — cycles 1,2,3,1
        dots = (frame % 3) + 1
        self._draw_thought_bubble(draw, cx + 38, cy - 72, dots)

    def _draw_responding(self, draw, cx, cy, frame):
        # Subtle head bob: shift cy by ±2
        bob = 2 if (frame % 2 == 0) else -2
        self._draw_tail(draw, cx, cy, wag_offset=3)
        self._draw_raccoon_base(draw, cx, cy + bob)
        open_amounts = [8, 12, 4, 2]
        self._draw_speech_mouth(draw, cx, cy + bob, open_amounts[frame % 4])

    def _draw_listening(self, draw, cx, cy, frame):
        lean = 5 if (frame % 4) < 2 else -5
        self._draw_tail(draw, cx, cy, wag_offset=0)
        self._draw_raccoon_base(draw, cx + lean, cy, ears_up=True)

    def _draw_working(self, draw, cx, cy, frame):
        self._draw_tail(draw, cx, cy, wag_offset=2)
        self._draw_raccoon_base(draw, cx, cy, looking_down=True)
        left_up  = (frame % 4) < 2
        self._draw_typing_paws(draw, cx, cy, left_up=left_up)

    def _draw_building(self, draw, cx, cy, frame):
        self._draw_tail(draw, cx, cy, wag_offset=0)
        self._draw_raccoon_base(draw, cx, cy, hard_hat=True)
        angle_left = (frame % 4) < 2
        self._draw_wrench(draw, cx, cy, angle_left=angle_left)

    def _draw_error(self, draw, cx, cy, frame):
        shake = 0
        if (frame % 4) >= 2:
            shake = 2 if (frame % 2 == 0) else -2
        self._draw_tail(draw, cx, cy, wag_offset=0, drooping=True)
        self._draw_raccoon_base(draw, cx + shake, cy + 6, x_eyes=True)

    def _draw_sleeping(self, draw, cx, cy, frame):
        # Gentle belly breathing — body shifts 2px on slow cycle
        breathe = 1 if (frame % 24) < 12 else -1
        self._draw_tail(draw, cx, cy, wag_offset=0)
        self._draw_raccoon_base(draw, cx, cy + breathe, sleeping=True)
        self._draw_zzz(draw, cx, cy, frame)

    def _draw_stretching(self, draw, cx, cy, frame):
        """Yawning raccoon — plays briefly on wakeup."""
        self._draw_tail(draw, cx, cy, wag_offset=3)
        self._draw_raccoon_base(draw, cx, cy, blink=(frame % 4 < 2))
        # Both arms raised
        draw.line([cx - 26, cy + 40, cx - 42, cy + 4], fill=DARK_GRAY, width=8)
        self._draw_paw(draw, cx - 42, cy + 2, scale=0.9)
        draw.line([cx + 26, cy + 40, cx + 42, cy + 4], fill=DARK_GRAY, width=8)
        self._draw_paw(draw, cx + 42, cy + 2, scale=0.9)
        # Wide yawn mouth
        self._draw_speech_mouth(draw, cx, cy, open_amount=14)

    # ------------------------------------------------------------------
    # ZZZ helpers
    # ------------------------------------------------------------------
    def _draw_z(self, draw, x, y, size, color):
        """Draw a single Z glyph with three lines."""
        draw.line([x,        y,        x + size, y       ], fill=color, width=2)
        draw.line([x + size, y,        x,        y + size], fill=color, width=2)
        draw.line([x,        y + size, x + size, y + size], fill=color, width=2)

    def _draw_zzz(self, draw, cx, cy, frame):
        """Three Z letters rising in sequence to the upper-right."""
        # Each Z rises over 18 frames then loops.  Phase drives which Zs are visible.
        cycle = frame % 18
        phase = frame % 54   # 3-step sequence of 18 frames each

        # Base anchor to the right of the raccoon's head
        bx, by = cx + 44, cy - 28

        # Rise offset grows as cycle advances (0..17 → 0..17 px up)
        rise = cycle

        # Small Z — always visible
        self._draw_z(draw, bx,     by - rise,      size=7,  color=LIGHT_BLUE)

        # Medium Z — appears in 2nd and 3rd phases
        if phase >= 18:
            self._draw_z(draw, bx + 10, by - 18 - rise // 2, size=10, color=LIGHT_BLUE)

        # Large Z — only in 3rd phase
        if phase >= 36:
            self._draw_z(draw, bx + 22, by - 36 - rise // 3, size=14, color=LIGHT_BLUE)

    def _draw_celebrating(self, draw, cx, cy, frame):
        bounce = -6 if (frame % 4) < 2 else 0
        wag = 8 if (frame % 2 == 0) else -8
        self._draw_tail(draw, cx, cy, wag_offset=wag)
        self._draw_raccoon_base(draw, cx, cy + bounce)
        self._draw_party_hat(draw, cx, cy + bounce)
        # Stars at fixed positions, alternate visibility per frame
        for i, (sx, sy) in enumerate([(cx-62,cy-44),(cx+62,cy-52),(cx-52,cy+18),(cx+68,cy+8)]):
            if (frame + i) % 2 == 0:
                self._draw_sparkle(draw, sx, sy, 6, YELLOW)

    def _draw_confused(self, draw, cx, cy, frame):
        # Head tilts left and right in a slow cycle
        lean_seq = [4, 7, 4, 0, -4, -7, -4, 0]
        lean = lean_seq[frame % len(lean_seq)]
        self._draw_tail(draw, cx, cy, wag_offset=0)
        self._draw_raccoon_base(draw, cx + lean, cy)
        self._draw_raised_paw(draw, cx + lean, cy)
        # Cycling ? marks
        q_count = (frame // 8) % 3 + 1
        for i in range(q_count):
            draw.text((cx + 36 + i * 14, cy - 58 - i * 6), "?",
                      fill=YELLOW, font=self._font_md)

    def _draw_searching(self, draw, cx, cy, frame):
        # Scan side to side
        scan_seq = [-10, -6, 0, 6, 10, 6, 0, -6]
        scan = scan_seq[frame % len(scan_seq)]
        self._draw_tail(draw, cx, cy, wag_offset=2)
        self._draw_raccoon_base(draw, cx + scan // 3, cy, looking_down=True)
        self._draw_magnifier(draw, cx + 56 + scan, cy - 18)

    def _draw_reading(self, draw, cx, cy, frame):
        breathe = 1 if (frame % 12) < 6 else 0
        self._draw_tail(draw, cx, cy, wag_offset=0)
        self._draw_raccoon_base(draw, cx, cy + breathe, looking_down=True)
        # Glasses overlay (calculated from same geometry as _draw_raccoon_base)
        s = 1.0
        hy     = (cy + breathe) - int(52 * s)
        mask_y = hy + int(16 * s)
        eye_y  = mask_y + int(2 * s)
        lex    = cx - int(26 * s)
        rex    = cx + int(26 * s)
        ew     = int(14 * s)
        for ex_c in [lex, rex]:
            draw.ellipse([ex_c - ew//2 - 1, eye_y - 1,
                          ex_c + ew//2 + 1, eye_y + int(10*s) + 2],
                         outline=BLACK, width=2)
        draw.line([lex + ew//2 + 1, eye_y + 4,
                   rex - ew//2 - 1, eye_y + 4], fill=BLACK, width=1)
        # Laptop/screen glow below raccoon
        draw.rectangle([cx - 36, cy + breathe + 46,
                         cx + 36, cy + breathe + 68],
                        fill=(20, 25, 55), outline=(50, 70, 140))
        for row, ly in enumerate([cy + breathe + 52, cy + breathe + 59, cy + breathe + 65]):
            lw = 50 if row < 2 else 30
            draw.line([cx - lw//2, ly, cx + lw//2, ly], fill=(70, 110, 200), width=1)

    def _draw_excited(self, draw, cx, cy, frame):
        bounce_seq = [-10, -14, -12, -6, 0, -4]
        bounce = bounce_seq[frame % len(bounce_seq)]
        wag = 10 if (frame % 2 == 0) else -10
        self._draw_tail(draw, cx, cy, wag_offset=wag)
        self._draw_raccoon_base(draw, cx, cy + bounce)
        # Star burst radiating outward
        for i, angle in enumerate(range(0, 360, 45)):
            rad  = math.radians(angle + frame * 20)
            dist = 52 + 8 * math.sin(frame * 0.8 + i)
            sx   = int(cx + dist * math.cos(rad))
            sy   = int((cy + bounce) + dist * 0.65 * math.sin(rad))
            self._draw_sparkle(draw, sx, sy, 5, YELLOW)

    def _draw_sneaky(self, draw, cx, cy, frame):
        # Crouched — shift down 10 px
        self._draw_tail(draw, cx, cy + 10, wag_offset=0)
        self._draw_raccoon_base(draw, cx, cy + 10)
        # Sunglasses overlay
        s = 1.0
        hy     = (cy + 10) - int(52 * s)
        mask_y = hy + int(16 * s)
        eye_y  = mask_y + int(2 * s)
        lex    = cx - int(26 * s)
        rex    = cx + int(26 * s)
        ew     = int(14 * s)
        for ex_c in [lex, rex]:
            draw.ellipse([ex_c - ew//2 - 1, eye_y - 1,
                          ex_c + ew//2 + 1, eye_y + int(10*s) + 1],
                         fill=(15, 15, 15), outline=BLACK, width=2)
        draw.line([lex + ew//2 + 1, eye_y + 4,
                   rex - ew//2 - 1, eye_y + 4], fill=BLACK, width=2)
        # Fast typing paws
        self._draw_typing_paws(draw, cx, cy + 10, left_up=(frame % 2 == 0))

    # ------------------------------------------------------------------
    # New animation helpers
    # ------------------------------------------------------------------
    def _draw_sparkle(self, draw, x, y, size, color):
        s2 = max(size // 2, 1)
        draw.line([x - size, y, x + size, y], fill=color, width=2)
        draw.line([x, y - size, x, y + size], fill=color, width=2)
        draw.line([x - s2, y - s2, x + s2, y + s2], fill=color, width=1)
        draw.line([x + s2, y - s2, x - s2, y + s2], fill=color, width=1)

    def _draw_party_hat(self, draw, cx, cy):
        """Cone hat on top of raccoon's head."""
        s = 1.0
        hy      = cy - int(52 * s)
        base_y  = hy + 6
        tip_y   = hy - 28
        hw      = 14
        draw.polygon([(cx - hw, base_y), (cx + hw, base_y), (cx, tip_y)],
                     fill=(220, 50, 50))
        # Stripe
        draw.polygon([(cx - hw//2, base_y - 10), (cx + hw//2, base_y - 10),
                      (cx + hw//4, base_y - 20), (cx - hw//4, base_y - 20)],
                     fill=YELLOW)
        # Pompom
        draw.ellipse([cx - 5, tip_y - 5, cx + 5, tip_y + 5],
                     fill=WHITE, outline=LIGHT_GRAY)

    def _draw_magnifier(self, draw, x, y):
        """Simple magnifying glass."""
        r = 11
        draw.ellipse([x - r, y - r, x + r, y + r],
                     outline=LIGHT_GRAY, width=3)
        draw.ellipse([x - r + 2, y - r + 2, x + r - 2, y + r - 2],
                     outline=(180, 220, 255), width=1)
        draw.line([x + r - 2, y + r - 2, x + r + 10, y + r + 10],
                  fill=LIGHT_GRAY, width=4)

    # ------------------------------------------------------------------
    # Sysinfo screen
    # ------------------------------------------------------------------
    def _draw_bar(self, draw, x, y, w, h, pct):
        clr = RED if pct >= 85 else (YELLOW if pct >= 60 else GREEN)
        draw.rectangle([(x, y), (x + w, y + h)], outline=DARK_GRAY, width=1)
        filled = max(0, int(w * pct / 100) - 2)
        if filled > 0:
            draw.rectangle([(x + 1, y + 1), (x + 1 + filled, y + h - 1)], fill=clr)

    def _draw_sysinfo_screen(self, draw, stats: dict, connectivity: str):
        # Header
        draw.rectangle([(0, 0), (self.W, 30)], fill=(15, 25, 50))
        self._text_centred(draw, 15, "SYSTEM INFO", self._font_md, (100, 180, 255))
        dot_col = GREEN if connectivity == "connected" else (80, 80, 80)
        draw.ellipse([(self.W - 18, 9), (self.W - 6, 21)], fill=dot_col)

        y = 36

        # CPU
        cpu = stats.get('cpu', 0)
        draw.text((8, y), "CPU", fill=DARK_GRAY, font=self._font_sm)
        self._draw_bar(draw, 50, y, 190, 12, cpu)
        draw.text((248, y), f"{cpu:3d}%", fill=WHITE, font=self._font_sm)
        y += 20

        # Memory
        mem_pct  = stats.get('mem_pct', 0)
        mem_used = stats.get('mem_used', 0)
        mem_tot  = stats.get('mem_total', 0)
        draw.text((8, y), "MEM", fill=DARK_GRAY, font=self._font_sm)
        self._draw_bar(draw, 50, y, 190, 12, mem_pct)
        draw.text((248, y), f"{mem_pct:3d}%", fill=WHITE, font=self._font_sm)
        y += 16
        draw.text((50, y), f"{mem_used} MB / {mem_tot} MB",
                  fill=DARK_GRAY, font=self._font_sm)
        y += 18

        # Temp
        temp     = stats.get('temp', 0)
        temp_col = RED if temp >= 75 else (YELLOW if temp >= 60 else GREEN)
        draw.text((8, y), "TEMP", fill=DARK_GRAY, font=self._font_sm)
        draw.text((58, y), f"{temp}°C", fill=temp_col, font=self._font_md)
        y += 20

        # Uptime
        draw.text((8, y), "UP", fill=DARK_GRAY, font=self._font_sm)
        draw.text((50, y), stats.get('uptime', '—'), fill=WHITE, font=self._font_sm)
        y += 20

        # Divider
        draw.line([(8, y), (self.W - 8, y)], fill=(40, 70, 120), width=1)
        y += 8

        # WiFi
        ssid = stats.get('ssid', '')
        draw.text((8, y), "WiFi", fill=DARK_GRAY, font=self._font_sm)
        draw.text((54, y), ssid[:24] if ssid else "—",
                  fill=(80, 220, 80) if ssid else DARK_GRAY, font=self._font_sm)
        y += 18

        # IP
        ip = stats.get('ip', '')
        draw.text((8, y), "IP", fill=DARK_GRAY, font=self._font_sm)
        draw.text((54, y), ip if ip else "no network",
                  fill=WHITE if ip else RED, font=self._font_sm)

        # Footer
        draw.rectangle([(0, self.H - 22), (self.W, self.H)], fill=(15, 25, 50))
        self._text_centred(draw, self.H - 11, "press A to return", self._font_sm, DARK_GRAY)

    # ------------------------------------------------------------------
    # Core raccoon drawing
    # ------------------------------------------------------------------
    def _draw_raccoon_base(self, draw, cx, cy, scale=1.0,
                           blink=False, ears_up=False, x_eyes=False,
                           looking_down=False, hard_hat=False, sleeping=False):
        """Draw body, head, ears, mask, muzzle, nose, eyes."""
        s = scale

        # ---- body ----
        bw, bh = int(54 * s), int(62 * s)
        bx, by = cx - bw // 2, cy - bh // 2 + int(30 * s)
        draw.ellipse([bx, by, bx + bw, by + bh], fill=DARK_GRAY, outline=BLACK, width=2)

        # Belly highlight
        belly_w, belly_h = int(30 * s), int(38 * s)
        bxb = cx - belly_w // 2
        byb = by + int(10 * s)
        draw.ellipse([bxb, byb, bxb + belly_w, byb + belly_h], fill=LIGHT_GRAY)

        # ---- ears ----
        ear_y_offset = int(8 * s) if ears_up else int(16 * s)
        ear_base_y   = cy - int(38 * s) - ear_y_offset

        # Left ear (triangle, outer)
        lx = cx - int(28 * s)
        draw.polygon([
            (lx - int(12 * s), ear_base_y + int(22 * s)),
            (lx,               ear_base_y - int(2 * s)),
            (lx + int(12 * s), ear_base_y + int(22 * s)),
        ], fill=BLACK, outline=BLACK)
        # Left ear inner (pink/white)
        draw.polygon([
            (lx - int(6 * s),  ear_base_y + int(18 * s)),
            (lx,               ear_base_y + int(4 * s)),
            (lx + int(6 * s),  ear_base_y + int(18 * s)),
        ], fill=PINK)

        # Right ear
        rx = cx + int(28 * s)
        draw.polygon([
            (rx - int(12 * s), ear_base_y + int(22 * s)),
            (rx,               ear_base_y - int(2 * s)),
            (rx + int(12 * s), ear_base_y + int(22 * s)),
        ], fill=BLACK, outline=BLACK)
        draw.polygon([
            (rx - int(6 * s),  ear_base_y + int(18 * s)),
            (rx,               ear_base_y + int(4 * s)),
            (rx + int(6 * s),  ear_base_y + int(18 * s)),
        ], fill=PINK)

        # ---- head ----
        hw, hh = int(64 * s), int(58 * s)
        hx, hy = cx - hw // 2, cy - int(52 * s)
        draw.ellipse([hx, hy, hx + hw, hy + hh], fill=DARK_GRAY, outline=BLACK, width=2)

        # ---- raccoon mask (black band across eyes) ----
        mask_y = hy + int(16 * s)
        mask_h = int(18 * s)
        draw.ellipse([hx + int(2*s), mask_y,
                      hx + hw - int(2*s), mask_y + mask_h],
                     fill=BLACK)

        # ---- white muzzle ----
        muz_w, muz_h = int(34 * s), int(22 * s)
        mx = cx - muz_w // 2
        my = hy + hh - int(26 * s)
        draw.ellipse([mx, my, mx + muz_w, my + muz_h], fill=WHITE, outline=LIGHT_GRAY)

        # ---- nose ----
        nw, nh = int(12 * s), int(7 * s)
        nx, ny = cx - nw // 2, my + int(2 * s)
        draw.ellipse([nx, ny, nx + nw, ny + nh], fill=BLACK)

        # ---- eyes ----
        eye_y = mask_y + int(2 * s)
        ey_h  = int(10 * s) if not blink else int(4 * s)
        eye_w = int(14 * s)
        lex   = cx - int(26 * s)
        rex   = cx + int(26 * s)

        if sleeping:
            # Closed arcs — peaceful sleep lines
            for ex_c in [lex, rex]:
                draw.arc([ex_c - eye_w // 2, eye_y - int(2 * s),
                          ex_c + eye_w // 2, eye_y + int(6 * s)],
                         start=0, end=180, fill=BLACK, width=2)
        else:
            # Left eye white
            draw.ellipse([lex - eye_w // 2, eye_y,
                          lex + eye_w // 2, eye_y + ey_h],
                         fill=WHITE, outline=BLACK)
            # Right eye white
            draw.ellipse([rex - eye_w // 2, eye_y,
                          rex + eye_w // 2, eye_y + ey_h],
                         fill=WHITE, outline=BLACK)

            if x_eyes:
                for ex_c in [lex, rex]:
                    xr = int(6 * s)
                    draw.line([ex_c - xr, eye_y, ex_c + xr, eye_y + ey_h],
                              fill=RED, width=2)
                    draw.line([ex_c + xr, eye_y, ex_c - xr, eye_y + ey_h],
                              fill=RED, width=2)
            else:
                pu_dy = int(3 * s) if looking_down else int(2 * s)
                pu_r  = int(4 * s)
                if not blink:
                    draw.ellipse([lex - pu_r, eye_y + pu_dy,
                                  lex + pu_r, eye_y + pu_dy + pu_r * 2],
                                 fill=BLACK)
                    draw.ellipse([rex - pu_r, eye_y + pu_dy,
                                  rex + pu_r, eye_y + pu_dy + pu_r * 2],
                                 fill=BLACK)
                    # Catchlights
                    draw.ellipse([lex - pu_r + 2, eye_y + pu_dy + 1,
                                  lex - pu_r + 4, eye_y + pu_dy + 3],
                                 fill=WHITE)
                    draw.ellipse([rex - pu_r + 2, eye_y + pu_dy + 1,
                                  rex - pu_r + 4, eye_y + pu_dy + 3],
                                 fill=WHITE)

        # ---- idle mouth (small smile) ----
        sm_y = my + int(12 * s)
        draw.arc([cx - int(8 * s), sm_y,
                  cx + int(8 * s), sm_y + int(8 * s)],
                 start=0, end=180, fill=BLACK, width=2)

        # ---- hard hat dot ----
        if hard_hat:
            hh_cx = cx
            hh_cy = hy - int(4 * s)
            hh_r  = int(10 * s)
            draw.ellipse([hh_cx - hh_r, hh_cy - hh_r,
                          hh_cx + hh_r, hh_cy + hh_r],
                         fill=YELLOW, outline=BLACK, width=2)

        # ---- front paws (resting) ----
        paw_y = by + bh - int(10 * s)
        for px_off in [-int(18 * s), int(18 * s)]:
            self._draw_paw(draw, cx + px_off, paw_y, s)

    def _draw_tail(self, draw, cx, cy, wag_offset=0, drooping=False):
        """Draw the striped raccoon tail curled around to the side."""
        # Build a curved tail using a series of ellipses/arcs
        # Tail base starts at lower-right of body
        base_x = cx + 30
        base_y = cy + 60

        if drooping:
            # Tail hangs straight down
            points = []
            for i in range(10):
                t  = i / 9.0
                tx = base_x + int(10 * math.sin(t * 0.8))
                ty = base_y + int(t * 50)
                points.append((tx, ty))
        else:
            # Tail curves around bottom-left
            points = []
            for i in range(14):
                t   = i / 13.0
                ang = math.pi * 0.1 + t * math.pi * 1.1
                r   = 30 + t * 18
                tx  = cx + int(r * math.cos(ang)) + wag_offset
                ty  = cy + 58 + int(r * 0.45 * math.sin(ang))
                points.append((tx, ty))

        # Draw thick tail with alternating stripes
        stripe_w = [10, 9, 8, 7, 6, 5, 5, 5, 4, 4, 4, 3, 3, 3]
        colors   = [BLACK, DARK_GRAY, BLACK, DARK_GRAY, BLACK, DARK_GRAY,
                    BLACK, DARK_GRAY, BLACK, DARK_GRAY, BLACK, DARK_GRAY,
                    BLACK, DARK_GRAY]

        for i in range(len(points) - 1):
            w = stripe_w[i] if i < len(stripe_w) else 3
            c = colors[i % 2]
            x0, y0 = points[i]
            x1, y1 = points[i + 1]
            draw.line([x0, y0, x1, y1], fill=c, width=w)

        # Tail tip — white fluffy dot
        if points:
            tx, ty = points[-1]
            draw.ellipse([tx - 5, ty - 5, tx + 5, ty + 5], fill=WHITE, outline=BLACK)

    def _draw_paw(self, draw, px, py, scale=1.0):
        s  = scale
        pw = int(14 * s)
        ph = int(10 * s)
        draw.ellipse([px - pw // 2, py - ph // 2,
                      px + pw // 2, py + ph // 2],
                     fill=DARK_GRAY, outline=BLACK, width=1)
        # Three toe nubs
        for i in range(3):
            tx = px - int(4 * s) + i * int(4 * s)
            ty = py - ph // 2 - int(3 * s)
            draw.ellipse([tx - 2, ty - 2, tx + 2, ty + 2], fill=DARK_GRAY, outline=BLACK)

    def _draw_raised_paw(self, draw, cx, cy):
        """Right paw raised to chin — thinking pose."""
        # Arm
        ax0, ay0 = cx + 26, cy + 40
        ax1, ay1 = cx + 38, cy + 10
        draw.line([ax0, ay0, ax1, ay1], fill=DARK_GRAY, width=8)
        # Paw at chin
        self._draw_paw(draw, ax1, ay1 - 2, scale=0.9)

    def _draw_typing_paws(self, draw, cx, cy, left_up=True):
        """Paws in a typing / working motion."""
        # Left paw
        lpy = cy + 45 if not left_up else cy + 30
        draw.line([cx - 26, cy + 55, cx - 22, lpy], fill=DARK_GRAY, width=7)
        self._draw_paw(draw, cx - 22, lpy, scale=0.85)

        # Right paw
        rpy = cy + 45 if left_up else cy + 30
        draw.line([cx + 26, cy + 55, cx + 22, rpy], fill=DARK_GRAY, width=7)
        self._draw_paw(draw, cx + 22, rpy, scale=0.85)

        # Surface (desk / object being worked on)
        draw.rectangle([cx - 40, cy + 60, cx + 40, cy + 66],
                       fill=LIGHT_GRAY, outline=BLACK)

    def _draw_wrench(self, draw, cx, cy, angle_left=True):
        """Draw a simple wrench shape held in front of the raccoon."""
        # Wrench handle as thick line + circle head
        if angle_left:
            x0, y0 = cx + 10, cy + 50
            x1, y1 = cx + 42, cy + 22
        else:
            x0, y0 = cx + 14, cy + 50
            x1, y1 = cx + 46, cy + 26

        draw.line([x0, y0, x1, y1], fill=LIGHT_GRAY, width=6)
        draw.line([x0, y0, x1, y1], fill=WHITE,      width=2)

        # Wrench head (open C shape)
        head_r = 9
        draw.ellipse([x1 - head_r, y1 - head_r, x1 + head_r, y1 + head_r],
                     fill=BG, outline=LIGHT_GRAY, width=4)
        # Jaw gap
        if angle_left:
            draw.line([x1, y1 - head_r, x1 + head_r, y1 - head_r + 5],
                      fill=BG, width=5)
        else:
            draw.line([x1 - head_r, y1, x1, y1 + head_r],
                      fill=BG, width=5)

    # ------------------------------------------------------------------
    # Mouth / bubble helpers
    # ------------------------------------------------------------------
    def _draw_speech_mouth(self, draw, cx, cy, open_amount: int):
        """Draw open talking mouth (replaces default smile).  open_amount 0-14."""
        # Mouth centre sits below muzzle midpoint
        my = cy + 14
        mw = 16
        if open_amount <= 2:
            # Closed — thin line
            draw.arc([cx - mw // 2, my - 3, cx + mw // 2, my + 3],
                     start=0, end=180, fill=BLACK, width=2)
        else:
            # Open oval
            oh = min(open_amount, 14)
            draw.ellipse([cx - mw // 2, my - 3,
                          cx + mw // 2, my - 3 + oh],
                         fill=BLACK, outline=BLACK)
            # White teeth strip
            draw.rectangle([cx - mw // 2 + 3, my - 1,
                             cx + mw // 2 - 3, my + 2],
                            fill=WHITE)

    def _draw_thought_bubble(self, draw, bx, by, dot_count: int):
        """Draw a thought bubble with *dot_count* dots (1-3)."""
        # Small ascending circles leading to main bubble
        for i, (ox, oy, r) in enumerate([(0, 14, 3), (-4, 8, 4), (2, 2, 5)]):
            draw.ellipse([bx + ox - r, by + oy - r,
                          bx + ox + r, by + oy + r],
                         fill=WHITE, outline=DARK_GRAY, width=1)

        # Main cloud bubble (overlapping circles)
        cloud_cx, cloud_cy = bx, by - 16
        cloud_r = 20
        for ox, oy in [(-8, 6), (8, 6), (0, 0), (-14, 2), (14, 2)]:
            r2 = cloud_r - abs(ox) // 3
            draw.ellipse([cloud_cx + ox - r2, cloud_cy + oy - r2,
                          cloud_cx + ox + r2, cloud_cy + oy + r2],
                         fill=WHITE, outline=DARK_GRAY, width=1)

        # Dots inside the bubble
        dot_positions = [(-9, 0), (0, -4), (9, 0)]
        for i in range(min(dot_count, 3)):
            dx = cloud_cx + dot_positions[i][0]
            dy = cloud_cy + dot_positions[i][1]
            draw.ellipse([dx - 3, dy - 3, dx + 3, dy + 3], fill=DARK_GRAY)

    # ------------------------------------------------------------------
    # Status bars
    # ------------------------------------------------------------------
    def _draw_status_bar(self, draw, state: str, connectivity: str,
                         provider: str = ""):
        # ---- Top bar ----
        draw.rectangle([0, 0, self.W, self.TOP_BAR], fill=(20, 20, 20))
        draw.line([0, self.TOP_BAR, self.W, self.TOP_BAR], fill=DARK_GRAY, width=1)

        # State label
        label = state.upper()
        draw.text((8, 8), label, font=self._font_sm, fill=WHITE)

        # Connectivity indicator (right side)
        dot_color  = GREEN if connectivity == "connected" else RED
        dot_r      = 6
        dot_x      = self.W - 40
        dot_y      = self.TOP_BAR // 2
        draw.ellipse([dot_x - dot_r, dot_y - dot_r,
                      dot_x + dot_r, dot_y + dot_r],
                     fill=dot_color)
        draw.text((dot_x + dot_r + 4, dot_y - 6), "BT",
                  font=self._font_sm, fill=WHITE)

        # ---- Bottom bar ----
        bar_top = self.H - self.BOTTOM_BAR
        draw.rectangle([0, bar_top, self.W, self.H], fill=(20, 20, 20))
        draw.line([0, bar_top, self.W, bar_top], fill=DARK_GRAY, width=1)

        # Provider label — truncate to fit
        prov = provider if provider else ""
        max_chars = 34
        if len(prov) > max_chars:
            prov = prov[:max_chars - 1] + "…"

        if prov:
            try:
                bbox  = draw.textbbox((0, 0), prov, font=self._font_sm)
                tw    = bbox[2] - bbox[0]
            except AttributeError:
                tw = len(prov) * 7
            tx = (self.W - tw) // 2
            ty = bar_top + (self.BOTTOM_BAR - 12) // 2
            draw.text((tx, ty), prov, font=self._font_sm, fill=LIGHT_GRAY)
