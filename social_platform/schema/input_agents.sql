CREATE TABLE IF NOT EXISTS input_agents (
    agent_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    role TEXT NOT NULL,
    ideology TEXT NOT NULL,
    communication_style TEXT NOT NULL,
    emotion REAL NOT NULL,
    stress REAL NOT NULL,
    expectation REAL NOT NULL,
    satisfaction REAL NOT NULL,
    dopamine_level REAL NOT NULL,
    influence_score REAL NOT NULL,
    schema_flexibility REAL NOT NULL,
    empathy_level REAL NOT NULL,
    schemas_json TEXT NOT NULL
);
