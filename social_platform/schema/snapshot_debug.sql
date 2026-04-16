CREATE TABLE IF NOT EXISTS snapshot_debug (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    exposed_frontend_params_json TEXT NOT NULL,
    provider_behavior_json TEXT NOT NULL,
    simulation_config_json TEXT NOT NULL,
    agent_runtime_summary_json TEXT NOT NULL,
    why_results_appear_without_api_key TEXT NOT NULL,
    auto_run_on_snapshot INTEGER NOT NULL,
    history_rounds INTEGER NOT NULL,
    raw_json TEXT NOT NULL
);
