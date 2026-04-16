CREATE TABLE IF NOT EXISTS round_results (
    row_id INTEGER PRIMARY KEY AUTOINCREMENT,
    round_index INTEGER NOT NULL,
    agent_id INTEGER NOT NULL,
    profile_name TEXT NOT NULL,
    profile_role TEXT NOT NULL,
    profile_ideology TEXT NOT NULL,
    profile_communication_style TEXT NOT NULL,
    state_delta_json TEXT NOT NULL,
    decision_action TEXT NOT NULL,
    decision_content TEXT NOT NULL,
    decision_target_post_id INTEGER,
    decision_target_agent_id INTEGER,
    decision_metadata_json TEXT NOT NULL,
    decision_influence_delta REAL NOT NULL,
    decision_reason TEXT NOT NULL,
    decision_suggested_action TEXT NOT NULL,
    decision_suggested_actions_json TEXT NOT NULL,
    behavior_primary_action TEXT NOT NULL,
    behavior_stimulus_excerpt TEXT NOT NULL,
    behavior_public_behavior_summary TEXT NOT NULL,
    behavior_simulated_public_content TEXT,
    behavior_state_hint_json TEXT NOT NULL,
    behavior_cam_summary_json TEXT NOT NULL,
    behavior_explicit_tom_triggered INTEGER NOT NULL,
    behavior_backend_action TEXT NOT NULL,
    behavior_round_index INTEGER NOT NULL,
    UNIQUE (round_index, agent_id)
);

-- state_delta_json stores compact replay fields only. If last_appraisal is
-- present inside the JSON, it is the exported AppraisalSummary shape.
