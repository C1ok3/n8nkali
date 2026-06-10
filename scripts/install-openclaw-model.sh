#!/usr/bin/env bash
# Creates the 'openclaw' Ollama model so you can type: ollama run openclaw
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
WORKSPACE="$HOME/.openclaw/workspace"
MODELFILE="$WORKSPACE/Modelfile"

echo "=== Installing OpenClaw Ollama Model ==="

# ── 1. Check Ollama is running ────────────────────────────────────────────────
if ! curl -sf http://127.0.0.1:11434/api/tags &>/dev/null; then
  echo "[ERROR] Ollama is not running. Start it first:"
  echo "  OLLAMA_HOST=0.0.0.0:11434 ollama serve &"
  echo ""
  echo "  Or run the full fix: bash $SCRIPT_DIR/fix-ollama.sh"
  exit 1
fi
echo "[OK] Ollama is running"

# ── 2. Check qwen3.6:latest is installed ──────────────────────────────────────
if ! ollama list 2>/dev/null | grep -q "qwen3.6"; then
  echo "[WARN] qwen3.6:latest not found. Checking for alternative base model..."
  # Fall back to best available model
  BEST_MODEL=$(ollama list 2>/dev/null | tail -n +2 | grep -E "qwen3|qwen2.5:32|llama3.1:70" | head -1 | awk '{print $1}')
  if [ -z "$BEST_MODEL" ]; then
    BEST_MODEL=$(ollama list 2>/dev/null | tail -n +2 | awk '{print $1}' | head -1)
  fi
  echo "[INFO] Using $BEST_MODEL as base model"
  # Update Modelfile to use available model
  sed -i "s|FROM qwen3.6:latest|FROM $BEST_MODEL|g" "$MODELFILE" 2>/dev/null || true
else
  echo "[OK] qwen3.6:latest found"
fi

# ── 3. Set up workspace directory ─────────────────────────────────────────────
mkdir -p "$WORKSPACE"
echo "[OK] Workspace: $WORKSPACE"

# Copy Modelfile and agent configs to workspace
cp "$PROJECT_ROOT/openclaw/workspace/Modelfile" "$MODELFILE"
cp "$PROJECT_ROOT/openclaw/workspace/AGENTS.md" "$WORKSPACE/AGENTS.md"

# Also copy SOUL.md agent prompts
mkdir -p "$WORKSPACE/agents"
for soul in "$PROJECT_ROOT/openclaw/agents/"*/SOUL.md; do
  agent_name=$(basename "$(dirname "$soul")")
  cp "$soul" "$WORKSPACE/agents/${agent_name}.md"
  echo "[OK] Copied agent: $agent_name"
done

echo ""
echo "--- Modelfile preview ---"
head -5 "$MODELFILE"
echo "..."
echo ""

# ── 4. Create the openclaw model ──────────────────────────────────────────────
echo "[INFO] Creating openclaw model in Ollama..."
cd "$WORKSPACE"
ollama create openclaw -f "$MODELFILE"

echo ""
echo "=== Done! ==="
echo ""
echo "  Run OpenClaw:"
echo "    cd ~/.openclaw/workspace && ollama run openclaw"
echo ""
echo "  Or add this alias to ~/.bashrc / ~/.zshrc:"
echo "    alias openclaw='cd ~/.openclaw/workspace && ollama run openclaw'"
echo ""

# ── 5. Optionally add alias ────────────────────────────────────────────────────
SHELL_RC="$HOME/.bashrc"
[ -f "$HOME/.zshrc" ] && SHELL_RC="$HOME/.zshrc"

if ! grep -q "alias openclaw=" "$SHELL_RC" 2>/dev/null; then
  echo "" >> "$SHELL_RC"
  echo "# n8nkali: OpenClaw pipeline brain" >> "$SHELL_RC"
  echo "alias openclaw='cd ~/.openclaw/workspace && ollama run openclaw'" >> "$SHELL_RC"
  echo "[OK] Added 'openclaw' alias to $SHELL_RC"
  echo "     Run: source $SHELL_RC"
fi

echo ""
echo "  Test it now:"
echo "    ollama run openclaw"
