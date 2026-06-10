# n8nkali — Fiverr Pipeline

## Project overview
Automated Fiverr product pipeline: Research → Create → Edit → QC → Publish.
Runs locally on Kali Linux. Ollama models, no cloud API costs.

## Stack
- **Brain**: OpenClaw (`ollama run openclaw`) — orchestrates via chat commands
- **Pipeline runner**: `pipeline/runner.py` — calls Ollama directly for each stage
- **Scraper**: Python Flask on port 5000 — Fiverr research + brand asset download
- **Database**: PostgreSQL (CRM + pipeline state)
- **Dashboard**: Flask + SocketIO at port 8080

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
# 1. Fix Ollama binding
bash scripts/fix-ollama.sh

# 2. Install openclaw brain model
bash scripts/install-openclaw-model.sh

# 3. Start services (postgres, scraper, dashboard)
cp .env.example .env
docker compose up -d

# 4. Run the pipeline
python pipeline/runner.py --category ebook
python pipeline/runner.py --category all
python pipeline/runner.py --status

# 5. Or talk to KALI directly
ollama run openclaw
```

## Key paths
- `openclaw/workspace/Modelfile` → defines the openclaw Ollama model
- `openclaw/agents/` → SOUL.md configs for each agent
- `pipeline/runner.py` → main pipeline orchestrator
- `pipeline/agents.py` → model + system prompt definitions
- `scraper/` → Fiverr scraping service
- `crm/schema.sql` → PostgreSQL schema
- `scripts/` → setup and fix scripts

## Coding tasks
Delegate all code changes to Claude Code:
```
claude -p --dangerously-skip-permissions "<task description>"
```
