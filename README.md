# moomoo-chatgpt-trader

This project aims to build a ChatGPT-powered automated stock trading bot for U.S. stocks using the moomoo (Futu) OpenAPI. The bot will:

- Connect to the moomoo API via a local OpenD gateway.
- Execute a configurable trading strategy (starting with simple moving-average crossovers).
- Expose a web-based UI for adjusting strategy parameters (e.g., moving-average windows, position sizing, stop-loss).
- Provide natural-language commands to adjust settings (e.g., "only trade between 9:30 and noon", "tighten stop to 2%").
- Later, allow the bot to learn and mimic a user's trading style from past trade history (stored locally).

This repository will evolve over time. For the initial version, we plan to:

- Set up the project skeleton with `src/` modules for core functionality, strategies, natural-language parser, UI, and backtesting.
- Implement a basic client for the moomoo OpenAPI that can authenticate, subscribe to market data, and place paper trades.
- Add a `.env.example` file describing environment variables (OpenD host/port, etc.).
- Provide a Streamlit-based UI skeleton for controlling strategy parameters and viewing open positions and logs.
- Add instructions on installing dependencies and running the application in paper-trading mode.

## Prerequisites

- Python 3.9+.
- A moomoo (Futu) account with OpenAPI enabled and the **OpenD** gateway running locally.
- Git for version control.
- A virtual environment (recommended) for Python dependencies.

## Setup

1. Clone this repository and install dependencies:

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

2. Copy `.env.example` to `.env` and fill in your OpenD connection details:

   ```
   MOOMOO_HOST=127.0.0.1
   MOOMOO_PORT=11111
   MOOMOO_CLIENT_ID=1

   # Optional (used by the Streamlit diagnostics UI)
   API_BASE_URL=http://127.0.0.1:8000

   # Optional feature flags for Streamlit diagnostics
   UI_SHOW_DIAGNOSTICS=true
   UI_ALLOW_MANUAL_ORDERS=false
   UI_SHOW_CHARTS=false
   ```

3. Start the OpenD gateway provided by moomoo.
   Launch the moomoo OpenD process on your machine and ensure it’s reachable at the host/port you configured.

4. Run the development server:

   ```bash
   uvicorn --app-dir src server:app --reload --port 8000
   ```

5. Open the Streamlit UI in your browser (the server will output a local URL).

'''bash
(Optional) Launch the Streamlit diagnostics UI

Helpful during development for inspecting positions/orders, tweaking risk, and checking PnL.

streamlit run src/ui/app_streamlit.py
'''
## Notes

The Streamlit app is intended as a developer diagnostics console. The long-term plan is a desktop app (e.g., Tauri + React) focused on bot configuration, autonomy, and action logs.

Paper trading is strongly recommended while testing. Real trading requires careful configuration of risk limits and explicit enablement.