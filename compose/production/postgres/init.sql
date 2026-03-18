CREATE EXTENSION IF NOT EXISTS vector;

-- NOTE: hnsw.iterative_scan and hnsw.ef_search are defined in
-- compose/postgres/shared.conf (single source of truth) and injected as
-- postgres -c flags by docker-entrypoint-wrapper.sh on every startup.
-- Current values: hnsw.iterative_scan=relaxed_order, hnsw.ef_search=64
-- This avoids database-level ALTER DATABASE SET which causes "invalid
-- configuration parameter name" warnings when the GUC isn't registered
-- during docker-entrypoint-initdb.d execution.
