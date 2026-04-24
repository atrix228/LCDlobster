# LCDlobster 🦞

A Pwnagotchi-inspired display companion for the Raspberry Pi Zero 2 W.
Runs an animated raccoon on a 320×240 LCD that reacts live to whatever AI assistant you're using — OpenClaw, Claude Code, or anything else.

```
┌─────────────────────────────────┐
│ THINKING              ● BT      │  ← top status bar
│                                 │
│         /\   /\                 │
│        (  o o  )                │  ← raccoon
│         \  ▼  /   💭 ...        │     + thought bubble
│          -----                  │
│         /|   |\                 │
│                                 │
│      openrouter / mistral-7b    │  ← bottom: active provider
└─────────────────────────────────┘
```

The raccoon changes pose based on what the AI is doing:

| State | What you see |
|-------|-------------|
| `idle` | Blinking, tail wagging |
| `thinking` | Raised paw, thought bubble cycling |
| `responding` | Mouth opens and closes |
| `working` | Typing paws on a surface |
| `building` | Hard hat + wrench |
| `listening` | Ears up, head tilting |
| `error` | X eyes, drooping tail |
| `network` | IP address, WiFi SSID, SSH hint |

---

## Hardware

| Part | Details |
|------|---------|
| **Raspberry Pi Zero 2 W** | aarch64, 512 MB RAM |
| **Pimoroni Display HAT Mini** | 2.0″ IPS, 320×240, ST7789 ([shop link](https://shop.pimoroni.com/products/display-hat-mini)) |
| **MicroSD card** | 8 GB minimum, 16 GB recommended |

The Display HAT Mini plugs directly onto the 40-pin GPIO header — no soldering needed.

---

## Option A — Flash the pre-built image (easiest)

### 1. Build the image

Run this on a Linux machine (not the Pi itself):

```bash
# Install build prerequisites
sudo apt-get install -y qemu-user-static binfmt-support xz-utils \
                        kpartx parted e2fsprogs curl rsync

# Clone and build
git clone https://github.com/atrix228/LCDlobster.git
cd LCDlobster
sudo ./build-image.sh
```

Build time: ~15–20 minutes (downloads Pi OS, Node.js, installs packages via QEMU).
Output: `build/lcdlobster-YYYYMMDD.img`

### 2. Configure before flashing

Create `lcdlobster.env` in the project root (it's gitignored — never committed):

```bash
cp lcdlobster.env.template lcdlobster.env   # or just create it
nano lcdlobster.env
```

Fill in your WiFi networks and API keys — the build script copies this file directly into the image's boot partition. You can also edit the file on the SD card after flashing (it's on the FAT32 partition, visible from any OS).

```ini
# lcdlobster.env — edit these before booting

WIFI_1_SSID=YourHomeNetwork
WIFI_1_PASS=YourPassword

WIFI_2_SSID=YourPhoneHotspot
WIFI_2_PASS=HotspotPassword

MINIMAX_API_KEY=
OPENROUTER_API_KEY=
ANTHROPIC_API_KEY=

# First provider with a valid key wins
PROVIDER_PRIORITY=minimax,openrouter,anthropic
```

### 3. Flash and boot

Flash `build/lcdlobster-YYYYMMDD.img` with [Balena Etcher](https://etcher.balena.io/) or `dd`.

On first boot the Pi will:
1. Connect to WiFi (tries networks in order)
2. Start the display service — raccoon appears on screen
3. Run `npm install` + TypeScript build in the background (~3–5 min, raccoon shows `building`)
4. Switch to `idle` when ready

SSH access: `ssh pi@lcdlobster.local` — password: `lcdlobster` (change via `PI_PASSWORD` in the env file).

---

## Option B — Manual install on existing Pi OS

Tested on **Raspberry Pi OS Lite 64-bit (Trixie/Bookworm)**.

```bash
git clone https://github.com/atrix228/LCDlobster.git
cd LCDlobster
sudo bash install.sh
```

The install script:
- Enables SPI
- Installs Python display packages (`rpi-lgpio`, `spidev`, `Pillow`, `displayhatmini`)
- Installs `lobster-status` to `/usr/local/bin`
- Sets up systemd services

Test the display before anything else:

```bash
sudo python3 display/diagnose_lcd.py   # full hardware diagnostic
sudo python3 display/test_lcd.py       # colour screens + raccoon
```

---

## Wiring up OpenClaw / Claude Code

The display hooks config is at `display/hooks/openclaw.json`.
Copy it to your Claude settings:

```bash
# Fresh install (no existing settings)
cp display/hooks/openclaw.json ~/.claude/settings.json

# Existing settings — merge the "hooks" block manually
cat display/hooks/openclaw.json
```

Once the hooks are in place the raccoon reacts automatically:

- **PreToolUse** → `working` (Bash/computer) or `building` (Edit/Write)
- **PostToolUse** → `thinking` (model composing reply)
- **Stop** → `idle`

---

## Using with other AI tools

`lobster-status` is a universal CLI any tool can call. It's installed at `/usr/local/bin/lobster-status`.

```bash
# Direct state control
lobster-status thinking
lobster-status working --provider "Gemini 2.0 Flash"
lobster-status idle

# Pipe raw JSON
echo '{"state": "responding", "provider": "GPT-4o"}' | lobster-status

# From a shell wrapper around any AI CLI
lobster-status thinking && your-ai-tool "$@" && lobster-status idle
```

For tools that have their own hook system, call `lobster-status` from the hook command the same way.

---

## Configuration reference

`lcdlobster.env` (on the FAT32 boot partition after flashing):

```ini
# WiFi — up to 5 networks, tried in order
WIFI_1_SSID=
WIFI_1_PASS=
WIFI_2_SSID=
WIFI_2_PASS=

# API keys — leave blank to skip that provider
MINIMAX_API_KEY=
OPENROUTER_API_KEY=
ANTHROPIC_API_KEY=

# Provider priority (first with a valid key wins)
PROVIDER_PRIORITY=minimax,openrouter,anthropic

# Model overrides
OPENROUTER_MODEL=mistralai/mistral-7b-instruct
MINIMAX_MODEL=MiniMax-Text-01
ANTHROPIC_MODEL=claude-haiku-4-5-20251001

# Other
WHATSAPP_ENABLED=true
HTTP_PORT=3000
PI_PASSWORD=lcdlobster
```

---

## Display service

The display service runs as a systemd unit (`raccoon-display`) and listens on `/tmp/raccoon.sock` for newline-delimited JSON:

```bash
# Check service status
sudo systemctl status raccoon-display

# Send a state update manually
echo '{"state": "thinking", "provider": "MiniMax"}' | nc -U /tmp/raccoon.sock

# Watch logs
sudo journalctl -fu raccoon-display
```

The socket accepts any combination of fields — missing fields keep their current value:

```json
{ "state": "working" }
{ "provider": "openrouter / mistral-7b" }
{ "connectivity": "connected" }
{ "state": "network", "ip": "192.168.1.42", "ssid": "MyWiFi", "hostname": "lcdlobster" }
```

---

## Project structure

```
LCDlobster/
├── display/
│   ├── display_service.py   # main display daemon (socket → animation)
│   ├── raccoon.py           # PIL-only raccoon renderer
│   ├── lobster_status.py    # lobster-status CLI (installed to /usr/local/bin)
│   ├── test_lcd.py          # hardware smoke test
│   ├── diagnose_lcd.py      # step-by-step diagnostic
│   ├── requirements.txt
│   └── hooks/
│       └── openclaw.json    # Claude Code / OpenClaw hooks config
├── src/                     # TypeScript AI assistant (optional, multi-provider)
│   ├── conversation.ts
│   ├── ipc.ts               # display socket client
│   └── providers/           # anthropic / openrouter / minimax
├── build-image.sh           # builds a flashable .img
├── install.sh               # manual install on existing Pi OS
├── config.toml              # AI assistant config (API keys via lcdlobster.env)
└── lcdlobster.env           # ← gitignored, fill in your keys here
```

---

## License

MIT
