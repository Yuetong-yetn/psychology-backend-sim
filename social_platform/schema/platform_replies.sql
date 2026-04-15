CREATE TABLE IF NOT EXISTS platform_replies (
    reply_id INTEGER PRIMARY KEY,
    post_id INTEGER NOT NULL,
    author_id INTEGER NOT NULL,
    content TEXT NOT NULL,
    emotion TEXT NOT NULL,
    dominant_emotion TEXT NOT NULL,
    intensity REAL NOT NULL,
    sentiment REAL NOT NULL,
    emotion_probs_json TEXT NOT NULL,
    pad_json TEXT NOT NULL,
    emotion_latent_json TEXT NOT NULL,
    round_index INTEGER NOT NULL
);
