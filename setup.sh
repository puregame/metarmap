#!/bin/bash
set -e

# Must run as root
if [ "$(id -u)" -ne 0 ]; then
    echo "ERROR: This script must be run as root (sudo su first)." >&2
    exit 1
fi

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="/root/venv"

echo "=== MetarMap Setup ==="
echo "Repo: $REPO_DIR"
echo ""

# 1. System packages
echo "[1/6] Installing system packages..."
apt-get update -qq
apt-get install -y -qq \
    python3-pip \
    python3-venv \
    libjpeg-dev \
    zlib1g-dev \
    libfreetype6-dev \
    dnsmasq \
    i2c-tools

# 2. Enable I2C
echo "[2/6] Enabling I2C interface..."
raspi-config nonint do_i2c 0
echo "      I2C enabled."

# 3. Python virtual environment
echo "[3/6] Creating Python virtual environment at $VENV_DIR..."
python3 -m venv "$VENV_DIR"

# 4. Install Python dependencies
echo "[4/6] Installing Python dependencies..."
"$VENV_DIR/bin/pip" install --quiet --upgrade pip
"$VENV_DIR/bin/pip" install --quiet -r "$REPO_DIR/requirements.txt"

# 5. Systemd service
echo "[5/6] Installing systemd service..."
cp "$REPO_DIR/metarmap.service" /etc/systemd/system/metarmap.service
systemctl daemon-reexec
systemctl daemon-reload
systemctl enable metarmap.service

# 6. Create default config if none exists
echo "[6/6] Checking for config.json..."
if [ ! -f "$REPO_DIR/config.json" ]; then
    echo '{"airports": [], "home": "", "num_leds": 50, "timezone": "UTC"}' > "$REPO_DIR/config.json"
    echo "      Created default config.json — configure via the web UI."
else
    echo "      config.json already exists, leaving it untouched."
fi

# Done
echo ""
echo "=== Setup complete ==="
echo ""
echo "Starting MetarMap service..."
systemctl start metarmap.service
systemctl status metarmap.service --no-pager

echo ""
echo "Open your browser to: http://$(hostname -I | awk '{print $1}'):80"
echo "Or use:               http://$(hostname).local:80"
