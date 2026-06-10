-- n8nkali CRM Schema
-- Run once on fresh PostgreSQL instance

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ── Pipeline runs ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS pipeline_runs (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    stage       VARCHAR(50) NOT NULL,   -- research | create | edit | qc | publish
    status      VARCHAR(20) NOT NULL DEFAULT 'running', -- running | complete | failed
    category    VARCHAR(100),
    started_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    error_msg   TEXT,
    metadata    JSONB DEFAULT '{}'
);

CREATE INDEX idx_pipeline_runs_status   ON pipeline_runs(status);
CREATE INDEX idx_pipeline_runs_category ON pipeline_runs(category);
CREATE INDEX idx_pipeline_runs_stage    ON pipeline_runs(stage);

-- ── Research items ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS research_items (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    run_id          UUID REFERENCES pipeline_runs(id) ON DELETE CASCADE,
    category        VARCHAR(100) NOT NULL,
    title           TEXT NOT NULL,
    seller          VARCHAR(255),
    seller_tier     VARCHAR(50),
    rating          NUMERIC(3,2),
    review_count    INTEGER,
    price_usd       NUMERIC(10,2),
    delivery_days   INTEGER,
    tags            TEXT[],
    thumbnail_url   TEXT,
    gig_url         TEXT,
    praise_themes   TEXT[],
    complaint_themes TEXT[],
    gap_opportunity TEXT,
    rank_score      NUMERIC(5,2),
    scraped_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_research_items_category ON research_items(category);
CREATE INDEX idx_research_items_rating   ON research_items(rating DESC);
CREATE INDEX idx_research_items_run_id   ON research_items(run_id);

-- ── Product drafts ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS product_drafts (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    research_item_id    UUID REFERENCES research_items(id) ON DELETE SET NULL,
    run_id              UUID REFERENCES pipeline_runs(id) ON DELETE CASCADE,
    product_type        VARCHAR(50) NOT NULL, -- ebook | workbook | thumbnail | logo | service
    status              VARCHAR(30) NOT NULL DEFAULT 'draft',
                         -- draft | edited | qc_pending | ready | published | rejected
    title               TEXT,
    description         TEXT,
    content             JSONB,   -- structured product content (chapters, modules, etc.)
    revision_cycle      INTEGER DEFAULT 0,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_product_drafts_status      ON product_drafts(status);
CREATE INDEX idx_product_drafts_type        ON product_drafts(product_type);
CREATE INDEX idx_product_drafts_run_id      ON product_drafts(run_id);

-- ── Edited products ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS edited_products (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    draft_id        UUID REFERENCES product_drafts(id) ON DELETE CASCADE,
    document_path   TEXT,           -- path to formatted markdown/pdf
    image_prompt    TEXT,           -- DALL-E / SD prompt
    asset_manifest  JSONB DEFAULT '[]',  -- list of downloaded assets
    edited_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Quality checks ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS quality_checks (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    draft_id            UUID REFERENCES product_drafts(id) ON DELETE CASCADE,
    decision            VARCHAR(20) NOT NULL, -- PASS | NEEDS_REVISION | REJECT
    score               INTEGER,
    completeness        INTEGER,
    differentiation     INTEGER,
    seo_score           INTEGER,
    content_quality     INTEGER,
    visual_readiness    INTEGER,
    feedback            TEXT,
    revision_cycle      INTEGER DEFAULT 0,
    checked_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_quality_checks_decision ON quality_checks(decision);
CREATE INDEX idx_quality_checks_draft_id ON quality_checks(draft_id);

-- ── Brand assets ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS brand_assets (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    draft_id        UUID REFERENCES product_drafts(id) ON DELETE SET NULL,
    source_url      TEXT NOT NULL,
    local_path      TEXT,
    filename        TEXT,
    size_bytes      BIGINT,
    asset_type      VARCHAR(50),  -- image | pdf | zip | other
    downloaded_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_brand_assets_draft_id ON brand_assets(draft_id);

-- ── Publish queue ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS publish_queue (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    draft_id        UUID REFERENCES product_drafts(id) ON DELETE CASCADE,
    platform        VARCHAR(50) DEFAULT 'fiverr',
    status          VARCHAR(20) DEFAULT 'queued', -- queued | published | failed
    queued_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    published_at    TIMESTAMPTZ
);

CREATE INDEX idx_publish_queue_status ON publish_queue(status);

-- ── Trigger: update product_drafts.updated_at ─────────────────────────────────
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_product_drafts_updated_at
    BEFORE UPDATE ON product_drafts
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
