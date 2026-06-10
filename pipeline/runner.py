#!/usr/bin/env python3
"""
n8nkali pipeline runner — calls Ollama directly for each stage.
Usage:
  python runner.py --category ebook
  python runner.py --category all
  python runner.py --status
"""

import argparse
import json
import logging
import os
import sys
import uuid
from datetime import datetime

import httpx
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

from agents import AGENTS

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("pipeline")

OLLAMA_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
SCRAPER_URL = os.environ.get("SCRAPER_SERVICE_URL", "http://localhost:5000")

DB_CONFIG = {
    "host":     os.environ.get("POSTGRES_HOST", "localhost"),
    "port":     int(os.environ.get("POSTGRES_PORT", 5432)),
    "dbname":   os.environ.get("POSTGRES_DB", "n8nkali"),
    "user":     os.environ.get("POSTGRES_USER", "n8nkali"),
    "password": os.environ.get("POSTGRES_PASSWORD", "changeme"),
}

CATEGORIES = ["ebook", "workbook", "thumbnail", "logo", "coaching"]


# ── Database helpers ───────────────────────────────────────────────────────────

def get_db():
    return psycopg2.connect(**DB_CONFIG, cursor_factory=psycopg2.extras.RealDictCursor)


def log_run(conn, run_id: str, stage: str, status: str, category: str, error: str = None):
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO pipeline_runs (id, stage, status, category, metadata)
               VALUES (%s, %s, %s, %s, %s)
               ON CONFLICT (id) DO UPDATE SET status = EXCLUDED.status,
               finished_at = CASE WHEN EXCLUDED.status != 'running' THEN NOW() ELSE NULL END,
               error_msg = EXCLUDED.error_msg""",
            (run_id, stage, status, category, json.dumps({"error": error}) if error else "{}"),
        )
    conn.commit()


def save_research(conn, run_id: str, category: str, items: list) -> list[str]:
    ids = []
    with conn.cursor() as cur:
        for item in items:
            cur.execute(
                """INSERT INTO research_items
                   (run_id, category, title, seller, seller_tier, rating, review_count,
                    price_usd, delivery_days, tags, thumbnail_url, gig_url,
                    praise_themes, complaint_themes, gap_opportunity)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   RETURNING id""",
                (
                    run_id, category,
                    item.get("title", ""),
                    item.get("seller", ""),
                    item.get("seller_tier", ""),
                    item.get("rating", 0),
                    item.get("review_count", 0),
                    item.get("price_usd", 0),
                    item.get("delivery_days", 0),
                    item.get("tags", []),
                    item.get("thumbnail_url", ""),
                    item.get("gig_url", ""),
                    item.get("praise_themes", []),
                    item.get("complaint_themes", []),
                    item.get("gap_opportunity", ""),
                ),
            )
            ids.append(str(cur.fetchone()["id"]))
    conn.commit()
    return ids


def save_draft(conn, run_id: str, research_id: str, product_type: str, content: dict) -> str:
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO product_drafts
               (run_id, research_item_id, product_type, status, title, description, content)
               VALUES (%s, %s, %s, 'draft', %s, %s, %s)
               RETURNING id""",
            (
                run_id, research_id, product_type,
                content.get("title", content.get("polished_title", "")),
                content.get("description", content.get("polished_description", "")),
                json.dumps(content),
            ),
        )
        draft_id = str(cur.fetchone()["id"])
    conn.commit()
    return draft_id


def update_draft_status(conn, draft_id: str, status: str):
    with conn.cursor() as cur:
        cur.execute("UPDATE product_drafts SET status=%s WHERE id=%s", (status, draft_id))
    conn.commit()


def save_qc(conn, draft_id: str, result: dict, revision_cycle: int):
    with conn.cursor() as cur:
        b = result.get("breakdown", {})
        cur.execute(
            """INSERT INTO quality_checks
               (draft_id, decision, score, completeness, differentiation,
                seo_score, content_quality, visual_readiness, feedback, revision_cycle)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (
                draft_id,
                result.get("decision", "REJECT"),
                result.get("score", 0),
                b.get("completeness", 0),
                b.get("differentiation", 0),
                b.get("seo", 0),
                b.get("content_quality", 0),
                b.get("visual_readiness", 0),
                result.get("feedback", ""),
                revision_cycle,
            ),
        )
    conn.commit()


def add_to_publish_queue(conn, draft_id: str):
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO publish_queue (draft_id, platform, status) VALUES (%s, 'fiverr', 'queued')",
            (draft_id,),
        )
    conn.commit()


# ── Ollama helpers ─────────────────────────────────────────────────────────────

def call_ollama(agent_key: str, user_content: str, timeout: int = 300) -> dict:
    agent = AGENTS[agent_key]
    log.info(f"  [{agent['name']}] Calling {agent['model']}...")

    payload = {
        "model": agent["model"],
        "messages": [
            {"role": "system", "content": agent["system"]},
            {"role": "user",   "content": user_content},
        ],
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.7, "num_ctx": 16384},
    }

    try:
        resp = httpx.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=timeout)
        resp.raise_for_status()
        raw = resp.json()["message"]["content"]
        return json.loads(raw)
    except json.JSONDecodeError:
        # Model returned non-JSON — try to extract JSON from the response
        import re
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            return json.loads(match.group())
        raise ValueError(f"[{agent['name']}] Could not parse JSON from response: {raw[:200]}")
    except Exception as e:
        raise RuntimeError(f"[{agent['name']}] Ollama call failed: {e}")


# ── Scraper helper ─────────────────────────────────────────────────────────────

def run_research_scrape(category: str) -> list:
    log.info(f"  [Scraper] Fetching Fiverr data for: {category}")
    try:
        resp = httpx.post(
            f"{SCRAPER_URL}/research",
            json={"category": category, "max_results": 20, "min_rating": 4.8, "min_reviews": 50},
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json().get("results", [])
    except Exception as e:
        raise RuntimeError(f"[Scraper] Failed: {e}")


# ── Pipeline stages ────────────────────────────────────────────────────────────

def run_pipeline(category: str, conn):
    run_id = str(uuid.uuid4())
    log.info(f"\n{'='*60}")
    log.info(f"PIPELINE START  category={category}  run_id={run_id[:8]}")
    log.info(f"{'='*60}")

    # ── Stage 1: Research ──────────────────────────────────────────────────────
    log.info("\n[Stage 1] RESEARCH")
    log_run(conn, run_id, "research", "running", category)
    try:
        raw_items = run_research_scrape(category)
        research_ids = save_research(conn, run_id, category, raw_items)
        log.info(f"  Scraped {len(raw_items)} products, stored {len(research_ids)} items")

        # Scout analyses the top 5 results
        top5 = raw_items[:5]
        scout_input = (
            f"Category: {category}\n\n"
            f"Top Fiverr products found:\n{json.dumps(top5, indent=2)}\n\n"
            f"Identify the best opportunity for a superior competing product."
        )
        research_analysis = call_ollama("scout", scout_input)
        log.info(f"  Scout recommendation: {research_analysis.get('recommended_title', '?')}")
        log_run(conn, run_id, "research", "complete", category)

    except Exception as e:
        log.error(f"  Research stage failed: {e}")
        log_run(conn, run_id, "research", "failed", category, str(e))
        return

    # Use first research_id for draft linking
    research_id = research_ids[0] if research_ids else None

    # ── Stage 2: Create ────────────────────────────────────────────────────────
    log.info("\n[Stage 2] CREATE")
    log_run(conn, run_id, "create", "running", category)
    try:
        forge_input = (
            f"Market research analysis:\n{json.dumps(research_analysis, indent=2)}\n\n"
            f"Product category: {category}\n"
            f"Create a complete, superior product brief that beats the competition."
        )
        product_brief = call_ollama("forge", forge_input, timeout=360)
        product_type = product_brief.get("product_type", category)
        draft_id = save_draft(conn, run_id, research_id, product_type, product_brief)
        log.info(f"  Created draft {draft_id[:8]} — type: {product_type}")
        log_run(conn, run_id, "create", "complete", category)

    except Exception as e:
        log.error(f"  Create stage failed: {e}")
        log_run(conn, run_id, "create", "failed", category, str(e))
        return

    # ── Stage 3: Edit (with revision loop) ────────────────────────────────────
    MAX_REVISIONS = 2
    revision = 0

    while revision <= MAX_REVISIONS:
        # ── Edit ──────────────────────────────────────────────────────────────
        log.info(f"\n[Stage 3] EDIT  (revision={revision})")
        log_run(conn, run_id, "edit", "running", category)
        try:
            pixel_input = (
                f"Product brief to polish:\n{json.dumps(product_brief, indent=2)}\n\n"
                f"Polish this to production quality. Write a detailed image prompt."
            )
            edited = call_ollama("pixel", pixel_input, timeout=300)
            update_draft_status(conn, draft_id, "edited")
            save_draft(conn, run_id, research_id, product_type, edited)
            log.info(f"  Pixel polished the draft")
            log_run(conn, run_id, "edit", "complete", category)

        except Exception as e:
            log.error(f"  Edit stage failed: {e}")
            log_run(conn, run_id, "edit", "failed", category, str(e))
            return

        # ── QC ─────────────────────────────────────────────────────────────────
        log.info(f"\n[Stage 4] QUALITY CHECK  (revision={revision})")
        log_run(conn, run_id, "qc", "running", category)
        try:
            apex_input = (
                f"Research context:\n{json.dumps(research_analysis, indent=2)}\n\n"
                f"Product to evaluate:\n{json.dumps(edited, indent=2)}\n\n"
                f"Score this product and make your routing decision."
            )
            qc_result = call_ollama("apex", apex_input, timeout=360)
            save_qc(conn, draft_id, qc_result, revision)
            decision = qc_result.get("decision", "REJECT")
            score = qc_result.get("score", 0)
            log.info(f"  Apex decision: {decision}  score={score}/100")
            log.info(f"  Feedback: {qc_result.get('feedback', '')[:120]}")
            log_run(conn, run_id, "qc", "complete", category)

        except Exception as e:
            log.error(f"  QC stage failed: {e}")
            log_run(conn, run_id, "qc", "failed", category, str(e))
            return

        if decision == "PASS":
            update_draft_status(conn, draft_id, "ready")
            add_to_publish_queue(conn, draft_id)
            log.info(f"\n✓ PASSED — added to publish queue (draft {draft_id[:8]})")
            break

        elif decision == "NEEDS_REVISION" and revision < MAX_REVISIONS:
            revision += 1
            log.info(f"\n↺ NEEDS_REVISION — sending back to creator (cycle {revision}/{MAX_REVISIONS})")
            # Feed QC feedback back into creator for next cycle
            product_brief["qc_feedback"] = qc_result.get("feedback", "")
            edited["qc_feedback"] = qc_result.get("feedback", "")

        else:
            update_draft_status(conn, draft_id, "rejected")
            log.info(f"\n✗ REJECTED — archived (draft {draft_id[:8]})")
            break

    log.info(f"\n{'='*60}")
    log.info(f"PIPELINE DONE  category={category}  run_id={run_id[:8]}")
    log.info(f"{'='*60}\n")


# ── Status command ─────────────────────────────────────────────────────────────

def show_status(conn):
    with conn.cursor() as cur:
        cur.execute("""
            SELECT stage, status, COUNT(*) as n
            FROM pipeline_runs
            WHERE started_at > NOW() - INTERVAL '7 days'
            GROUP BY stage, status ORDER BY stage, status
        """)
        runs = cur.fetchall()

        cur.execute("SELECT COUNT(*) as n FROM publish_queue WHERE status='queued'")
        queue = cur.fetchone()["n"]

        cur.execute("""
            SELECT decision, COUNT(*) as n FROM quality_checks
            WHERE checked_at > NOW() - INTERVAL '7 days'
            GROUP BY decision
        """)
        qc = cur.fetchall()

    print("\n=== Pipeline Status (last 7 days) ===")
    for r in runs:
        print(f"  {r['stage']:12} {r['status']:10} × {r['n']}")
    print(f"\n  Publish queue: {queue} products ready")
    print("\n  QC results:")
    for r in qc:
        print(f"    {r['decision']:20} × {r['n']}")
    print()


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="n8nkali pipeline runner")
    parser.add_argument("--category", default="ebook",
                        help=f"Category to run ({', '.join(CATEGORIES)}) or 'all'")
    parser.add_argument("--status", action="store_true", help="Show pipeline status")
    args = parser.parse_args()

    try:
        conn = get_db()
    except Exception as e:
        log.error(f"Database connection failed: {e}")
        log.error("Is PostgreSQL running? Try: docker compose up -d postgres")
        sys.exit(1)

    if args.status:
        show_status(conn)
        conn.close()
        return

    categories = CATEGORIES if args.category == "all" else [args.category]
    for cat in categories:
        run_pipeline(cat, conn)

    conn.close()


if __name__ == "__main__":
    main()
