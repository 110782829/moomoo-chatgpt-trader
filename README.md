# moomoo-chatgpt-trader

ChatGPT‑powered automated US‑stock trading using the moomoo OpenAPI (`moomoo-api`). It includes a FastAPI backend, a SIM execution engine, and a Tauri + React desktop UI for status, preferences, and logs.

Core capabilities:

- Connect to moomoo via local OpenD gateway
- Run strategies (e.g., MA crossover) and Autopilot GPT planner
- Desktop UI for controls, preferences, Autopilot, and activity logs
- Current stats card shows win rate, average R multiple, average realized move, and drawdown
- Settings tab for connection, risk, data, signals, planner, trading preferences, style preferences, watchlist, and news
- Preference card accepts natural language style instructions with bullet summary under "GPT will note:"
- Signal card adjusts weights for six built-in strategies (MACD Cross, Bollinger Breakout, Stochastic RSI Extreme, MA Trend, RSI Extreme, News)
- Watchlist card lists up to six symbols with scroll
- Activity tab shows recent market data with its provider
- Activity tab shows diff table of planner proposals versus executed orders
- Live account card with equity, cash, buying power, and leverage
- Local SQLite persistence for orders, fills, and bot action logs
- Tracks last action and realized R per symbol for planner memory
- Uses Yahoo Finance for recent bars when broker quotes are unavailable
- Tracks analyst EPS and revenue revisions over 7/30/90 days; fundamentals include `eps_rev_pct_*` and `rev_est_rev_pct_*`
- Computes EV/EBITDA, P/S, and ROIC fundamentals when data is available
- Calculates delta-based 25D risk reversals with multi-expiry IV term structure
- Logs liquidity gate reasons for dropped symbols
- Flags high portfolio correlation using MV- and risk-weighted returns over 20/60/120 days
- Detects highest-volume option open-interest changes or large trades per symbol with `unusual_flow` strength
- Stores IV history per tenor with metadata and short-window smoothing
- Maintains sliding-window NBBO medians from quote push with broker risk flags
- Market breadth uses NYSE advance/decline series beyond the watchlist
- Macro surprises such as the Citi Economic Surprise Index feed planner input
- Weekly report lists per-symbol decision reasons
- Planner notes clarify why no trades; shown in the UI when all decisions are gated
- Quote subscriptions retry with backoff and log failures
- Sync recent fills via `POST /sync/deals`; it uses the execution service when available or falls back to direct storage
- `GET /exec/orders` accepts multiple `status` filters
- Trading API wrapper in `core.moomoo_client.MoomooClient`

## Prerequisites

- Python 3.9+
- A moomoo account with OpenAPI enabled and the OpenD gateway running locally
- OpenD required; the moomoo API communicates through this gateway
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
   # Optional for GPT planner and preference summarizer
   # If omitted, uses a basic local summary
   OPENAI_API_KEY=sk-...
   ```

- `/connect` reads host, port, and client ID from the request body first, then environment variables (`MOOMOO_HOST`, `MOOMOO_PORT`, `MOOMOO_CLIENT_ID`). Defaults to `127.0.0.1`, `11111`, and `1`.

3) Start OpenD (moomoo) with WebSocket enabled and confirm the gateway responds at the configured host and port. WebSocket uses port `33333` by default.

   For a non-local listening address:
   - Enable SSL and use a certificate key without password.
   - Provide a 32-character MD5 hash as the auth key.
   - The trading interface enforces this requirement; the quote interface does not.
   - OpenD reads `OpenD.xml` in its run directory. On macOS, run `fixrun.sh` or start with `-cfg_file <path>` when the path is randomized.
   - Keep log level at `info` during development.

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

## Unlock trading

1. Start OpenD and sign in.
2. Confirm a simulated account under the avatar menu; create one in the moomoo app if the list is empty.
3. Set a trade password in the moomoo app.
4. If a real trading account exists, send `POST /trade/unlock` with `{ "passcode": "<trade password>" }`.
   Simulation accounts unlock automatically.
5. Successful calls return `unlock_trade ok`; errors bubble up from OpenD.

Call `GET /accounts` to list account IDs with env and account type. `POST /accounts/select` needs only the account ID; env is derived from that list.
Use `GET /accounts/info?account_id=<id>` to check account currency and map IDs to US (USD) or HK (HKD).

Paper trading requires `TrdEnv.SIMULATE`. Account authority details: [Authorities and Limitations](https://openapi.moomoo.com/moomoo-api-doc/en/intro/authority.html).

## Notes

- Paper trading is strongly recommended while testing. Real trading requires careful risk limits and explicit enablement.
- SIM execution uses `db/trader.db` by default (auto-created). Strategy/automation storage uses `data/trader.db`.
- To enable GPT Autopilot set `PLANNER_PROVIDER=gpt` and `OPENAI_API_KEY`.
- If the GPT call fails, planner can fall back to a stub. Set `PLANNER_FALLBACK_STUB=0` to surface the error instead.
- The planner context now surfaces `positions_exit_candidates` and a `positions_summary` section so the UI and fallback logic can
  highlight close/trim opportunities.
- When the GPT planner is unavailable, the stub evaluates those exit candidates first and can close or trim active positions
  before attempting any new opens.
- Execution mode switches to `moomoo` upon connect or session restore and reverts to `sim` on disconnect. No automatic fallback to `sim` when in `moomoo` mode.
- Account card fetches equity, cash, and buying power when a broker link is active, even without the execution container.
- Account assets query falls back to get_accinfo if accinfo_query is missing and logs errors.
- Account assets sums per-currency rows and adds unsettled cash when present.
- Broker returns best-effort figures; totals can still differ from paper-trade app.
- Market data source defaults to Yahoo Finance and can switch to Moomoo without automatic fallback.
- Yahoo Finance fetches at least five days of intraday bars to avoid empty data on market closures.
- Quote context starts on connect to enable basic quote subscriptions.
- Market orders log fills immediately using the latest quote when available.

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
6. EV/EBITDA, P/S, and ROIC come from yfinance fundamentals; missing data leaves ratios blank.
