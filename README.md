# LCDlobster

**A Pwnagotchi-inspired AI companion for the Raspberry Pi Zero 2W.**

Same hardware, full-colour LCD, animated raccoon — and a real AI you can chat with from anywhere over Telegram.

```
┌─────────────────────────────────┐
│ THINKING              ● online  │
│                                 │
│         /\   /\                 │
│        (  ◕ ◕  )                │
│         \  ▼  /   💭 ...        │
│          -----                  │
│         /|   |\                 │
│                                 │
│       ZeroClaw / Qwen3          │
└─────────────────────────────────┘
```

---

## Why switch from Pwnagotchi?

| | Pwnagotchi | LCDlobster |
|---|---|---|
| Hardware | Pi Zero / Zero W | **Pi Zero 2W** (same GPIO) |
| Display | 2.13″ e-ink, monochrome | **2.0″ IPS, full colour, 320×240** |
| AI | Local A2C WiFi model | **Cloud AI via Telegram** |
| Chat | None | **Message your Pi from anywhere** |
| Reactions | Static face | **12 animated states** |
| Skills | None | **3,000+ via ClawHub** |

LCDlobster uses the same Pi Zero 2W and plugs a [Pimoroni Display HAT Mini](https://shop.pimoroni.com/products/display-hat-mini) onto the GPIO header. No soldering. Boot time under 30 seconds.

---

## Hardware

| Part | Details |
|---|---|
| **Raspberry Pi Zero 2W** | aarch64, 512 MB RAM |
| **Pimoroni Display HAT Mini** | 2.0″ IPS, 320×240, ST7789 |
| **MicroSD card** | 8 GB minimum, 16 GB recommended |

The Display HAT Mini plugs directly onto the 40-pin GPIO header — no soldering.

---

## Flash and go (easiest)

### 1. Build the image

Run on a Linux machine (not the Pi):

```bash
sudo apt-get install -y qemu-user-static binfmt-support xz-utils \
                        kpartx parted e2fsprogs curl rsync
git clone https://github.com/atrix228/LCDlobster.git
cd LCDlobster
sudo ./build-image.sh
```

Output: `build/lcdlobster-YYYYMMDD.img` (~10 min build time)

### 2. Configure before flashing

```bash
cp lcdlobster.env.template lcdlobster.env
nano lcdlobster.env
```

Fill in your WiFi credentials and at least one AI provider API key. The build script copies this file into the FAT32 boot partition — you can also edit it on the SD card after flashing from any OS.

```ini
WIFI_1_SSID=YourNetwork
WIFI_1_PASS=YourPassword

# Get a free key at openrouter.ai — access 100+ models
OPENROUTER_API_KEY=sk-or-...

# Or use Anthropic Claude directly
ANTHROPIC_API_KEY=sk-ant-...
```

### 3. Flash and boot

Flash `build/lcdlobster-YYYYMMDD.img` with [Balena Etcher](https://etcher.balena.io/) or `dd`.

On first boot the Pi will:
1. Connect to WiFi
2. Show the raccoon on the LCD immediately
3. Be ready for SSH: `ssh pi@lcdlobster.local` (password: `lcdlobster`)

---

## Connect a Telegram AI (ZeroClaw)

ZeroClaw turns your Pi into a Telegram bot powered by any cloud AI. Chat with your Pi from your phone, have it run commands, search the web, and use [ClawHub](https://clawhub.ai) skills.

### Install ZeroClaw

```bash
# On the Pi (SSH in first)
curl -fsSL https://zeroclawlabs.ai/install.sh | bash
```

### Configure ZeroClaw

```bash
~/.cargo/bin/zeroclaw init
```

Follow the prompts to connect your Telegram bot token and AI provider API key.

Recommended: **OpenRouter** gives access to 100+ models with a single key:
```bash
~/.cargo/bin/zeroclaw config set providers.models.openrouter.api_key "sk-or-..."
~/.cargo/bin/zeroclaw config set providers.models.openrouter.model "qwen/qwen3-235b-a22b"
~/.cargo/bin/zeroclaw config set providers.fallback "openrouter"
```

### Wire ZeroClaw to the raccoon display

```bash
bash ~/LCDlobster/display/hooks/setup-zeroclaw-bridge.sh
```

The bridge tails ZeroClaw's log and maps every event to a raccoon state in real time:

| ZeroClaw event | Raccoon shows |
|---|---|
| Telegram message received | `listening` — ears up |
| Processing / memory recall | `thinking` — raised paw |
| LLM call in progress | `thinking` |
| Tool / skill executing | `working` — typing paws |
| Reply composed | `responding` — mouth moves |
| Reply sent | `idle` — tail wagging |
| Error | `error` — X eyes |

### Start ZeroClaw

```bash
systemctl --user enable --now zeroclaw
```

Now message your Pi on Telegram and watch the raccoon react live.

---

## Connect Claude Code / OpenClaw

If you use Claude Code (the Anthropic CLI), the raccoon reacts to every tool call:

```bash
bash ~/LCDlobster/display/hooks/setup-hooks.sh
```

This installs Claude Code hooks so the raccoon shows:
- `working` when Bash/computer tools run
- `building` when Edit/Write tools run
- `thinking` while Claude composes a reply
- `idle` when Claude stops

---

## Raccoon states

| State | Animation | Trigger |
|---|---|---|
| `idle` | Blinking, tail wagging | Default |
| `sleeping` | Eyes closed, ZZZ rising | Auto after 5 min idle |
| `stretching` | Arms up, yawning | Automatic on wakeup |
| `thinking` | Raised paw, thought bubble | LLM processing |
| `responding` | Mouth opens/closes | Reply composing |
| `working` | Typing paws | Tool / command executing |
| `building` | Hard hat + wrench | File edit / write |
| `listening` | Ears up, head tilt | Message received |
| `error` | X eyes, drooping tail | Error detected |
| `network` | IP + WiFi SSID | Startup / network check |
| `celebrating` | Arms up, star burst | Task completed |
| `confused` | Head scratch, `?` bubble | Unexpected input |
| `searching` | Magnifying glass sweep | Web / file search |
| `reading` | Open book, scanning eyes | Reading long content |
| `excited` | Bouncing, sparkles | Positive result |
| `sneaky` | Low crouch, side-eye | Background task |

---

## Sysinfo page

Press **Button A** (GPIO 5) on the Display HAT Mini to toggle a system stats page:

```
┌─────────────────────────────────┐
│  CPU  [████████░░░░░░░░] 47%    │
│  MEM  [████████████░░░░] 71%    │
│  TEMP  52°C   UP  2h 14m        │
│  IP   192.168.1.42              │
│  WiFi MyNetwork          ● ok   │
└─────────────────────────────────┘
```

Press again to return to the raccoon.

---

## Manual state control

`lobster-status` is a CLI installed at `/usr/local/bin/lobster-status`. Any script can call it:

```bash
lobster-status thinking
lobster-status working --provider "My Tool"
lobster-status idle

# Pipe raw JSON
echo '{"state": "celebrating", "provider": "ZeroClaw"}' | lobster-status

# Wrap any AI CLI
lobster-status thinking && my-ai-tool "$@"; lobster-status idle
```

---

## Manual install on existing Pi OS

Tested on **Raspberry Pi OS Lite 64-bit (Bookworm)**.

```bash
git clone https://github.com/atrix228/LCDlobster.git
cd LCDlobster
sudo bash install.sh
```

The install script:
- Writes `dtoverlay=spi0-2cs` to `/boot/firmware/config.txt` (correct overlay for Pi OS Bookworm / kernel 6.6+)
- Installs Python display packages (`rpi-lgpio`, `spidev`, `Pillow`, `displayhatmini`)
- Installs `lobster-status` to `/usr/local/bin`
- Sets up systemd services

Test the display before anything else:

```bash
sudo python3 display/diagnose_lcd.py   # full hardware diagnostic
sudo python3 display/test_lcd.py       # colour screens + raccoon
```

---

## Display socket protocol

The display service listens on `/tmp/raccoon.sock` for newline-delimited JSON. Any process on the Pi can send state updates:

```bash
echo '{"state": "thinking", "provider": "My Tool"}' | nc -U /tmp/raccoon.sock
```

Supported fields — all optional, missing fields keep current value:

```json
{ "state": "working" }
{ "provider": "ZeroClaw / Qwen3" }
{ "connectivity": "connected" }
{ "state": "network", "ip": "192.168.1.42", "ssid": "MyWiFi", "hostname": "lcdlobster" }
```

---

## Configuration reference

`lcdlobster.env` (edit before flashing, or on the FAT32 boot partition after):

```ini
# WiFi — up to 5 networks, tried in order
WIFI_1_SSID=
WIFI_1_PASS=

# API keys — leave blank to skip that provider
OPENROUTER_API_KEY=
ANTHROPIC_API_KEY=
MINIMAX_API_KEY=

# Provider priority (first with a valid key wins)
PROVIDER_PRIORITY=openrouter,anthropic,minimax

# Model overrides
OPENROUTER_MODEL=qwen/qwen3-235b-a22b
ANTHROPIC_MODEL=claude-haiku-4-5-20251001
MINIMAX_MODEL=MiniMax-Text-01

# SSH password for the pi user
PI_PASSWORD=lcdlobster
```

---

## Project structure

```
LCDlobster/
├── display/
│   ├── display_service.py     # main display daemon (socket → animation)
│   ├── raccoon.py             # PIL-only raccoon renderer (16 states)
│   ├── zeroclaw_bridge.py     # ZeroClaw log → raccoon state bridge
│   ├── lobster_status.py      # lobster-status CLI
│   ├── test_lcd.py            # hardware smoke test
│   ├── diagnose_lcd.py        # step-by-step diagnostic
│   ├── requirements.txt
│   └── hooks/
│       ├── openclaw.json              # Claude Code hooks config
│       ├── setup-hooks.sh             # install OpenClaw hooks
│       └── setup-zeroclaw-bridge.sh   # install ZeroClaw bridge service
├── src/                       # TypeScript AI assistant (optional)
│   ├── conversation.ts
│   ├── ipc.ts
│   └── providers/
├── build-image.sh             # builds a flashable .img
├── install.sh                 # manual install on existing Pi OS
├── lcdlobster.env.template    # ← copy to lcdlobster.env, fill in keys
└── config.toml                # AI assistant config
```

---

## Troubleshooting

**Display stays blank after install**
```bash
ls /dev/spidev*   # should show /dev/spidev0.0 and /dev/spidev0.1
sudo python3 display/diagnose_lcd.py
```
If `/dev/spidev*` is missing, check that `dtoverlay=spi0-2cs` is in `/boot/firmware/config.txt` and reboot.

**ZeroClaw 400 errors (reasoning_content)**
ZeroClaw v4 thinking models (`deepseek-v4-pro`, `deepseek-v4-flash`) are incompatible with ZeroClaw's session history. Use `deepseek-chat` or switch to OpenRouter.

**ZeroClaw 400 errors (tool role mismatch)**
Clear the session history:
```bash
systemctl --user stop zeroclaw
rm -f ~/.zeroclaw/workspace/sessions/telegram_*.jsonl \
       ~/.zeroclaw/workspace/sessions/sessions.db*
systemctl --user start zeroclaw
```
Set `keep_tool_context_turns = 0` in `~/.zeroclaw/config.toml` to prevent recurrence.

**Raccoon stuck in wrong state**
```bash
echo '{"state": "idle"}' | nc -U /tmp/raccoon.sock
```

---

## License

MIT
