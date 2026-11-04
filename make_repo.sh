#!/bin/bash
# make_repo.sh
# Produces ghosty-owo.zip — a complete, ready-to-host repo.
#
# Prereq: original main.py (the one with _EMBEDDED_TEXT/_EMBEDDED_BIN)
#         must be in the SAME folder as this script.
#
# Run: bash make_repo.sh
# Output: ghosty-owo.zip in current folder

set -e

BUILD="ghosty-owo"
OUT="ghosty-owo.zip"

# ── Sanity check ────────────────────────────────────────────────────
if [ ! -f "main.py" ]; then
    echo "[ERR] main.py not found in current folder."
    echo "      Place your ORIGINAL main.py here, then rerun."
    exit 1
fi

if ! grep -q "_EMBEDDED_BIN" main.py; then
    echo "[ERR] main.py has no _EMBEDDED_BIN dict."
    echo "      This looks like the WRONG main.py. Use the original."
    exit 1
fi

echo "[1/8] Preparing build tree…"
rm -rf "$BUILD" "$OUT"
mkdir -p "$BUILD"/bot
mkdir -p "$BUILD"/core
mkdir -p "$BUILD"/dashboard/static/css
mkdir -p "$BUILD"/dashboard/static/js
mkdir -p "$BUILD"/dashboard/templates
mkdir -p "$BUILD"/assets

# ── Root files ──────────────────────────────────────────────────────
echo "[2/8] Writing root config files…"

cat > "$BUILD"/.env.example <<'EOF'
# -- Node.js controller bot (discord.js) --
DISCORD_BOT_TOKEN=

# -- Python API bridge (Node -> Python) --
PY_API_URL=http://127.0.0.1:5000

# -- Web dashboard toggle --
WEB_DASHBOARD=true

# -- Optional: legacy standalone selfbot --
# SELFBOT_TOKEN=
# SELFBOT_CHANNEL_ID=
EOF

cat > "$BUILD"/.gitignore <<'EOF'
.env
__pycache__/
*.pyc
*.pyo
node_modules/
package-lock.json
.venv/
venv/
*.log
ghostyhbworkers.json
ghostyworkerquests.json
data/
.DS_Store
EOF

cat > "$BUILD"/requirements.txt <<'EOF'
discord.py-self
colorama
aiohttp
requests
pillow
numpy
flask
flask-cors
waitress
EOF

cat > "$BUILD"/package.json <<'EOF'
{
  "name": "ghosty-owo-multiuser",
  "version": "4.1.0",
  "description": "GhoSty OwO - discord.js controller + discord.py-self workers",
  "main": "bot/index.js",
  "type": "commonjs",
  "engines": { "node": ">=18" },
  "scripts": {
    "start": "node bot/index.js",
    "start:python": "python3 main.py",
    "start:all": "concurrently \"npm start\" \"npm run start:python\""
  },
  "dependencies": {
    "discord.js": "^14.14.1",
    "dotenv": "^16.3.1"
  },
  "devDependencies": {
    "concurrently": "^8.2.2"
  }
}
EOF

echo "python-3.11.0" > "$BUILD"/runtime.txt

cat > "$BUILD"/prestart.sh <<'EOF'
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
EOF
chmod +x "$BUILD"/prestart.sh

cat > "$BUILD"/Dockerfile <<'EOF'
FROM node:18-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip python3-venv \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt

COPY package.json .
RUN npm install --production --no-audit --no-fund

COPY . .
EXPOSE 5000 8765
CMD ["bash", "prestart.sh"]
EOF

cat > "$BUILD"/docker-compose.yml <<'EOF'
version: '3.8'
services:
  ghosty:
    build: .
    ports:
      - "5000:5000"
      - "8765:8765"
    env_file:
      - .env
    volumes:
      - ./data:/app/data
    restart: unless-stopped
EOF

# ── README ──────────────────────────────────────────────────────────
echo "[3/8] Writing README.md…"
cat > "$BUILD"/README.md <<'MDEOF'
# GhoSty OwO - Multi-User Edition

discord.js controller (bot) + discord.py-self workers (selfbots) + Flask bridge + web dashboard.

Zero package conflict. Two processes. One HTTP bridge.

## Architecture
