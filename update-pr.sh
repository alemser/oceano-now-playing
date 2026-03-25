#!/bin/bash

# Oceano Now Playing - PR/Branch Test Update Script
# Stops service, checks out a PR or branch, restarts, and rolls back on failure.
set -euo pipefail

SERVICE_NAME="oceano-now-playing.service"
REMOTE_NAME="origin"
MAIN_BRANCH="main"
BACKUP_COMMIT=$(git rev-parse HEAD)
BACKUP_BRANCH=$(git rev-parse --abbrev-ref HEAD)

usage() {
    echo "Usage: $0 <pr-number|branch-name>"
    echo "Examples:"
    echo "  $0 123"
    echo "  $0 feature/album-art-fix"
}

rollback() {
    echo "--- Rolling back to previous version ---"

    if [ "$BACKUP_BRANCH" != "HEAD" ]; then
        git checkout "$BACKUP_BRANCH" || true
    fi
    git reset --hard "$BACKUP_COMMIT"

    if [ -f "requirements.txt" ] && [ -d "venv" ]; then
        source venv/bin/activate
        pip install -r requirements.txt
    fi

    sudo systemctl daemon-reload
    sudo systemctl restart "$SERVICE_NAME"
    echo "--- Rollback complete. Running previous commit: $BACKUP_COMMIT ---"
}

if [ "$#" -ne 1 ]; then
    usage
    exit 1
fi

TARGET="$1"

echo "--- Starting PR/Branch Test Update ---"
echo "Current branch: $BACKUP_BRANCH"
echo "Current commit: $BACKUP_COMMIT"
echo "Target: $TARGET"

echo "Stopping $SERVICE_NAME..."
if ! timeout 20s sudo systemctl stop "$SERVICE_NAME"; then
    echo "WARNING: Service did not stop gracefully. Forcing stop..."
    sudo systemctl kill -s SIGKILL "$SERVICE_NAME" || true
    sudo systemctl stop "$SERVICE_NAME" || true
fi

echo "Fetching latest refs from $REMOTE_NAME..."
git fetch --prune "$REMOTE_NAME"

if [[ "$TARGET" =~ ^[0-9]+$ ]]; then
    PR_NUM="$TARGET"
    TEST_BRANCH="pr-$PR_NUM"

    echo "Checking out PR #$PR_NUM into local branch $TEST_BRANCH..."
    if ! git fetch "$REMOTE_NAME" "pull/$PR_NUM/head:$TEST_BRANCH"; then
        echo "ERROR: Could not fetch PR #$PR_NUM"
        rollback
        exit 1
    fi
    git checkout "$TEST_BRANCH"
else
    TEST_BRANCH="$TARGET"

    echo "Checking out branch $TEST_BRANCH..."
    if git show-ref --verify --quiet "refs/heads/$TEST_BRANCH"; then
        git checkout "$TEST_BRANCH"
    elif git show-ref --verify --quiet "refs/remotes/$REMOTE_NAME/$TEST_BRANCH"; then
        git checkout -b "$TEST_BRANCH" "$REMOTE_NAME/$TEST_BRANCH"
    else
        echo "ERROR: Branch not found locally or on $REMOTE_NAME: $TEST_BRANCH"
        rollback
        exit 1
    fi

    if git show-ref --verify --quiet "refs/remotes/$REMOTE_NAME/$TEST_BRANCH"; then
        git reset --hard "$REMOTE_NAME/$TEST_BRANCH"
    fi
fi

NEW_COMMIT=$(git rev-parse HEAD)
echo "Checked out commit: $NEW_COMMIT"

echo "Checking dependencies..."
if [ -f "requirements.txt" ] && [ -d "venv" ]; then
    source venv/bin/activate
    pip install -r requirements.txt
fi

echo "Starting service on test target..."
sudo systemctl daemon-reload
if ! sudo systemctl start "$SERVICE_NAME"; then
    echo "CRITICAL ERROR: Service failed to start on test target."
    rollback
    exit 1
fi

sleep 2
if ! systemctl is-active --quiet "$SERVICE_NAME"; then
    echo "ERROR: Service started but died shortly after."
    rollback
    exit 1
fi

echo "--- Test update successful! ---"
echo "Now running branch: $(git rev-parse --abbrev-ref HEAD)"
echo "Now running commit: $(git rev-parse HEAD)"
sudo systemctl status "$SERVICE_NAME" --no-pager
