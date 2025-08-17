# Moomoo ChatGPT Trader

ChatGPT-powered trading assistant for U.S. stocks. FastAPI backend and desktop UI now rendered with a small React app (targeting a future Tauri build).

## Features

- Connect to the moomoo API via a local OpenD gateway.
- Execute a configurable trading strategy (starting with simple moving-average crossovers).
- Expose a desktop UI for adjusting strategy parameters (e.g., moving-average windows, position sizing, stop-loss).
- Provide natural-language commands to adjust settings (e.g., "only trade between 9:30 and noon", "tighten stop to 2%").
- Later, allow the bot to learn and mimic a user's trading style from past trade history (stored locally).

## Setup
Clone repository and install dependencies.

```bash
git clone https://github.com/110782829/moomoo-chatgpt-trader.git
cd moomoo-chatgpt-trader
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Start OpenD gateway, then launch desktop app.

```bash
python desktop-ui/main.py
```

## Layout
- `src/` backend modules
- `desktop-ui/` PyWebview wrapper and React HTML page
- `requirements.txt` dependencies

4. Start the desktop app (launches the API and UI):

   ```bash
   python desktop-ui/main.py
   ```

## Roadmap
- Autopilot mode driven by ChatGPT (skeleton in place)
- Natural language commands for settings (basic mapping)
- Backtesting tab for strategy validation
