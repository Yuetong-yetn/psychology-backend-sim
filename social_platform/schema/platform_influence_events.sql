CREATE TABLE IF NOT EXISTS platform_influence_events (
    row_id INTEGER PRIMARY KEY AUTOINCREMENT,
    round_index INTEGER NOT NULL,
    source_agent_id INTEGER NOT NULL,
    target_agent_id INTEGER NOT NULL,
    delta REAL NOT NULL,
    reason TEXT NOT NULL
);
