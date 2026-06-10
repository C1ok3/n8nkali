-- Run schema first, then this seed file
\i /docker-entrypoint-initdb.d/schema.sql

-- Seed: initial pipeline run marker
INSERT INTO pipeline_runs (stage, status, category, metadata)
VALUES ('init', 'complete', 'system', '{"note": "Database initialized"}');
