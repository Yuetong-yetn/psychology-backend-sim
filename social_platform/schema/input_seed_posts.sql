CREATE TABLE IF NOT EXISTS input_seed_posts (
    row_id INTEGER PRIMARY KEY AUTOINCREMENT,
    author_id INTEGER NOT NULL,
    content TEXT NOT NULL,
    emotion TEXT NOT NULL,
    intensity REAL NOT NULL,
    sentiment REAL NOT NULL,
    round_index INTEGER NOT NULL
);
