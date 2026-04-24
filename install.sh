#!/usr/bin/env bash
# =============================================================================
# install.sh — Set up LCDlobster on a fresh Raspberry Pi OS installation
#
# Usage (on your Pi, after flashing standard Pi OS Lite):
#   git clone <this-repo>  OR  copy this folder to the Pi, then:
#   cd LCDlobster && bash install.sh
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

R='\033[0;31m'; G='\033[0;32m'; Y='\033[1;33m'; B='\033[1;34m'; NC='\033[0m'
log()  { echo -e "${G}[install]${NC} $*"; }
warn() { echo -e "${Y}[warn   ]${NC} $*"; }
die()  { echo -e "${R}[error  ]${NC} $*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die "Run as root: sudo bash install.sh"

# ---------------------------------------------------------------------------
# 1. Enable SPI (needed for Display HAT Mini)
# ---------------------------------------------------------------------------
log "Enabling SPI interface..."
if ! grep -q "^dtparam=spi=on" /boot/firmware/config.txt 2>/dev/null && \
   ! grep -q "^dtparam=spi=on" /boot/config.txt 2>/dev/null; then
    BOOT_CFG=$([ -f /boot/firmware/config.txt ] && echo /boot/firmware/config.txt || echo /boot/config.txt)
    cat >> "$BOOT_CFG" << 'CFG'

# LCDlobster — Display HAT Mini
dtparam=spi=on
dtoverlay=spi1-3cs
dtoverlay=pwm-2chan,pin=12,func=4,pin2=13,func2=4
dtoverlay=vc4-fkms-v3d
CFG
    log "  SPI enabled in $BOOT_CFG (reboot required after install)"
else
    log "  SPI already enabled"
fi

# ---------------------------------------------------------------------------
# 2. System packages
# ---------------------------------------------------------------------------
log "Installing system packages..."
apt-get update -qq
apt-get install -y --no-install-recommends \
    python3-pip \
    python3-pil \
    python3-spidev \
    i2c-tools \
    libopenjp2-7 \
    libtiff6 \
    wireless-tools \
    netcat-openbsd \
    nodejs \
    npm \
    git \
    curl 2>/dev/null

# ---------------------------------------------------------------------------
# 3. Node.js — upgrade to v20 if system version is too old
# ---------------------------------------------------------------------------
NODE_VER=$(node --version 2>/dev/null | grep -o '[0-9]*' | head -1 || echo 0)
if [[ "$NODE_VER" -lt 20 ]]; then
    log "Node.js $NODE_VER is too old — installing v20 from nodejs.org..."
    ARCH=$(uname -m)
    case "$ARCH" in
        armv7l|armv6l) NODE_ARCH="armv7l" ;;
        aarch64)        NODE_ARCH="arm64"  ;;
        x86_64)         NODE_ARCH="x64"    ;;
        *)              die "Unknown arch: $ARCH" ;;
    esac
    NODE_TARBALL=$(curl -s https://nodejs.org/dist/latest-v20.x/ \
        | grep -o "node-v[0-9.]*-linux-${NODE_ARCH}\.tar\.xz" | head -1)
    [[ -z "$NODE_TARBALL" ]] && die "Could not find Node.js tarball for $NODE_ARCH"
    log "  Downloading $NODE_TARBALL ..."
    curl -fsSL "https://nodejs.org/dist/latest-v20.x/${NODE_TARBALL}" -o /tmp/node.tar.xz
    tar -xf /tmp/node.tar.xz -C /usr/local --strip-components=1
    rm /tmp/node.tar.xz
    log "  Node.js $(node --version) installed"
else
    log "  Node.js v$NODE_VER OK"
fi

# ---------------------------------------------------------------------------
# 4. Python display packages
# ---------------------------------------------------------------------------
log "Installing Python display packages..."
PIP="pip3 install --break-system-packages --no-cache-dir -q"

# rpi-lgpio must come first — it's the Bookworm replacement for RPi.GPIO
# and displayhatmini's st7789 dependency will pick it up automatically.
$PIP "rpi-lgpio>=0.6" || warn "rpi-lgpio install failed — trying RPi.GPIO fallback"
$PIP "spidev>=3.5"
$PIP "Pillow>=10.0.0"
$PIP displayhatmini
$PIP "qrcode[pil]>=7.4.2"

log "Python display packages installed."
log "  Verify with: sudo python3 ${SCRIPT_DIR}/display/diagnose_lcd.py"

# ---------------------------------------------------------------------------
# 4b. Install lobster-status CLI
# ---------------------------------------------------------------------------
log "Installing lobster-status CLI..."
cp "${SCRIPT_DIR}/display/lobster_status.py" /usr/local/bin/lobster-status
chmod +x /usr/local/bin/lobster-status
log "  lobster-status installed — test with: lobster-status idle"

# ---------------------------------------------------------------------------
# 5. Node.js dependencies & TypeScript build
# ---------------------------------------------------------------------------
log "Installing Node.js dependencies..."
cd "$SCRIPT_DIR"
npm install

log "Building TypeScript..."
npm run build

# ---------------------------------------------------------------------------
# 6. Systemd services
# ---------------------------------------------------------------------------
log "Installing systemd services..."

cat > /etc/systemd/system/raccoon-display.service << SVC
[Unit]
Description=LCDlobster Raccoon Display Service
After=sysinit.target local-fs.target

[Service]
Type=simple
WorkingDirectory=${SCRIPT_DIR}/display
ExecStartPre=/bin/sleep 3
ExecStart=/usr/bin/python3 display_service.py
Restart=always
RestartSec=5
User=root
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
SVC

cat > /etc/systemd/system/lcdlobster.service << SVC
[Unit]
Description=LCDlobster AI Assistant
After=network.target raccoon-display.service

[Service]
Type=simple
WorkingDirectory=${SCRIPT_DIR}
ExecStart=/usr/local/bin/node dist/index.js
Restart=always
RestartSec=5
User=pi
Environment=NODE_ENV=production
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
SVC

systemctl daemon-reload
systemctl enable raccoon-display lcdlobster

# ---------------------------------------------------------------------------
# 7. Create data directories
# ---------------------------------------------------------------------------
mkdir -p "$SCRIPT_DIR/data" "$SCRIPT_DIR/sessions"
chown -R pi:pi "$SCRIPT_DIR"

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
echo ""
echo -e "${G}╔══════════════════════════════════════════╗${NC}"
echo -e "${G}║       LCDlobster install complete!       ║${NC}"
echo -e "${G}╚══════════════════════════════════════════╝${NC}"
echo ""
echo -e "${Y}Next steps:${NC}"
echo "  1. Start the display service:"
echo "       sudo systemctl start raccoon-display"
echo ""
echo "  2. Wire up OpenClaw / Claude Code hooks:"
echo "       cat ${SCRIPT_DIR}/display/hooks/openclaw.json"
echo "       # Merge into ~/.claude/settings.json"
echo ""
echo "  3. For other AI tools, call lobster-status directly:"
echo "       lobster-status thinking --provider \"Gemini 1.5\""
echo "       lobster-status idle"
echo ""
echo "  4. Test the display:"
echo "       sudo python3 ${SCRIPT_DIR}/display/test_lcd.py"
echo ""
