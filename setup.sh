#!/usr/bin/env bash
# setup.sh — One-shot setup for LCDlobster on Raspberry Pi OS (Bullseye / Bookworm)
# Run as root:  sudo bash setup.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "============================================"
echo "  LCDlobster setup"
echo "  Working directory: ${SCRIPT_DIR}"
echo "============================================"

# ---------------------------------------------------------------------------
# 1. System packages
# ---------------------------------------------------------------------------
echo "[setup] Updating apt..."
apt-get update -y

echo "[setup] Installing system dependencies..."
apt-get install -y \
    python3-pip \
    python3-pil \
    git \
    i2c-tools \
    python3-smbus \
    python3-rpi.gpio \
    libopenjp2-7 \
    curl \
    ca-certificates

# ---------------------------------------------------------------------------
# 2. Node.js 20.x via NodeSource
# ---------------------------------------------------------------------------
if ! command -v node &>/dev/null || [[ "$(node --version | cut -d. -f1 | tr -d 'v')" -lt 20 ]]; then
    echo "[setup] Installing Node.js 20.x..."
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
    apt-get install -y nodejs
else
    echo "[setup] Node.js $(node --version) already present."
fi

echo "[setup] npm version: $(npm --version)"

# ---------------------------------------------------------------------------
# 3. Python display dependencies
# ---------------------------------------------------------------------------
echo "[setup] Installing Python display dependencies..."
pip3 install --break-system-packages -r "${SCRIPT_DIR}/display/requirements.txt" \
    || pip3 install -r "${SCRIPT_DIR}/display/requirements.txt"

# ---------------------------------------------------------------------------
# 4. Node.js project dependencies & build
# ---------------------------------------------------------------------------
echo "[setup] Installing npm dependencies..."
cd "${SCRIPT_DIR}"
npm install

echo "[setup] Building TypeScript project..."
npm run build

# ---------------------------------------------------------------------------
# 5. Create data directories
# ---------------------------------------------------------------------------
echo "[setup] Creating data directories..."
mkdir -p "${SCRIPT_DIR}/data"
mkdir -p "${SCRIPT_DIR}/sessions"

# ---------------------------------------------------------------------------
# 6. systemd service — raccoon-display (Python)
# ---------------------------------------------------------------------------
echo "[setup] Writing raccoon-display.service..."
cat > /etc/systemd/system/raccoon-display.service <<EOF
[Unit]
Description=Raccoon Display Service (LCDlobster)
After=local-fs.target
Wants=local-fs.target

[Service]
Type=simple
User=root
WorkingDirectory=${SCRIPT_DIR}/display
ExecStart=/usr/bin/python3 display_service.py
Restart=always
RestartSec=3
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# ---------------------------------------------------------------------------
# 7. systemd service — lcdlobster (Node.js)
# ---------------------------------------------------------------------------
echo "[setup] Writing lcdlobster.service..."
cat > /etc/systemd/system/lcdlobster.service <<EOF
[Unit]
Description=LCDlobster Node.js Service
After=network.target raccoon-display.service
Wants=network.target

[Service]
Type=simple
User=root
WorkingDirectory=${SCRIPT_DIR}
ExecStart=/usr/bin/node dist/index.js
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
Environment=NODE_ENV=production

[Install]
WantedBy=multi-user.target
EOF

# ---------------------------------------------------------------------------
# 8. Reload systemd and enable services
# ---------------------------------------------------------------------------
echo "[setup] Reloading systemd and enabling services..."
systemctl daemon-reload
systemctl enable raccoon-display.service
systemctl enable lcdlobster.service

# ---------------------------------------------------------------------------
# 9. Done — print instructions
# ---------------------------------------------------------------------------
echo ""
echo "============================================"
echo "  Setup complete!"
echo "============================================"
echo ""
echo "Next steps:"
echo "  1. Edit ${SCRIPT_DIR}/config.toml and fill in your API keys."
echo ""
echo "  2. Start the services:"
echo "       sudo systemctl start raccoon-display lcdlobster"
echo ""
echo "  3. Check service status:"
echo "       sudo systemctl status raccoon-display"
echo "       sudo systemctl status lcdlobster"
echo ""
echo "  4. Follow logs in real time:"
echo "       sudo journalctl -fu raccoon-display"
echo "       sudo journalctl -fu lcdlobster"
echo ""
echo "  5. Send a test state update to the display:"
echo "       echo '{\"state\":\"idle\",\"connectivity\":\"connected\",\"provider\":\"Claude 3.5\"}' | socat - UNIX-CONNECT:/tmp/raccoon.sock"
echo ""
