import logging
import os
import uuid
from datetime import datetime

from flask import Flask, jsonify, request

from fiverr_scraper import CATEGORY_QUERIES, scrape_category
from brand_assets import download_assets, list_assets

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)


@app.get("/health")
def health():
    return jsonify({"status": "ok", "timestamp": datetime.utcnow().isoformat()})


@app.get("/categories")
def categories():
    return jsonify({"categories": list(CATEGORY_QUERIES.keys())})


@app.post("/research")
def research():
    """
    Body: { "category": "ebook", "max_results": 20, "min_rating": 4.8, "min_reviews": 50 }
    Returns: { "run_id": "...", "category": "...", "results": [...], "count": N }
    """
    body = request.get_json(silent=True) or {}
    category = body.get("category", "ebook")
    max_results = int(body.get("max_results", 20))
    min_rating = float(body.get("min_rating", 4.8))
    min_reviews = int(body.get("min_reviews", 50))

    if category not in CATEGORY_QUERIES and not category.replace("_", " ").replace("-", " ").isalpha():
        return jsonify({"error": "Invalid category"}), 400

    run_id = str(uuid.uuid4())
    logger.info(f"Research run {run_id}: category={category} max={max_results}")

    results = scrape_category(
        category=category,
        max_results=max_results,
        min_rating=min_rating,
        min_reviews=min_reviews,
    )

    return jsonify({
        "run_id": run_id,
        "category": category,
        "scraped_at": datetime.utcnow().isoformat(),
        "count": len(results),
        "results": results,
    })


@app.post("/brand-assets")
def brand_assets():
    """
    Body: { "urls": ["https://..."], "subfolder": "brands/seller_name" }
    Returns: { "downloaded": N, "failed": N, "assets": [...] }
    """
    body = request.get_json(silent=True) or {}
    urls = body.get("urls", [])
    subfolder = body.get("subfolder", "brands")

    if not isinstance(urls, list):
        return jsonify({"error": "urls must be a list"}), 400

    # Only allow http/https URLs
    safe_urls = [u for u in urls if isinstance(u, str) and u.startswith(("http://", "https://"))]
    blocked = len(urls) - len(safe_urls)

    results = download_assets(safe_urls, subfolder=subfolder)

    downloaded = sum(1 for r in results if r["success"])
    failed = sum(1 for r in results if not r["success"])

    return jsonify({
        "downloaded": downloaded,
        "failed": failed,
        "blocked_unsafe": blocked,
        "assets": results,
    })


@app.get("/assets")
def assets():
    """List all downloaded assets. Query: ?subfolder=brands/seller"""
    subfolder = request.args.get("subfolder", "")
    return jsonify({"assets": list_assets(subfolder)})


if __name__ == "__main__":
    port = int(os.environ.get("SCRAPER_PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
