#!/bin/bash
set -e

echo "[prestart] Cleaning conflicting discord packages..."
pip uninstall discord.py discord.py-self -y --quiet 2>/dev/null || true
rm -rf ~/.local/lib/python3.*/site-packages/discord* 2>/dev/null || true

echo "[prestart] Installing Python deps..."
pip install --quiet -r requirements.txt

if ! command -v node &> /dev/null; then
    echo "[prestart] Node.js not found. Downloading portable Node.js..."
    if command -v wget &> /dev/null; then
        wget -q https://nodejs.org/dist/v18.20.2/node-v18.20.2-linux-x64.tar.xz
    else
        curl -sLO https://nodejs.org/dist/v18.20.2/node-v18.20.2-linux-x64.tar.xz
    fi
    tar -xf node-v18.20.2-linux-x64.tar.xz
    export PATH=$PWD/node-v18.20.2-linux-x64/bin:$PATH
    rm node-v18.20.2-linux-x64.tar.xz
fi

echo "[prestart] Installing Node deps..."
npm install --quiet --no-audit --no-fund

echo "[prestart] Launching..."
python3 -u main.py &
PY_PID=$!
trap "kill $PY_PID 2>/dev/null" EXIT
node bot/index.js
