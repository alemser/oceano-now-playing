#!/bin/bash

# Oceano Now Playing - Installation Script for Raspberry Pi 5
set -euo pipefail

BRANCH="main"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --branch) BRANCH="${2:-}"; shift 2 ;;
    *) echo "Unknown argument: $1"; exit 1 ;;
  esac
done

echo "--- Installing Oceano Now Playing (branch: ${BRANCH}) ---"

# 0. Pull latest code
echo "Fetching latest code from branch ${BRANCH}..."
git fetch origin
git checkout "${BRANCH}"
git reset --hard "origin/${BRANCH}"

# 1. Update and Install System Dependencies
echo "Installing system dependencies..."
sudo apt-get update
sudo apt-get install -y python3-pip python3-venv python3-numpy python3-pil fonts-dejavu-core libopenblas-dev

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
SERVICE_PATH="/etc/systemd/system/oceano-now-playing.service"
WORKING_DIR=$(pwd)
USER_NAME=$(whoami)

cat <<EOF | sudo tee $SERVICE_PATH
[Unit]
Description=Oceano Now Playing Display
After=network-online.target
Wants=network-online.target
StartLimitIntervalSec=0

[Service]
Type=simple
ExecStart=${WORKING_DIR}/venv/bin/python ${WORKING_DIR}/src/oceano-now-playing.py
WorkingDirectory=${WORKING_DIR}
StandardOutput=journal
StandardError=journal
Restart=always
RestartSec=10
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
sudo systemctl enable oceano-now-playing.service
sudo systemctl restart oceano-now-playing.service

echo "--- Installation Complete! ---"
echo "You can check the service status with: sudo systemctl status oceano-now-playing.service"
echo "Or view logs with: journalctl -u oceano-now-playing.service -f"
