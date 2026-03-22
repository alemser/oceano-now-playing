#!/bin/bash

# SPI Now Playing - Installation Script for Raspberry Pi 5
set -e

echo "--- Installing SPI Now Playing ---"

# 1. Update and Install System Dependencies
echo "Installing system dependencies..."
sudo apt-get update
sudo apt-get install -y python3-pip python3-venv python3-numpy python3-pil fonts-dejavu-core libopenblas-dev libatlas-base-dev

# 2. Add current user to video group
echo "Ensuring user $(whoami) is in the video group for framebuffer access..."
sudo usermod -a -G video $(whoami)
sudo usermod -a -G tty $(whoami) # Also add to tty group to control cursor

# 3. Disable cursor on boot (optional but recommended)
echo "Disabling blinking cursor on terminal..."
sudo sh -c "setterm -cursor off > /dev/tty1" || true
echo "Setting up virtual environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate
pip install -r requirements.txt

# 3. Setup Systemd Service
echo "Creating systemd service..."
SERVICE_PATH="/etc/systemd/system/spi-now-playing.service"
WORKING_DIR=$(pwd)
USER_NAME=$(whoami)

cat <<EOF | sudo tee $SERVICE_PATH
[Unit]
Description=SPI Now Playing Display for Volumio
After=network-online.target volumio.service
Wants=network-online.target

[Service]
Type=simple
ExecStart=${WORKING_DIR}/venv/bin/python ${WORKING_DIR}/src/spi-now-playing.py
WorkingDirectory=${WORKING_DIR}
StandardOutput=journal
StandardError=journal
Restart=always
RestartSec=10
StartLimitIntervalSec=0
TimeoutStopSec=30
User=${USER_NAME}
Group=video
SupplementaryGroups=video

[Install]
WantedBy=multi-user.target
EOF

# 4. Finalize and Start Service
echo "Reloading systemd and starting service..."
sudo systemctl daemon-reload
sudo systemctl enable spi-now-playing.service
sudo systemctl start spi-now-playing.service

echo "--- Installation Complete! ---"
echo "You can check the service status with: sudo systemctl status spi-now-playing.service"
echo "Or view logs with: journalctl -u spi-now-playing.service -f"
