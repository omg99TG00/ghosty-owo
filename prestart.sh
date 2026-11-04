#!/bin/bash
set -e

echo "[prestart] Cleaning conflicting discord packages..."
pip uninstall discord.py discord.py-self -y --quiet 2>/dev/null || true
rm -rf /home/container/.local/lib/python3.*/site-packages/discord* 2>/dev/null || true

echo "[prestart] Installing Python deps..."
pip install --quiet -r requirements.txt

if command -v npm &> /dev/null; then
    echo "[prestart] Installing Node deps..."
    npm install --quiet --no-audit --no-fund
else
    echo "[prestart] WARN: npm not found. Node controller will not start."
fi

echo "[prestart] Launching..."
if command -v npm &> /dev/null && [ -f bot/index.js ]; then
    python3 -u main.py &
    PY_PID=$!
    trap "kill $PY_PID 2>/dev/null" EXIT
    node bot/index.js
else
    exec python3 -u main.py
fi
