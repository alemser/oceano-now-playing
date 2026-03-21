#!/bin/bash

# SPI Now Playing - Reliable Update Script
# Stops service, pulls from git, and restarts. Rolls back on failure.
set -e

SERVICE_NAME="spi-now-playing.service"
BACKUP_COMMIT=$(git rev-parse HEAD)

echo "--- Starting Reliable Update ---"

# 1. Stop the service
echo "Stopping $SERVICE_NAME..."
# Try to stop the service gracefully, but kill it if it takes too long (10s timeout)
if ! timeout 10s sudo systemctl stop $SERVICE_NAME; then
    echo "WARNING: Service failed to stop gracefully. Killing it..."
    sudo systemctl kill -s SIGKILL $SERVICE_NAME || true
    sudo systemctl stop $SERVICE_NAME || true
fi

# 2. Pull the latest changes
echo "Fetching latest changes from git..."
if ! git pull origin main; then
    echo "ERROR: Git pull failed. Aborting update."
    sudo systemctl start $SERVICE_NAME
    exit 1
fi

# 3. Check for dependency changes
echo "Checking for new dependencies..."
if [ -f "requirements.txt" ] && [ -d "venv" ]; then
    source venv/bin/activate
    pip install -r requirements.txt
fi

# 4. Try to start the service
echo "Starting updated service..."
sudo systemctl daemon-reload
if ! sudo systemctl start $SERVICE_NAME; then
    echo "CRITICAL ERROR: Service failed to start after update!"
    echo "--- Initiating Rollback ---"
    
    # Rollback git
    git reset --hard $BACKUP_COMMIT
    
    # Re-install previous dependencies if needed
    if [ -f "requirements.txt" ] && [ -d "venv" ]; then
        pip install -r requirements.txt
    fi
    
    # Restart original version
    sudo systemctl daemon-reload
    sudo systemctl start $SERVICE_NAME
    
    echo "--- Rollback Complete. Project is back to previous version. ---"
    exit 1
fi

# 5. Final check
sleep 2
if ! systemctl is-active --quiet $SERVICE_NAME; then
    echo "ERROR: Service started but died shortly after. Rolling back..."
    git reset --hard $BACKUP_COMMIT
    sudo systemctl daemon-reload
    sudo systemctl restart $SERVICE_NAME
    echo "--- Rollback Complete. ---"
    exit 1
fi

echo "--- Update Successful! ---"
sudo systemctl status $SERVICE_NAME --no-pager
