# Oceano Now Playing

Displays now-playing metadata (title, artist, album, artwork, playback progress,
and real-time VU meters) on an SPI-connected display using the Linux framebuffer
(`/dev/fb0`). Designed for Raspberry Pi 5 and integrated with
[oceano-player](https://github.com/alemser/oceano-player).

> Requires [Oceano Player](https://github.com/alemser/oceano-player) to be installed first:
> ```bash
> curl -fsSL -o install.sh https://raw.githubusercontent.com/alemser/oceano-player/main/install.sh
> chmod +x install.sh && sudo ./install.sh
> ```

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

> Oceano Player must be installed before this step (see above).


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

Display settings are managed through the **Oceano Player web UI** at `http://<pi-ip>:8080` → **Display** section. Changes take effect immediately without editing any files.

| Setting | Description |
|---|---|
| UI preset | Layout and display mode (`rotate`, `text`, `artwork`, `hybrid`, `vu`) |
| Cycle time | Seconds between text and artwork in rotate mode |
| Standby timeout | Seconds of silence before the display sleeps |
| External artwork | Fetch album art from online providers |

### Display modes

| Mode | Description |
|---|---|
| `rotate` | Alternates between track info and artwork |
| `text` | Track title, artist, album, progress bar |
| `artwork` | Album art full screen |
| `hybrid` | Artwork and text side by side |
| `vu` | Analog-style VU meters (requires physical audio source via REC OUT) |

### Advanced: switching modes from the command line

If the web UI is not available, use the `oceano-mode` command directly on the Pi:

```bash
oceano-mode vu        # analog VU meters
oceano-mode text      # track title / artist / album
oceano-mode artwork   # album art full screen
oceano-mode hybrid    # artwork + text side by side
oceano-mode rotate    # alternates text and artwork
oceano-mode status    # show current mode
```

### Hardware-specific settings

| Variable | Default | When to change |
|---|---|---|
| `FB_DEVICE` | `/dev/fb0` | If your framebuffer is at a different path |
| `COLOR_FORMAT` | `RGB565` | Set to `BGR565` if red and blue are swapped on your display |

These can be set in `/etc/oceano/display.env` if needed.

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
│   ├── state_file.py        # Unified state reader (/tmp/oceano-state.json)
│   └── sse_client.py        # Push-based state reader via SSE (oceano-state-manager :8081)
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
