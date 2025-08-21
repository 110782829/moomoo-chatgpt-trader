
-- src/db/migrations/20250820_autopilot.sql
-- Autopilot tables (v1 scaffolding)
CREATE TABLE IF NOT EXISTS planner_context (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    context_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS planner_output (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    output_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    sym TEXT,
    action TEXT,
    side TEXT,
    size_type TEXT,
    size_value REAL,
    entry TEXT,
    limit_price REAL,
    stop_json TEXT,
    take_profit_json TEXT,
    tif TEXT,
    confidence REAL,
    expires_sec INTEGER,
    rationale TEXT
);

CREATE TABLE IF NOT EXISTS guardrail_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    reason TEXT,
    detail TEXT
);

CREATE TABLE IF NOT EXISTS autopilot_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    key TEXT,
    value REAL
);
