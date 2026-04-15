CREATE TABLE IF NOT EXISTS agent_graph_info (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    num_nodes INTEGER NOT NULL,
    num_edges INTEGER NOT NULL
);
