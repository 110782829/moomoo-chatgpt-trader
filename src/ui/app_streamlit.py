# src/ui/app_streamlit.py
"""
Streamlit UI app for controlling the trading bot.
"""

import time
import json
import math
import os
import pandas as pd
from datetime import datetime, time as dtime, timezone

import requests
import streamlit as st

# ---------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------
API_BASE = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")


# ---------- Backend helpers ----------
def connect_backend(host, port, client_id):
    return requests.post(f"{API_BASE}/connect", json={
        "host": host, "port": port, "client_id": client_id
    }, timeout=15).json()

def select_account(account_id, trd_env):
    return requests.post(f"{API_BASE}/accounts/select", json={
        "account_id": account_id, "trd_env": trd_env
    }, timeout=15).json()

def get_positions():
    return requests.get(f"{API_BASE}/positions", timeout=15).json()

def get_orders():
    return requests.get(f"{API_BASE}/orders", timeout=15).json()

def place_order(symbol, qty, side, order_type="MARKET", price=None):
    payload = {"symbol": symbol, "qty": qty, "side": side, "order_type": order_type}
    if price is not None:
        payload["price"] = price
    return requests.post(f"{API_BASE}/orders/place", json=payload, timeout=20).json()

def cancel_order(order_id):
    return requests.post(f"{API_BASE}/orders/cancel", json={"order_id": order_id}, timeout=15).json()

def risk_get():
    return requests.get(f"{API_BASE}/risk/config", timeout=15).json()

def risk_put(cfg):
    return requests.put(f"{API_BASE}/risk/config", json=cfg, timeout=20).json()

def risk_status():
    return requests.get(f"{API_BASE}/risk/status", timeout=15).json()

def list_strategies():
    return requests.get(f"{API_BASE}/automation/strategies", timeout=15).json()

def start_ma(payload):
    return requests.post(f"{API_BASE}/automation/start/ma-crossover", json=payload, timeout=20).json()

def strat_by_id(strategy_id: int):
    return requests.get(f"{API_BASE}/automation/strategies/{strategy_id}", timeout=15).json()

def runs_for_strategy(strategy_id: int, limit: int = 25):
    return requests.get(f"{API_BASE}/automation/strategies/{strategy_id}/runs?limit={limit}", timeout=15).json()

def strat_update(strategy_id: int, payload: dict):
    return requests.patch(f"{API_BASE}/automation/strategies/{strategy_id}", json=payload, timeout=20).json()

def strat_start(strategy_id: int):
    return requests.post(f"{API_BASE}/automation/start/{strategy_id}", timeout=15).json()

def strat_stop(strategy_id: int):
    return requests.post(f"{API_BASE}/automation/stop/{strategy_id}", timeout=15).json()

def bt_ma(payload):
    return requests.post(f"{API_BASE}/backtest/ma-crossover", json=payload, timeout=60).json()

def bt_grid(payload):
    return requests.post(f"{API_BASE}/backtest/ma-grid", json=payload, timeout=120).json()

def session_status():
    return requests.get(f"{API_BASE}/session/status", timeout=15).json()

def session_save(host, port, account_id, trd_env):
    return requests.post(f"{API_BASE}/session/save", json={
        "host": host, "port": port, "account_id": account_id, "trd_env": trd_env
    }, timeout=15).json()

def session_clear():
    return requests.post(f"{API_BASE}/session/clear", timeout=15).json()


# ---------- Latest price with broker→yfinance fallback ----------
def latest_price(symbol: str) -> tuple[float | None, str]:
    """Return (price, source). Tries broker /quotes/{symbol}, falls back to yfinance."""
    # try broker first
    try:
        r = requests.get(f"{API_BASE}/quotes/{symbol}", timeout=10)
        if r.ok:
            j = r.json()
            for k in ("last", "last_price", "price", "close"):
                if k in j and j[k] not in (None, "", 0):
                    return float(j[k]), "broker"
    except Exception:
        pass

    # fallback to yfinance
    try:
        import yfinance as yf
        yf_sym = symbol.split(".")[-1] if "." in symbol else symbol
        df = yf.download(yf_sym, period="1d", interval="1m", progress=False, threads=False)
        if df is not None and not df.empty:
            return float(df["Close"].dropna().iloc[-1]), "yfinance"
    except Exception:
        pass

    return None, "n/a"


# ---------- Small helpers used by UI ----------
def in_flatten_window(cfg: dict) -> bool:
    try:
        flat_min = int(cfg.get("flatten_before_close_min", 0))
        end = str(cfg.get("trading_hours_pt", {}).get("end", "13:00"))
        now_str = datetime.now().strftime("%H:%M")
        def mins(hhmm: str):
            h, m = [int(x) for x in hhmm.split(":")]
            return h * 60 + m
        return mins(end) - mins(now_str) <= flat_min
    except Exception:
        return False

def market_open_now(cfg: dict) -> bool:
    try:
        start = str(cfg.get("trading_hours_pt", {}).get("start", "06:30"))
        end = str(cfg.get("trading_hours_pt", {}).get("end", "13:00"))
        now_str = datetime.now().strftime("%H:%M")
        return start <= now_str <= end
    except Exception:
        return True  # UI hint only

def _yf_fetch_close(symbol: str, interval: str, rows: int):
    """Return (DataFrame with Close + index, error_str)."""
    try:
        import yfinance as yf
    except Exception as e:
        return None, f"yfinance not installed: {e}"

    i_map = {"1m":"1m","5m":"5m","15m":"15m","30m":"30m","1h":"60m","1d":"1d"}
    yf_int = i_map.get(interval, "1m")
    p_map = {"1m":"7d","5m":"60d","15m":"60d","30m":"60d","60m":"730d","1d":"5y"}
    period = p_map.get(yf_int, "7d")

    try:
        df = yf.download(symbol, period=period, interval=yf_int, auto_adjust=True, progress=False)
    except Exception as e:
        return None, f"yfinance download failed: {e}"
    if df is None or df.empty:
        return None, "No data returned from yfinance."

    # normalize Close
    try:
        if isinstance(df.columns, pd.MultiIndex):
            close = df["Close"]
            if isinstance(close, pd.DataFrame):
                close = close.iloc[:, 0]
        else:
            close = df["Close"]
    except KeyError:
        return None, "Close column not found in data."

    out = pd.DataFrame({"Close": pd.to_numeric(close, errors="coerce")}).dropna()
    out = out.tail(int(rows))
    if out.empty:
        return None, "Data empty after trimming."
    return out, None


# ---------------------------------------------------------------------
# Main app
# ---------------------------------------------------------------------
def main():
    st.set_page_config(page_title="Moomoo ChatGPT Trading Bot", layout="wide")
    st.title("Moomoo ChatGPT Trading Bot")

    # ----- Sidebar: Backend Connection -----
    st.sidebar.header("Backend Connection")
    host = st.sidebar.text_input("Host", "127.0.0.1", key="sb_host")
    port = st.sidebar.number_input("Port", value=11111, key="sb_port")
    client_id = st.sidebar.number_input("Client ID", value=1, key="sb_client_id")
    if st.sidebar.button("Connect to Backend", key="btn_connect_backend"):
        st.sidebar.write(connect_backend(host, port, client_id))

    if st.sidebar.button("Save Session", key="btn_save_session"):
        st.sidebar.write(session_save(
            host, port,
            st.session_state.get("last_account_id", ""),
            st.session_state.get("last_trd_env", "")
        ))

    if st.sidebar.button("Reconnect (from saved)", key="btn_reconnect_saved"):
        try:
            s = session_status().get("saved", {})
            if not s or not s.get("host") or not s.get("port"):
                st.sidebar.error("No saved session.")
            else:
                c1 = connect_backend(s["host"], s["port"], 1)
                st.sidebar.write(c1)
                if s.get("account_id") and s.get("trd_env"):
                    c2 = select_account(str(s["account_id"]), str(s["trd_env"]))
                    st.sidebar.write(c2)
        except Exception as e:
            st.sidebar.error(f"Reconnect failed: {e}")

    if st.sidebar.button("Clear Saved Session", key="btn_clear_session"):
        st.sidebar.write(session_clear())

    # ----- Sidebar: Account Selection -----
    st.sidebar.header("Account Selection")
    account_id = st.sidebar.text_input("Account ID", "54871", key="sb_account_id")
    trd_env = st.sidebar.selectbox("Trading Env", ["SIMULATE", "REAL"], key="sb_trd_env")
    if st.sidebar.button("Select Account", key="btn_select_account"):
        resp = select_account(account_id, trd_env)
        st.sidebar.write(resp)
        st.session_state["last_account_id"] = account_id
        st.session_state["last_trd_env"] = trd_env

    # ----- Top status bar -----
    col_a, col_b, col_c = st.columns([1, 1, 2], gap="small")
    try:
        acct_resp = requests.get(f"{API_BASE}/accounts/active", timeout=2)
        acct_json = acct_resp.json() if acct_resp.ok else {}
        with col_a:
            st.metric("Account", acct_json.get("account_id", "—"))
            st.caption(acct_json.get("trd_env", ""))
    except Exception:
        with col_a:
            st.metric("Account", "—")

    try:
        rstat = risk_status()
        cfg = rstat.get("config", {}) if isinstance(rstat, dict) else {}
        with col_b:
            st.metric("Risk", "ENABLED" if cfg.get("enabled") else "OFF")
            st.caption(f"max ${cfg.get('max_usd_per_trade', '—')} / trade")
        with col_c:
            opn = rstat.get("open_positions", None)
            st.metric("Open Positions", opn if opn is not None else "—")
            st.caption("From /positions")
    except Exception:
        with col_b:
            st.metric("Risk", "—")
        with col_c:
            st.metric("Open Positions", "—")

    st.divider()

    # ---------- Tabs ----------
    tabs = st.tabs(["Dashboard", "Trading", "Strategies", "Backtests", "Risk", "Charts", "Session"])

    # ===== Dashboard =====
    with tabs[0]:
        st.subheader("Overview")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Refresh Positions", key="btn_dash_positions"):
                st.json(get_positions())
        with c2:
            if st.button("Refresh Orders", key="btn_dash_orders"):
                st.json(get_orders())

    # ===== Trading =====
    with tabs[1]:
        st.subheader("Trader Console")

        # --- Live quote + mini MA overlay (yfinance fallback) ---
        qc1, qc2 = st.columns([1, 2])
        with qc1:
            q_symbol = st.text_input("Quote Symbol", "US.AAPL", key="q_symbol")
            if st.button("Get Quote", key="btn_get_quote"):
                px, src = latest_price(q_symbol)
                if px is None:
                    st.error("No price available.")
                else:
                    st.metric("Last Price", f"{px:.2f}", help=f"Source: {src}")
            st.caption("Broker is tried first; falls back to yfinance.")

        with qc2:
            with st.expander("Mini chart (yfinance)", expanded=False):
                col_a, col_b, col_c, col_d, col_e = st.columns([1.2, 0.9, 0.9, 0.9, 0.8])
                with col_a:
                    mini_sym = st.text_input("Symbol", "AAPL", key="mini_sym")
                with col_b:
                    mini_int = st.selectbox("Interval", ["1m", "5m", "15m", "30m", "1h", "1d"], index=1, key="mini_int")
                with col_c:
                    mini_fast = st.number_input("Fast MA", min_value=2, value=20, step=1, key="mini_fast")
                with col_d:
                    mini_slow = st.number_input("Slow MA", min_value=3, value=50, step=1, key="mini_slow")
                with col_e:
                    mini_rows = st.number_input("Rows", min_value=50, value=400, step=50, key="mini_rows")

                if st.button("Load Chart", key="btn_load_mini_chart"):
                    df, err = _yf_fetch_close(mini_sym.strip(), mini_int, int(mini_rows))
                    if err:
                        st.warning(f"Chart unavailable: {err}. Install yfinance in venv.")
                    else:
                        if len(df) < max(mini_fast, mini_slow):
                            st.info(
                                f"Not enough rows ({len(df)}) for slow MA={mini_slow}. "
                                f"Increase Rows or lower MA windows."
                            )
                        df["fast"] = df["Close"].rolling(window=int(mini_fast), min_periods=1).mean()
                        df["slow"] = df["Close"].rolling(window=int(mini_slow), min_periods=1).mean()
                        st.line_chart(df[["Close", "fast", "slow"]])

        st.divider()

        # --- Quick Order panel (shares or USD sizing, risk blocks inline) ---
        st.markdown("**Quick Order**")
        to_col1, to_col2, to_col3, to_col4 = st.columns([1.2, 0.8, 0.8, 1.2])
        with to_col1:
            po_symbol = st.text_input("Symbol", "US.AAPL", key="po_symbol")
        with to_col2:
            size_mode = st.selectbox("Size Mode", ["shares", "usd"], key="po_size_mode")
        with to_col3:
            po_side = st.selectbox("Side", ["BUY", "SELL"], key="po_side")
        with to_col4:
            po_type = st.selectbox("Order Type", ["MARKET", "LIMIT"], key="po_type")

        if size_mode == "shares":
            qty_input = st.number_input("Qty (shares)", value=1.0, min_value=0.0, step=1.0, key="po_qty_shares")
            dollar_input = None
        else:
            dollar_input = st.number_input("Notional ($)", value=100.0, min_value=0.0, step=10.0, key="po_qty_usd")
            qty_input = None

        po_price = None
        if po_type == "LIMIT":
            po_price = st.number_input("Limit Price", value=0.0, step=0.01, key="po_price")

        cfg = {}
        try:
            rstat = risk_status()
            cfg = rstat.get("config", {}) if isinstance(rstat, dict) else {}
        except Exception:
            cfg = {}

        max_usd = float(cfg.get("max_usd_per_trade", 0) or 0)
        flatten_block = in_flatten_window(cfg)
        mkt_open = market_open_now(cfg)

        est_qty = qty_input or 0
        est_cost = None
        price_hint = None
        if size_mode == "usd":
            px, _src = latest_price(po_symbol)
            price_hint = px
            if px:
                shares = math.floor((dollar_input or 0) / px)
                est_qty = float(max(0, shares))
                est_cost = (dollar_input or 0)

        rcols = st.columns(3)
        with rcols[0]:
            st.info(f"Market: {'OPEN' if mkt_open else 'CLOSED'}")
        with rcols[1]:
            st.info(f"Flatten window: {'YES' if flatten_block else 'NO'}")
        with rcols[2]:
            if size_mode == "usd":
                st.info(f"Cost: ${est_cost or 0:.2f} (limit ${max_usd or 0:.2f})")
            else:
                st.info(f"Qty: {est_qty:.0f}  Price ref: {price_hint or '—'}")

        if st.button("Place Order", key="btn_place_order"):
            if flatten_block and po_side == "BUY":
                st.error("Blocked by risk: within flatten window; new longs disabled.")
            elif size_mode == "usd" and (price_hint is None or est_qty <= 0):
                st.error("Unable to compute shares from $ notional. Check price/inputs.")
            elif max_usd and size_mode == "usd" and (est_cost or 0) > max_usd:
                st.error("Blocked by risk: exceeds max $ per trade.")
            else:
                st.write(place_order(po_symbol, float(est_qty), po_side, po_type, po_price))

        st.divider()

        # --- Positions table with Close actions ---
        st.markdown("**Positions**")
        _raw_pos = None
        try:
            _raw_pos = get_positions()
        except Exception as e:
            st.error(f"Positions error: {e}")
            _raw_pos = []

        pos: list[dict] = []
        if isinstance(_raw_pos, list):
            pos = [x for x in _raw_pos if isinstance(x, dict)]
        elif isinstance(_raw_pos, dict):
            if "detail" in _raw_pos and isinstance(_raw_pos["detail"], str):
                st.warning(_raw_pos["detail"])
            else:
                pos = [_raw_pos]
        elif _raw_pos in (None, "", "[]"):
            pos = []
        else:
            st.warning(f"Unexpected positions payload type: {type(_raw_pos).__name__}")
            pos = []

        if not pos:
            st.caption("No positions.")
        else:
            for i, p in enumerate(pos):
                code = p.get("code") or p.get("symbol") or "—"
                qty = float(
                    p.get("qty")
                    or p.get("qty_today")
                    or p.get("qty_total", 0)
                    or 0
                )
                pnl = p.get("pnl") or p.get("pl_val") or p.get("profit", 0)

                row = st.columns([1.2, 0.8, 0.8, 1])
                with row[0]:
                    st.write(code)
                with row[1]:
                    st.write(f"Qty: {qty:g}")
                with row[2]:
                    st.write(f"PnL: {pnl}")
                with row[3]:
                    if qty != 0:
                        side = "SELL" if qty > 0 else "BUY"
                        if st.button("Close", key=f"btn_close_{i}_{code}"):
                            st.write(place_order(code, abs(qty), side, "MARKET"))
                    else:
                        st.write("—")

        st.divider()

        # --- Orders table with Cancel + status chips ---
        st.markdown("**Orders**")
        _raw_orders = None
        try:
            _raw_orders = get_orders()
        except Exception as e:
            st.error(f"Orders error: {e}")
            _raw_orders = []

        orders: list[dict] = []
        if isinstance(_raw_orders, list):
            orders = [x for x in _raw_orders if isinstance(x, dict)]
        elif isinstance(_raw_orders, dict):
            if "detail" in _raw_orders and isinstance(_raw_orders["detail"], str):
                st.warning(_raw_orders["detail"])
            else:
                orders = [_raw_orders]
        elif _raw_orders in (None, "", "[]"):
            orders = []
        else:
            st.warning(f"Unexpected orders payload type: {type(_raw_orders).__name__}")
            orders = []

        if not orders:
            st.caption("No orders.")
        else:
            for od in orders:
                oc = st.columns([1.1, 0.8, 0.9, 0.9, 0.9])
                with oc[0]:
                    st.write(od.get("code", "—"))
                with oc[1]:
                    st.write(od.get("trd_side", "—"))
                with oc[2]:
                    st.write(od.get("order_type", "—"))
                with oc[3]:
                    st.write(od.get("order_status", "—"))
                with oc[4]:
                    oid = str(od.get("order_id", "") or "")
                    if oid and st.button("Cancel", key=f"btn_cancel_{oid}"):
                        st.write(cancel_order(oid))

    # ===== Strategies =====
    with tabs[2]:
        st.header("Automation — MA Crossover")
        with st.expander("Start MA Crossover Strategy", expanded=False):
            s_symbol = st.text_input("Symbol", "US.AAPL", key="ma_symbol")
            s_fast = st.number_input("Fast MA", value=20, min_value=1, step=1, key="ma_fast")
            s_slow = st.number_input("Slow MA", value=50, min_value=2, step=1, key="ma_slow")
            s_ktype = st.text_input("KType (bar timeframe)", "K_1M", key="ma_ktype")
            s_qty = st.number_input("Qty", value=1.0, min_value=0.0, step=1.0, key="ma_qty")
            s_interval = st.number_input("Interval (sec)", value=15, min_value=1, step=1, key="ma_interval")
            s_allow_real = st.checkbox("Allow Real Trading", value=False, key="ma_allow_real")
            if st.button("Start Strategy", key="btn_start_ma"):
                payload = {
                    "symbol": s_symbol, "fast": int(s_fast), "slow": int(s_slow),
                    "ktype": s_ktype, "qty": float(s_qty),
                    "interval_sec": int(s_interval), "allow_real": bool(s_allow_real),
                }
                r = start_ma(payload)
                st.json(r)

        with st.expander("Manage Strategies", expanded=False):
            c1, c2 = st.columns(2)
            with c1:
                if st.button("List Strategies", key="btn_list_strat"):
                    st.session_state["strategies"] = list_strategies()
                st.json(st.session_state.get("strategies", []))
            with c2:
                strat_id_in = st.text_input("Strategy ID", "", key="strat_id_in")
                cc1, cc2, cc3 = st.columns(3)
                with cc1:
                    if st.button("Start", key="btn_start_id") and strat_id_in.strip():
                        st.json(strat_start(int(strat_id_in)))
                with cc2:
                    if st.button("Stop", key="btn_stop_id") and strat_id_in.strip():
                        st.json(strat_stop(int(strat_id_in)))
                with cc3:
                    limit = st.number_input("Rows", value=20, step=5, key="runs_limit")
                    if st.button("Recent Runs", key="btn_runs") and strat_id_in.strip():
                        st.json(runs_for_strategy(int(strat_id_in), int(limit)))

        st.header("Edit Strategy")
        with st.expander("Load + Edit", expanded=False):
            es_id = st.text_input("Strategy ID", "", key="edit_strategy_id")
            if st.button("Load Strategy", key="btn_load_strategy") and es_id.strip():
                st.session_state["edit_strategy"] = strat_by_id(int(es_id))
            s = st.session_state.get("edit_strategy")
            if s:
                s_params = s.get("params", {})
                col1, col2, col3 = st.columns(3)
                with col1:
                    es_fast = st.number_input("Fast", value=int(s_params.get("fast", 20)), step=1, key="es_fast")
                    es_ktype = st.text_input("KType", value=str(s_params.get("ktype", "K_1M")), key="es_ktype")
                    es_size_mode = st.selectbox("Size Mode", ["shares","usd"],
                                                index=0 if s_params.get("size_mode","shares")=="shares" else 1,
                                                key="es_size_mode")
                with col2:
                    es_slow = st.number_input("Slow", value=int(s_params.get("slow", 50)), step=1, key="es_slow")
                    es_qty = st.number_input("Qty (shares)", value=float(s_params.get("qty", 1.0)), step=1.0, key="es_qty")
                    es_dollar = st.number_input("Dollar Size", value=float(s_params.get("dollar_size", 0.0)), step=10.0, key="es_dollar")
                with col3:
                    es_sl = st.number_input("Stop Loss %", value=float(s_params.get("stop_loss_pct", 0.0)), step=0.01, format="%.4f", key="es_sl")
                    es_tp = st.number_input("Take Profit %", value=float(s_params.get("take_profit_pct", 0.0)), step=0.01, format="%.4f", key="es_tp")
                    es_allow_real = st.checkbox("Allow Real", value=bool(s_params.get("allow_real", False)), key="es_allow_real")

                es_interval = st.number_input("Interval (sec)", value=int(s.get("interval_sec", 15)), step=1, key="es_interval")
                es_active = st.checkbox("Active", value=bool(s.get("active", True)), key="es_active")

                if st.button("Save Changes", key="btn_save_strategy"):
                    payload = {
                        "fast": int(es_fast), "slow": int(es_slow), "ktype": es_ktype,
                        "qty": float(es_qty), "size_mode": es_size_mode, "dollar_size": float(es_dollar),
                        "stop_loss_pct": float(es_sl), "take_profit_pct": float(es_tp),
                        "allow_real": bool(es_allow_real),
                        "interval_sec": int(es_interval), "active": bool(es_active),
                    }
                    st.json(strat_update(int(es_id), payload))

    # ===== Backtests =====
    with tabs[3]:
        st.header("Backtest — MA Crossover")
        with st.expander("Run Backtest", expanded=False):
            bt_symbol = st.text_input("Symbol", "US.AAPL", key="bt_symbol")
            bt_fast = st.number_input("Fast", value=20, step=1, key="bt_fast")
            bt_slow = st.number_input("Slow", value=50, step=1, key="bt_slow")
            bt_ktype = st.text_input("KType", "K_1M", key="bt_ktype")
            bt_qty = st.number_input("Qty (shares)", value=1.0, step=1.0, key="bt_qty")
            bt_mode = st.selectbox("Size Mode", ["shares","usd"], index=0, key="bt_mode")
            bt_dol = st.number_input("Dollar Size", value=0.0, step=10.0, key="bt_dol")
            bt_sl = st.number_input("Stop Loss %", value=0.0, step=0.01, format="%.4f", key="bt_sl")
            bt_tp = st.number_input("Take Profit %", value=0.0, step=0.01, format="%.4f", key="bt_tp")
            bt_comm = st.number_input("Commission / share", value=0.0, step=0.001, format="%.4f", key="bt_comm")
            bt_slip = st.number_input("Slippage (bps)", value=0.0, step=1.0, key="bt_slip")
            if st.button("Run Backtest", key="btn_bt_run"):
                payload = {
                    "symbol": bt_symbol, "fast": int(bt_fast), "slow": int(bt_slow),
                    "ktype": bt_ktype, "qty": float(bt_qty), "size_mode": bt_mode,
                    "dollar_size": float(bt_dol), "stop_loss_pct": float(bt_sl),
                    "take_profit_pct": float(bt_tp), "commission_per_share": float(bt_comm),
                    "slippage_bps": float(bt_slip),
                }
                st.json(bt_ma(payload))

        st.header("Backtest — Grid Search")
        with st.expander("MA Grid Sweep", expanded=False):
            gs_symbol = st.text_input("Symbol", "US.AAPL", key="gs_symbol")
            gs_ktype = st.text_input("KType", "K_1M", key="gs_ktype")
            colA, colB, colC = st.columns(3)
            with colA:
                gs_fast_min = st.number_input("fast_min", value=5, step=1, key="gs_fast_min")
                gs_fast_max = st.number_input("fast_max", value=30, step=1, key="gs_fast_max")
                gs_fast_step = st.number_input("fast_step", value=5, step=1, key="gs_fast_step")
            with colB:
                gs_slow_min = st.number_input("slow_min", value=40, step=1, key="gs_slow_min")
                gs_slow_max = st.number_input("slow_max", value=200, step=1, key="gs_slow_max")
                gs_slow_step = st.number_input("slow_step", value=10, step=1, key="gs_slow_step")
            with colC:
                gs_qty = st.number_input("Qty (shares)", value=1.0, step=1.0, key="gs_qty")
                gs_top_n = st.number_input("Top N", value=10, step=1, key="gs_top_n")
            if st.button("Run Grid", key="btn_grid"):
                payload = {
                    "symbol": gs_symbol, "ktype": gs_ktype,
                    "fast_min": int(gs_fast_min), "fast_max": int(gs_fast_max), "fast_step": int(gs_fast_step),
                    "slow_min": int(gs_slow_min), "slow_max": int(gs_slow_max), "slow_step": int(gs_slow_step),
                    "qty": float(gs_qty), "top_n": int(gs_top_n),
                }
                st.session_state["grid_results"] = bt_grid(payload)
                st.json(st.session_state.get("grid_results", {}))

    # ===== Risk =====
    with tabs[4]:
        st.header("Risk Manager")
        with st.expander("View / Update Risk Config", expanded=False):
            if st.button("Load Config", key="btn_risk_load"):
                st.session_state["risk_cfg"] = risk_get()
            cfg_view = st.session_state.get("risk_cfg", {})
            st.json(cfg_view)

            if isinstance(cfg_view, dict):
                trow = st.columns(3)
                with trow[0]:
                    st.info(f"Market open now: {'YES' if market_open_now(cfg_view) else 'NO'}")
                with trow[1]:
                    st.info(f"In flatten window: {'YES' if in_flatten_window(cfg_view) else 'NO'}")
                with trow[2]:
                    st.info(f"Max $/trade: {cfg_view.get('max_usd_per_trade', '—')}")

            col1, col2, col3 = st.columns(3)
            with col1:
                r_enabled = st.checkbox("Enabled", value=True, key="r_enabled")
                r_max_usd = st.number_input("Max $ per trade", value=1000.0, step=50.0, key="r_max_usd")
            with col2:
                r_max_pos = st.number_input("Max open positions", value=5, step=1, key="r_max_pos")
                r_max_dd = st.number_input("Max daily loss ($)", value=200.0, step=10.0, key="r_max_dd")
            with col3:
                r_start = st.text_input("Start (PT)", "06:30", key="r_start")
                r_end = st.text_input("End (PT)", "13:00", key="r_end")
                r_flat_min = st.number_input("Flatten before close (min)", value=5, step=1, key="r_flat_min")

            if st.button("Save Config", key="btn_risk_save"):
                payload = {
                    "enabled": bool(r_enabled),
                    "max_usd_per_trade": float(r_max_usd),
                    "max_open_positions": int(r_max_pos),
                    "max_daily_loss_usd": float(r_max_dd),
                    "trading_hours_pt": {"start": r_start, "end": r_end},
                    "flatten_before_close_min": int(r_flat_min),
                }
                st.json(risk_put(payload))

    # ===== Charts =====
    with tabs[5]:
        st.header("Chart — Price & MAs (yfinance)")
        with st.expander("Preview recent bars and MAs", expanded=False):
            ch_symbol = st.text_input("Symbol", "AAPL", key="ch_sym")
            ch_interval = st.selectbox("Interval", ["1m","5m","15m","30m","60m","1d"], index=1, key="ch_int")
            ch_fast = st.number_input("Fast MA", value=20, step=1, key="ch_fast")
            ch_slow = st.number_input("Slow MA", value=50, step=1, key="ch_slow")
            ch_rows = st.number_input("Rows", value=400, step=50, key="ch_rows")

            if st.button("Load Chart", key="btn_load_chart"):
                try:
                    import pandas as pd
                    import yfinance as yf

                    period = "7d" if ch_interval.endswith("m") else "60d"
                    df = yf.download(
                        tickers=ch_symbol,
                        period=period,
                        interval=ch_interval,
                        auto_adjust=False,
                        progress=False,
                        threads=False,
                        group_by="column",
                    )
                    if df is None or df.empty:
                        st.warning("No data from yfinance.")
                    else:
                        def _extract_close(_df: "pd.DataFrame") -> "pd.Series":
                            cols = _df.columns
                            if isinstance(cols, pd.MultiIndex):
                                for col in cols:
                                    parts = col if isinstance(col, tuple) else (col,)
                                    if any(str(p).lower() == "close" for p in parts):
                                        s = _df[col]
                                        return s.iloc[:, 0] if isinstance(s, pd.DataFrame) else s
                                raise KeyError("Close column not found in MultiIndex dataframe.")
                            if "Close" not in _df.columns:
                                raise KeyError("Close column not found.")
                            return _df["Close"]

                        close = _extract_close(df).tail(int(ch_rows)).copy()
                        fast = close.rolling(int(ch_fast)).mean()
                        slow = close.rolling(int(ch_slow)).mean()

                        chart_df = pd.DataFrame({"Close": close, "fast": fast, "slow": slow})
                        st.line_chart(chart_df)
                except Exception as e:
                    st.error(f"Chart error: {e}. Try `pip install yfinance` in your venv.")

    # ===== Session =====
    with tabs[6]:
        st.subheader("Session")
        st.json(session_status())


if __name__ == "__main__":
    main()
