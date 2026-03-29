# Oceano Now Playing

Displays now-playing metadata (title, artist, album, artwork, playback progress,
and real-time VU meters) on an SPI-connected display using the Linux framebuffer
(`/dev/fb0`). Designed for Raspberry Pi 5 and integrated with
[oceano-player](https://github.com/alemser/oceano-player).

> Requires [Oceano Player](https://github.com/alemser/oceano-player) to be installed first.

## How it works

`oceano-now-playing` reads unified playback state from `/tmp/oceano-state.json`
(written by `oceano-state-manager`). When that file is not present it falls back
to reading the `shairport-sync` metadata FIFO directly. It resolves album artwork,
animates a progress bar, and can optionally display live analog-style VU meters
driven by the real-time audio signal from `oceano-source-detector`.

```
oceano-player (backend)
    │
    ├── /tmp/oceano-state.json    ← track metadata, seek position, source
    └── /tmp/oceano-vu.sock       ← stereo RMS frames at ~22 fps
              │
              ▼
    oceano-now-playing  ──▶  /dev/fb0  ──▶  SPI display
```

## Development Quick Start

```bash
git clone https://github.com/alemser/oceano-now-playing.git
cd oceano-now-playing
chmod +x setup.sh
./setup.sh
source venv/bin/activate
make test
```

- Use the `venv/` directory. Scripts and docs assume `venv`, not `.venv`.
- In VS Code, select `venv/bin/python` as the workspace interpreter.
- Start every coding session from a passing `make test`.

## Prerequisites

- **Raspberry Pi 5** running Raspberry Pi OS.
- **SPI display** configured and visible as `/dev/fb0`.
- **[oceano-player](https://github.com/alemser/oceano-player)** installed and running (provides `/tmp/oceano-state.json` and `/tmp/oceano-vu.sock`).
- Fallback: `shairport-sync` producing metadata at `/tmp/shairport-sync-metadata` (AirPlay only, no VU).

## Installation

> It requires [Oceano Player](https://github.com/alemser/oceano-player) to be installed first.


### 1. Enable SPI Display Framebuffer

Add the appropriate overlay to your boot config (e.g. `/boot/firmware/config.txt`):

```bash
dtparam=spi=on
dtoverlay=piscreen,speed=16000000,rotate=90
dtoverlay=vc4-kms-v3d,no_display
```

Verify after reboot: `ls /dev/fb0`

### 2. Enable shairport-sync metadata pipe

In `/etc/shairport-sync.conf`:

```
metadata = {
    enabled = "yes";
    include_cover_art = "yes";
    pipe_name = "/tmp/shairport-sync-metadata";
};
```

Restart shairport-sync: `sudo systemctl restart shairport-sync`

### 3. Install oceano-now-playing

```bash
git clone https://github.com/alemser/oceano-now-playing.git
cd oceano-now-playing
chmod +x install.sh
./install.sh
```

This installs system dependencies, creates a Python virtual environment, and registers the `oceano-now-playing` systemd service.

## Configuration

Set these via environment variables or inside the systemd service file. All values shown are defaults.

| Variable | Default | Description |
|---|---|---|
| `FB_DEVICE` | `/dev/fb0` | Framebuffer device path |
| `COLOR_FORMAT` | `RGB565` | Pixel format; use `BGR565` if red/blue are swapped |
| `UI_PRESET` | `high_contrast_rotate` | Layout preset (see below) |
| `LAYOUT_PROFILE` | *(from preset)* | `high_contrast` or `classic` |
| `DISPLAY_MODE` | *(from preset)* | `rotate`, `text`, `artwork`, `hybrid`, or `vu` |
| `MEDIA_PLAYER` | `auto` | `auto`, `state_file`, or `oceano` |
| `OCEANO_STATE_FILE` | `/tmp/oceano-state.json` | Unified state file from oceano-player |
| `OCEANO_METADATA_PIPE` | `/tmp/shairport-sync-metadata` | shairport-sync FIFO (fallback) |
| `VU_SOCKET` | `/tmp/oceano-vu.sock` | VU meter socket from oceano-source-detector |
| `EXTERNAL_ARTWORK_ENABLED` | `true` | Fetch artwork from Cover Art Archive / iTunes / Deezer |
| `CYCLE_TIME` | `30` | Seconds between text and artwork modes (rotate only) |
| `STANDBY_TIMEOUT` | `600` | Seconds of silence before display sleeps |

**UI presets** (`UI_PRESET`): `high_contrast_rotate`, `high_contrast_text`, `high_contrast_artwork`, `high_contrast_hybrid`, `classic_rotate`, `classic_text`, `classic_artwork`, `classic_hybrid`.

**`MEDIA_PLAYER=auto`** (default): uses `StateFileClient` when `/tmp/oceano-state.json`
exists (oceano-player running), otherwise falls back to `OceanoClient` (shairport-sync
pipe directly).

### Switching display modes at runtime

After installation, use the `oceano-mode` command — no need to edit config files:

```bash
oceano-mode vu        # analog VU meters (requires oceano-source-detector)
oceano-mode text      # track title / artist / album
oceano-mode artwork   # album art full screen
oceano-mode hybrid    # artwork + text side by side
oceano-mode rotate    # alternates text and artwork every CYCLE_TIME seconds
oceano-mode status    # show current mode
```

`oceano-mode` automatically uses `sudo` if needed and runs `daemon-reload` + `restart`.

## Service Management

```bash
sudo systemctl status oceano-now-playing.service
sudo systemctl stop oceano-now-playing.service
sudo systemctl restart oceano-now-playing.service
journalctl -u oceano-now-playing.service -f
```

## Updating

```bash
./update.sh
```

Stops the service, pulls latest code, updates dependencies, and restarts. Rolls back automatically if the new version fails to start.

To test a PR or branch on-device without moving `main`:

```bash
./update-pr.sh 123
./update-pr.sh feature/some-fix
```

## Uninstallation

```bash
./uninstall.sh
```

## Manual Run

```bash
source venv/bin/activate
python src/oceano-now-playing.py
```

## Source Layout

```text
src/
├── app/
│   └── main.py              # State machine and main loop
├── artwork/
│   └── providers.py         # External artwork lookup (Cover Art Archive, iTunes, Deezer)
├── media_players/
│   ├── base.py              # MediaPlayer abstract base class
│   ├── oceano.py            # AirPlay metadata reader via shairport-sync FIFO
│   └── state_file.py        # Unified state reader (/tmp/oceano-state.json)
├── config.py                # Application configuration
├── renderer.py              # PIL → framebuffer renderer (text, artwork, hybrid, VU)
├── vu_client.py             # VU socket reader with attack/decay ballistics
└── oceano-now-playing.py    # Entrypoint

oceano-mode                  # CLI helper to switch display modes at runtime

docs/
└── vu-display-options.md    # VU meter design options and rationale

tests/
├── conftest.py              # Shared fixtures
├── test_oceano.py           # OceanoClient tests
├── test_media_player.py     # MediaPlayer base class and factory tests
├── test_state_machine.py    # State machine and transition tests
├── test_renderer.py         # Renderer utility tests
├── test_config.py           # Configuration tests
├── test_vu_client.py        # VU ballistics tests
└── test_artwork_providers.py
```

## Testing

```bash
make test            # Run all tests (quiet)
make test-verbose    # Full output
make test-oceano     # Oceano client only
make test-state      # State machine only
make test-renderer   # Renderer only
```
