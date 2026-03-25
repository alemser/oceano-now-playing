# Oceano Now Playing

Displays now-playing metadata (title, artist, album, artwork, and playback details) on an SPI-connected display using the Linux framebuffer (`/dev/fb0`). Designed for Raspberry Pi 5 and integrated with [oceano-player](https://github.com/alemser/oceano-player) via the `shairport-sync` metadata pipe.

> This project was specifically designed for the Raspberry Pi (tested on version 5). It aims to address the limitations of using cheap and simple SPI displays, which often cause compatibility issues with software like Volumio and Moode. It addresses the author's basic needs, and he hopes it proves useful for others in the same situation.

>It requires [Oceano Player](https://github.com/alemser/oceano-player) to be installed first.

## How it works

`oceano-now-playing` reads AirPlay metadata that `shairport-sync` writes to a named FIFO (default: `/tmp/shairport-sync-metadata`). It decodes the metadata, resolves album artwork, and drives a framebuffer display in real time.

```
AirPlay source
    │  (AirPlay protocol)
    ▼
shairport-sync
    │  writes to FIFO: /tmp/shairport-sync-metadata
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
- **shairport-sync** installed and producing metadata at `/tmp/shairport-sync-metadata` (enabled via `metadata` block in `/etc/shairport-sync.conf`).
- Optionally, [oceano-player](https://github.com/alemser/oceano-player) managing shairport-sync.

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
| `DISPLAY_MODE` | *(from preset)* | `rotate`, `text`, `artwork`, or `hybrid` |
| `OCEANO_METADATA_PIPE` | `/tmp/shairport-sync-metadata` | shairport-sync FIFO path |
| `EXTERNAL_ARTWORK_ENABLED` | `true` | Fetch artwork from Cover Art Archive / iTunes / Deezer |
| `CYCLE_TIME` | `30` | Seconds between text and artwork modes (rotate only) |
| `STANDBY_TIMEOUT` | `600` | Seconds of silence before display sleeps |

**UI presets** (`UI_PRESET`): `high_contrast_rotate`, `high_contrast_text`, `high_contrast_artwork`, `high_contrast_hybrid`, `classic_rotate`, `classic_text`, `classic_artwork`, `classic_hybrid`.

To override settings via the service file, edit `/etc/systemd/system/oceano-now-playing.service` and add entries under `[Service]`:

```ini
Environment="UI_PRESET=high_contrast_rotate"
Environment="OCEANO_METADATA_PIPE=/tmp/shairport-sync-metadata"
Environment="CYCLE_TIME=45"
Environment="EXTERNAL_ARTWORK_ENABLED=false"
```

Then reload and restart:

```bash
sudo systemctl daemon-reload
sudo systemctl restart oceano-now-playing.service
```

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
│   └── oceano.py            # AirPlay metadata reader via shairport-sync FIFO
├── config.py                # Application configuration
├── renderer.py              # PIL → framebuffer renderer
└── oceano-now-playing.py    # Entrypoint

tests/
├── conftest.py              # Shared fixtures
├── test_oceano.py           # OceanoClient tests
├── test_media_player.py     # MediaPlayer base class and factory tests
├── test_state_machine.py    # State machine and transition tests
├── test_renderer.py         # Renderer utility tests
├── test_config.py           # Configuration tests
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
