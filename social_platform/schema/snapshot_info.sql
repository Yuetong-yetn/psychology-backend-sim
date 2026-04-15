CREATE TABLE IF NOT EXISTS snapshot_info (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    round_index INTEGER NOT NULL,
    scenario_prompt TEXT NOT NULL,
    export_path TEXT,
    raw_json TEXT NOT NULL
);
