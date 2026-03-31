#!/usr/bin/env bash
set -euo pipefail

# ─────────────────────────────────────────────
#  Oceano Now Playing — Install / Update Script
#  Sets up the Python display service and registers it with systemd.
# ─────────────────────────────────────────────

SERVICE_NAME="oceano-now-playing.service"
SERVICE_DEST="/etc/systemd/system/${SERVICE_NAME}"
OCEANO_MODE_DEST="/usr/local/bin/oceano-mode"

DEFAULT_BRANCH="main"

# ─── Output colors ───────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
RESET='\033[0m'

log_info()    { echo -e "${CYAN}[INFO]${RESET}  $*"; }
log_ok()      { echo -e "${GREEN}[OK]${RESET}    $*"; }
log_warn()    { echo -e "${YELLOW}[WARN]${RESET}  $*"; }
log_error()   { echo -e "${RED}[ERROR]${RESET} $*" >&2; }
log_section() { echo -e "\n${BOLD}━━━ $* ━━━${RESET}"; }

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    log_error "Required command not found: $1"
    exit 1
  }
}

is_installed() {
  [[ -f "${SERVICE_DEST}" ]]
}

# ─── Main ────────────────────────────────────

main() {
  require_cmd git
  require_cmd python3
  require_cmd sudo
  require_cmd systemctl

  local branch="${DEFAULT_BRANCH}"

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --branch) branch="${2:-}"; shift 2 ;;
      -h|--help)
        echo "Usage: ./install.sh [options]"
        echo ""
        echo "Options:"
        echo "  --branch <name>   Git branch to install (default: ${DEFAULT_BRANCH})"
        exit 0
        ;;
      *) log_error "Unknown argument: $1"; exit 1 ;;
    esac
  done

  local mode
  mode=$(is_installed && echo "UPDATE" || echo "INSTALL")

  echo -e "\n${BOLD}╔══════════════════════════════════════╗"
  echo -e "║   Oceano Now Playing — ${mode}      ║"
  echo -e "╚══════════════════════════════════════╝${RESET}"

  # ── Pre-flight ──
  log_section "Pre-flight"
  if [[ ! -f "/etc/oceano/config.json" ]]; then
    log_error "Oceano Player is not installed (config not found at /etc/oceano/config.json)."
    echo ""
    echo -e "  Install oceano-player first:"
    echo -e "  ${BOLD}curl -fsSL -o install.sh https://raw.githubusercontent.com/alemser/oceano-player/main/install.sh${RESET}"
    echo -e "  ${BOLD}chmod +x install.sh && sudo ./install.sh${RESET}"
    exit 1
  fi
  log_ok "Oceano Player detected."

  # ── Repository ──
  log_section "Repository"
  log_info "Fetching branch ${branch}..."
  git fetch origin
  git checkout "${branch}"
  git reset --hard "origin/${branch}"
  log_ok "Repository synced to branch ${branch}."

  # ── System packages ──
  log_section "System Packages"
  log_info "Installing system dependencies..."
  sudo apt-get update -qq
  sudo apt-get install -y --no-install-recommends \
    python3-pip python3-venv python3-numpy python3-pil \
    fonts-dejavu-core libopenblas-dev
  log_ok "System packages ready."

  # ── User groups ──
  log_section "User Groups"
  local user_name
  user_name="$(whoami)"
  sudo usermod -a -G video "${user_name}"
  sudo usermod -a -G tty   "${user_name}"
  log_ok "User ${user_name} added to video and tty groups."

  # ── Virtual environment ──
  log_section "Python Environment"
  if [[ ! -d "venv" ]]; then
    log_info "Creating virtual environment..."
    python3 -m venv venv
  else
    log_info "Virtual environment already exists — reusing."
  fi
  venv/bin/pip install --quiet -r requirements.txt
  log_ok "Dependencies installed."

  # ── oceano-mode helper ──
  log_section "Helper Command"
  local working_dir
  working_dir="$(pwd)"
  sudo install -m 0755 "${working_dir}/oceano-mode" "${OCEANO_MODE_DEST}"
  log_ok "oceano-mode installed at ${OCEANO_MODE_DEST}."

  # ── Cursor suppression ──
  sudo sh -c "setterm -cursor off > /dev/tty1" 2>/dev/null || true

  # ── systemd service ──
  log_section "systemd Service"
  cat > /tmp/oceano-now-playing-unit <<EOF
[Unit]
Description=Oceano Now Playing Display
After=network-online.target oceano-state-manager.service shairport-sync.service
Wants=network-online.target oceano-state-manager.service shairport-sync.service
StartLimitIntervalSec=0

[Service]
Type=simple
ExecStart=${working_dir}/venv/bin/python ${working_dir}/src/oceano-now-playing.py
WorkingDirectory=${working_dir}
EnvironmentFile=-/etc/oceano/display.env
StandardOutput=journal
StandardError=journal
Restart=always
RestartSec=10
TimeoutStopSec=30
User=${user_name}
Group=video
SupplementaryGroups=video

[Install]
WantedBy=multi-user.target
EOF
  sudo mv /tmp/oceano-now-playing-unit "${SERVICE_DEST}"
  sudo systemctl daemon-reload
  sudo systemctl enable "${SERVICE_NAME}"
  sudo systemctl restart "${SERVICE_NAME}"
  log_ok "${SERVICE_NAME} is now running."

  # ── Done ──
  log_section "Done"
  log_ok "${mode} completed successfully!"
  echo -e "Use ${BOLD}journalctl -u ${SERVICE_NAME} -f${RESET} to monitor logs."
  echo -e "Switch display modes with: ${BOLD}oceano-mode <rotate|text|artwork|hybrid|vu>${RESET}"
}

main "$@"
