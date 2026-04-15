CREATE TABLE IF NOT EXISTS input_scenario (
    scenario_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    environment_context_json TEXT NOT NULL
);
