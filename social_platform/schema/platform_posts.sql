CREATE TABLE IF NOT EXISTS platform_posts (
    post_id INTEGER PRIMARY KEY,
    author_id INTEGER NOT NULL,
    content TEXT NOT NULL,
    emotion TEXT NOT NULL,
    dominant_emotion TEXT NOT NULL,
    intensity REAL NOT NULL,
    sentiment REAL NOT NULL,
    emotion_probs_json TEXT NOT NULL,
    pad_json TEXT NOT NULL,
    emotion_latent_json TEXT NOT NULL,
    like_count INTEGER NOT NULL,
    share_count INTEGER NOT NULL,
    shared_post_id INTEGER,
    round_index INTEGER NOT NULL
);
