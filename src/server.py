'''
Start command: uvicorn --app-dir src server:app --reload --port 8000
'''
from fastapi import FastAPI, HTTPException, APIRouter
from pydantic import BaseModel
from typing import List, Optional, Dict, Any 
import os
import json
from datetime import datetime
from pathlib import Path

from fastapi.middleware.cors import CORSMiddleware
import yfinance as yf

try:
    from dotenv import load_dotenv
    # Load default .env from current working directory
    load_dotenv()
    # Also try project-root .env relative to this file (src/.. /.env)
    try:
        ROOT_ENV = Path(__file__).resolve().parent.parent / ".env"
        if ROOT_ENV.exists():
            load_dotenv(dotenv_path=str(ROOT_ENV), override=False)
    except Exception:
        pass
except Exception:
    pass

try:
    from execution.container import init_execution, get_execution, set_mode
except Exception:
    init_execution = lambda *a, **k: None  # type: ignore
    def get_execution():
        return None
    def set_mode(_: str) -> None:
        pass
try:
    from routers import exec_orders as exec_orders_router
except Exception:
    exec_orders_router = None  # type: ignore


# --- Internal modules ---
from core.market_data import get_bars_safely
from core.moomoo_client import MoomooClient
from core.deals import fetch_deals
from moomoo import TrdEnv
from core.session import load_session, save_session, clear_session, reconnect_from_session
from risk.limits import enforce_order_limits

# Automation (scheduler + storage + strategy step)
try:
    from core.storage import (
        init_db,
        insert_strategy,
        set_strategy_active,
        get_strategy,
        list_strategies,
        list_runs,
        update_strategy,
        record_fill,
        pnl_today,
        pnl_history,
        insert_action_log,
        list_action_logs,
        get_setting,
        set_setting,
    )
    from core.scheduler import TraderScheduler
    from strategies.ma_crossover import step as ma_crossover_step
    _AUTOMATION_AVAILABLE = True
except Exception as _e:
    _AUTOMATION_AVAILABLE = False
    _AUTOMATION_IMPORT_ERR = _e
    TraderScheduler = None  # type: ignore[misc]

# Backtest modules
try:
    from backtest.engine import load_bars_csv, run_ma_crossover
    _BACKTEST_AVAILABLE = True
    _BACKTEST_IMPORT_ERR = None
except Exception as _be:
    _BACKTEST_AVAILABLE = False
    _BACKTEST_IMPORT_ERR = _be

try:
    from backtest.grid import run_ma_grid
    _GRID_AVAILABLE = True
    _GRID_IMPORT_ERR = None
except Exception as _ge:
    _GRID_AVAILABLE = False
    _GRID_IMPORT_ERR = _ge


# ---------- App + CORS ----------

app = FastAPI(title="Moomoo ChatGPT Trader API")
init_execution(app)  # initialize execution container (broker-backed)
if exec_orders_router is not None:
    app.include_router(exec_orders_router.router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- Globals ----------

# Global broker client instance; created on /connect
client: Optional[MoomooClient] = None

# Global scheduler (if automation imports are available)
scheduler = None  # will hold TraderScheduler


# ---------- Risk config (local file) ----------

RISK_PATH = Path(os.getenv("RISK_FILE", "data/risk.json"))
_DEFAULT_RISK = {
    "enabled": True,
    "max_usd_per_trade": 1000.0,
    "max_open_positions": 5,
    "max_daily_loss_usd": 200.0,
    "symbol_whitelist": [],  # empty → allow all
    "trading_hours_pt": {"start": "06:30", "end": "13:00"},  # US market regular hours (PT)
    "flatten_before_close_min": 5,
}

def _risk_load() -> dict:
    try:
        if RISK_PATH.exists():
            return json.loads(RISK_PATH.read_text())
    except Exception:
        pass
    RISK_PATH.parent.mkdir(parents=True, exist_ok=True)
    RISK_PATH.write_text(json.dumps(_DEFAULT_RISK, indent=2))
    return dict(_DEFAULT_RISK)

def _risk_save(cfg: dict) -> None:
    RISK_PATH.parent.mkdir(parents=True, exist_ok=True)
    RISK_PATH.write_text(json.dumps(cfg, indent=2))


# yfinance fetch helper
def fetch_yf(symbol: str):
    attempts = [
        {"period": "5d", "interval": "1m"},
        {"period": "1mo", "interval": "5m"},
        {"period": "1mo", "interval": "1d"},
    ]
    for kw in attempts:
        df = yf.download(symbol, progress=False, repair=True, **kw)
        if not df.empty:
            return df
    df = yf.Ticker(symbol).history(period="1mo", interval="1d")
    if not df.empty:
        return df
    raise HTTPException(502, f"yfinance empty for '{symbol}' (check ticker, interval, or network)")


# ---------- Request Models ----------

class ConnectRequest(BaseModel):
    host: Optional[str] = None
    port: Optional[int] = None
    client_id: Optional[int] = None

class SelectAccountRequest(BaseModel):
    account_id: str

class PlaceOrderRequest(BaseModel):
    symbol: str                 # e.g., "AAPL" or "US.AAPL"
    qty: float
    side: str                   # "BUY" or "SELL"
    order_type: str = "MARKET"  # "MARKET" or "LIMIT"
    price: Optional[float] = None

class CancelOrderRequest(BaseModel):
    order_id: str

class SubscribeQuotesRequest(BaseModel):
    symbols: list[str]

class UnlockTradeRequest(BaseModel):
    passcode: str

class FlattenRequest(BaseModel):
    symbols: Optional[List[str]] = None  # optional subset; if omitted, flatten all

class StartMACrossoverRequest(BaseModel):
    # core
    symbol: str              # e.g., "US.AAPL"
    fast: int = 20
    slow: int = 50
    ktype: str = "K_1M"      # bar timeframe; entitlement-dependent

    # sizing
    qty: float = 1
    size_mode: Optional[str] = "shares"   # 'shares' | 'usd'
    dollar_size: Optional[float] = 0.0

    # risk per-trade
    stop_loss_pct: Optional[float] = 0.0  # e.g. 0.02 = 2%
    take_profit_pct: Optional[float] = 0.0

    # run cadence / execution
    interval_sec: int = 15
    allow_real: bool = False


class UpdateStrategyRequest(BaseModel):
    # params
    fast: Optional[int] = None
    slow: Optional[int] = None
    ktype: Optional[str] = None
    qty: Optional[float] = None
    size_mode: Optional[str] = None          # 'shares' | 'usd'
    dollar_size: Optional[float] = None
    stop_loss_pct: Optional[float] = None
    take_profit_pct: Optional[float] = None
    allow_real: Optional[bool] = None
    # meta
    interval_sec: Optional[int] = None
    active: Optional[bool] = None

class BacktestMARequest(BaseModel):
    symbol: str
    fast: int = 20
    slow: int = 50
    ktype: str = "K_1M"
    qty: float = 1.0
    size_mode: Optional[str] = "shares"   # 'shares' | 'usd'
    dollar_size: Optional[float] = 0.0
    stop_loss_pct: Optional[float] = 0.0
    take_profit_pct: Optional[float] = 0.0
    commission_per_share: Optional[float] = 0.0
    slippage_bps: Optional[float] = 0.0

class BacktestMAGridRequest(BaseModel):
    symbol: str
    ktype: str = "K_1M"
    fast_min: int = 5
    fast_max: int = 30
    fast_step: int = 5
    slow_min: int = 40
    slow_max: int = 200
    slow_step: int = 10
    qty: float = 1.0
    size_mode: Optional[str] = "shares"
    dollar_size: Optional[float] = 0.0
    stop_loss_pct: Optional[float] = 0.0
    take_profit_pct: Optional[float] = 0.0
    commission_per_share: Optional[float] = 0.0
    slippage_bps: Optional[float] = 0.0
    top_n: int = 10

class RiskConfig(BaseModel):
    enabled: Optional[bool] = None
    max_usd_per_trade: Optional[float] = None
    max_open_positions: Optional[int] = None
    max_daily_loss_usd: Optional[float] = None
    symbol_whitelist: Optional[list[str]] = None
    trading_hours_pt: Optional[dict] = None  # {"start":"06:30","end":"13:00"}
    flatten_before_close_min: Optional[int] = None

# ---: simple models for bot mode & flatten ---
class BotModeRequest(BaseModel):
    mode: str  # 'automatic' | 'manual'

class FlattenAllRequest(BaseModel):
    symbols: Optional[list[str]] = None  # if provided, only flatten these symbols


# ---------- Helpers ----------

def _two_mode() -> str:
    """
    Returns 'automatic' if Autopilot is ON, else 'manual'.
    Falls back to persisted bot_mode only to disambiguate when manager is unavailable.
    """
    try:
        mgr = _get_autopilot()
        st = mgr.status()
        if bool(st.get("on")):
            return "automatic"
        return "manual"
    except Exception:
        val = get_setting("bot_mode") or "manual"
        return "automatic" if str(val).lower().strip() == "automatic" else "manual"


def _env_from_str(name: str):
    return TrdEnv.SIMULATE if name.upper() == "SIMULATE" else TrdEnv.REAL

def set_client(c: Optional[MoomooClient]) -> None:
    """Set the singleton broker client."""
    global client
    client = c

def get_client() -> Optional[MoomooClient]:
    """Return the singleton broker client."""
    return client

# Wire execution container with client accessor and mode on import
try:
    from execution import container as exec_container  # type: ignore
    exec_container.set_client_accessor(get_client)  # type: ignore[attr-defined]
except Exception:
    pass


# ---------- App lifecycle (automation) ----------

@app.on_event("startup")
async def _on_startup():
    global scheduler
    try:
        c = reconnect_from_session()
        if c:
            set_client(c)
            try:
                set_mode("moomoo")
            except Exception:
                pass
    except Exception:
        pass
    if _AUTOMATION_AVAILABLE:
        init_db()
        scheduler = TraderScheduler(get_client)
        scheduler.register("ma_crossover", ma_crossover_step)
        scheduler.start()

@app.on_event("shutdown")
async def _on_shutdown():
    # Stop scheduler gracefully
    global scheduler
    if scheduler:
        await scheduler.stop()
        scheduler = None


# ---------- Routes ----------

@app.get("/")
def health_check():
    return {"status": "ok"}


@app.get("/debug/bars")
def debug_bars(symbol: str, ktype: str = "K_DAY", n: int = 120):
    """
    Fetch recent bars via unified provider to help diagnose planner idling.
    Returns source ('futu' or 'yfinance'), count, and last 3 rows.
    """
    try:
        c = get_client()
    except Exception:
        c = None
    try:
        bars, source = get_bars_safely(c, symbol, ktype, n)
        sample = bars[-3:] if isinstance(bars, list) else []
        return {
            "symbol": symbol,
            "ktype": ktype,
            "source": source,
            "count": (len(bars) if isinstance(bars, list) else 0),
            "last": sample,
        }
    except Exception as e:
        # expose error to help diagnose fetch issues
        return {"symbol": symbol, "ktype": ktype, "error": str(e)}


# --- Connection & accounts ---

@app.post("/connect")
def connect(req: ConnectRequest):
    """
    Connect to the OpenD gateway using host/port from request JSON
    or .env (MOOMOO_HOST/MOOMOO_PORT). Keeps a singleton client.
    """
    host = req.host or os.getenv("MOOMOO_HOST") or "127.0.0.1"
    port_raw = req.port or os.getenv("MOOMOO_PORT") or "11111"
    client_id = req.client_id or int(os.getenv("MOOMOO_CLIENT_ID", "1"))

    if not (host and host.strip()):
        raise HTTPException(status_code=400, detail="host empty")
    try:
        port = int(port_raw)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="port not numeric")

    try:
        c = MoomooClient(host=host, port=port, client_id=client_id)
        c.connect()
        set_client(c)
        try:
            set_mode("moomoo")
        except Exception:
            pass
        # persist partial session (account may be None here)
        try:
            save_session(
                host,
                port,
                getattr(c, "account_id", None),
                getattr(c, "env", None).name if getattr(c, "env", None) else None,
                client_id,
            )
        except Exception:
            pass
        return {"status": "connected", "host": host, "port": port, "client_id": client_id}
    except (RuntimeError, TypeError) as e:
        set_client(None)
        raise HTTPException(status_code=400, detail=f"Failed to connect: {e}")
    except Exception as e:
        set_client(None)
        raise HTTPException(status_code=500, detail=f"Failed to connect: {e}")

@app.get("/accounts")
def list_accounts():
    """
    Return account IDs with trading env and type. Requires active connection.
    """
    c = get_client()
    if c is None or not c.connected:
        raise HTTPException(status_code=400, detail="Not connected")
    try:
        return c.list_accounts()
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list accounts: {e}")

@app.post("/accounts/select")
def select_account(req: SelectAccountRequest):
    """
    Select the active account. Env inferred from account list.
    """
    c = get_client()
    if c is None or not c.connected:
        raise HTTPException(status_code=400, detail="Not connected")
    try:
        info = next((a for a in c.list_accounts() if a.get("account_id") == req.account_id), None)
        if not info:
            raise RuntimeError("account not found")
        env = _env_from_str(info.get("trd_env", "SIMULATE"))
        c.set_account(req.account_id, env)
        try:
            save_session(
                c.host,
                c.port,
                c.account_id,
                c.env.name if c.env else None,
                getattr(c, "client_id", None),
            )
        except Exception:
            pass
        return {
            "status": "ok",
            "account_id": req.account_id,
            "trd_env": info.get("trd_env", "SIMULATE"),
            "account_type": info.get("account_type"),
        }
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to select account: {e}")

@app.get("/accounts/active")
def accounts_active():
    """
    Inspect currently selected account/env.
    """
    c = get_client()
    if c is None or not c.connected:
        raise HTTPException(status_code=400, detail="Not connected")
    info = None
    try:
        for a in c.list_accounts():
            if a.get("account_id") == str(c.account_id):
                info = a
                break
    except Exception:
        pass
    return {
        "account_id": c.account_id,
        "trd_env": "SIMULATE" if getattr(c, "env", None) == TrdEnv.SIMULATE else "REAL",
        "account_type": info.get("account_type") if info else None,
    }

@app.get("/accounts/info")
def account_info(account_id: str):
    """Get details for account_id."""
    c = get_client()
    if c is None or not c.connected:
        raise HTTPException(status_code=400, detail="Not connected")
    try:
        return c.get_account_info(account_id)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get account info: {e}")

@app.get("/accounts/assets")
def accounts_assets():
    """
    Best-effort account assets snapshot to help verify the selected account.
    Queries broker via accinfo_query when available; falls back to estimating from
    broker positions if necessary.
    """
    # Prefer execution mode; if unavailable, infer from client
    try:
        from execution.container import get_mode, get_execution  # type: ignore
        mode = get_mode()
    except Exception:
        get_execution = lambda: None  # type: ignore
        c_try = None
        try:
            c_try = get_client()
        except Exception:
            pass
        mode = "moomoo" if c_try is not None and getattr(c_try, "connected", False) else "sim"

    if mode == "moomoo":
        c = get_client()
        if c is None or not getattr(c, "connected", False):
            raise HTTPException(status_code=400, detail="Not connected")
        try:
            info = c.get_account_assets()  # type: ignore[attr-defined]
            return {"mode": "moomoo", **info}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to fetch broker assets: {e}")

    # Fallback: sum MV across broker-reported positions when asset API not available
    try:
        exec_service = get_execution()
    except Exception:
        exec_service = None
    equity = None
    if exec_service is not None and hasattr(exec_service, "list_positions"):
        try:
            poss = exec_service.list_positions() or []
            equity = sum(float(p.get("mv") or 0.0) for p in poss)
        except Exception:
            equity = None
    return {"mode": "sim", "equity": equity, "bp": None, "cash": None}

@app.get("/debug/accounts_raw")
def accounts_raw():
    """
    Raw passthrough of get_acc_list to help debug schema/signature differences.
    """
    c = get_client()
    if c is None or not c.connected:
        raise HTTPException(status_code=400, detail="Not connected")
    try:
        ret, df = c.trading_ctx.get_acc_list(trd_env=c.env)  # type: ignore[attr-defined]
    except TypeError:
        ret, df = c.trading_ctx.get_acc_list()  # type: ignore[attr-defined]
    if ret != 0:
        raise HTTPException(status_code=500, detail=f"get_acc_list failed: {df}")
    try:
        import pandas as pd
        if isinstance(df, pd.DataFrame):
            return df.to_dict(orient="records")
    except Exception:
        pass
    return df


# --- Trade unlock ---

@app.post("/trade/unlock")
def trade_unlock(req: UnlockTradeRequest):
    """Unlock trading with passcode."""
    c = get_client()
    if c is None or not c.connected:
        raise HTTPException(status_code=400, detail="Not connected")
    try:
        return c.unlock_trade(req.passcode)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to unlock: {e}")


# --- Positions & orders ---

@app.get("/positions")
def get_positions():
    """
    Return current positions for the active account.
    """
    c = get_client()
    if c is None or not c.connected:
        raise HTTPException(status_code=400, detail="Not connected")
    try:
        return c.get_positions()
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get positions: {e}")

@app.get("/orders")
def get_orders():
    """
    Return orders for the active account.
    """
    c = get_client()
    if c is None or not c.connected:
        raise HTTPException(status_code=400, detail="Not connected")
    try:
        return c.get_orders()
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get orders: {e}")

@app.get("/orders/{order_id}")
def get_order(order_id: str):
    """
    Return a single order by ID.
    """
    c = get_client()
    if c is None or not c.connected:
        raise HTTPException(status_code=400, detail="Not connected")
    try:
        return c.get_order(order_id)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get order: {e}")

@app.post("/orders/place")
def place_order(req: PlaceOrderRequest):
    """
    Place a market or limit order for the active account (with risk checks).
    """
    c = get_client()
    if c is None or not c.connected:
        raise HTTPException(status_code=400, detail="Not connected")
    if not c.account_id:
        raise HTTPException(status_code=400, detail="No account selected")

    side = (req.side or "").upper()
    if side not in {"BUY", "SELL"}:
        raise HTTPException(status_code=400, detail=f"Invalid side: {req.side}")

    order_type = (req.order_type or "MARKET").upper()
    if order_type not in {"MARKET", "LIMIT"}:
        raise HTTPException(status_code=400, detail=f"Invalid order_type: {req.order_type}")

    if order_type == "LIMIT" and (req.price is None or float(req.price) <= 0):
        raise HTTPException(status_code=400, detail="Limit order requires positive 'price'")

    qty = float(req.qty)
    if qty <= 0:
        raise HTTPException(status_code=400, detail="qty must be > 0")

    # Risk guardrails (raises ValueError when blocked)
    try:
        enforce_order_limits(
            client=c,
            symbol=req.symbol,
            qty=qty,
            side=side,
            order_type=order_type,
            price=req.price,
        )
    except ValueError as e:
        insert_action_log(
            "place", mode=_two_mode(),
            symbol=req.symbol, side=side, qty=qty, price=req.price,
            reason="risk_block", status="blocked", extra={"msg": str(e)}
        )
        raise HTTPException(status_code=400, detail=f"Blocked by risk: {e}")

    try:
        result = c.place_order(
            symbol=req.symbol,
            qty=qty,
            side=side,
            order_type=order_type,
            price=req.price,
        )
        insert_action_log(
            "place", mode=_two_mode(),
            symbol=req.symbol, side=side, qty=qty, price=req.price,
            reason="manual/place_order", status="ok", extra={"result": result}
        )
        return {"status": "ok", "result": result}
    except Exception as e:
        insert_action_log(
            "place", mode=_two_mode(),
            symbol=req.symbol, side=side, qty=qty, price=req.price,
            reason="exception", status="error", extra={"msg": str(e)}
        )
        raise HTTPException(status_code=500, detail=f"place_order failed: {e}")

@app.post("/orders/cancel")
def cancel_order(req: CancelOrderRequest):
    """
    Cancel an order by ID.
    """
    c = get_client()
    if c is None or not c.connected:
        raise HTTPException(status_code=400, detail="Not connected")
    try:
        res = c.cancel_order(req.order_id)
        insert_action_log("cancel", mode=_two_mode(),
                          symbol=None, side=None, qty=None, price=None,
                          reason=f"cancel {req.order_id}", status="ok", extra={"result": res})
        return res
    except RuntimeError as e:
        insert_action_log("cancel", mode=_two_mode(),
                          reason=f"runtime_error {req.order_id}", status="error", extra={"msg": str(e)})
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        insert_action_log("cancel", mode=_two_mode(),
                          reason=f"exception {req.order_id}", status="error", extra={"msg": str(e)})
        raise HTTPException(status_code=500, detail=f"Failed to cancel order: {e}")


# --- Quotes ---

@app.post("/quotes/subscribe")
def quotes_subscribe(req: SubscribeQuotesRequest):
    """
    Subscribe to basic quotes for one or more symbols.
    """
    c = get_client()
    if c is None or not c.connected:
        raise HTTPException(status_code=400, detail="Not connected")
    try:
        return c.subscribe_quotes(req.symbols)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to subscribe quotes: {e}")

@app.get("/quotes/{symbol}")
def quotes_latest(symbol: str):
    """
    Get the latest quote for a symbol.
    """
    c = get_client()
    if c is None or not c.connected:
        raise HTTPException(status_code=400, detail="Not connected")
    try:
        return c.get_quote_latest(symbol)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get quote: {e}")


# ---- Execution mode (SIM | Moomoo) ----
class ExecMode(BaseModel):
    mode: str  # 'sim' | 'moomoo'


@app.get("/execution/mode")
def exec_mode_get():
    try:
        from execution.container import get_mode  # type: ignore
        mode = get_mode()
    except Exception:
        mode = "sim"
    return {"mode": mode}


@app.put("/execution/mode")
def exec_mode_put(body: ExecMode):
    mode = (body.mode or "sim").strip().lower()
    if mode not in {"sim","moomoo"}:
        raise HTTPException(status_code=400, detail="mode must be 'sim' or 'moomoo'")
    try:
        from execution.container import set_mode  # type: ignore
        set_mode(mode)
        insert_action_log("execution_mode", mode=_two_mode(), reason="user_update", status="ok", extra={"mode": mode})
    except Exception:
        pass
    return {"mode": mode}


# --- Sync deals + PnL ---

@app.post("/sync/deals")
def sync_deals(simulate_if_absent: bool = True):
    """Pull recent fills from broker and store them locally."""
    c = get_client()
    if c is None or not c.connected:
        raise HTTPException(status_code=400, detail="Not connected")
    try:
        recs, source = fetch_deals(c, simulate_if_absent)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    exec_service = get_execution()
    inserted = 0
    if exec_service and hasattr(exec_service, "sync_deals"):
        try:
            inserted = exec_service.sync_deals(recs)  # type: ignore[attr-defined]
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"deal sync failed: {e}")
    else:
        for r in recs:
            record_fill(r["order_id"], r["symbol"], r["side"], r["qty"], r["price"], r["ts"])
            inserted += 1
    return {"status": "ok", "inserted": inserted, "source": source}

@app.get("/pnl/today")
def pnl_today_endpoint():
    """Realized PnL for today (computed from fills)."""
    try:
        return pnl_today()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to compute PnL: {e}")

@app.get("/pnl/history")
def pnl_history_endpoint(days: int = 7):
    """Realized PnL by day for the last N days."""
    try:
        return pnl_history(days=days)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to compute PnL history: {e}")


# --- Bot Mode (persisted in settings) ---

@app.get("/bot/mode")
def bot_mode_get():
    """
    Two-mode model: 'automatic' when Autopilot is ON, else 'manual'.
    Strict two-mode only: 'automatic' or 'manual'.
    """
    try:
        mgr = _get_autopilot()
        st = mgr.status()
        if bool(st.get("on")):
            return {"mode": "automatic"}
    except Exception:
        pass
    return {"mode": "manual"}

@app.put("/bot/mode")
async def bot_mode_put(req: BotModeRequest):
    """
    Set mode to 'automatic' or 'manual' and sync Autopilot accordingly.
    """
    mode_in = (req.mode or "").lower().strip()
    if mode_in not in {"automatic", "manual"}:
        raise HTTPException(status_code=400, detail="mode must be 'automatic' or 'manual'")

    # Persist the exact value (for transparency), though GET derives mode from Autopilot status.
    set_setting("bot_mode", mode_in)
    insert_action_log("mode_change", mode=mode_in, reason="user_update", status="ok")

    try:
        mgr = _get_autopilot()
        if mode_in == "automatic":
            await mgr.start()
        else:
            await mgr.stop()
    except Exception:
        # If Autopilot manager isn't available yet, GET will report 'manual' until running.
        pass

    return {"mode": mode_in}

@app.get("/logs/actions")
def action_logs(limit: int = 100, symbol: Optional[str] = None, since_hours: Optional[int] = None):
    """
    List recent action log entries for explainability/chronology.
    """
    try:
        return list_action_logs(limit=limit, symbol=symbol, since_hours=since_hours)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch action logs: {e}")


# --- Flatten All ---

@app.post("/positions/flatten")
def positions_flatten(body: FlattenAllRequest = FlattenAllRequest()):
    """
    Close all open positions by placing opposite MARKET orders.
    - Disallowed when account env is REAL (safety). Revisit with explicit flag later.
    """
    c = get_client()
    if c is None or not c.connected:
        raise HTTPException(status_code=400, detail="Not connected")
    if not c.account_id:
        raise HTTPException(status_code=400, detail="No account selected")
    if getattr(c, "env", None) == TrdEnv.REAL:
        insert_action_log("flatten", mode=_two_mode(),
                          reason="blocked_real_env", status="blocked")
        raise HTTPException(status_code=400, detail="Flatten disabled in REAL environment")

    try:
        pos = c.get_positions()
        if not isinstance(pos, list):
            pos = []
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch positions: {e}")

    target_symbols = set([s.strip() for s in (body.symbols or []) if s and s.strip()]) if body.symbols else None

    attempts = []
    for p in pos:
        code = p.get("code") or p.get("stock_code") or p.get("symbol")
        if not code:
            continue
        if target_symbols and code not in target_symbols:
            continue

        # best-effort qty detection across schemas
        qty = float(
            p.get("qty")
            or p.get("qty_today")
            or p.get("qty_total", 0)
            or 0
        )
        if qty == 0:
            continue

        side = "SELL" if qty > 0 else "BUY"
        try:
            res = c.place_order(symbol=code, qty=abs(qty), side=side, order_type="MARKET", price=None)
            attempts.append({"symbol": code, "qty": abs(qty), "side": side, "status": "ok", "result": res})
            insert_action_log("flatten", mode=_two_mode(),
                              symbol=code, side=side, qty=abs(qty),
                              reason="flatten_all", status="ok", extra={"result": res})
        except Exception as e:
            attempts.append({"symbol": code, "qty": abs(qty), "side": side, "status": "error", "error": str(e)})
            insert_action_log("flatten", mode=_two_mode(),
                              symbol=code, side=side, qty=abs(qty),
                              reason="exception", status="error", extra={"msg": str(e)})

    return {"status": "ok", "attempts": attempts}


# --- Automation: Strategies ---

@app.post("/automation/start/ma-crossover")
def automation_start_ma(req: StartMACrossoverRequest):
    """
    Start an MA crossover strategy instance (persisted in SQLite; picked up by scheduler).
    """
    if not _AUTOMATION_AVAILABLE:
        raise HTTPException(
            status_code=500,
            detail=f"Automation modules not available: {_AUTOMATION_IMPORT_ERR}",
        )
    c = get_client()
    if c is None or not c.connected:
        raise HTTPException(status_code=400, detail="Not connected")
    if scheduler is None:
        raise HTTPException(status_code=500, detail="Scheduler not available")
    if req.slow <= req.fast:
        raise HTTPException(status_code=400, detail="slow must be > fast")

    params = {
        "fast": int(req.fast),
        "slow": int(req.slow),
        "ktype": req.ktype,
        # sizing
        "qty": float(req.qty),
        "size_mode": (req.size_mode or "shares"),
        "dollar_size": float(req.dollar_size or 0),
        # risk
        "stop_loss_pct": float(req.stop_loss_pct or 0),
        "take_profit_pct": float(req.take_profit_pct or 0),
        # execution
        "allow_real": bool(req.allow_real),
    }
    
    sid = insert_strategy("ma_crossover", req.symbol.strip(), params, int(req.interval_sec))
    insert_action_log("start_strategy", mode=_two_mode(),
                      symbol=req.symbol.strip(), reason="ma_crossover", status="ok",
                      extra={"strategy_id": sid, "params": params})
    return {"status": "ok", "strategy_id": sid, "name": "ma_crossover", "symbol": req.symbol, "params": params}

@app.get("/automation/strategies")
def automation_list():
    """
    List all stored strategies with params and active flags.
    """
    if not _AUTOMATION_AVAILABLE:
        raise HTTPException(status_code=500, detail="Automation modules not available")
    return list_strategies()

@app.get("/automation/strategies/{strategy_id}")
def automation_get(strategy_id: int):
    """
    Get one strategy by id.
    """
    if not _AUTOMATION_AVAILABLE:
        raise HTTPException(status_code=500, detail="Automation modules not available")
    s = get_strategy(strategy_id)
    if not s:
        raise HTTPException(status_code=404, detail="strategy not found")
    return s

@app.patch("/automation/strategies/{strategy_id}")
def automation_update(strategy_id: int, req: UpdateStrategyRequest):
    """
    Update params/interval/active for a strategy.
    """
    if not _AUTOMATION_AVAILABLE:
        raise HTTPException(status_code=500, detail="Automation modules not available")

    p = {}
    for k in ["fast", "slow", "ktype", "qty", "size_mode", "dollar_size",
              "stop_loss_pct", "take_profit_pct", "allow_real"]:
        v = getattr(req, k)
        if v is not None:
            p[k] = v

    updated = update_strategy(
        strategy_id,
        params=p if p else None,
        interval_sec=req.interval_sec,
        active=req.active,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="strategy not found")
    insert_action_log("update_strategy", mode=_two_mode(),
                      reason=f"id={strategy_id}", status="ok", extra={"params": p, "interval_sec": req.interval_sec, "active": req.active})
    return updated

@app.get("/automation/strategies/{strategy_id}/runs")
def automation_runs(strategy_id: int, limit: int = 50):
    """
    Recent run records for a strategy.
    """
    if not _AUTOMATION_AVAILABLE:
        raise HTTPException(status_code=500, detail="Automation modules not available")
    if not get_strategy(strategy_id):
        raise HTTPException(status_code=404, detail="strategy not found")
    return list_runs(strategy_id, limit=limit)

@app.post("/automation/stop/{strategy_id}")
def automation_stop(strategy_id: int):
    """
    Stop a strategy (set active=0). The job remains stored; can re-activate later.
    """
    if not _AUTOMATION_AVAILABLE:
        raise HTTPException(status_code=500, detail="Automation modules not available")
    if not get_strategy(strategy_id):
        raise HTTPException(status_code=404, detail="strategy not found")
    set_strategy_active(strategy_id, False)
    insert_action_log("stop_strategy", mode=_two_mode(),
                      reason=f"id={strategy_id}", status="ok")
    return {"status": "ok", "strategy_id": strategy_id, "active": False}

@app.post("/automation/stop_all")
def automation_stop_all():
    """
    Stop all active strategies (set active=0 in SQLite).
    Works even if you are not connected to the broker.
    """
    if not _AUTOMATION_AVAILABLE:
        raise HTTPException(
            status_code=500,
            detail=f"Automation modules not available: {_AUTOMATION_IMPORT_ERR}",
        )

    rows = list_strategies()
    def _is_active(v):
        s = str(v).strip().lower()
        return v is True or s in {"1", "true", "yes"}

    stopped = 0
    for r in rows or []:
        if _is_active(r.get("active")):
            set_strategy_active(int(r["id"]), False)
            stopped += 1

    return {"status": "ok", "stopped": stopped}

@app.post("/automation/start/{strategy_id}")
def automation_reactivate(strategy_id: int):
    """
    Reactivate a previously stored strategy.
    """
    if not _AUTOMATION_AVAILABLE:
        raise HTTPException(status_code=500, detail="Automation modules not available")
    if not get_strategy(strategy_id):
        raise HTTPException(status_code=404, detail="strategy not found")
    set_strategy_active(strategy_id, True)
    insert_action_log("start_strategy", mode=_two_mode(),
                      reason=f"id={strategy_id}", status="ok")
    return {"status": "ok", "strategy_id": strategy_id, "active": True}


# --- Risk config & status ---

@app.get("/risk/config")
def risk_get():
    """
    Return current risk configuration (local file).
    """
    try:
        return _risk_load()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read risk config: {e}")

@app.put("/risk/config")
def risk_put(req: RiskConfig):
    """
    Update risk configuration (partial update).
    """
    try:
        cfg = _risk_load()
        for k, v in req.model_dump(exclude_none=True).items():
            cfg[k] = v
        _risk_save(cfg)
        return cfg
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save risk config: {e}")

@app.get("/risk/status")
def risk_status():
    """
    Basic runtime risk status: open positions count, config snapshot.
    """
    cfg = _risk_load()
    open_positions = None
    try:
        c = get_client()
        if c and c.connected:
            pos = c.get_positions()
            if isinstance(pos, list):
                open_positions = len(pos)
    except Exception:
        pass
    return {"ok": True, "config": cfg, "open_positions": open_positions}


# --- Session management ---

@app.get("/session/status")
def session_status():
    s = load_session()
    c = get_client()
    # env as string
    env_obj = getattr(c, "env", None)
    env_name = getattr(env_obj, "name", None)
    if env_name is None:
        if env_obj == TrdEnv.SIMULATE:
            env_name = "SIMULATE"
        elif env_obj == TrdEnv.REAL:
            env_name = "REAL"
    return {
        "saved": s or {},
        "connected": bool(c and getattr(c, "connected", False)),
        "active_account": {
            "account_id": getattr(c, "account_id", None),
            "trd_env": env_name,
        } if c else None,
    }

@app.post("/session/save")
def session_save_endpoint(body: dict):
    host = body.get("host")
    port = int(body.get("port", 0))
    client_id = body.get("client_id")
    account_id = body.get("account_id")
    trd_env = body.get("trd_env")
    if not host or not port:
        raise HTTPException(status_code=400, detail="host and port required")
    return {"ok": True, "saved": save_session(host, port, account_id, trd_env, client_id)}

@app.post("/session/clear")
def session_clear_endpoint():
    clear_session()
    return {"ok": True}


# --- Disconnect ---

@app.post("/disconnect")
def disconnect():
    """
    Disconnect and clear the global client.
    """
    c = get_client()
    if c is None:
        return {"status": "ok"}  # already clear
    try:
        c.disconnect()
    except Exception:
        pass  # ignore errors on shutdown
    set_client(None)
    try:
        set_mode("sim")
    except Exception:
        pass
    return {"status": "disconnected"}


# --- Backtest: single run ---

@app.post("/backtest/ma-crossover")
def backtest_ma(req: BacktestMARequest):
    """
    Run a local MA-crossover backtest using CSV bars in data/bars/{SYMBOL}_{KTYPE}.csv.
    Returns metrics and the first 20 trades.
    """
    if not _BACKTEST_AVAILABLE:
        raise HTTPException(status_code=500, detail=f"Backtest module not available: {_BACKTEST_IMPORT_ERR}")
    if req.slow <= req.fast:
        raise HTTPException(status_code=400, detail="slow must be > fast")
    try:
        bars = load_bars_csv(req.symbol, req.ktype)
        res = run_ma_crossover(
            bars=bars,
            fast=int(req.fast),
            slow=int(req.slow),
            qty=float(req.qty),
            size_mode=(req.size_mode or "shares"),
            dollar_size=float(req.dollar_size or 0),
            stop_loss_pct=float(req.stop_loss_pct or 0),
            take_profit_pct=float(req.take_profit_pct or 0),
            commission_per_share=float(req.commission_per_share or 0),
            slippage_bps=float(req.slippage_bps or 0),
        )
        trades = [{
            "entry_ts": t.entry_ts, "exit_ts": t.exit_ts, "side": t.side,
            "entry_px": t.entry_px, "exit_px": t.exit_px, "qty": t.qty, "pnl": t.pnl
        } for t in res.trades[:20]]
        return {"metrics": res.metrics, "trades_sample": trades}
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=400,
            detail=f"{e}. Put a CSV at data/bars/{req.symbol.split('.')[-1].upper()}_{req.ktype}.csv with columns time,open,high,low,close,volume"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Backtest failed: {e}")


# --- Backtest: parameter grid ---

@app.post("/backtest/ma-grid")
def backtest_ma_grid(req: BacktestMAGridRequest):
    """
    Run an MA-crossover parameter sweep; returns top-N results by gross_pnl.
    """
    if not _BACKTEST_AVAILABLE:
        raise HTTPException(status_code=500, detail=f"Backtest module not available: {_BACKTEST_IMPORT_ERR}")
    if not _GRID_AVAILABLE:
        raise HTTPException(status_code=500, detail=f"Backtest grid not available: {_GRID_IMPORT_ERR}")
    try:
        bars = load_bars_csv(req.symbol, req.ktype)
        results = run_ma_grid(
            bars=bars,
            fast_min=req.fast_min, fast_max=req.fast_max, fast_step=req.fast_step,
            slow_min=req.slow_min, slow_max=req.slow_max, slow_step=req.slow_step,
            qty=float(req.qty),
            size_mode=(req.size_mode or "shares"),
            dollar_size=float(req.dollar_size or 0),
            stop_loss_pct=float(req.stop_loss_pct or 0),
            take_profit_pct=float(req.take_profit_pct or 0),
            commission_per_share=float(req.commission_per_share or 0),
            slippage_bps=float(req.slippage_bps or 0),
            top_n=int(req.top_n),
        )
        return {"count": len(results), "results": results}
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=400,
            detail=f"{e}. Put a CSV at data/bars/{req.symbol.split('.')[-1].upper()}_{req.ktype}.csv"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Backtest grid failed: {e}")


# --- Autopilot (planner/executor) scaffold ---
try:
    from autopilot.worker import AutopilotManager
    from autopilot import schemas as ap_schemas
    _AUTOPILOT_AVAILABLE = True
    _AUTOPILOT_IMPORT_ERR = None
except Exception as _ae:
    AutopilotManager = None  # type: ignore
    ap_schemas = None        # type: ignore
    _AUTOPILOT_AVAILABLE = False
    _AUTOPILOT_IMPORT_ERR = _ae

autopilot_router = APIRouter(prefix="/autopilot", tags=["autopilot"])

_autopilot_mgr = None  # lazy singleton

def _get_autopilot():
    global _autopilot_mgr
    if _autopilot_mgr is None:
        if not _AUTOPILOT_AVAILABLE:
            raise HTTPException(status_code=500, detail=f"Autopilot unavailable: {_AUTOPILOT_IMPORT_ERR}")
        # lazy-create manager; pass client accessor and risk-loader
        def _risk_loader():
            try:
                return _risk_load()
            except Exception:
                return {}
        _autopilot_mgr = AutopilotManager(get_client, _risk_loader, get_execution=get_execution)
    return _autopilot_mgr

@autopilot_router.post("/enable")
async def autopilot_enable(body: dict):
    """
    Enable/disable the Autopilot worker loop.
    Body: {"on": bool}
    """
    on = bool(body.get("on", False))
    mgr = _get_autopilot()
    if on:
        await mgr.start()
        return {"on": True, "status": "started"}
    else:
        await mgr.stop()
        return {"on": False, "status": "stopped"}

@autopilot_router.get("/status")
async def autopilot_status():
    try:
        mgr = _get_autopilot()
        st = mgr.status()
    except Exception as e:
        # Return a minimal status payload instead of 500 to aid debugging
        st = {"on": False, "last_tick": None, "last_decision": None, "stats": {}, "reject_streak": 0, "error": str(e)}
    # Enrich with performance stats and model info (best-effort)
    try:
        from core.storage import performance_stats, exits_coverage  # type: ignore
        perf = performance_stats(days=365)
        coverage = exits_coverage(since_hours=24)
        stats = dict(st.get("stats") or {})
        stats.update(perf)
        stats.update(coverage)
        # Surface model name for UI badge
        stats["model"] = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        st["stats"] = stats
    except Exception:
        pass
    # Planner meta for UI (provider + enabled)
    try:
        provider = (os.getenv("PLANNER_PROVIDER", "stub") or "stub").strip().lower()
        has_key = bool((os.getenv("OPENAI_API_KEY", "") or "").strip())
        effective = ("gpt" if (provider == "stub" and has_key) else provider)
        st["planner_info"] = {
            "provider": effective,
            "enabled": (effective == "gpt" and has_key),
            "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        }
    except Exception:
        pass
    return st

@autopilot_router.post("/preview")
async def autopilot_preview():
    """
    Run a single Sense→Think (no Act). Returns planner input, raw planner output, and validation details.
    """
    mgr = _get_autopilot()
    return await mgr.preview()

@autopilot_router.get("/context")
async def autopilot_context():
    mgr = _get_autopilot()
    return {"last_input": mgr.last_input or {}}

@autopilot_router.get("/last_output")
async def autopilot_last_output():
    mgr = _get_autopilot()
    return {"last_output": mgr.last_output or {}}

@autopilot_router.get("/last_diff")
async def autopilot_last_diff():
    try:
        mgr = _get_autopilot()
    except Exception:
        return {"proposed": [], "kept": []}
    try:
        proposed = getattr(mgr, "_last_proposed", []) or []
    except Exception:
        proposed = []
    try:
        kept = getattr(mgr, "_last_evaluated", []) or []
    except Exception:
        kept = []
    return {"proposed": proposed[:12], "kept": kept[:12]}

@autopilot_router.get("/env_debug")
def autopilot_env_debug():
    """Return minimal planner-related env info (sanitized) for troubleshooting."""
    provider = (os.getenv("PLANNER_PROVIDER", "stub") or "stub").strip().lower()
    has_key = bool((os.getenv("OPENAI_API_KEY", "") or "").strip())
    model = os.getenv("OPENAI_MODEL", None)
    effective = ("gpt" if (provider == "stub" and has_key) else provider)
    return {
        "provider_env": provider,
        "has_openai_key": has_key,
        "effective_provider": effective,
        "model": model,
        "json_mode": os.getenv("OPENAI_JSON_MODE", None),
        "fallback_stub": os.getenv("PLANNER_FALLBACK_STUB", None),
    }


@autopilot_router.get("/logs")
async def autopilot_logs(limit: int = 100, offset: int = 0, since_hours: int = 72):
    """
    Return Autopilot logs from persistent storage when available, with an in-memory fallback.
    We prefer rows written via core.storage.insert_action_log() by the worker, filtered to
    sources that start with 'autopilot' or mode == 'auto'.
    """
    # Try DB-backed logs first (core.storage.list_action_logs)
    try:
        rows = list_action_logs(limit=limit * 5, symbol=None, since_hours=since_hours)  # type: ignore[name-defined]
        def _is_auto(r: dict) -> bool:
            src = str(r.get("source", "")).lower()
            md = str(r.get("mode", "")).lower()
            return src.startswith("autopilot") or md in ("auto", "autopilot")
        out = [r for r in rows if isinstance(r, dict) and _is_auto(r)]
        out.sort(key=lambda x: str(x.get("ts", "")), reverse=True)
        return out[offset: offset + limit]
    except Exception:
        # fall back to manager in-memory logs
        mgr = _get_autopilot()
        return mgr.get_logs(limit=limit, offset=offset)

# stop Autopilot cleanly on shutdown (in addition to scheduler)
@app.on_event("shutdown")
async def _autopilot_shutdown():
    try:
        mgr = _get_autopilot()
        await mgr.stop()
    except Exception:
        pass

# ---------------- Autopilot: Preferences, Style, Watchlist ---------------- #

class AutopilotPrefs(BaseModel):
    target_winrate_pct: Optional[float] = None
    target_rr: Optional[float] = None
    stop_loss_pct: Optional[float] = None
    take_profit_pct: Optional[float] = None
    measured_move_atr_mult: Optional[float] = None
    max_dd_pct: Optional[float] = None
    per_trade_max_bps: Optional[int] = None


class StyleUpdate(BaseModel):
    text: str


def _get_json_setting(key: str, default):
    try:
        raw = get_setting(key)  # type: ignore[name-defined]
        if raw is None:
            return default
        try:
            return json.loads(raw)
        except Exception:
            return raw
    except Exception:
        return default


def _set_json_setting(key: str, value) -> None:
    try:
        set_setting(key, value)  # type: ignore[name-defined]
    except Exception:
        pass


def _openai_chat(system: str, user: str) -> Optional[str]:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    base = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()
    if not api_key:
        return None
    try:
        import requests  # lazy import
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0,
        }
        try:
            if os.getenv("OPENAI_JSON_MODE", "0") not in ("0", "false", "no"):
                payload["response_format"] = {"type": "json_object"}
        except Exception:
            pass
        r = requests.post(
            f"{base}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=float(os.getenv("OPENAI_TIMEOUT", "15")),
        )
        r.raise_for_status()
        data = r.json()
        return data["choices"][0]["message"]["content"]
    except Exception:
        return None


def _summarize_style(text: str) -> str:
    text = (text or "").strip()
    if not text:
        return ""
    system = (
        "You are a trading-style summarizer. Write a concise, actionable style note "
        "(<= 6 bullet lines or 400 chars) for a trading assistant. "
        "Prefer rules and thresholds (e.g., win rate target, RR, stop %, time windows)."
    )
    user = f"User preferences/notes to summarize:\n{text}"
    out = _openai_chat(system, user)
    if out and isinstance(out, str):
        return out.strip()[:600]
    # Fallback summary when model call fails
    try:
        import re
        sents = [s.strip() for s in re.split(r"[\n.;]+", text) if s.strip()]
        bullets = [f"- {s[:100].strip()}" for s in sents[:6]]
        if bullets:
            return "\n".join(bullets)[:600]
    except Exception:
        pass
    return text[:600]

def _extract_symbols(text: str) -> list[str]:
    try:
        import re
    except Exception:
        return []
    if not text:
        return []
    txt = str(text).upper()
    out: list[str] = []
    # Explicit US.TICKER tokens
    out += re.findall(r"\bUS\.[A-Z0-9]{1,6}\b", txt)
    # Bare tickers (2–5 letters) excluding common words
    COMMON = {"THE","AND","FOR","WITH","THIS","THAT","ONLY","WHEN","STOP","TAKE","LOSS","SELL","BUY","LONG","SHORT","NEWS","RSI","ATR","MA","UP","DOWN","HOLD","OPEN","CLOSE","DAY","WEEK","MONTH","YEARS"}
    for token in re.findall(r"\b[A-Z]{2,5}\b", txt):
        if token in COMMON:
            continue
        out.append(f"US.{token}")
    # Dedup preserve order, cap length
    seen = set()
    uniq: list[str] = []
    for s in out:
        if s not in seen:
            seen.add(s)
            uniq.append(s)
    return uniq[:50]


@autopilot_router.get("/prefs")
def autopilot_prefs_get():
    return _get_json_setting("autopilot.prefs", {})


@autopilot_router.put("/prefs")
def autopilot_prefs_put(prefs: AutopilotPrefs):
    cur = _get_json_setting("autopilot.prefs", {})
    upd = cur if isinstance(cur, dict) else {}
    for k, v in prefs.dict().items():
        if v is not None:
            upd[k] = v
    _set_json_setting("autopilot.prefs", upd)
    insert_action_log("prefs_update", mode=_two_mode(), reason="user_update", status="ok", extra=upd)  # type: ignore[name-defined]
    return upd


@autopilot_router.get("/style")
def autopilot_style_get():
    return {
        "raw": _get_json_setting("autopilot.style_raw", "") or "",
        "summary": _get_json_setting("autopilot.style_summary", "") or "",
    }


@autopilot_router.post("/style")
def autopilot_style_post(body: StyleUpdate):
    raw = (body.text or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="text is required")
    summary = _summarize_style(raw)
    _set_json_setting("autopilot.style_raw", raw)
    _set_json_setting("autopilot.style_summary", summary)
    # Extract and store candidate symbols
    syms = list(dict.fromkeys(_extract_symbols(raw) + _extract_symbols(summary)))
    if syms:
        _set_json_setting("autopilot.style_symbols", syms)
    insert_action_log("style_update", mode=_two_mode(), reason="user_update", status="ok", extra={"len": len(raw), "symbols": len(syms)})  # type: ignore[name-defined]
    return {"raw": raw, "summary": summary, "symbols": syms}


@autopilot_router.delete("/style")
def autopilot_style_delete():
    """
    Clear stored natural-language style and its summary (and any derived symbols).
    Safe no-op if nothing is stored.
    """
    try:
        _set_json_setting("autopilot.style_raw", "")
        _set_json_setting("autopilot.style_summary", "")
        # Also clear derived symbols and toggle (best-effort)
        _set_json_setting("autopilot.style_symbols", [])
        _set_json_setting("autopilot.style_symbols_enabled", False)
        insert_action_log("style_update", mode=_two_mode(), reason="delete", status="ok", extra={})  # type: ignore[name-defined]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete style: {e}")
    return {"raw": "", "summary": "", "symbols": []}


class StyleSymbolsUpdate(BaseModel):
    enabled: Optional[bool] = None
    symbols: Optional[List[str]] = None


@autopilot_router.get("/style_symbols")
def autopilot_style_symbols_get():
    enabled = bool(_get_json_setting("autopilot.style_symbols_enabled", False))
    syms = _get_json_setting("autopilot.style_symbols", [])
    if not isinstance(syms, list):
        syms = []
    return {"enabled": enabled, "symbols": syms}


@autopilot_router.put("/style_symbols")
def autopilot_style_symbols_put(body: StyleSymbolsUpdate):
    if isinstance(body.symbols, list):
        def _norm(x: str) -> str:
            x = (x or "").strip().upper()
            return x if "." in x else (f"US.{x}" if x else x)
        symbols = list({ _norm(s) for s in body.symbols if isinstance(s, str) and s.strip() })
        _set_json_setting("autopilot.style_symbols", symbols)
        insert_action_log("style_symbols", mode=_two_mode(), reason="update", status="ok", extra={"n": len(symbols)})  # type: ignore[name-defined]
    if body.enabled is not None:
        _set_json_setting("autopilot.style_symbols_enabled", bool(body.enabled))
        insert_action_log("style_symbols", mode=_two_mode(), reason="enabled_toggle", status="ok", extra={"enabled": bool(body.enabled)})  # type: ignore[name-defined]
    return autopilot_style_symbols_get()


class WatchlistUpdate(BaseModel):
    symbols: List[str]


def _normalize_symbol(s: str) -> str:
    s = (s or "").strip().upper()
    if not s:
        return s
    return s if "." in s else f"US.{s}"


@autopilot_router.get("/watchlist")
def autopilot_watchlist_get():
    wl = _get_json_setting("autopilot.watchlist", None)
    if isinstance(wl, list) and wl:
        return {"symbols": wl}
    env = os.getenv("AUTOPILOT_WATCHLIST", "US.AAPL,US.MSFT,US.TSLA")
    syms = [_normalize_symbol(x) for x in env.split(",") if x.strip()]
    return {"symbols": syms}


@autopilot_router.put("/watchlist")
def autopilot_watchlist_put(body: WatchlistUpdate):
    symbols = list({_normalize_symbol(x) for x in (body.symbols or []) if str(x).strip()})
    _set_json_setting("autopilot.watchlist", symbols)
    insert_action_log("watchlist_update", mode=_two_mode(), reason="user_update", status="ok", extra={"n": len(symbols)})  # type: ignore[name-defined]
    return {"symbols": symbols}


# ---- Discovery config and preview ----
class DiscoveryUpdate(BaseModel):
    enabled: bool | None = None
    only: bool | None = None
    seed: List[str] | None = None


@autopilot_router.get("/discovery")
def autopilot_discovery_get():
    enabled = True
    try:
        raw = _get_json_setting("autopilot.discovery_enabled", None)
        if raw is not None:
            enabled = bool(raw)
    except Exception:
        pass
    only = False
    try:
        raw = _get_json_setting("autopilot.discovery_only", None)
        if raw is not None:
            only = bool(raw)
    except Exception:
        pass
    seed = _get_json_setting("autopilot.discovery_seed", None)
    if not isinstance(seed, list):
        seed = []
    # Optional live preview (best-effort)
    preview: List[str] = []
    try:
        from autopilot.discovery import discover_symbols  # type: ignore
        preview = discover_symbols(get_client(), limit=10, ktype="K_DAY")  # type: ignore[arg-type]
    except Exception:
        preview = []
    return {"enabled": enabled, "only": only, "seed": seed, "preview": preview}


@autopilot_router.put("/discovery")
def autopilot_discovery_put(body: DiscoveryUpdate):
    if body.enabled is not None:
        _set_json_setting("autopilot.discovery_enabled", bool(body.enabled))
        insert_action_log("discovery_update", mode=_two_mode(), reason="enabled_toggle", status="ok", extra={"enabled": bool(body.enabled)})  # type: ignore[name-defined]
    if body.only is not None:
        _set_json_setting("autopilot.discovery_only", bool(body.only))
        insert_action_log("discovery_update", mode=_two_mode(), reason="only_toggle", status="ok", extra={"only": bool(body.only)})  # type: ignore[name-defined]
    if isinstance(body.seed, list):
        # normalize seed to US.TICKER
        symbols = list({_normalize_symbol(x) for x in body.seed if str(x).strip()})
        _set_json_setting("autopilot.discovery_seed", symbols)
        insert_action_log("discovery_update", mode=_two_mode(), reason="seed_update", status="ok", extra={"n": len(symbols)})  # type: ignore[name-defined]
    return autopilot_discovery_get()


# ---- Planner settings (min confidence, top_n) ----
class PlannerUpdate(BaseModel):
    min_confidence: float | None = None
    top_n: int | None = None
    strict_prefs: bool | None = None


@autopilot_router.get("/planner")
def autopilot_planner_get():
    try:
        mc_raw = _get_json_setting("autopilot.min_confidence", None)
        min_conf = float(mc_raw) if mc_raw is not None else 0.6
    except Exception:
        min_conf = 0.6
    try:
        tn_raw = _get_json_setting("autopilot.top_n", None)
        top_n = int(tn_raw) if tn_raw is not None else int(os.getenv("AUTOPILOT_TOP_N", "8") or "8")
    except Exception:
        top_n = int(os.getenv("AUTOPILOT_TOP_N", "8") or "8")
    try:
        sp_raw = _get_json_setting("autopilot.strict_prefs", None)
        strict_prefs = bool(sp_raw) if sp_raw is not None else False
    except Exception:
        strict_prefs = False
    return {"min_confidence": min_conf, "top_n": top_n, "strict_prefs": strict_prefs}


@autopilot_router.put("/planner")
def autopilot_planner_put(body: PlannerUpdate):
    if body.min_confidence is not None:
        _set_json_setting("autopilot.min_confidence", float(body.min_confidence))
        insert_action_log("planner_update", mode=_two_mode(), reason="min_conf", status="ok", extra={"min_conf": float(body.min_confidence)})  # type: ignore[name-defined]
    if isinstance(body.top_n, int) and body.top_n > 0:
        _set_json_setting("autopilot.top_n", int(body.top_n))
        insert_action_log("planner_update", mode=_two_mode(), reason="top_n", status="ok", extra={"top_n": int(body.top_n)})  # type: ignore[name-defined]
    if body.strict_prefs is not None:
        _set_json_setting("autopilot.strict_prefs", bool(body.strict_prefs))
        insert_action_log("planner_update", mode=_two_mode(), reason="strict_prefs", status="ok", extra={"strict_prefs": bool(body.strict_prefs)})  # type: ignore[name-defined]
    return autopilot_planner_get()


# ---- News settings (toggle + ttl) ----
class NewsUpdate(BaseModel):
    enabled: bool | None = None
    ttl_sec: int | None = None
    provider: str | None = None  # 'heuristic' | 'gpt'


@autopilot_router.get("/news")
def autopilot_news_get():
    enabled = True
    try:
        raw = _get_json_setting("autopilot.use_news", None)
        if raw is not None:
            enabled = bool(raw)
    except Exception:
        pass
    try:
        ttl = int(_get_json_setting("autopilot.news_ttl_sec", None) or 0)
    except Exception:
        ttl = 0
    if ttl <= 0:
        ttl = int(os.getenv("AUTOPILOT_NEWS_TTL_SEC", "1800") or "1800")
    # provider (default heuristic)
    provider = "heuristic"
    try:
        pv = _get_json_setting("autopilot.news_provider", None)
        if isinstance(pv, str) and pv.strip():
            provider = pv.strip()
    except Exception:
        pass
    return {"enabled": enabled, "ttl_sec": ttl, "provider": provider}


@autopilot_router.put("/news")
def autopilot_news_put(body: NewsUpdate):
    if body.enabled is not None:
        _set_json_setting("autopilot.use_news", bool(body.enabled))
        insert_action_log("news_update", mode=_two_mode(), reason="enabled_toggle", status="ok", extra={"enabled": bool(body.enabled)})  # type: ignore[name-defined]
    if isinstance(body.ttl_sec, int) and body.ttl_sec > 0:
        _set_json_setting("autopilot.news_ttl_sec", int(body.ttl_sec))
        insert_action_log("news_update", mode=_two_mode(), reason="ttl_update", status="ok", extra={"ttl_sec": int(body.ttl_sec)})  # type: ignore[name-defined]
    if isinstance(body.provider, str) and body.provider.strip():
        pv = body.provider.strip().lower()
        if pv not in ("heuristic", "gpt"):
            raise HTTPException(status_code=400, detail="provider must be 'heuristic' or 'gpt'")
        _set_json_setting("autopilot.news_provider", pv)
        insert_action_log("news_update", mode=_two_mode(), reason="provider", status="ok", extra={"provider": pv})  # type: ignore[name-defined]
    return autopilot_news_get()


# ---- Data settings (ktype, bars ttl) ----
class DataUpdate(BaseModel):
    ktype: str | None = None
    bars_ttl_sec: int | None = None
    deals_sync_sec: int | None = None
    data_source: str | None = None


_KTYPES = {"K_1M","K_5M","K_15M","K_30M","K_60M","K_DAY","K_1D"}


@autopilot_router.get("/data")
def autopilot_data_get():
    ktype = str(_get_json_setting("autopilot.ktype", None) or os.getenv("AUTOPILOT_KTYPE", "K_DAY"))
    bars_ttl = 0
    try:
        bars_ttl = int(_get_json_setting("autopilot.bars_ttl_sec", None) or 0)
    except Exception:
        bars_ttl = 0
    if bars_ttl <= 0:
        bars_ttl = int(os.getenv("AUTOPILOT_BARS_TTL_SEC", "60") or "60")
    try:
        deals_sync = int(_get_json_setting("autopilot.deals_sync_sec", None) or 0)
    except Exception:
        deals_sync = 0
    if deals_sync <= 0:
        deals_sync = int(os.getenv("AUTOPILOT_DEALS_SYNC_SEC", "180") or "180")
    src = str(_get_json_setting("autopilot.data_source", None) or os.getenv("AUTOPILOT_DATA_SOURCE", "futu"))
    return {"ktype": ktype, "bars_ttl_sec": bars_ttl, "deals_sync_sec": deals_sync, "data_source": src}


@autopilot_router.put("/data")
def autopilot_data_put(body: DataUpdate):
    if body.ktype is not None:
        kt = str(body.ktype).upper().strip()
        if kt not in _KTYPES:
            raise HTTPException(status_code=400, detail=f"ktype must be one of: {sorted(_KTYPES)}")
        _set_json_setting("autopilot.ktype", kt)
        insert_action_log("data_update", mode=_two_mode(), reason="ktype", status="ok", extra={"ktype": kt})  # type: ignore[name-defined]
    if isinstance(body.bars_ttl_sec, int) and body.bars_ttl_sec > 0:
        _set_json_setting("autopilot.bars_ttl_sec", int(body.bars_ttl_sec))
        insert_action_log("data_update", mode=_two_mode(), reason="bars_ttl", status="ok", extra={"bars_ttl_sec": int(body.bars_ttl_sec)})  # type: ignore[name-defined]
    if isinstance(body.deals_sync_sec, int) and body.deals_sync_sec > 0:
        _set_json_setting("autopilot.deals_sync_sec", int(body.deals_sync_sec))
        insert_action_log("data_update", mode=_two_mode(), reason="deals_sync", status="ok", extra={"deals_sync_sec": int(body.deals_sync_sec)})  # type: ignore[name-defined]
    if body.data_source is not None:
        ds = str(body.data_source).lower().strip()
        if ds not in {"futu", "yfinance"}:
            raise HTTPException(status_code=400, detail="data_source must be 'futu' or 'yfinance'")
        _set_json_setting("autopilot.data_source", ds)
        insert_action_log("data_update", mode=_two_mode(), reason="data_source", status="ok", extra={"data_source": ds})  # type: ignore[name-defined]
    return autopilot_data_get()


# ---- Signals settings (enable + per-strategy weights) ----
class SignalsSettings(BaseModel):
    enabled: Optional[bool] = None
    strategies: Optional[Dict[str, bool]] = None
    weights: Optional[Dict[str, float]] = None
    auto_weight: Optional[bool] = None


@autopilot_router.get("/signals")
def autopilot_signals_get():
    # defaults
    enabled = True
    strategies: Dict[str, bool] = {
        "macd_cross": True,
        "bb_breakout": True,
        "stoch_rsi_extreme": True,
        "ma_trend": True,
        "rsi_extreme": True,
        "news": True,
    }
    weights: Dict[str, float] = {
        "macd_cross": 1.0,
        "bb_breakout": 1.0,
        "stoch_rsi_extreme": 1.0,
        "ma_trend": 1.0,
        "rsi_extreme": 1.0,
        "news": 1.0,
    }
    try:
        raw = _get_json_setting("autopilot.signals.enabled", None)
        if raw is not None:
            enabled = bool(raw)
    except Exception:
        pass
    try:
        m = _get_json_setting("autopilot.signals.strategies", None)
        if isinstance(m, dict):
            strategies.update({str(k): bool(v) for k, v in m.items()})
    except Exception:
        pass
    try:
        w = _get_json_setting("autopilot.signals.weights", None)
        if isinstance(w, dict):
            for k, v in w.items():
                try:
                    weights[str(k)] = float(v)
                except Exception:
                    continue
    except Exception:
        pass
    # auto-weight flag
    auto_weight = False
    try:
        raw = _get_json_setting("autopilot.signals.auto_weight", None)
        if raw is not None:
            auto_weight = bool(raw)
    except Exception:
        pass
    return {"enabled": enabled, "strategies": strategies, "weights": weights, "auto_weight": auto_weight}


@autopilot_router.put("/signals")
def autopilot_signals_put(body: SignalsSettings):
    if body.enabled is not None:
        _set_json_setting("autopilot.signals.enabled", bool(body.enabled))
        insert_action_log("signals_update", mode=_two_mode(), reason="enabled_toggle", status="ok", extra={"enabled": bool(body.enabled)})  # type: ignore[name-defined]
    if isinstance(body.strategies, dict):
        # sanitize to booleans
        clean = {str(k): bool(v) for k, v in body.strategies.items()}
        _set_json_setting("autopilot.signals.strategies", clean)
        insert_action_log("signals_update", mode=_two_mode(), reason="strategies", status="ok", extra={"n": len(clean)})  # type: ignore[name-defined]
    if isinstance(body.weights, dict):
        clean_w: Dict[str, float] = {}
        for k, v in body.weights.items():
            try:
                clean_w[str(k)] = float(v)
            except Exception:
                continue
        _set_json_setting("autopilot.signals.weights", clean_w)
        insert_action_log("signals_update", mode=_two_mode(), reason="weights", status="ok", extra={"n": len(clean_w)})  # type: ignore[name-defined]
    # optional auto_weight toggle
    try:
        aw = getattr(body, 'auto_weight', None)  # type: ignore
        if aw is not None:
            _set_json_setting("autopilot.signals.auto_weight", bool(aw))
            insert_action_log("signals_update", mode=_two_mode(), reason="auto_weight", status="ok", extra={"enabled": bool(aw)})  # type: ignore[name-defined]
    except Exception:
        pass
    return autopilot_signals_get()

# Ensure all /autopilot routes are registered only after definitions
@autopilot_router.get("/weekly")
def autopilot_weekly():
    """
    Weekly report: realized metrics, per-strategy attribution (from signals_used),
    auto-weight adjustment summary, missed rules, and % dropped by validator.
    """
    try:
        from core.storage import performance_stats, list_action_logs  # type: ignore
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Storage unavailable: {e}")

    out: Dict[str, Any] = {}
    # Realized metrics (7d window)
    try:
        out["performance_7d"] = performance_stats(days=7)
    except Exception:
        out["performance_7d"] = {}

    # Action logs in 7d for attribution + validator/evaluator summaries
    rows = []
    try:
        rows = list_action_logs(limit=2000, symbol=None, since_hours=24*7)
    except Exception:
        rows = []

    import json as _json
    # Per-strategy attribution: count strength weighted appearances in 'autopilot_act' signals_used
    strat_use: Dict[str, float] = {}
    reweights: int = 0
    proposed_total = 0
    validator_dropped = 0
    evaluator_dropped = 0
    missed_rules = {"planner_invalid_json": 0, "guardrails": 0}
    proposed_counts: Dict[str, int] = {}
    executed_counts: Dict[str, int] = {}
    decision_reasons: Dict[str, List[str]] = {}
    for r in rows:
        try:
            act = str(r.get("action") or "")
            src = str(r.get("source") or "")
            reason = str(r.get("reason") or "")
            if act == "autopilot_act":
                extra = {}
                try:
                    extra = _json.loads(r.get("extra_json") or "{}")
                except Exception:
                    extra = {}
                for s in extra.get("signals_used", []) or []:
                    k = str(s.get("strategy") or "")
                    if not k:
                        continue
                    strat_use[k] = strat_use.get(k, 0.0) + float(s.get("strength") or 0.0)
                sym = str(r.get("symbol") or "")
                if sym:
                    executed_counts[sym] = executed_counts.get(sym, 0) + 1
                    rc = extra.get("rule_checks") or {}
                    try:
                        bad = [k for k, v in rc.items() if v is False]
                        if bad:
                            decision_reasons.setdefault(sym, []).extend(bad)
                    except Exception:
                        pass
            elif act == "autopilot" and reason == "signals_reweighted":
                reweights += 1
            elif act == "planner_proposed":
                extra = {}
                try:
                    extra = _json.loads(r.get("extra_json") or "{}")
                except Exception:
                    extra = {}
                proposed_total += int(extra.get("n") or 0)
                for s in extra.get("syms") or []:
                    sym = str(s)
                    if sym:
                        proposed_counts[sym] = proposed_counts.get(sym, 0) + 1
            elif act == "validator_result":
                extra = {}
                try:
                    extra = _json.loads(r.get("extra_json") or "{}")
                except Exception:
                    extra = {}
                validator_dropped += int(extra.get("dropped") or 0)
            elif act == "evaluator_result":
                extra = {}
                try:
                    extra = _json.loads(r.get("extra_json") or "{}")
                except Exception:
                    extra = {}
                evaluator_dropped += int(extra.get("dropped") or 0)
            elif act == "autopilot" and reason == "planner_invalid_json":
                missed_rules["planner_invalid_json"] += 1
            elif act == "autopilot_act" and reason == "guardrail":
                missed_rules["guardrails"] += 1
        except Exception:
            continue

    out["attribution"] = strat_use
    out["auto_weight_adjustments"] = reweights
    out["dropped"] = {
        "proposed_total": proposed_total,
        "validator_dropped": validator_dropped,
        "evaluator_dropped": evaluator_dropped,
        "pct_dropped_validator": (0 if proposed_total==0 else round(validator_dropped / proposed_total * 100.0, 2)),
    }
    out["missed_rules"] = missed_rules
    out["proposed_counts"] = proposed_counts
    out["executed_counts"] = executed_counts
    out["decision_reasons"] = decision_reasons
    return out

# Ensure router registration happens after all route definitions
app.include_router(autopilot_router)
