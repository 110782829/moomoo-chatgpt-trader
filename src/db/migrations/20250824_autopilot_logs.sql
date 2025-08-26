-- db/migration/20250824_autopilot_logs.sql
-- Adds helpful indexes for persisted Autopilot logs and SIM execution speed.

-- Action log: fast filter by mode/action + time
CREATE INDEX IF NOT EXISTS idx_action_log_mode_ts ON action_log(mode, ts);

-- Orders/fills: ensure indexes exist (no-op if already created elsewhere)
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_symbol ON orders(symbol);
CREATE INDEX IF NOT EXISTS idx_fills_symbol ON fills(symbol);
CREATE INDEX IF NOT EXISTS idx_fills_order ON fills(order_id);
