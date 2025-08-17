# Moomoo ChatGPT Trader

ChatGPT-powered trading assistant for U.S. stocks. FastAPI backend and a React desktop UI target a future Tauri build.

## Features

- Connect to the moomoo API via a local OpenD gateway.
- Execute a configurable trading strategy (starting with simple moving-average crossovers).
- Desktop React UI with autopilot controls, tick counter, backtesting tab, and settings placeholder.
- Natural-language commands to start or stop autopilot, set strategy, or trigger ticks.
- Planned learning mode that mirrors trader style from past history.

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

## Roadmap
- Autopilot mode driven by ChatGPT
- Rich natural language controls
- Expanded backtesting and analysis tools
