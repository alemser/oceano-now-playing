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
| `LAYOUT_PROFILE` | `high_contrast` | Environment variable or edit `Config.layout_profile` (`high_contrast` or `classic`) |
| `MEDIA_PLAYER` | `auto` | Environment variable or edit `Config.media_player_type` |
| `VOLUMIO_URL` | `ws://localhost:3000/socket.io/?EIO=3&transport=websocket` | Environment variable or edit `Config.volumio_url` |
| `MOODE_URL` | `http://localhost/engine-mpd.php` | Environment variable or edit `Config.moode_url` |
| `LMS_URL` | `ws://localhost:9000` | Environment variable or edit `Config.lms_url` |
| `EXTERNAL_ARTWORK_ENABLED` | `true` | Environment variable using `true/false`, `on/off`, `yes/no`, or `1/0` |
| `CYCLE_TIME` | `30` | Environment variable or edit `Config.mode_cycle_time` |
| `STANDBY_TIMEOUT` | `600` | Environment variable or edit `Config.standby_timeout` |

Notes:

- `MEDIA_PLAYER=auto` tries to detect the active backend automatically.
- `EXTERNAL_ARTWORK_ENABLED=true` allows fallback artwork lookup from external services when Volumio only returns its placeholder image.
- `EXTERNAL_ARTWORK_ENABLED=false` keeps Volumio's own artwork behavior intact, including its default placeholder when nothing better is available.
- `COLOR_FORMAT=BGR565` is useful if red and blue look swapped on your panel.
- `LAYOUT_PROFILE=high_contrast` is optimized for lower-quality/off-angle resistive panels; `classic` keeps the previous visual style.

To change these via the service, edit `/etc/systemd/system/spi-now-playing.service` and add entries under `[Service]`, for example:

```ini
Environment="MEDIA_PLAYER=volumio"
Environment="LAYOUT_PROFILE=high_contrast"
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
