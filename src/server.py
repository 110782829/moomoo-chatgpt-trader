from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional

import os

from core.moomoo_client import MoomooClient
from core.futu_client import TrdEnv

app = FastAPI(title="Moomoo ChatGPT Trader API")

# Global client instance; created on /connect
client: Optional[MoomooClient] = None


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


# ---------- Helpers ----------

def _env_from_str(name: str):
    return TrdEnv.SIMULATE if name.upper() == "SIMULATE" else TrdEnv.REAL


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
    global client
    if client is None or not client.connected:
        raise HTTPException(status_code=400, detail="Not connected")
    return {
        "account_id": client.account_id,  # should now be an int
        "trd_env": "SIMULATE" if getattr(client, "env", None) == TrdEnv.SIMULATE else "REAL"
    }

@app.get("/debug/accounts_raw")
def accounts_raw():
    global client
    if client is None or not client.connected:
        raise HTTPException(status_code=400, detail="Not connected")
    # Direct passthrough of whatever Futu returns, to confirm shapes
    try:
        # try preferred signature first
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
