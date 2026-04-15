CREATE TABLE IF NOT EXISTS platform_likes (
    like_id INTEGER PRIMARY KEY,
    post_id INTEGER NOT NULL,
    agent_id INTEGER NOT NULL,
    round_index INTEGER NOT NULL
);
