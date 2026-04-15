CREATE TABLE IF NOT EXISTS platform_traces (
    trace_index INTEGER PRIMARY KEY,
    type TEXT NOT NULL,
    round_index INTEGER,
    raw_json TEXT NOT NULL
);
