CREATE TABLE IF NOT EXISTS platform_snapshot (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    current_round INTEGER NOT NULL,
    scenario_prompt TEXT NOT NULL,
    agent_count INTEGER NOT NULL,
    agents_json TEXT NOT NULL,
    trace_size INTEGER NOT NULL,
    runtime_profile_json TEXT NOT NULL
);
