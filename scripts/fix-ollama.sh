#!/usr/bin/env bash
# Run this on your Kali machine to fix Ollama + OpenClaw connection issues
set -e

OLLAMA_PORT="${OLLAMA_PORT:-11434}"
OPENCLAW_CONFIG="$HOME/.openclaw/openclaw.json"

echo "=== n8nkali: Ollama + OpenClaw Fix Script ==="

# ── 1. Check if Ollama is installed ───────────────────────────────────────────
if ! command -v ollama &>/dev/null; then
  echo "[ERROR] Ollama not found. Install it first:"
  echo "  curl -fsSL https://ollama.com/install.sh | sh"
  exit 1
fi
echo "[OK] Ollama binary found: $(which ollama)"

# ── 2. Kill any stuck Ollama processes ────────────────────────────────────────
if pgrep -x ollama &>/dev/null; then
  echo "[INFO] Stopping existing Ollama process..."
  pkill -x ollama 2>/dev/null || true
  sleep 2
fi

# ── 3. Start Ollama bound to all interfaces (fixes container/VM access) ───────
echo "[INFO] Starting Ollama on 0.0.0.0:$OLLAMA_PORT ..."
OLLAMA_HOST="0.0.0.0:$OLLAMA_PORT" nohup ollama serve \
  > /tmp/ollama.log 2>&1 &
OLLAMA_PID=$!
echo "[INFO] Ollama PID: $OLLAMA_PID"

# Wait for Ollama to become ready
echo "[INFO] Waiting for Ollama to be ready..."
for i in $(seq 1 20); do
  if curl -sf "http://127.0.0.1:$OLLAMA_PORT/api/tags" &>/dev/null; then
    echo "[OK] Ollama is up on port $OLLAMA_PORT"
    break
  fi
  if [ "$i" -eq 20 ]; then
    echo "[ERROR] Ollama failed to start. Check /tmp/ollama.log"
    cat /tmp/ollama.log
    exit 1
  fi
  sleep 1
done

# ── 4. List available models ───────────────────────────────────────────────────
echo ""
echo "=== Available Ollama Models ==="
ollama list
echo ""

# Pull a recommended model if nothing is installed
MODELS=$(ollama list 2>/dev/null | tail -n +2 | awk '{print $1}' | head -1)
if [ -z "$MODELS" ]; then
  echo "[INFO] No models found. Pulling llama3.2 (good general model, ~2GB)..."
  ollama pull llama3.2
  MODELS="llama3.2"
fi

# Use the first available model as default
DEFAULT_MODEL=$(ollama list 2>/dev/null | tail -n +2 | awk '{print $1}' | head -1)
echo "[INFO] Default model set to: $DEFAULT_MODEL"

# ── 5. Write openclaw.json ─────────────────────────────────────────────────────
mkdir -p "$(dirname "$OPENCLAW_CONFIG")"

# Build models array from installed models
MODELS_JSON=""
while IFS= read -r line; do
  MODEL_ID=$(echo "$line" | awk '{print $1}')
  [ -z "$MODEL_ID" ] && continue
  [ "$MODEL_ID" = "NAME" ] && continue
  # Strip :latest suffix for cleaner IDs
  MODEL_NAME="${MODEL_ID%:latest}"
  MODELS_JSON="${MODELS_JSON}
          {
            \"id\": \"${MODEL_ID}\",
            \"name\": \"${MODEL_NAME}\",
            \"api\": \"ollama\",
            \"reasoning\": false,
            \"input\": [\"text\"],
            \"cost\": { \"input\": 0, \"output\": 0, \"cacheRead\": 0, \"cacheWrite\": 0 },
            \"contextWindow\": 128000,
            \"maxTokens\": 8192,
            \"params\": { \"num_ctx\": 32768, \"keep_alive\": \"15m\" }
          },"
done < <(ollama list | tail -n +2)

# Remove trailing comma from last entry
MODELS_JSON="${MODELS_JSON%,}"

cat > "$OPENCLAW_CONFIG" << JSONEOF
{
  "models": {
    "mode": "merge",
    "providers": {
      "ollama": {
        "baseUrl": "http://127.0.0.1:${OLLAMA_PORT}",
        "apiKey": "ollama-local",
        "api": "ollama",
        "timeoutSeconds": 300,
        "models": [${MODELS_JSON}
        ]
      }
    }
  },
  "tools": {
    "byProvider": {
      "ollama/*": {
        "allow": ["*"]
      }
    }
  },
  "agents": {
    "defaults": {
      "model": {
        "primary": "ollama/${DEFAULT_MODEL}"
      }
    }
  },
  "memory": {
    "enabled": true,
    "provider": "local",
    "path": "${HOME}/.openclaw/memory"
  }
}
JSONEOF

echo "[OK] Written $OPENCLAW_CONFIG"

# ── 6. Verify OpenClaw can see the models ────────────────────────────────────
if command -v openclaw &>/dev/null; then
  echo ""
  echo "=== OpenClaw Model Check ==="
  openclaw models list --provider ollama 2>/dev/null || \
    echo "[WARN] openclaw models list failed — check openclaw install"
  openclaw models set "ollama/${DEFAULT_MODEL}" 2>/dev/null || \
    echo "[WARN] Could not set default model via CLI"
else
  echo "[WARN] openclaw CLI not in PATH. Install or add to PATH, then run:"
  echo "  openclaw models set ollama/${DEFAULT_MODEL}"
fi

# ── 7. Add openclaw agents for this project ───────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

if command -v openclaw &>/dev/null && [ -d "$PROJECT_ROOT/openclaw/agents" ]; then
  echo ""
  echo "=== Registering n8nkali Pipeline Agents ==="
  for soul in "$PROJECT_ROOT"/openclaw/agents/*/SOUL.md; do
    echo "  Adding agent: $soul"
    openclaw agents add "$soul" 2>/dev/null || echo "  [WARN] Failed to add $soul"
  done
fi

# ── 8. Firewall — open port if ufw is active ─────────────────────────────────
if command -v ufw &>/dev/null && ufw status 2>/dev/null | grep -q "Status: active"; then
  echo "[INFO] Opening port $OLLAMA_PORT in ufw..."
  ufw allow "$OLLAMA_PORT/tcp" 2>/dev/null || true
fi

echo ""
echo "=== Summary ==="
echo "  Ollama:         http://127.0.0.1:$OLLAMA_PORT"
echo "  Default model:  $DEFAULT_MODEL"
echo "  Config file:    $OPENCLAW_CONFIG"
echo ""
echo "  Test connectivity:"
echo "    curl http://127.0.0.1:$OLLAMA_PORT/api/tags"
echo ""
echo "  Start OpenClaw gateway:"
echo "    openclaw gateway start"
echo ""
echo "  Run the Fiverr pipeline:"
echo "    openclaw agents chat orchestrator"
