CREATE TABLE IF NOT EXISTS agent_graph_edges (
    row_id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_agent_id INTEGER NOT NULL,
    target_agent_id INTEGER NOT NULL
);
