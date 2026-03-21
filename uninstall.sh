#!/bin/bash

# SPI Now Playing - Uninstallation Script
set -e

echo "--- Uninstalling SPI Now Playing ---"

# 1. Stop and Disable Systemd Service
echo "Stopping and removing systemd service..."
if [ -f "/etc/systemd/system/spi-now-playing.service" ]; then
    sudo systemctl stop spi-now-playing.service || true
    sudo systemctl disable spi-now-playing.service || true
    sudo rm /etc/systemd/system/spi-now-playing.service
    sudo systemctl daemon-reload
fi

# 2. Cleanup Virtual Environment
echo "Cleaning up files..."
if [ -d "venv" ]; then
    rm -rf venv
fi

echo "--- Uninstallation Complete! ---"
echo "Note: System dependencies (pip, venv, fonts) and the project files themselves were not removed."
