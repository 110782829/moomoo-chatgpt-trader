from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import os
from typing import Optional
from core.futu_client import MoomooClient

try:
    from futu import TrdEnv  # type: ignore
except ImportError:
    class _DummyTrdEnv:
        SIMULATE = 'SIMULATE'
        REAL = 'REAL'
    TrdEnv = _DummyTrdEnv()  # type: ignore

app = FastAPI(title="Moomoo ChatGPT Trader API")

client: Optional[MoomooClient] = None

class ConnectRequest(BaseModel):
    host: Optional[str] = None
    port: Optional[int] = None
    client_id: Optional[int] = None

class SelectAccountRequest(BaseModel):
    account_id: int
    environment: Optional[str] = 'SIMULATE'

@app.get("/")
def health_check():
    return {"status": "ok"}

@app.post("/connect")
def connect(req: ConnectRequest):
    global client
    host = req.host or os.getenv("MOOMOO_HOST", "127.0.0.1")
    port = req.port or int(os.getenv("MOOMOO_PORT", "11111"))
    # client_id is not currently used by MoomooClient, but we store for potential features
    if client is not None and getattr(client, "connected", False):
        raise HTTPException(status_code=400, detail="Already connected")
    client = MoomooClient(host, port)
    try:
        client.connect()
    except Exception as e:
        client = None
        raise HTTPException(status_code=500, detail=f"Failed to connect: {e}")
    return {"status": "connected", "host": host, "port": port}

@app.get("/accounts")
def list_accounts():
    if client is None or not getattr(client, "connected", False):
        raise HTTPException(status_code=400, detail="Not connected")
    return client.list_accounts()

@app.post("/accounts/select")
def select_account(req: SelectAccountRequest):
    if client is None or not getattr(client, "connected", False):
        raise HTTPException(status_code=400, detail="Not connected")
    env_str = (req.environment or "SIMULATE").upper()
    env = getattr(TrdEnv, env_str, env_str)
    try:
        client.set_account(env, req.account_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"status": "account selected", "account_id": req.account_id, "environment": env_str}

@app.post("/disconnect")
def disconnect():
    global client
    if client is None or not getattr(client, "connected", False):
        return {"status": "not connected"}
    try:
        client.disconnect()
    except Exception:
        pass
    client = None
    return {"status": "disconnected"}
