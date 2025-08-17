from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional
import os
import json
from datetime import datetime
from pathlib import Path

from fastapi.middleware.cors import CORSMiddleware

# --- Internal modules ---
from core.market_data import get_bars_safely
from core.moomoo_client import MoomooClient
from core.futu_client import TrdEnv
from core.session import load_session, save_session, clear_session
from risk.limits import enforce_order_limits

# Optional automation (scheduler + storage + strategy step)
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


# ---------- Request Models ----------

class ConnectRequest(BaseModel):
    host: Optional[str] = None
    port: Optional[int] = None
    client_id: Optional[int] = None  # parity only

class SelectAccountRequest(BaseModel):
    account_id: str
    trd_env: str = "SIMULATE"  # "SIMULATE" or "REAL"

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
    mode: str  # 'assist' | 'semi' | 'auto'

class FlattenAllRequest(BaseModel):
    symbols: Optional[list[str]] = None  # if provided, only flatten these symbols


# ---------- Helpers ----------

def _env_from_str(name: str):
    return TrdEnv.SIMULATE if name.upper() == "SIMULATE" else TrdEnv.REAL

def set_client(c: Optional[MoomooClient]) -> None:
    """Set the singleton broker client."""
    global client
    client = c

def get_client() -> Optional[MoomooClient]:
    """Return the singleton broker client."""
    return client


# ---------- App lifecycle (automation) ----------

@app.on_event("startup")
async def _on_startup():
    # Start scheduler if automation modules are importable
    global scheduler
    if _AUTOMATION_AVAILABLE:
        init_db()
        scheduler = TraderScheduler(get_client)  # pass accessor
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


# --- Connection & accounts ---

@app.post("/connect")
def connect(req: ConnectRequest):
    """
    Connect to the OpenD gateway using host/port from request JSON
    or .env (MOOMOO_HOST/MOOMOO_PORT). Keeps a singleton client.
    """
    host = req.host or os.getenv("MOOMOO_HOST", "127.0.0.1")
    port = req.port or int(os.getenv("MOOMOO_PORT", "11111"))
    _ = req.client_id or int(os.getenv("MOOMOO_CLIENT_ID", "1"))  # parity only

    try:
        c = MoomooClient(host=host, port=port)  # client_id not required by current build
        c.connect()
        set_client(c)
        # persist partial session (account may be None here)
        try:
            save_session(
                host,
                port,
                getattr(c, "account_id", None),
                getattr(c, "env", None).name if getattr(c, "env", None) else None,
            )
        except Exception:
            pass
        return {"status": "connected", "host": host, "port": port}
    except (RuntimeError, TypeError) as e:
        set_client(None)
        raise HTTPException(status_code=400, detail=f"Failed to connect: {e}")
    except Exception as e:
        set_client(None)
        raise HTTPException(status_code=500, detail=f"Failed to connect: {e}")

@app.get("/accounts")
def list_accounts():
    """
    Return available account IDs. Requires an active connection.
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
    Select the active account + env (SIMULATE/REAL).
    """
    c = get_client()
    if c is None or not c.connected:
        raise HTTPException(status_code=400, detail="Not connected")
    try:
        env = _env_from_str(req.trd_env)
        c.set_account(req.account_id, env)
        # persist full session
        try:
            save_session(
                c.host,
                c.port,
                c.account_id,
                c.env.name if c.env else None,
            )
        except Exception:
            pass
        return {"status": "ok", "account_id": req.account_id, "trd_env": req.trd_env.upper()}
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
    return {
        "account_id": c.account_id,
        "trd_env": "SIMULATE" if getattr(c, "env", None) == TrdEnv.SIMULATE else "REAL"
    }

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
            "place", mode=(get_setting("bot_mode") or "assist"),
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
            "place", mode=(get_setting("bot_mode") or "assist"),
            symbol=req.symbol, side=side, qty=qty, price=req.price,
            reason="manual/place_order", status="ok", extra={"result": result}
        )
        return {"status": "ok", "result": result}
    except Exception as e:
        insert_action_log(
            "place", mode=(get_setting("bot_mode") or "assist"),
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
        insert_action_log("cancel", mode=(get_setting("bot_mode") or "assist"),
                          symbol=None, side=None, qty=None, price=None,
                          reason=f"cancel {req.order_id}", status="ok", extra={"result": res})
        return res
    except RuntimeError as e:
        insert_action_log("cancel", mode=(get_setting("bot_mode") or "assist"),
                          reason=f"runtime_error {req.order_id}", status="error", extra={"msg": str(e)})
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        insert_action_log("cancel", mode=(get_setting("bot_mode") or "assist"),
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


# --- Sync deals + PnL ---

@app.post("/sync/deals")
def sync_deals(simulate_if_absent: bool = True):
    """
    Pull recent fills from broker and store them locally.

    If the broker (paper trading) does not support deal_list_query, fall back to
    synthesizing fills from orders:
      - Use dealt_avg_price when available
      - Otherwise pull a last close via unified market-data fallback and use that
    This synthetic path is for development/testing only.
    """
    c = get_client()
    if c is None or not c.connected:
        raise HTTPException(status_code=400, detail="Not connected")

    # 1) Try real fills first
    try:
        recs = c.get_deals()
        inserted = 0
        for r in recs:
            oid = r.get("order_id") or r.get("orderId") or ""
            code = r.get("code") or r.get("stock_code") or ""
            side = str(r.get("trd_side") or r.get("side") or "").upper()
            qty = float(r.get("deal_qty") or r.get("qty") or r.get("fill_qty") or 0)
            price = float(r.get("deal_price") or r.get("price") or r.get("fill_price") or 0)
            ts = str(r.get("create_time") or r.get("time") or r.get("ts") or "")
            if not code or not side or qty <= 0 or price <= 0 or not ts:
                continue
            record_fill(str(oid), str(code), "BUY" if "BUY" in side else "SELL", qty, price, ts)
            inserted += 1
        return {"status": "ok", "inserted": inserted, "source": "broker_deals"}
    except RuntimeError as e:
        msg = str(e)

    # 2) Paper trading fallback (orders → fills)
    try_fallback = simulate_if_absent or "Simulated trade does not support deal list" in msg or "deal_list_query" in msg
    if not try_fallback:
        raise HTTPException(status_code=400, detail=msg)

    try:
        orders = c.get_orders()
    except Exception as e2:
        raise HTTPException(status_code=500, detail=f"Failed to fetch orders for fallback: {e2}")

    inserted = 0
    for o in orders:
        status = str(o.get("order_status") or "").upper()
        code = str(o.get("code") or o.get("stock_code") or "")
        side = str(o.get("trd_side") or "").upper()
        oid = str(o.get("order_id") or o.get("orderId") or "")
        qty = float(o.get("qty") or 0)

        if not code or not side or not oid or qty <= 0:
            continue

        price = float(o.get("dealt_avg_price") or 0)
        is_filled = status in {"FILLED", "FILLED_ALL", "DEALT", "SUCCESS"}
        may_synthesize = simulate_if_absent and status in {"SUBMITTED", "SUBMITTING"} and price <= 0

        if price <= 0 and (is_filled or may_synthesize):
            try:
                bars, _source = get_bars_safely(c, code, "K_1M", 1)
                if bars:
                    price = float(bars[-1].get("close", 0) or 0)
            except Exception:
                price = 0.0

        if (is_filled or may_synthesize) and price > 0:
            ts = str(o.get("updated_time") or o.get("create_time") or datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))
            record_fill(oid, code, "BUY" if "BUY" in side else "SELL", qty, price, ts)
            inserted += 1

    return {"status": "ok", "inserted": inserted, "source": "orders_fallback"}

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
    Return current bot autonomy mode (assist|semi|auto). Defaults to 'assist' if unset.
    """
    val = get_setting("bot_mode") or "assist"
    try:
        # Normalize JSON/string to plain string
        if isinstance(val, str):
            try:
                j = json.loads(val)
                if isinstance(j, str):
                    val = j
            except Exception:
                pass
    except Exception:
        pass
    return {"mode": val}

@app.put("/bot/mode")
def bot_mode_put(req: BotModeRequest):
    """
    Update bot autonomy mode.
    """
    mode = (req.mode or "").lower().strip()
    if mode not in {"assist", "semi", "auto"}:
        raise HTTPException(status_code=400, detail="mode must be one of: assist|semi|auto")
    set_setting("bot_mode", mode)
    insert_action_log("mode_change", mode=mode, reason="user_update", status="ok")
    return {"mode": mode}


# --- Action Log API ---

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
        insert_action_log("flatten", mode=(get_setting("bot_mode") or "assist"),
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
            insert_action_log("flatten", mode=(get_setting("bot_mode") or "assist"),
                              symbol=code, side=side, qty=abs(qty),
                              reason="flatten_all", status="ok", extra={"result": res})
        except Exception as e:
            attempts.append({"symbol": code, "qty": abs(qty), "side": side, "status": "error", "error": str(e)})
            insert_action_log("flatten", mode=(get_setting("bot_mode") or "assist"),
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
    insert_action_log("start_strategy", mode=(get_setting("bot_mode") or "assist"),
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
    insert_action_log("update_strategy", mode=(get_setting("bot_mode") or "assist"),
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
    insert_action_log("stop_strategy", mode=(get_setting("bot_mode") or "assist"),
                      reason=f"id={strategy_id}", status="ok")
    return {"status": "ok", "strategy_id": strategy_id, "active": False}

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
    insert_action_log("start_strategy", mode=(get_setting("bot_mode") or "assist"),
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
        changed = []
        for k, v in req.model_dump(exclude_none=True).items():
            cfg[k] = v
            changed.append(k)
        _risk_save(cfg)
        # log update
        insert_action_log("risk_update", mode=(get_setting("bot_mode") or "assist"), status="ok", extra={"fields": changed})
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
    return {
        "saved": s or {},
        "connected": bool(c and getattr(c, "connected", False)),
        "active_account": {
            "account_id": getattr(c, "account_id", None),
            "trd_env": getattr(getattr(c, "env", None), "name", None),
        } if c else None,
    }

@app.post("/session/save")
def session_save_endpoint(body: dict):
    host = body.get("host")
    port = int(body.get("port", 0))
    account_id = body.get("account_id")
    trd_env = body.get("trd_env")
    if not host or not port:
        raise HTTPException(status_code=400, detail="host and port required")
    return {"ok": True, "saved": save_session(host, port, account_id, trd_env)}

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
