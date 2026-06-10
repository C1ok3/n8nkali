#!/usr/bin/env bash
# Full first-time setup for n8nkali on Kali Linux
set -e

echo "=== n8nkali Setup ==="

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

# ── 1. Copy env ────────────────────────────────────────────────────────────────
if [ ! -f .env ]; then
  cp .env.example .env
  echo "[OK] Created .env — edit it with your values before continuing"
else
  echo "[SKIP] .env already exists"
fi

# ── 2. Fix Ollama ──────────────────────────────────────────────────────────────
echo ""
echo "--- Fixing Ollama ---"
bash "$SCRIPT_DIR/fix-ollama.sh"

# ── 3. Copy openclaw config ────────────────────────────────────────────────────
echo ""
echo "--- Configuring OpenClaw ---"
OPENCLAW_CONF="$HOME/.openclaw/openclaw.json"
mkdir -p "$(dirname "$OPENCLAW_CONF")"
cp "$PROJECT_ROOT/openclaw/openclaw.json" "$OPENCLAW_CONF"
echo "[OK] Copied openclaw.json → $OPENCLAW_CONF"

# ── 4. Start Docker stack ──────────────────────────────────────────────────────
echo ""
echo "--- Starting Docker stack ---"
if ! command -v docker &>/dev/null; then
  echo "[ERROR] Docker not found. Install Docker Desktop or Docker Engine first."
  exit 1
fi

docker compose up -d --build
echo "[OK] Stack started"

# Wait for n8n
echo "[INFO] Waiting for n8n to be ready..."
for i in $(seq 1 30); do
  if curl -sf http://localhost:5678/healthz &>/dev/null; then
    echo "[OK] n8n is ready at http://localhost:5678"
    break
  fi
  if [ "$i" -eq 30 ]; then
    echo "[WARN] n8n not ready after 30s. Check: docker compose logs n8n"
  fi
  sleep 2
done

# ── 5. Register OpenClaw agents ────────────────────────────────────────────────
echo ""
echo "--- Registering OpenClaw agents ---"
if command -v openclaw &>/dev/null; then
  for soul in "$PROJECT_ROOT"/openclaw/agents/*/SOUL.md; do
    agent_name=$(basename "$(dirname "$soul")")
    openclaw agents add "$soul" 2>/dev/null && echo "[OK] Agent: $agent_name" || \
      echo "[WARN] Could not add $agent_name"
  done
else
  echo "[WARN] openclaw not in PATH. After installing, run:"
  for soul in "$PROJECT_ROOT"/openclaw/agents/*/SOUL.md; do
    echo "  openclaw agents add $soul"
  done
fi

echo ""
echo "=== Setup complete ==="
echo ""
echo "  n8n UI:      http://localhost:5678"
echo "  Scraper API: http://localhost:5000"
echo "  Postgres:    localhost:5432 / DB: n8nkali"
echo ""
echo "  Next:"
echo "  1. Import n8n workflows from n8n/workflows/"
echo "  2. openclaw gateway start"
echo "  3. openclaw agents chat orchestrator"
