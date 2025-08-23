-- Orders & fills for SIM broker (ExecutionService)
CREATE TABLE IF NOT EXISTS orders (
  order_id TEXT PRIMARY KEY,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  status TEXT NOT NULL,
  account_id TEXT NOT NULL,
  symbol TEXT NOT NULL,
  side TEXT NOT NULL,
  order_type TEXT NOT NULL,
  limit_price REAL,
  tif TEXT NOT NULL,
  requested_qty INTEGER NOT NULL,
  filled_qty INTEGER NOT NULL,
  avg_fill_price REAL,
  decision_id INTEGER,
  reject_reason TEXT
);

CREATE INDEX IF NOT EXISTS idx_orders_symbol ON orders(symbol);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_created ON orders(created_at DESC);

CREATE TABLE IF NOT EXISTS fills (
  fill_id TEXT PRIMARY KEY,
  order_id TEXT NOT NULL,
  ts TEXT NOT NULL,
  symbol TEXT NOT NULL,
  qty INTEGER NOT NULL,
  price REAL NOT NULL,
  FOREIGN KEY(order_id) REFERENCES orders(order_id)
);

CREATE INDEX IF NOT EXISTS idx_fills_order ON fills(order_id);
CREATE INDEX IF NOT EXISTS idx_fills_ts ON fills(ts DESC);
