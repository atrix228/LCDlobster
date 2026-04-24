#!/usr/bin/env bash
# =============================================================================
# build-image.sh — Build a flashable LCDlobster .img for Raspberry Pi Zero 2 W
#
# Usage:  sudo ./build-image.sh
# Output: build/lcdlobster-YYYYMMDD.img   (flash with Balena Etcher)
#
# Requirements (on the builder Linux machine):
#   apt-get install -y qemu-user-static binfmt-support xz-utils \
#                      kpartx parted e2fsprogs curl
# =============================================================================
set -euo pipefail

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="${SCRIPT_DIR}/build"
WORK_DIR="${BUILD_DIR}/work"
ROOT_MNT="${WORK_DIR}/rootfs"
BOOT_MNT="${WORK_DIR}/bootfs"

IMAGE_URL="https://downloads.raspberrypi.com/raspios_lite_arm64_latest"
XZ_CACHE="${BUILD_DIR}/raspios-lite-arm64-latest.img.xz"
RAW_IMG="${BUILD_DIR}/raspios-lite-arm64.img"
OUT_IMG="${BUILD_DIR}/lcdlobster-$(date +%Y%m%d).img"

# Pi credentials baked into the image
PI_USER="pi"
PI_PASS="lcdlobster"       # user changes via /boot/firmware/lcdlobster.env
PI_HOSTNAME="lcdlobster"

EXTRA_SPACE_MB=2048        # extra MB added to the image for packages / project

# Colours
R='\033[0;31m'; G='\033[0;32m'; Y='\033[1;33m'; B='\033[1;34m'; NC='\033[0m'
log()  { echo -e "${G}[build]${NC} $*"; }
info() { echo -e "${B}[info ]${NC} $*"; }
warn() { echo -e "${Y}[warn ]${NC} $*"; }
die()  { echo -e "${R}[error]${NC} $*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# Root check
# ---------------------------------------------------------------------------
[[ $EUID -eq 0 ]] || die "Run as root: sudo $0"

# ---------------------------------------------------------------------------
# Prerequisite check
# ---------------------------------------------------------------------------
MISSING=()
for cmd in losetup kpartx parted mkfs.ext4 qemu-aarch64-static curl xz; do
    command -v "$cmd" &>/dev/null || MISSING+=("$cmd")
done
if [ ${#MISSING[@]} -gt 0 ]; then
    die "Missing prerequisites: ${MISSING[*]}\n\nFix with:\n  sudo apt-get update && sudo apt-get install -y qemu-user-static binfmt-support xz-utils kpartx parted e2fsprogs curl rsync"
fi

# Ensure binfmt_misc is mounted (needed for qemu chroot emulation)
if ! mountpoint -q /proc/sys/fs/binfmt_misc 2>/dev/null; then
    modprobe binfmt_misc 2>/dev/null || true
    mount -t binfmt_misc binfmt_misc /proc/sys/fs/binfmt_misc 2>/dev/null || true
fi

# Register qemu-aarch64 handler
update-binfmts --enable qemu-aarch64 2>/dev/null || true

# ---------------------------------------------------------------------------
# Cleanup trap
# ---------------------------------------------------------------------------
LOOP_DEV=""

cleanup() {
    set +e
    log "Cleaning up mounts..."
    # Unmount pseudo-filesystems inside chroot
    for fs in dev/pts dev proc sys run; do
        mountpoint -q "${ROOT_MNT}/${fs}" 2>/dev/null && umount -lf "${ROOT_MNT}/${fs}"
    done
    # Unmount boot partition mounted inside rootfs
    mountpoint -q "${ROOT_MNT}/boot/firmware" 2>/dev/null && umount -lf "${ROOT_MNT}/boot/firmware"
    # Unmount standalone mounts
    mountpoint -q "${ROOT_MNT}" 2>/dev/null  && umount -lf "${ROOT_MNT}"
    mountpoint -q "${BOOT_MNT}" 2>/dev/null  && umount -lf "${BOOT_MNT}"
    # Detach loop device
    if [[ -n "$LOOP_DEV" ]]; then
        kpartx -d "$LOOP_DEV" 2>/dev/null || true
        losetup -d "$LOOP_DEV" 2>/dev/null || true
    fi
    log "Cleanup done."
}
trap cleanup EXIT

# ---------------------------------------------------------------------------
# Directories
# ---------------------------------------------------------------------------
mkdir -p "${BUILD_DIR}" "${WORK_DIR}" "${ROOT_MNT}" "${BOOT_MNT}"

# ---------------------------------------------------------------------------
# 1. Download Raspberry Pi OS Lite 64-bit (arm64 / Bookworm)
# ---------------------------------------------------------------------------
if [[ ! -f "$XZ_CACHE" ]]; then
    log "Downloading Raspberry Pi OS Lite 64-bit..."
    curl -L --progress-bar -o "$XZ_CACHE" "$IMAGE_URL"
else
    log "Using cached download: $XZ_CACHE"
fi

# ---------------------------------------------------------------------------
# 2. Decompress
# ---------------------------------------------------------------------------
if [[ ! -f "$RAW_IMG" ]]; then
    log "Decompressing image (this takes a few minutes)..."
    xz --decompress --keep --stdout "$XZ_CACHE" > "$RAW_IMG"
else
    log "Using existing decompressed image: $RAW_IMG"
fi

# ---------------------------------------------------------------------------
# 3. Expand image to add room for packages
# ---------------------------------------------------------------------------
log "Expanding image by ${EXTRA_SPACE_MB} MB..."
cp "$RAW_IMG" "$OUT_IMG"
truncate -s "+${EXTRA_SPACE_MB}M" "$OUT_IMG"

# Expand the root partition (partition 2) to use the new space
PART_INFO=$(parted "$OUT_IMG" -sm unit B print 2>/dev/null | grep "^2:")
PART2_START=$(echo "$PART_INFO" | cut -d: -f2 | tr -d 'B')
parted "$OUT_IMG" -s resizepart 2 100%

# ---------------------------------------------------------------------------
# 4. Mount image via loop device
# ---------------------------------------------------------------------------
log "Attaching loop device..."
LOOP_DEV=$(losetup --find --partscan --show "$OUT_IMG")
log "  Loop device: $LOOP_DEV"

# kpartx to expose partition devices
kpartx -as "$LOOP_DEV"
sleep 1

BOOT_DEV="/dev/mapper/$(basename ${LOOP_DEV})p1"
ROOT_DEV="/dev/mapper/$(basename ${LOOP_DEV})p2"

# Resize the ext4 filesystem on the root partition
log "Resizing root filesystem..."
e2fsck -fp "$ROOT_DEV" || true
resize2fs "$ROOT_DEV"

# Mount
log "Mounting partitions..."
mount "$ROOT_DEV" "$ROOT_MNT"
mkdir -p "${ROOT_MNT}/boot/firmware"
mount "$BOOT_DEV" "${ROOT_MNT}/boot/firmware"

# ---------------------------------------------------------------------------
# 5. Bind-mount pseudo-filesystems for chroot
# ---------------------------------------------------------------------------
log "Setting up chroot environment..."
mount --bind /dev     "${ROOT_MNT}/dev"
mount --bind /dev/pts "${ROOT_MNT}/dev/pts"
mount -t proc  proc   "${ROOT_MNT}/proc"
mount -t sysfs sysfs  "${ROOT_MNT}/sys"
mount -t tmpfs tmpfs  "${ROOT_MNT}/run"

# Install QEMU binary for ARM 64-bit emulation
cp /usr/bin/qemu-aarch64-static "${ROOT_MNT}/usr/bin/"

# ---------------------------------------------------------------------------
# 6. Chroot helper
# ---------------------------------------------------------------------------
RUN() {
    chroot "$ROOT_MNT" /usr/bin/qemu-aarch64-static /bin/bash -c "$*"
}

# ---------------------------------------------------------------------------
# 7. System configuration (hostname, user, locale)
# ---------------------------------------------------------------------------
log "Configuring system..."

echo "$PI_HOSTNAME" > "${ROOT_MNT}/etc/hostname"
sed -i "s/raspberrypi/${PI_HOSTNAME}/g" "${ROOT_MNT}/etc/hosts" 2>/dev/null || true

# Create pi user if it doesn't exist (newer Pi OS removed the default pi user)
RUN "id ${PI_USER} &>/dev/null || adduser --disabled-password --gecos '' ${PI_USER}"
RUN "usermod -aG sudo,video,gpio,spi,i2c,dialout,plugdev ${PI_USER} 2>/dev/null || \
     usermod -aG sudo,video ${PI_USER}"

# Set password via chpasswd
RUN "echo '${PI_USER}:${PI_PASS}' | chpasswd"

# userconf.txt — the Bookworm/Trixie mechanism for setting credentials on first boot
# Format: username:hashed_password  (SHA-512)
HASHED_PASS=$(echo "$PI_PASS" | openssl passwd -6 -stdin)
echo "${PI_USER}:${HASHED_PASS}" > "${ROOT_MNT}/boot/firmware/userconf.txt"
log "  userconf.txt written (user: ${PI_USER})"

# Enable SSH — touch the file AND enable the service (both methods for compatibility)
touch "${ROOT_MNT}/boot/firmware/ssh"
RUN "systemctl enable ssh 2>/dev/null || systemctl enable sshd 2>/dev/null || true"

# Remove password expiry so SSH works immediately without forced change
RUN "passwd -u ${PI_USER} 2>/dev/null; chage -d -1 ${PI_USER} 2>/dev/null || true"

# Sudoers — ensure pi can sudo without password for convenience
echo "${PI_USER} ALL=(ALL) NOPASSWD: ALL" > "${ROOT_MNT}/etc/sudoers.d/010_pi-nopasswd"
chmod 440 "${ROOT_MNT}/etc/sudoers.d/010_pi-nopasswd"

# ---------------------------------------------------------------------------
# 8. Boot partition — display overlays
# ---------------------------------------------------------------------------
log "Writing /boot/firmware/config.txt overlays..."
BOOT_CFG="${ROOT_MNT}/boot/firmware/config.txt"

# Append our overlays (only if not already present)
grep -q "lcdlobster" "$BOOT_CFG" 2>/dev/null || cat >> "$BOOT_CFG" << 'BOOTCFG'

# ---- LCDlobster: Display HAT Mini ----------------------------------------
dtparam=spi=on
dtoverlay=spi1-3cs
dtoverlay=pwm-2chan,pin=12,func=4,pin2=13,func2=4
dtoverlay=vc4-fkms-v3d
dtoverlay=dwc2
# Disable HDMI to save power (headless)
hdmi_blanking=2
# lcdlobster-marker
BOOTCFG

# cmdline.txt — add framebuffer size and USB gadget modules
CMDLINE_FILE="${ROOT_MNT}/boot/firmware/cmdline.txt"
CMDLINE=$(cat "$CMDLINE_FILE")
# Add modules-load if not present
echo "$CMDLINE" | grep -q "modules-load" || \
    CMDLINE="${CMDLINE} modules-load=dwc2,g_ether"
# Add framebuffer params if not present
echo "$CMDLINE" | grep -q "bcm2708_fb.fbwidth" || \
    CMDLINE="bcm2708_fb.fbwidth=656 bcm2708_fb.fbheight=416 bcm2708_fb.fbdepth=16 bcm2708_fb.fbswap=1 ${CMDLINE}"
echo "$CMDLINE" > "$CMDLINE_FILE"

# ---------------------------------------------------------------------------
# 9. API key config file on boot partition (editable from any OS)
# ---------------------------------------------------------------------------
log "Writing lcdlobster.env to boot partition..."
# Use pre-filled lcdlobster.env from project root if it exists,
# otherwise write a blank template the user fills in after flashing.
if [[ -f "${SCRIPT_DIR}/lcdlobster.env" ]]; then
    log "  Using existing lcdlobster.env (with pre-filled credentials)"
    cp "${SCRIPT_DIR}/lcdlobster.env" "${ROOT_MNT}/boot/firmware/lcdlobster.env"
else
    log "  No lcdlobster.env found — writing blank template"
fi

# Write template only if no pre-filled file was copied
[[ -f "${ROOT_MNT}/boot/firmware/lcdlobster.env" ]] || cat > "${ROOT_MNT}/boot/firmware/lcdlobster.env" << 'ENVFILE'
# ==========================================================
# LCDlobster configuration — edit before first boot
# This file lives on the FAT32 boot partition (visible from
# Windows / Mac / Linux without any special tools).
# After editing, safely eject and insert into the Pi.
# ==========================================================

# ----------------------------------------------------------
# WiFi networks (up to 5 — tried in order, highest priority first)
# Leave blank to skip. Supports WPA2/WPA3 personal.
# ----------------------------------------------------------
WIFI_1_SSID=
WIFI_1_PASS=

WIFI_2_SSID=
WIFI_2_PASS=

WIFI_3_SSID=
WIFI_3_PASS=

WIFI_4_SSID=
WIFI_4_PASS=

WIFI_5_SSID=
WIFI_5_PASS=

# ----------------------------------------------------------
# AI Provider API Keys
# ----------------------------------------------------------
MINIMAX_API_KEY=
OPENROUTER_API_KEY=
ANTHROPIC_API_KEY=

# Provider priority (comma-separated, first valid key wins)
PROVIDER_PRIORITY=minimax,openrouter,anthropic

# Model overrides (optional — defaults shown)
OPENROUTER_MODEL=mistralai/mistral-7b-instruct
MINIMAX_MODEL=MiniMax-Text-01
ANTHROPIC_MODEL=claude-haiku-4-5-20251001

# ----------------------------------------------------------
# Other settings
# ----------------------------------------------------------
# Set to "false" to disable WhatsApp
WHATSAPP_ENABLED=true

# Local HTTP API port
HTTP_PORT=3000

# Pi SSH password (applied on first boot, default: lcdlobster)
PI_PASSWORD=lcdlobster
ENVFILE

# ---------------------------------------------------------------------------
# 10. Install system packages
# ---------------------------------------------------------------------------
log "Updating apt (this takes a while inside qemu)..."
RUN "apt-get update -qq"

log "Installing system packages..."
RUN "DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    python3-pip \
    python3-dev \
    python3-pil \
    python3-spidev \
    i2c-tools \
    python3-smbus \
    libopenjp2-7 \
    libtiff6 \
    wireless-tools \
    bluetooth \
    bluez \
    bluez-tools \
    network-manager \
    git \
    curl \
    ca-certificates \
    libssl-dev \
    netcat-openbsd 2>/dev/null"

# ---------------------------------------------------------------------------
# 11. Install Node.js 22.x (arm64 — Pi Zero 2 W is aarch64)
# ---------------------------------------------------------------------------
log "Installing Node.js 22.x for arm64..."
NODE_TARBALL=$(curl -s https://nodejs.org/dist/latest-v22.x/ \
    | grep -o 'node-v[0-9.]*-linux-arm64\.tar\.xz' | head -1)
[[ -z "$NODE_TARBALL" ]] && die "Could not determine Node.js arm64 tarball filename"
NODE_URL="https://nodejs.org/dist/latest-v22.x/${NODE_TARBALL}"
log "  Downloading $NODE_TARBALL ..."
curl -fsSL "$NODE_URL" -o "${WORK_DIR}/node.tar.xz"
tar -xf "${WORK_DIR}/node.tar.xz" -C "${ROOT_MNT}/usr/local" --strip-components=1
rm "${WORK_DIR}/node.tar.xz"
RUN "node --version && npm --version"

# ---------------------------------------------------------------------------
# 12. Install Python display packages
# ---------------------------------------------------------------------------
log "Installing Python display packages..."
PIP_OPTS="--break-system-packages --no-cache-dir -q"
RUN "pip3 install $PIP_OPTS rpi-lgpio"      # Trixie/Bookworm replacement for RPi.GPIO
RUN "pip3 install $PIP_OPTS spidev"
RUN "pip3 install $PIP_OPTS Pillow"
RUN "pip3 install $PIP_OPTS displayhatmini"
RUN "pip3 install $PIP_OPTS 'qrcode[pil]'"

# ---------------------------------------------------------------------------
# 12b. Install lobster-status CLI
# ---------------------------------------------------------------------------
log "Installing lobster-status CLI..."
cp "${SCRIPT_DIR}/display/lobster_status.py" "${ROOT_MNT}/usr/local/bin/lobster-status"
chmod +x "${ROOT_MNT}/usr/local/bin/lobster-status"

# ---------------------------------------------------------------------------
# 12c. Install OpenClaw (Claude Code)
# ---------------------------------------------------------------------------
log "Installing OpenClaw (Claude Code)..."
RUN "npm install -g @anthropic-ai/claude-code"

# Set up OpenClaw display hooks for the pi user
log "Configuring OpenClaw display hooks..."
mkdir -p "${ROOT_MNT}/home/${PI_USER}/.claude"
cp "${SCRIPT_DIR}/display/hooks/openclaw.json" \
   "${ROOT_MNT}/home/${PI_USER}/.claude/settings.json"
chown -R 1000:1000 "${ROOT_MNT}/home/${PI_USER}/.claude"

# ---------------------------------------------------------------------------
# 13. Copy LCDlobster project
# ---------------------------------------------------------------------------
log "Copying LCDlobster project..."
PROJECT_DEST="${ROOT_MNT}/home/${PI_USER}/LCDlobster"
rm -rf "$PROJECT_DEST"
mkdir -p "$PROJECT_DEST"

# Copy everything except build artifacts and this script's output dir
rsync -a --exclude="build/" \
         --exclude="node_modules/" \
         --exclude="dist/" \
         --exclude=".git/" \
         --exclude="*.img" \
         --exclude="*.img.xz" \
         "${SCRIPT_DIR}/" "${PROJECT_DEST}/"

RUN "chown -R ${PI_USER}:${PI_USER} /home/${PI_USER}/LCDlobster"

# ---------------------------------------------------------------------------
# 14. Systemd service files
# ---------------------------------------------------------------------------
log "Installing systemd services..."

# raccoon-display.service
cat > "${ROOT_MNT}/etc/systemd/system/raccoon-display.service" << 'SVC'
[Unit]
Description=LCDlobster Raccoon Display Service
After=local-fs.target sysinit.target
Wants=local-fs.target

[Service]
Type=simple
WorkingDirectory=/home/pi/LCDlobster/display
# Brief delay lets SPI/GPIO subsystems finish initialising
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

# lcdlobster.service
cat > "${ROOT_MNT}/etc/systemd/system/lcdlobster.service" << 'SVC'
[Unit]
Description=LCDlobster AI Assistant
After=network.target raccoon-display.service bluetooth.target
Wants=raccoon-display.service

[Service]
Type=simple
WorkingDirectory=/home/pi/LCDlobster
ExecStart=/usr/bin/node dist/index.js
Restart=always
RestartSec=5
User=pi
Environment=NODE_ENV=production
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
SVC

# ---------------------------------------------------------------------------
# 15. First-boot service (npm install + npm build + apply API keys)
# ---------------------------------------------------------------------------
log "Creating first-boot setup service..."

# ---------------------------------------------------------------------------
# Script 1: lcdlobster-wifi-setup.sh
# Runs very early (before network), reads lcdlobster.env and writes
# NetworkManager connection files so WiFi is available on first boot.
# No network dependency — breaks the chicken-and-egg problem.
# ---------------------------------------------------------------------------
cat > "${ROOT_MNT}/usr/local/bin/lcdlobster-wifi-setup.sh" << 'WIFISETUP'
#!/usr/bin/env bash
set -euo pipefail
ENV_FILE="/boot/firmware/lcdlobster.env"
NM_DIR="/etc/NetworkManager/system-connections"
LOG="/var/log/lcdlobster-wifi-setup.log"
exec > >(tee -a "$LOG") 2>&1
echo "[wifi-setup] Starting at $(date)"

[[ -f "$ENV_FILE" ]] || { echo "[wifi-setup] No lcdlobster.env found, skipping."; exit 0; }

source <(grep -v '^#' "$ENV_FILE" | grep -E '^WIFI_[0-9]' | sed 's/^/export /')

for i in 1 2 3 4 5; do
    ssid="${!WIFI_${i}_SSID:-}" 2>/dev/null || true
    eval "ssid=\${WIFI_${i}_SSID:-}"
    eval "pass=\${WIFI_${i}_PASS:-}"
    [[ -z "$ssid" ]] && continue

    priority=$((60 - i * 10))
    CONN_FILE="${NM_DIR}/wifi-${i}.nmconnection"

    cat > "$CONN_FILE" << EOF
[connection]
id=wifi-${i}
type=wifi
autoconnect=true
autoconnect-priority=${priority}

[wifi]
mode=infrastructure
ssid=${ssid}

[wifi-security]
key-mgmt=wpa-psk
psk=${pass}

[ipv4]
method=auto

[ipv6]
addr-gen-mode=stable-privacy
method=auto
EOF
    chmod 600 "$CONN_FILE"
    echo "[wifi-setup] Wrote WiFi $i: $ssid (priority $priority)"
done

# Also apply pi password if set
source <(grep -v '^#' "$ENV_FILE" | grep -E '^PI_PASSWORD' | sed 's/^/export /') 2>/dev/null || true
if [[ -n "${PI_PASSWORD:-}" && "${PI_PASSWORD}" != "lcdlobster" ]]; then
    echo "pi:${PI_PASSWORD}" | chpasswd
    echo "[wifi-setup] Pi password updated"
fi

echo "[wifi-setup] Done."
WIFISETUP
chmod +x "${ROOT_MNT}/usr/local/bin/lcdlobster-wifi-setup.sh"

cat > "${ROOT_MNT}/etc/systemd/system/lcdlobster-wifi-setup.service" << 'SVC'
[Unit]
Description=LCDlobster WiFi Setup (pre-network)
DefaultDependencies=no
After=local-fs.target
Before=network.target NetworkManager.service
ConditionPathExists=/boot/firmware/lcdlobster.env

[Service]
Type=oneshot
ExecStart=/usr/local/bin/lcdlobster-wifi-setup.sh
RemainAfterExit=yes
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=sysinit.target
SVC

# ---------------------------------------------------------------------------
# Script 2: lcdlobster-firstboot.sh
# Runs after network is up — applies API keys and builds the Node.js app.
# ---------------------------------------------------------------------------
cat > "${ROOT_MNT}/usr/local/bin/lcdlobster-firstboot.sh" << 'FIRSTBOOT'
#!/usr/bin/env bash
set -euo pipefail
PROJ="/home/pi/LCDlobster"
ENV_FILE="/boot/firmware/lcdlobster.env"
CONFIG="$PROJ/config.toml"
LOG="/var/log/lcdlobster-firstboot.log"
exec > >(tee -a "$LOG") 2>&1
echo "[firstboot] Starting at $(date)"

systemctl start raccoon-display 2>/dev/null || true
sleep 3
lobster-status building --provider "first boot setup" 2>/dev/null || true

if [[ -f "$ENV_FILE" ]]; then
    echo "[firstboot] Reading $ENV_FILE"
    source <(grep -v '^#' "$ENV_FILE" | grep -E '^[A-Z_]+=.' | sed 's/^/export /')

    [[ -n "${MINIMAX_API_KEY:-}"    ]] && \
        sed -i "/\[providers\.minimax\]/,/\[/ s|api_key = \".*\"|api_key = \"${MINIMAX_API_KEY}\"|" "$CONFIG"
    [[ -n "${OPENROUTER_API_KEY:-}" ]] && \
        sed -i "/\[providers\.openrouter\]/,/\[/ s|api_key = \".*\"|api_key = \"${OPENROUTER_API_KEY}\"|" "$CONFIG"
    [[ -n "${ANTHROPIC_API_KEY:-}"  ]] && \
        sed -i "/\[providers\.anthropic\]/,/\[/ s|api_key = \".*\"|api_key = \"${ANTHROPIC_API_KEY}\"|" "$CONFIG"

    if [[ -n "${PROVIDER_PRIORITY:-}" ]]; then
        PY_LIST=$(echo "$PROVIDER_PRIORITY" | python3 -c \
            "import sys; parts=sys.stdin.read().strip().split(','); \
             print('[' + ', '.join('\"'+p.strip()+'\"' for p in parts) + ']')")
        sed -i "s|^priority = \[.*\]|priority = ${PY_LIST}|" "$CONFIG"
    fi

    [[ -n "${OPENROUTER_MODEL:-}" ]] && \
        sed -i "/\[providers\.openrouter\]/,/\[/ s|model = \".*\"|model = \"${OPENROUTER_MODEL}\"|" "$CONFIG"
    [[ -n "${MINIMAX_MODEL:-}" ]] && \
        sed -i "/\[providers\.minimax\]/,/\[/ s|model = \".*\"|model = \"${MINIMAX_MODEL}\"|" "$CONFIG"
    [[ -n "${ANTHROPIC_MODEL:-}" ]] && \
        sed -i "/\[providers\.anthropic\]/,/\[/ s|model = \".*\"|model = \"${ANTHROPIC_MODEL}\"|" "$CONFIG"

    [[ "${WHATSAPP_ENABLED:-true}" == "false" ]] && \
        sed -i '/\[channels\.whatsapp\]/,/\[/ s|enabled = true|enabled = false|' "$CONFIG"
    [[ -n "${HTTP_PORT:-}" ]] && \
        sed -i "s|^port = [0-9]*|port = ${HTTP_PORT}|" "$CONFIG"
fi

echo "[firstboot] Running npm install..."
lobster-status working --provider "npm install" 2>/dev/null || true
cd "$PROJ"
sudo -u pi npm install --prefer-offline 2>&1 | tail -5

echo "[firstboot] Building TypeScript..."
lobster-status building --provider "npm build" 2>/dev/null || true
sudo -u pi npm run build 2>&1 | tail -5

echo "[firstboot] Build complete."
lobster-status idle 2>/dev/null || true
chown -R pi:pi "$PROJ"

systemctl enable lcdlobster
systemctl start lcdlobster || true

systemctl disable lcdlobster-firstboot
echo "[firstboot] Done at $(date). This service will not run again."
FIRSTBOOT
chmod +x "${ROOT_MNT}/usr/local/bin/lcdlobster-firstboot.sh"

cat > "${ROOT_MNT}/etc/systemd/system/lcdlobster-firstboot.service" << 'SVC'
[Unit]
Description=LCDlobster First-Boot Build
After=network-online.target raccoon-display.service
Wants=network-online.target
ConditionPathExists=/home/pi/LCDlobster/package.json
ConditionPathExists=!/home/pi/LCDlobster/dist/index.js

[Service]
Type=oneshot
ExecStart=/usr/local/bin/lcdlobster-firstboot.sh
RemainAfterExit=yes
StandardOutput=journal+console
StandardError=journal+console
TimeoutStartSec=600

[Install]
WantedBy=multi-user.target
SVC

# ---------------------------------------------------------------------------
# 16. Enable services
# ---------------------------------------------------------------------------
log "Enabling systemd services..."
RUN "systemctl enable raccoon-display"
RUN "systemctl enable lcdlobster-wifi-setup"
RUN "systemctl enable lcdlobster-firstboot"
# lcdlobster.service itself is started by firstboot after build succeeds
# so we don't enable it here — firstboot enables it on first run

# Enable bluetooth & network-manager for BT tethering
RUN "systemctl enable bluetooth NetworkManager 2>/dev/null || true"

# ---------------------------------------------------------------------------
# 17. Bluetooth tethering pre-configuration (NAP profile)
# ---------------------------------------------------------------------------
log "Configuring bluetooth for tethering..."
mkdir -p "${ROOT_MNT}/etc/NetworkManager/system-connections"
cat > "${ROOT_MNT}/etc/NetworkManager/system-connections/bt-tether.nmconnection" << 'NMCON'
[connection]
id=bt-tether
type=bluetooth
autoconnect=true

[bluetooth]
type=panu

[ipv4]
method=auto

[ipv6]
addr-gen-mode=stable-privacy
method=auto
NMCON
chmod 600 "${ROOT_MNT}/etc/NetworkManager/system-connections/bt-tether.nmconnection"

# ---------------------------------------------------------------------------
# 18. Clean up chroot artefacts
# ---------------------------------------------------------------------------
log "Cleaning apt cache to reduce image size..."
RUN "apt-get clean"
RUN "rm -rf /var/lib/apt/lists/*"
rm -f "${ROOT_MNT}/usr/bin/qemu-aarch64-static"

# ---------------------------------------------------------------------------
# 19. Unmount everything
# ---------------------------------------------------------------------------
log "Unmounting..."
for fs in dev/pts dev proc sys run; do
    mountpoint -q "${ROOT_MNT}/${fs}" 2>/dev/null && umount -lf "${ROOT_MNT}/${fs}" || true
done
mountpoint -q "${ROOT_MNT}/boot/firmware" && umount -lf "${ROOT_MNT}/boot/firmware" || true
mountpoint -q "${ROOT_MNT}"              && umount -lf "${ROOT_MNT}"              || true

kpartx -d "$LOOP_DEV" || true
losetup -d "$LOOP_DEV" || true
LOOP_DEV=""

# ---------------------------------------------------------------------------
# 20. Done
# ---------------------------------------------------------------------------
SIZE_MB=$(du -m "$OUT_IMG" | cut -f1)
echo ""
echo -e "${G}╔══════════════════════════════════════════════════════════╗${NC}"
echo -e "${G}║             LCDlobster image build complete!             ║${NC}"
echo -e "${G}╚══════════════════════════════════════════════════════════╝${NC}"
echo ""
info "Output image : $OUT_IMG"
info "Size         : ${SIZE_MB} MB"
echo ""
echo -e "${Y}Next steps:${NC}"
echo "  1. Flash with Balena Etcher → select $OUT_IMG"
echo "  2. Re-insert SD card — edit the FAT32 boot partition:"
echo "       lcdlobster.env  ← add your API keys here"
echo "  3. Insert SD card into Pi Zero 2, power on"
echo "  4. First boot: npm install + build runs automatically (~3-5 min)"
echo "     Watch progress:  ssh pi@lcdlobster.local"
echo "     Password:        lcdlobster  (change via PI_PASSWORD in .env)"
echo "  5. WhatsApp QR code will appear on the LCD — scan with WhatsApp"
echo ""
