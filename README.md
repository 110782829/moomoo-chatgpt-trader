# moomoo-chatgpt-trader

This project aims to build a ChatGPT-powered automated stock trading bot for U.S. stocks using the moomoo (Futu) OpenAPI. The bot will:

- Connect to the moomoo API via a local OpenD gateway.
- Execute a configurable trading strategy (starting with simple moving-average crossovers).
- Expose a desktop UI for adjusting strategy parameters (e.g., moving-average windows, position sizing, stop-loss).
- Provide natural-language commands to adjust settings (e.g., "only trade between 9:30 and noon", "tighten stop to 2%").
- Later, allow the bot to learn and mimic a user's trading style from past trade history (stored locally).

This repository will evolve over time. For the initial version, we plan to:

- Set up the project skeleton with `src/` modules for core functionality, strategies, natural-language parser, UI, and backtesting.
- Implement a basic client for the moomoo OpenAPI that can authenticate, subscribe to market data, and place paper trades.
- Add a `.env.example` file describing environment variables (OpenD host/port, etc.).
- Provide a PyWebview-based UI skeleton for controlling strategy parameters and viewing open positions and logs.
- Add instructions on installing dependencies and running the application in paper-trading mode.

## Prerequisites

- Python 3.9+.
- A moomoo (Futu) account with OpenAPI enabled and the **OpenD** gateway running locally.
- Git for version control.
- A virtual environment (recommended) for Python dependencies.

## Setup

1. Clone this repository and install dependencies:

   ```bash
   git clone https://github.com/yourusername/moomoo-chatgpt-trader.git
   cd moomoo-chatgpt-trader
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

2. Copy `.env.example` to `.env` and fill in your OpenD connection details:

   ```
   MOOMOO_HOST=127.0.0.1
   MOOMOO_PORT=11111
   MOOMOO_CLIENT_ID=1
   ```

3. Start the OpenD gateway provided by moomoo.

4. Start the desktop app (launches the API and UI):

   ```bash
   python desktop-ui/main.py
   ```

## Contributing

We plan to use a branch-based workflow (`main`, `dev`, and feature branches). Feel free to open issues for bugs or feature suggestions.
