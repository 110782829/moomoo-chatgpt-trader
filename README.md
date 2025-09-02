# moomoo-chatgpt-trader

ChatGPT‑powered automated US‑stock trading using the moomoo OpenAPI (`moomoo-api`). It includes a FastAPI backend, a SIM execution engine, and a Tauri + React desktop UI for status, preferences, and logs.

Core capabilities:

- Connect to moomoo via local OpenD gateway
- Run strategies (e.g., MA crossover) and Autopilot GPT planner
- Desktop UI for controls, preferences, Autopilot, and activity logs
- Settings tab for connection, risk, data, signals, planner, trading preferences, style preferences, watchlist, and news
- Signal card adjusts weights for six built-in strategies
- Watchlist card lists up to six symbols with scroll
- Activity tab shows recent market data with its provider
- Live account card with equity, cash, buying power, and leverage
- Local SQLite persistence for orders, fills, and bot action logs
- Uses Yahoo Finance for recent bars when broker quotes are unavailable
- Sync recent fills via `POST /exec/sync/deals`
- Trading API wrapper in `core.moomoo_client.MoomooClient`

## Prerequisites

- Python 3.9+
- A moomoo account with OpenAPI enabled and the OpenD gateway running locally
- Node.js 18+ (for the desktop app)

## Setup

1) Clone and install Python deps

   ```bash
   git clone --branch main --single-branch https://github.com/110782829/moomoo-chatgpt-trader.git
   cd moomoo-chatgpt-trader

   # create & activate a virtual env (macOS/Linux)
   python3 -m venv .venv
   source .venv/bin/activate

   # on Windows (PowerShell):
   # py -3 -m venv .venv
   # .\.venv\Scripts\Activate.ps1

   python -m pip install --upgrade pip
   pip install -r requirements.txt
   ```

2) Copy `.env.example` to `.env` and fill in OpenD details:

   ```
   MOOMOO_HOST=127.0.0.1
   MOOMOO_PORT=11111
   MOOMOO_CLIENT_ID=1
   # Optional for GPT planner
   OPENAI_API_KEY=sk-...
   ```

- `/connect` reads host and port from the request body first, then `MOOMOO_HOST` and `MOOMOO_PORT`, defaulting to `127.0.0.1` and `11111`.

3) Start OpenD (moomoo) and ensure it’s reachable at the host/port you configured.

4) Run the backend server

   ```bash
   uvicorn --app-dir src server:app --reload --port 8000
   ```
   The server restores the last saved session on start.

5) Run the desktop UI (Tauri + React)

   In a separate terminal:

   ```bash
   cd desktop/app
   npm install
   npm run dev
   ```

   The UI uses `VITE_API_BASE` (defaults to `http://127.0.0.1:8000`).
   It detects an active session automatically.
## Notes

- Paper trading is strongly recommended while testing. Real trading requires careful risk limits and explicit enablement.
- SIM execution uses `db/trader.db` by default (auto-created). Strategy/automation storage uses `data/trader.db`.
- To enable GPT Autopilot set `PLANNER_PROVIDER=gpt` and `OPENAI_API_KEY`.
- If the GPT call fails, planner can fall back to a stub. Set `PLANNER_FALLBACK_STUB=0` to surface the error instead.
- Execution mode switches to `moomoo` upon connect or session restore and reverts to `sim` on disconnect.
- Account card fetches equity, cash, and buying power when a broker link is active, even without the execution container.
- Account assets query falls back to get_accinfo if accinfo_query is missing and logs errors.
- Account assets sums per-currency rows and adds unsettled cash when present.
- Broker returns best-effort figures; totals can still differ from paper-trade app.
- Market data source is selectable (Moomoo or Yahoo Finance) with no automatic fallback.
- Yahoo Finance fetches at least five days of intraday bars to avoid empty data on market closures.

## Troubleshooting market data

If you see `bars_unavailable: yfinance fetch failed`:

1. Ensure `yfinance` is installed:
   ```bash
   pip install yfinance
   ```
2. Verify internet access and that the symbol exists on Yahoo Finance.
3. Check `AUTOPILOT_DATA_SOURCE` in your environment; set it to `yfinance` or `futu` as needed.
4. Use the `/debug/bars` endpoint to test fetching bars:
   `GET /debug/bars?symbol=US.AAPL&ktype=K_1M&n=3`
5. If "The truth value of a Series is ambiguous" appears, upgrade to a recent build.
