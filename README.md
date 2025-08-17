# Moomoo ChatGPT Trader

ChatGPT-powered trading assistant for U.S. stocks. FastAPI backend and desktop UI built with PyWebview.

## Features
- Connects to local OpenD gateway
- Risk guards for size, positions, daily loss, and market hours
- Strategy runner with moving-average crossover
- Autonomy modes: assist and semi
- Action log stored in SQLite
- Desktop dashboard showing mode, risk, strategies, and activity

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

API listens on `http://127.0.0.1:8000` and opens the dashboard window.

## Development
Run checks before committing.

```bash
python -m py_compile $(git ls-files '*.py')
pytest
```

## Layout
- `src/` backend modules
- `desktop-ui/` PyWebview wrapper and HTML page
- `requirements.txt` dependencies

## Roadmap
- Autopilot mode driven by ChatGPT
- Natural language commands for settings
- Backtesting tab for strategy validation
