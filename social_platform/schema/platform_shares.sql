CREATE TABLE IF NOT EXISTS platform_shares (
    share_id INTEGER PRIMARY KEY,
    post_id INTEGER NOT NULL,
    agent_id INTEGER NOT NULL,
    round_index INTEGER NOT NULL
);
