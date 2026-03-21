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

### 3. Automatic Installation
Run the following commands in the project directory:
```bash
chmod +x install.sh
./install.sh
```
This will:
- Install system dependencies (`pip`, `venv`, `numpy`, `pil`).
- Setup a Python virtual environment.
- Install all Python libraries from `requirements.txt`.
- Create, enable, and start a systemd service (`spi-now-playing.service`).

## Service Management

The program runs automatically on startup. Use these commands to manage it:

- **Check Status**: `sudo systemctl status spi-now-playing.service`
- **Stop Service**: `sudo systemctl stop spi-now-playing.service`
- **Restart Service**: `sudo systemctl restart spi-now-playing.service`
- **View Logs**: `journalctl -u spi-now-playing.service -f`

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
