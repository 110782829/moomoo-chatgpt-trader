# moomoo-chatgpt-trader

ChatGPT‑powered automated US‑stock trading using the moomoo (Futu) OpenAPI. It includes a FastAPI backend, a SIM execution engine, and a Tauri + React desktop UI for status, preferences, and logs.

Core capabilities:

- Connect to moomoo via local OpenD gateway
- Run strategies (e.g., MA crossover) and Autopilot GPT planner
- Desktop UI for controls, preferences, Autopilot, and activity logs
- Local SQLite persistence for orders, fills, and bot action logs

## Prerequisites

- Python 3.9+
- A moomoo (Futu) account with OpenAPI enabled and the OpenD gateway running locally
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

3) Start OpenD (moomoo) and ensure it’s reachable at the host/port you configured.

4) Run the backend server

   ```bash
   uvicorn --app-dir src server:app --reload --port 8000
   ```

5) Run the desktop UI (Tauri + React)

   In a separate terminal:

   ```bash
   cd desktop/app
   npm install
   npm run dev
   ```

   The UI uses `VITE_API_BASE` (defaults to `http://127.0.0.1:8000`).
## Notes

- Paper trading is strongly recommended while testing. Real trading requires careful risk limits and explicit enablement.
- SIM execution uses `db/trader.db` by default (auto-created). Strategy/automation storage uses `data/trader.db`.
- To enable GPT Autopilot set `PLANNER_PROVIDER=gpt` and `OPENAI_API_KEY`.
