#!/bin/bash

# Oceano Now Playing - Uninstallation Script
set -e

echo "--- Uninstalling Oceano Now Playing ---"

# 1. Stop and Disable Systemd Service
echo "Stopping and removing systemd service..."
if [ -f "/etc/systemd/system/oceano-now-playing.service" ]; then
    sudo systemctl stop oceano-now-playing.service || true
    sudo systemctl disable oceano-now-playing.service || true
    sudo rm /etc/systemd/system/oceano-now-playing.service
    sudo systemctl daemon-reload
fi

# 2. Cleanup Virtual Environment
echo "Cleaning up files..."
if [ -d "venv" ]; then
    rm -rf venv
fi

echo "--- Uninstallation Complete! ---"
echo "Note: System dependencies (pip, venv, fonts) and the project files themselves were not removed."
echo "To also remove the old spi-now-playing service if present:"
echo "  sudo systemctl stop spi-now-playing.service 2>/dev/null || true"
echo "  sudo rm -f /etc/systemd/system/spi-now-playing.service"
echo "  sudo systemctl daemon-reload"
