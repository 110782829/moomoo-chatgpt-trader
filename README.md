# moomoo-chatgpt-trader

This project builds a ChatGPT-powered automated stock trading bot for U.S. stocks using the moomoo (Futu) OpenAPI. The bot will:

- Connect to the moomoo API via a local OpenD gateway.
- Execute a configurable trading strategy (starting with simple moving-average crossovers).
- Expose a web-based UI for adjusting strategy parameters (e.g., moving-average windows, position sizing, stop-loss).
- Provide natural-language commands to adjust settings (e.g., "only trade between 9:30 and noon", "tighten stop to 2%").
- Later, learn and mimic a trading style from past trade history.

This repository will evolve over time. Initial goals:

- Set up project modules for core functionality, strategies, natural-language parser, UI, and backtesting.
- Implement a basic client for the moomoo OpenAPI that can authenticate, subscribe to market data, and place paper trades.
- Include a `.env.example` file describing environment variables (OpenD host/port, etc.).
- Provide instructions on installing dependencies and running the application in paper-trading mode.

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

   python3 -m venv .venv
   source .venv/bin/activate    # on Windows use: .\\.venv\\Scripts\\Activate.ps1

   python -m pip install --upgrade pip
   pip install -r requirements.txt
   ```

2. Copy `.env.example` to `.env` and fill in OpenD connection details:

   ```
   MOOMOO_HOST=127.0.0.1
   MOOMOO_PORT=11111
   MOOMOO_CLIENT_ID=1
   ```

3. Start the OpenD gateway provided by moomoo. Ensure the process is reachable at the configured host/port.

4. Run the development server:

   ```bash
   uvicorn --app-dir src server:app --reload --port 8000
   ```

## Notes

Paper trading is strongly recommended while testing. Real trading requires careful configuration of risk limits and explicit enablement.

