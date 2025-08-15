from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional
import os

from datetime import datetime
from core.market_data import get_bars_safely
from core.moomoo_client import MoomooClient
from core.futu_client import TrdEnv
from core.session import load_session, save_session, clear_session

from fastapi.middleware.cors import CORSMiddleware

# simple risk config persistence (local file) ---
from pathlib import Path
import json

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

# --------------------------------------------

try:
    from core.storage import (
        init_db,
        insert_strategy,
        set_strategy_active,
        get_strategy,
        list_strategies,
        list_runs,
        update_strategy,
        record_order,
        record_fill,
        pnl_today,
        pnl_history,
    )
    from core.scheduler import TraderScheduler
    from strategies.ma_crossover import step as ma_crossover_step
    _AUTOMATION_AVAILABLE = True
except Exception as _e:
    _AUTOMATION_AVAILABLE = False
    _AUTOMATION_IMPORT_ERR = _e
    TraderScheduler = None  # type: ignore[misc]

try:
    from backtest.engine import load_bars_csv, run_ma_crossover
    _BACKTEST_AVAILABLE = True
except Exception as _be:
    _BACKTEST_AVAILABLE = False
    _BACKTEST_IMPORT_ERR = _be

# backtest grid
try:
    from backtest.grid import run_ma_grid
    _GRID_AVAILABLE = True
except Exception as _ge:
    _GRID_AVAILABLE = False
    _GRID_IMPORT_ERR = _ge

app = FastAPI(title="Moomoo ChatGPT Trader API")

# Enable CORS (loose for now; tighten allow_origins later)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global client instance; created on /connect
client: Optional[MoomooClient] = None

scheduler = None  # will hold TraderScheduler


# ---------- Request Models ----------

class ConnectRequest(BaseModel):
    host: Optional[str] = None
    port: Optional[int] = None
    client_id: Optional[int] = None  # not always required by every build, kept for parity


class SelectAccountRequest(BaseModel):
    account_id: str
    trd_env: str = "SIMULATE"  # "SIMULATE" or "REAL"


class PlaceOrderRequest(BaseModel):
    symbol: str                 # e.g., "AAPL" (we'll normalize to "US.AAPL" in client)
    qty: float
    side: str                   # "BUY" or "SELL"
    order_type: str = "MARKET"  # "MARKET" or "LIMIT"
    price: Optional[float] = None

class CancelOrderRequest(BaseModel):
    order_id: str

class SubscribeQuotesRequest(BaseModel):
    symbols: list[str]

class StartMACrossoverRequest(BaseModel):
    symbol: str              # e.g., "US.AAPL"
    fast: int = 20
    slow: int = 50
    ktype: str = "K_1M"      # bar timeframe; entitlement-dependent
    qty: float = 1
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

# New: risk config model (partial update)
class RiskConfig(BaseModel):
    enabled: Optional[bool] = None
    max_usd_per_trade: Optional[float] = None
    max_open_positions: Optional[int] = None
    max_daily_loss_usd: Optional[float] = None
    symbol_whitelist: Optional[list[str]] = None
    trading_hours_pt: Optional[dict] = None  # {"start":"06:30","end":"13:00"}
    flatten_before_close_min: Optional[int] = None

# New: backtest grid request
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


# ---------- Helpers ----------

def _env_from_str(name: str):
    return TrdEnv.SIMULATE if name.upper() == "SIMULATE" else TrdEnv.REAL


# ---------- App lifecycle (automation) ----------

@app.on_event("startup")
async def _on_startup():
    # Start scheduler if automation modules are importable
    global scheduler
    if _AUTOMATION_AVAILABLE:
        init_db()
        scheduler = TraderScheduler(lambda: client)  # type: ignore[call-arg]
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


@app.post("/connect")
def connect(req: ConnectRequest):
    """
    Connect to the OpenD gateway using host/port from request JSON
    or .env (MOOMOO_HOST/MOOMOO_PORT). Keeps a singleton client.
    """
    global client

    host = req.host or os.getenv("MOOMOO_HOST", "127.0.0.1")
    port = req.port or int(os.getenv("MOOMOO_PORT", "11111"))
    client_id = req.client_id or int(os.getenv("MOOMOO_CLIENT_ID", "1"))

    try:
        client = MoomooClient(host=host, port=port)  # ← no client_id here
        client.connect()
        # persist partial session (account may be None here)
        try:
            save_session(
                host,
                port,
                getattr(client, "account_id", None),
                getattr(client, "env", None).name if getattr(client, "env", None) else None,
            )
        except Exception:
            pass
        return {"status": "connected", "host": host, "port": port}
    except (RuntimeError, TypeError) as e:
        client = None
        raise HTTPException(status_code=400, detail=f"Failed to connect: {e}")
    except Exception as e:
        client = None
        raise HTTPException(status_code=500, detail=f"Failed to connect: {e}")


@app.get("/accounts")
def list_accounts():
    """
    Return available account IDs. Requires an active connection.
    """
    global client
    if client is None or not client.connected:
        raise HTTPException(status_code=400, detail="Not connected")
    try:
        return client.list_accounts()
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list accounts: {e}")


@app.post("/accounts/select")
def select_account(req: SelectAccountRequest):
    """
    Select the active account + env (SIMULATE/REAL).
    """
    global client
    if client is None or not client.connected:
        raise HTTPException(status_code=400, detail="Not connected")
    try:
        env = _env_from_str(req.trd_env)
        client.set_account(req.account_id, env)
        # persist full session
        try:
            save_session(
                client.host,
                client.port,
                client.account_id,
                client.env.name if client.env else None,
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
    global client
    if client is None or not client.connected:
        raise HTTPException(status_code=400, detail="Not connected")
    return {
        "account_id": client.account_id,  # should now be an int
        "trd_env": "SIMULATE" if getattr(client, "env", None) == TrdEnv.SIMULATE else "REAL"
    }


@app.get("/debug/accounts_raw")
def accounts_raw():
    """
    Raw passthrough of get_acc_list to help debug schema/signature differences.
    """
    global client
    if client is None or not client.connected:
        raise HTTPException(status_code=400, detail="Not connected")
    try:
        ret, df = client.trading_ctx.get_acc_list(trd_env=client.env)  # type: ignore[attr-defined]
    except TypeError:
        ret, df = client.trading_ctx.get_acc_list()  # type: ignore[attr-defined]
    if ret != 0:
        raise HTTPException(status_code=500, detail=f"get_acc_list failed: {df}")
    try:
        import pandas as pd
        if isinstance(df, pd.DataFrame):
            return df.to_dict(orient="records")
    except Exception:
        pass
    return df


@app.get("/positions")
def get_positions():
    """
    Return current positions for the active account.
    """
    global client
    if client is None or not client.connected:
        raise HTTPException(status_code=400, detail="Not connected")
    try:
        return client.get_positions()
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get positions: {e}")


@app.get("/orders")
def get_orders():
    """
    Return orders for the active account.
    """
    global client
    if client is None or not client.connected:
        raise HTTPException(status_code=400, detail="Not connected")
    try:
        return client.get_orders()
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get orders: {e}")


@app.get("/orders/{order_id}")
def get_order(order_id: str):
    """
    Return a single order by ID.
    """
    global client
    if client is None or not client.connected:
        raise HTTPException(status_code=400, detail="Not connected")
    try:
        return client.get_order(order_id)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get order: {e}")


@app.post("/orders/place")
def place_order(req: PlaceOrderRequest):
    """
    Place a market or limit order for the active account.
    """
    global client
    if client is None or not client.connected:
        raise HTTPException(status_code=400, detail="Not connected")
    try:
        result = client.place_order(
            symbol=req.symbol,
            qty=req.qty,
            side=req.side,
            order_type=req.order_type,
            price=req.price,
        )
        return result
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to place order: {e}")


@app.post("/orders/cancel")
def cancel_order(req: CancelOrderRequest):
    """
    Cancel an order by ID.
    """
    global client
    if client is None or not client.connected:
        raise HTTPException(status_code=400, detail="Not connected")
    try:
        return client.cancel_order(req.order_id)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to cancel order: {e}")


# ---------- Quotes ----------

@app.post("/quotes/subscribe")
def quotes_subscribe(req: SubscribeQuotesRequest):
    """
    Subscribe to basic quotes for one or more symbols.
    """
    global client
    if client is None or not client.connected:
        raise HTTPException(status_code=400, detail="Not connected")
    try:
        return client.subscribe_quotes(req.symbols)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to subscribe quotes: {e}")


@app.get("/quotes/{symbol}")
def quotes_latest(symbol: str):
    """
    Get the latest quote for a symbol.
    """
    global client
    if client is None or not client.connected:
        raise HTTPException(status_code=400, detail="Not connected")
    try:
        return client.get_quote_latest(symbol)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get quote: {e}")


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
    global client
    if client is None or not client.connected:
        raise HTTPException(status_code=400, detail="Not connected")

    # 1) Try real fills first
    try:
        recs = client.get_deals()
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
    # Only do this if explicitly allowed (default True) or message suggests no deal support
    try_fallback = simulate_if_absent or "Simulated trade does not support deal list" in msg or "deal_list_query" in msg
    if not try_fallback:
        raise HTTPException(status_code=400, detail=msg)

    try:
        orders = client.get_orders()
    except Exception as e2:
        raise HTTPException(status_code=500, detail=f"Failed to fetch orders for fallback: {e2}")

    inserted = 0
    for o in orders:
        status = str(o.get("order_status") or "").upper()
        code = str(o.get("code") or o.get("stock_code") or "")
        side = str(o.get("trd_side") or "").upper()
        oid = str(o.get("order_id") or o.get("orderId") or "")
        qty = float(o.get("qty") or 0)

        # Skip if critical fields are missing
        if not code or not side or not oid or qty <= 0:
            continue

        # Determine a “filled” price
        price = float(o.get("dealt_avg_price") or 0)
        # Consider these statuses as filled; SUBMITTED can be synthesized if simulate_if_absent
        is_filled = status in {"FILLED", "FILLED_ALL", "DEALT", "SUCCESS"}
        may_synthesize = simulate_if_absent and status in {"SUBMITTED", "SUBMITTING"} and price <= 0

        if price <= 0 and (is_filled or may_synthesize):
            # Pull a last close from unified market-data (futu → yfinance fallback)
            try:
                bars, source = get_bars_safely(client, code, "K_1M", 1)
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


# ---------- Automation: Strategies ----------


@app.post("/automation/start/ma-crossover")
def automation_start_ma(req: StartMACrossoverRequest):
    """
    Start an MA crossover strategy instance (persisted in SQLite; picked up by scheduler).
    """
    global client, scheduler
    if not _AUTOMATION_AVAILABLE:
        raise HTTPException(
            status_code=500,
            detail=f"Automation modules not available: {_AUTOMATION_IMPORT_ERR}",
        )
    if client is None or not client.connected:
        raise HTTPException(status_code=400, detail="Not connected")
    if scheduler is None:
        raise HTTPException(status_code=500, detail="Scheduler not available")
    if req.slow <= req.fast:
        raise HTTPException(status_code=400, detail="slow must be > fast")

    params = {
        "fast": int(req.fast),
        "slow": int(req.slow),
        "ktype": req.ktype,
        "qty": float(req.qty),
        "allow_real": bool(req.allow_real),
    }
    sid = insert_strategy("ma_crossover", req.symbol.strip(), params, int(req.interval_sec))
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

    # collect params to update (only non-None)
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
    return {"status": "ok", "strategy_id": strategy_id, "active": True}


# ---------- Risk config & status ----------

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
    global client
    cfg = _risk_load()
    open_positions = None
    try:
        if client and client.connected:
            pos = client.get_positions()
            if isinstance(pos, list):
                open_positions = len(pos)
    except Exception:
        pass
    return {"ok": True, "config": cfg, "open_positions": open_positions}


@app.post("/disconnect")
def disconnect():
    """
    Disconnect and clear the global client.
    """
    global client
    if client is None:
        return {"status": "ok"}  # already clear
    try:
        client.disconnect()
    except Exception:
        # Ignore errors on shutdown, just clear
        pass
    client = None
    return {"status": "disconnected"}


# ---------- Backtest: single run ----------

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
        # keep the response small
        trades = [{
            "entry_ts": t.entry_ts, "exit_ts": t.exit_ts, "side": t.side,
            "entry_px": t.entry_px, "exit_px": t.exit_px, "qty": t.qty, "pnl": t.pnl
        } for t in res.trades[:20]]
        return {"metrics": res.metrics, "trades_sample": trades}
    except FileNotFoundError as e:
        raise HTTPException(status_code=400, detail=f"{e}. Put a CSV at data/bars/{req.symbol.split('.')[-1].upper()}_{req.ktype}.csv with columns time,open,high,low,close,volume")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Backtest failed: {e}")


# ---------- Backtest: parameter grid ----------

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
        raise HTTPException(status_code=400, detail=f"{e}. Put a CSV at data/bars/{req.symbol.split('.')[-1].upper()}_{req.ktype}.csv")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Backtest grid failed: {e}")

# ------------- Session --------------

@app.get("/session/status")
def session_status():
    s = load_session()
    return {
        "saved": s or {},
        "connected": bool(client and getattr(client, "connected", False)),
        "active_account": {
            "account_id": getattr(client, "account_id", None),
            "trd_env": getattr(getattr(client, "env", None), "name", None),
        } if client else None,
    }


@app.post("/session/save")
def session_save(body: dict):
    host = body.get("host")
    port = int(body.get("port", 0))
    account_id = body.get("account_id")
    trd_env = body.get("trd_env")
    if not host or not port:
        raise HTTPException(status_code=400, detail="host and port required")
    return {"ok": True, "saved": save_session(host, port, account_id, trd_env)}


@app.post("/session/clear")
def session_clear():
    clear_session()
    return {"ok": True}
