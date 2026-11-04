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
