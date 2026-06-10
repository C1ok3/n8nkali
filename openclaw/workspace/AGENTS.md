# n8nkali Agent Roster

## Main Brain — KALI (Orchestrator)
- **Run**: `ollama run openclaw`
- **Model**: qwen3.6:latest (base)
- **Location**: `~/.openclaw/workspace/`
- **Purpose**: Central control — run pipeline, check status, delegate to agents

## Scout (Researcher)
- **Model**: `ollama run deepseek-r1:14b`
- **Purpose**: Analyse Fiverr research data, find gaps
- **Input**: JSON from scraper at http://localhost:5000/research
- **System prompt**: `~/.openclaw/workspace/agents/scout.md`

## Forge (Creator)
- **Model**: `ollama run qwen3.6`
- **Purpose**: Generate superior product briefs
- **Input**: Scout's research analysis
- **System prompt**: `~/.openclaw/workspace/agents/forge.md`

## Pixel (Editor)
- **Model**: `ollama run qwen2.5-coder:14b`
- **Purpose**: Polish content, write image prompts, manage assets
- **Input**: Forge's product brief
- **System prompt**: `~/.openclaw/workspace/agents/pixel.md`

## Apex (QC)
- **Model**: `ollama run deepseek-r1:32b`
- **Purpose**: Score products, approve or send back for revision
- **Input**: Pixel's edited product
- **System prompt**: `~/.openclaw/workspace/agents/apex.md`

---

## Quick Commands

```bash
# Start main orchestrator
cd ~/.openclaw/workspace && ollama run openclaw

# Run a pipeline stage manually
curl -X POST http://localhost:5000/research -H "Content-Type: application/json" \
  -d '{"category":"ebook","max_results":20}'

# Open dashboard
open http://localhost:8080

# Check all services
bash ~/n8nkali/scripts/health-check.sh
```
