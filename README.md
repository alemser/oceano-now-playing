# SPI Now Playing for Volumio

This project displays Volumio's current playing status (title, artist, album, art, and quality) on an SPI-connected display using the Linux framebuffer (`/dev/fb0`). Optimized for Raspberry Pi 5.

## Prerequisites

- **Raspberry Pi 5** running Raspberry Pi OS or Volumio.
- **SPI Display** correctly configured and visible as `/dev/fb0`.
- **Volumio** running on the same Pi (localhost:3000).

## Installation

### 1. Enable SPI Display Framebuffer
Ensure your display's overlay is enabled. On Volumio, add the following to `/boot/userconfig.txt`:

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

You can customize the behavior by editing the constants at the top of `src/spi-now-playing.py` or by setting environment variables in the service file.

- **STANDBY_TIMEOUT**: Time in seconds of inactivity before the screen goes black (default: `600` = 10 minutes).
- **CYCLE_TIME**: Time in seconds to switch from Text Mode to Album Art Mode (default: `30` seconds).
- **FB_DEVICE**: Framebuffer device path (default: `/dev/fb0`).

To change these via the service, edit `/etc/systemd/system/spi-now-playing.service` and add `Environment="STANDBY_TIMEOUT=600"` under the `[Service]` section.

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
