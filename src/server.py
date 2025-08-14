from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional
import os

from core.moomoo_client import MoomooClient
from core.futu_client import TrdEnv

from fastapi.middleware.cors import CORSMiddleware

try:
    from core.storage import (
        init_db,
        insert_strategy,
        set_strategy_active,
        get_strategy,
        list_strategies,
        list_runs,
        update_strategy,   # ← added
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
