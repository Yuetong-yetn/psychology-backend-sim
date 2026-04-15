CREATE TABLE IF NOT EXISTS input_meta (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    description TEXT NOT NULL,
    num_agents INTEGER NOT NULL,
    rounds INTEGER NOT NULL,
    seed_posts INTEGER NOT NULL,
    seed INTEGER NOT NULL,
    debug_run_config_json TEXT
);
