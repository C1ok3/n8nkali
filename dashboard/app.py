import os
import json
import logging
import threading
import time
from datetime import datetime

import httpx
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO, emit

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger(__name__)

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("DASHBOARD_SECRET", "n8nkali-dashboard")
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="gevent")

OLLAMA_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
SCRAPER_URL = os.environ.get("SCRAPER_SERVICE_URL", "http://localhost:5000")
N8N_URL = os.environ.get("WEBHOOK_URL", "http://localhost:5678")

DB_CONFIG = {
    "host": os.environ.get("POSTGRES_HOST", "localhost"),
    "port": int(os.environ.get("POSTGRES_PORT", 5432)),
    "dbname": os.environ.get("POSTGRES_DB", "n8nkali"),
    "user": os.environ.get("POSTGRES_USER", "n8nkali"),
    "password": os.environ.get("POSTGRES_PASSWORD", "changeme"),
}

AGENTS = {
    "kali":  {"name": "Kali",  "role": "Orchestrator", "model": "openclaw",           "color": "#7c3aed"},
    "scout": {"name": "Scout", "role": "Researcher",   "model": "deepseek-r1:14b",    "color": "#0891b2"},
    "forge": {"name": "Forge", "role": "Creator",      "model": "qwen3.6:latest",     "color": "#059669"},
    "pixel": {"name": "Pixel", "role": "Editor",       "model": "qwen2.5-coder:14b",  "color": "#d97706"},
    "apex":  {"name": "Apex",  "role": "QC",           "model": "deepseek-r1:32b",    "color": "#dc2626"},
}

AGENT_SYSTEM_PROMPTS = {
    "kali":  "You are Kali, the n8nkali pipeline orchestrator. Coordinate research, creation, editing, and quality control for Fiverr products.",
    "scout": "You are Scout, a Fiverr market researcher. Analyse top-selling products, find gaps, and recommend opportunities.",
    "forge": "You are Forge, a Fiverr content creator. Create superior product briefs: eBooks, workbooks, thumbnails, logos, service listings.",
    "pixel": "You are Pixel, an editor and visual specialist. Polish content, write DALL-E image prompts, and manage brand assets.",
    "apex":  "You are Apex, a quality assurance specialist. Score products 0-100 across completeness, differentiation, SEO, quality, and visual readiness.",
}


def get_db():
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        conn.autocommit = True
        return conn
    except Exception as e:
        log.warning(f"DB connection failed: {e}")
        return None


def db_query(sql, params=None):
    conn = get_db()
    if not conn:
        return []
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]
    except Exception as e:
        log.warning(f"DB query error: {e}")
        return []
    finally:
        conn.close()


def check_service(url: str, path: str = "/health") -> dict:
    try:
        resp = httpx.get(f"{url}{path}", timeout=3)
        return {"ok": resp.status_code < 400, "status": resp.status_code}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def check_ollama() -> dict:
    try:
        resp = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=3)
        if resp.status_code == 200:
            models = [m["name"] for m in resp.json().get("models", [])]
            return {"ok": True, "models": models}
        return {"ok": False}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def get_pipeline_stats() -> dict:
    runs = db_query("""
        SELECT stage, status, COUNT(*) as count
        FROM pipeline_runs
        WHERE started_at > NOW() - INTERVAL '7 days'
        GROUP BY stage, status
        ORDER BY stage, status
    """)

    queue = db_query("""
        SELECT COUNT(*) as total FROM publish_queue WHERE status = 'queued'
    """)

    recent_qc = db_query("""
        SELECT decision, COUNT(*) as count
        FROM quality_checks
        WHERE checked_at > NOW() - INTERVAL '7 days'
        GROUP BY decision
    """)

    recent_runs = db_query("""
        SELECT id, stage, status, category, started_at, finished_at, error_msg
        FROM pipeline_runs
        ORDER BY started_at DESC
        LIMIT 10
    """)

    for r in recent_runs:
        if r.get("started_at"):
            r["started_at"] = r["started_at"].isoformat()
        if r.get("finished_at"):
            r["finished_at"] = r["finished_at"].isoformat()

    return {
        "runs": runs,
        "queue_count": queue[0]["total"] if queue else 0,
        "qc_summary": recent_qc,
        "recent_runs": recent_runs,
    }


def get_products(status: str = None, limit: int = 20) -> list:
    if status:
        rows = db_query(
            "SELECT * FROM product_drafts WHERE status = %s ORDER BY updated_at DESC LIMIT %s",
            (status, limit)
        )
    else:
        rows = db_query(
            "SELECT * FROM product_drafts ORDER BY updated_at DESC LIMIT %s",
            (limit,)
        )
    for r in rows:
        if r.get("created_at"):
            r["created_at"] = r["created_at"].isoformat()
        if r.get("updated_at"):
            r["updated_at"] = r["updated_at"].isoformat()
    return rows


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.get("/")
def index():
    return render_template("index.html", agents=AGENTS)


@app.get("/api/health")
def api_health():
    ollama = check_ollama()
    scraper = check_service(SCRAPER_URL)
    n8n = check_service(N8N_URL, "/healthz")

    conn = get_db()
    db_ok = conn is not None
    if conn:
        conn.close()

    return jsonify({
        "ollama": ollama,
        "scraper": scraper,
        "n8n": n8n,
        "database": {"ok": db_ok},
        "timestamp": datetime.utcnow().isoformat(),
    })


@app.get("/api/pipeline/stats")
def api_pipeline_stats():
    return jsonify(get_pipeline_stats())


@app.get("/api/pipeline/products")
def api_products():
    status = request.args.get("status")
    return jsonify(get_products(status))


@app.get("/api/agents")
def api_agents():
    ollama_data = check_ollama()
    installed = set(ollama_data.get("models", []))
    result = {}
    for key, agent in AGENTS.items():
        result[key] = {
            **agent,
            "model_installed": any(agent["model"] in m for m in installed),
        }
    return jsonify(result)


@app.post("/api/pipeline/run")
def api_run_pipeline():
    body = request.get_json(silent=True) or {}
    categories = body.get("categories", ["ebook"])
    try:
        resp = httpx.post(
            f"{N8N_URL}/webhook/pipeline/start",
            json={"categories": categories},
            timeout=10,
        )
        return jsonify({"triggered": True, "categories": categories, "n8n_status": resp.status_code})
    except Exception as e:
        return jsonify({"triggered": False, "error": str(e)}), 500


@app.post("/api/research")
def api_research():
    body = request.get_json(silent=True) or {}
    category = body.get("category", "ebook")
    try:
        resp = httpx.post(
            f"{SCRAPER_URL}/research",
            json={"category": category, "max_results": 20, "min_rating": 4.8},
            timeout=60,
        )
        return jsonify(resp.json())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── WebSocket: agent chat ───────────────────────────────────────────────────────

@socketio.on("chat")
def handle_chat(data):
    agent_key = data.get("agent", "kali")
    message = data.get("message", "").strip()
    history = data.get("history", [])

    if not message:
        return

    agent = AGENTS.get(agent_key, AGENTS["kali"])
    system_prompt = AGENT_SYSTEM_PROMPTS.get(agent_key, AGENT_SYSTEM_PROMPTS["kali"])

    messages = [{"role": "system", "content": system_prompt}]
    for h in history[-10:]:
        messages.append({"role": h["role"], "content": h["content"]})
    messages.append({"role": "user", "content": message})

    emit("chat_start", {"agent": agent_key})

    full_response = ""
    try:
        with httpx.Client(timeout=120) as client:
            with client.stream(
                "POST",
                f"{OLLAMA_URL}/api/chat",
                json={
                    "model": agent["model"],
                    "messages": messages,
                    "stream": True,
                    "options": {"temperature": 0.7, "num_ctx": 16384},
                },
            ) as resp:
                for line in resp.iter_lines():
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                        token = chunk.get("message", {}).get("content", "")
                        if token:
                            full_response += token
                            emit("chat_token", {"agent": agent_key, "token": token})
                        if chunk.get("done"):
                            break
                    except json.JSONDecodeError:
                        continue

    except Exception as e:
        emit("chat_error", {"agent": agent_key, "error": str(e)})
        return

    emit("chat_done", {"agent": agent_key, "response": full_response})


@socketio.on("connect")
def on_connect():
    emit("connected", {"message": "n8nkali dashboard connected"})
    socketio.emit("health_update", check_ollama())


# ── Background health broadcaster ─────────────────────────────────────────────

def broadcast_health():
    while True:
        try:
            health = {
                "ollama": check_ollama(),
                "scraper": check_service(SCRAPER_URL),
                "n8n": check_service(N8N_URL, "/healthz"),
            }
            socketio.emit("health_update", health)
            stats = get_pipeline_stats()
            socketio.emit("stats_update", stats)
        except Exception:
            pass
        time.sleep(15)


if __name__ == "__main__":
    t = threading.Thread(target=broadcast_health, daemon=True)
    t.start()
    port = int(os.environ.get("DASHBOARD_PORT", 8080))
    log.info(f"Dashboard starting on http://0.0.0.0:{port}")
    socketio.run(app, host="0.0.0.0", port=port, debug=False)
