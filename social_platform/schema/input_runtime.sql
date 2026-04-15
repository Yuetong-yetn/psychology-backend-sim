CREATE TABLE IF NOT EXISTS input_runtime (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    mode TEXT NOT NULL,
    llm_provider TEXT NOT NULL,
    enable_fallback INTEGER NOT NULL,
    feed_limit INTEGER NOT NULL,
    appraisal_llm_ratio REAL NOT NULL
);
