# SPI Now Playing for Volumio

This project displays Volumio's current playing status (title, artist, album, art, and quality) on an SPI-connected display using the Linux framebuffer (`/dev/fb0`). Optimized for Raspberry Pi 5.

## Prerequisites

- **Raspberry Pi 5** running Raspberry Pi OS or Volumio.
- **SPI Display** correctly configured and visible as `/dev/fb0`.
- **Volumio** running on the same Pi (localhost:3000).

## Installation

### 1. Enable SPI Display Framebuffer
Ensure your display's overlay is enabled. On Volumio, add the following to `/boot/userconfig.txt` for Volumio or `/boot/firmware/config.txt` for MoOde:

```bash
dtparam=spi=on
dtoverlay=piscreen,speed=16000000,rotate=90
dtoverlay=vc4-kms-v3d,no_display
```

### 2. Configure X11 for the LCD
Create the file `/etc/X11/xorg.conf.d/95-pi5-lcd.conf` with the following content:

```bash
Section "Device"
    Identifier "LCD"
    Driver "fbdev"
    Option "fbdev" "/dev/fb0"
EndSection

Section "Screen"
    Identifier "Screen0"
    Device "LCD"
EndSection
```

Check if the device exists after a reboot: `ls /dev/fb0`.

### 3. Quick One-Line Installation
If you haven't cloned the repository yet, you can run this command directly on your Raspberry Pi:

```bash
git clone https://github.com/alemser/spi-now-playing.git && cd spi-now-playing && chmod +x install.sh && ./install.sh
```

This will clone the project and run the installer.

### 4. Manual Installation
If you already have the files locally:
```bash
chmod +x install.sh
./install.sh
```
This will:
- Install system dependencies (`pip`, `venv`, `numpy`, `pil`).
- Setup a Python virtual environment.
- Install all Python libraries from `requirements.txt`.
- Create, enable, and start a systemd service (`spi-now-playing.service`).

## Configuration

You can customize the behavior in `src/config.py` or by setting environment variables in the service file. These are the current runtime defaults:

| Setting | Default | How to override |
| --- | --- | --- |
| `FB_DEVICE` | `/dev/fb0` | Environment variable or edit `Config.framebuffer_device` |
| `COLOR_FORMAT` | `RGB565` | Environment variable or edit `Config.color_format` |
| `UI_PRESET` | `high_contrast_rotate` | Environment variable or edit `Config.ui_preset` |
| `LAYOUT_PROFILE` | from `UI_PRESET` | Optional explicit override: `high_contrast` or `classic` |
| `DISPLAY_MODE` | from `UI_PRESET` | Optional explicit override: `rotate`, `text`, `artwork`, or `hybrid` |
| `MEDIA_PLAYER` | `auto` | Environment variable or edit `Config.media_player_type` |
| `VOLUMIO_URL` | `ws://localhost:3000/socket.io/?EIO=3&transport=websocket` | Environment variable or edit `Config.volumio_url` |
| `MOODE_URL` | `http://localhost/engine-mpd.php` | Environment variable or edit `Config.moode_url` |
| `LMS_URL` | `ws://localhost:9000` | Environment variable or edit `Config.lms_url` |
| `EXTERNAL_ARTWORK_ENABLED` | `true` | Environment variable using `true/false`, `on/off`, `yes/no`, or `1/0` |
| `CYCLE_TIME` | `30` | Environment variable or edit `Config.mode_cycle_time` |
| `STANDBY_TIMEOUT` | `600` | Environment variable or edit `Config.standby_timeout` |

Notes:

- `MEDIA_PLAYER=auto` tries to detect the active backend automatically.
- `UI_PRESET` is the recommended single control because it keeps style and mode connected.
- Supported presets: `high_contrast_rotate`, `high_contrast_text`, `high_contrast_artwork`, `high_contrast_hybrid`, `classic_rotate`, `classic_text`, `classic_artwork`, `classic_hybrid`.
- `LAYOUT_PROFILE` and `DISPLAY_MODE` can still be used as explicit overrides when needed.
- For your own device/runtime behavior, set `UI_PRESET` in Linux (systemd service `Environment=` entries), not in code.
- Edit `src/config.py` only if you want to change project defaults for all installations.
- `EXTERNAL_ARTWORK_ENABLED=true` enables artwork lookup from external providers (Cover Art Archive, iTunes, Deezer) using artist + album metadata.
- `EXTERNAL_ARTWORK_ENABLED=false` disables external lookup; if no artwork is resolved, the app shows the built-in no-cover card.
- `COLOR_FORMAT=BGR565` is useful if red and blue look swapped on your panel.
- `LAYOUT_PROFILE=high_contrast` is optimized for lower-quality/off-angle resistive panels; `classic` keeps the previous visual style.
- `DISPLAY_MODE=rotate` alternates text/artwork using `CYCLE_TIME`; `text` and `artwork` stay fixed on one mode.
- `DISPLAY_MODE=hybrid` shows artwork and metadata together on one screen (no rotation).

To change these via the service, edit `/etc/systemd/system/spi-now-playing.service` and add entries under `[Service]`, for example:

```ini
Environment="MEDIA_PLAYER=volumio"
Environment="UI_PRESET=high_contrast_rotate"
Environment="CYCLE_TIME=45"
Environment="STANDBY_TIMEOUT=900"
Environment="EXTERNAL_ARTWORK_ENABLED=false"
```

After changing the service file, reload and restart the service:

```bash
sudo systemctl daemon-reload
sudo systemctl restart spi-now-playing.service
```

## Service Management

The program runs automatically on startup. Use these commands to manage it:

- **Check Status**: `sudo systemctl status spi-now-playing.service`
- **Stop Service**: `sudo systemctl stop spi-now-playing.service`
- **Restart Service**: `sudo systemctl restart spi-now-playing.service`
- **View Logs**: `journalctl -u spi-now-playing.service -f`

## Updating

To update the project reliably (with automatic rollback on failure):
```bash
./update.sh
```
This script will stop the service, pull the latest code, update dependencies, and restart the service. If the new version fails to start, it will automatically roll back to the previous working version.

To test a pull request or a branch on Raspberry Pi without moving `main` manually:
```bash
./update-pr.sh 123
./update-pr.sh feature/album-art-fix
```
This script will:
- stop the service
- fetch the requested PR or branch from `origin`
- install dependencies if needed
- restart the service
- automatically roll back to the previous commit if startup fails

## Uninstallation

To remove the service and the virtual environment:
```bash
./uninstall.sh
```

## Manual Run
If you want to run the script manually for testing:
```bash
source venv/bin/activate
./src/spi-now-playing.py
```
*Note: You may need to run as `sudo` if your user doesn't have permissions for `/dev/fb0`.*

## Source Layout

```text
src/
├── app/
│   └── main.py              # Main controller and state loop
├── artwork/
│   └── providers.py         # Cover Art Archive fallback lookup
├── audio_input/             # Audio input work in progress
├── media_players/
│   ├── base.py              # MediaPlayer abstract base class
│   ├── volumio.py           # Volumio integration and artwork resolution
│   ├── moode.py             # MoOde integration stub
│   └── picore.py            # piCorePlayer integration stub
├── config.py                # Application configuration
├── renderer.py              # Framebuffer renderer
└── spi-now-playing.py       # Thin compatibility entrypoint
```
