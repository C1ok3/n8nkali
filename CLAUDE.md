# n8nkali — Fiverr Pipeline

## Project overview
Automated Fiverr product pipeline: Research → Create → Edit → QC → Publish.
Runs locally on Kali Linux. Ollama models, no cloud API costs.

## Stack
- **Orchestrator**: OpenClaw (agents in `openclaw/agents/`)
- **Workflows**: n8n (import JSONs from `n8n/workflows/`)
- **Scraper**: Python Flask on port 5000
- **Database**: PostgreSQL (CRM + n8n state)
- **Queue**: Redis
- **Models**: All via local Ollama on port 11434

## Model assignments
| Agent | Model | Purpose |
|-------|-------|---------|
| Orchestrator (Kali) | qwen3.6:latest | Planning, coordination |
| Researcher (Scout) | deepseek-r1:14b | Market analysis |
| Creator (Forge) | qwen3.6:latest | Content generation |
| Editor (Pixel) | qwen2.5-coder:14b | Formatting, prompts |
| QC (Apex) | deepseek-r1:32b | Scoring, gating |
| Embeddings | nomic-embed-text | Memory/search |
| Vision tasks | llama3.2-vision | Image analysis |
| Code tasks | qwen3-coder-next | Delegate to Claude Code |

## Quick start
```bash
# 1. Fix Ollama binding (run on Kali)
bash scripts/fix-ollama.sh

# 2. Copy env and start stack
cp .env.example .env
docker compose up -d

# 3. Import n8n workflows
# Go to http://localhost:5678 → Workflows → Import from File
# Import all files in n8n/workflows/

# 4. Register OpenClaw agents
openclaw agents add openclaw/agents/orchestrator/SOUL.md
openclaw agents add openclaw/agents/researcher/SOUL.md
openclaw agents add openclaw/agents/creator/SOUL.md
openclaw agents add openclaw/agents/editor/SOUL.md
openclaw agents add openclaw/agents/quality-check/SOUL.md

# 5. Start OpenClaw gateway
openclaw gateway start

# 6. Chat with the orchestrator
openclaw agents chat orchestrator
```

## Coding tasks
For all code changes, OpenClaw should delegate to Claude Code:
```
claude -p --dangerously-skip-permissions "<task description>"
```

## Key paths
- `openclaw/openclaw.json` → copy to `~/.openclaw/openclaw.json` on Kali
- `openclaw/agents/` → SOUL.md configs for each pipeline agent
- `n8n/workflows/` → Import these into n8n UI
- `scraper/` → Python Flask scraping service
- `crm/schema.sql` → PostgreSQL schema
- `scripts/fix-ollama.sh` → Fixes Ollama binding + writes openclaw.json

## Ollama connection fix
If you get "connection refused" to Ollama:
```bash
# Stop existing process
pkill ollama

# Start bound to all interfaces
OLLAMA_HOST=0.0.0.0:11434 ollama serve &

# Test
curl http://127.0.0.1:11434/api/tags

# Copy config
cp openclaw/openclaw.json ~/.openclaw/openclaw.json
```

## Pipeline products
- eBook writing
- Workbook / fillable PDF creation  
- YouTube thumbnail design
- Logo creation
- Consulting/coaching service listings
- Social media graphics
