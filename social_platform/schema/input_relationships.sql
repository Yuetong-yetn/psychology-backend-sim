CREATE TABLE IF NOT EXISTS input_relationships (
    row_id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_agent_id INTEGER NOT NULL,
    target_agent_id INTEGER NOT NULL,
    type TEXT NOT NULL
);
