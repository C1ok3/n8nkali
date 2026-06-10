#!/usr/bin/env bash
# Quick health check for all n8nkali services
echo "=== n8nkali Health Check ==="
echo ""

check() {
  local name="$1" url="$2"
  if curl -sf "$url" &>/dev/null; then
    echo "  ✓ $name"
  else
    echo "  ✗ $name  →  $url"
  fi
}

check "Ollama"   "http://localhost:11434/api/tags"
check "Scraper"  "http://localhost:5000/health"
check "n8n"      "http://localhost:5678/healthz"
check "Dashboard" "http://localhost:8080/"

echo ""
echo "=== Ollama Models ==="
ollama list 2>/dev/null | head -10 || echo "  Ollama not reachable"

echo ""
echo "=== openclaw model ==="
ollama show openclaw 2>/dev/null | head -5 || echo "  Not installed. Run: bash scripts/install-openclaw-model.sh"
