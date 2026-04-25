#!/usr/bin/env bash
# =============================================================================
# setup-zeroclaw-bridge.sh — Install the ZeroClaw → raccoon display bridge
#
# Run as the user who runs ZeroClaw (not root):
#   bash ~/LCDlobster/display/hooks/setup-zeroclaw-bridge.sh
#
# What it does:
#   1. Installs a systemd user service that tails ~/.zeroclaw/daemon.log
#   2. Maps ZeroClaw log events to raccoon display states in real time
#   3. Polls the ZeroClaw health endpoint every 5s for connectivity status
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BRIDGE="$(realpath "${SCRIPT_DIR}/../zeroclaw_bridge.py")"
SERVICE_DIR="${HOME}/.config/systemd/user"
SERVICE_FILE="${SERVICE_DIR}/zeroclaw-bridge.service"

mkdir -p "$SERVICE_DIR"

cat > "$SERVICE_FILE" << EOF
[Unit]
Description=ZeroClaw → Raccoon Display Bridge
After=zeroclaw.service raccoon-display.service network.target
Wants=raccoon-display.service

[Service]
ExecStart=/usr/bin/python3 ${BRIDGE}
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1
# Optional: set the provider label shown on the raccoon screen
# Environment=ZEROCLAW_PROVIDER_LABEL=ZeroClaw / Qwen3

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now zeroclaw-bridge.service

echo ""
echo "✓ zeroclaw-bridge service installed and started"
echo ""
echo "Check status:  systemctl --user status zeroclaw-bridge"
echo "Watch logs:    journalctl --user -fu zeroclaw-bridge"
echo ""
echo "To customise the provider label on the display:"
echo "  Edit ZEROCLAW_PROVIDER_LABEL in ${SERVICE_FILE}"
echo "  Then: systemctl --user restart zeroclaw-bridge"
echo ""
