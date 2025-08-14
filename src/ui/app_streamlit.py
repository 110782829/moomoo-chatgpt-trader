"""
Streamlit UI app for controlling the trading bot.
"""

import requests
import streamlit as st

API_BASE = "http://127.0.0.1:8000"

def connect_backend(host, port, client_id):
    resp = requests.post(f"{API_BASE}/connect", json={
        "host": host,
        "port": port,
        "client_id": client_id
    })
    return resp.json()

def select_account(account_id, trd_env):
    resp = requests.post(f"{API_BASE}/accounts/select", json={
        "account_id": account_id,
        "trd_env": trd_env
    })
    return resp.json()

def get_positions():
    return requests.get(f"{API_BASE}/positions").json()

def get_orders():
    return requests.get(f"{API_BASE}/orders").json()

def place_order(symbol, qty, side, order_type="MARKET"):
    return requests.post(f"{API_BASE}/orders/place", json={
        "symbol": symbol,
        "qty": qty,
        "side": side,
        "order_type": order_type
    }).json()

def cancel_order(order_id):
    return requests.post(f"{API_BASE}/orders/cancel", json={"order_id": order_id}).json()

def main():
    st.set_page_config(page_title="Moomoo ChatGPT Trading Bot", layout="wide")
    st.title("Moomoo ChatGPT Trading Bot")

    # --- Backend Connection ---
    st.sidebar.header("Backend Connection")
    host = st.sidebar.text_input("Host", "127.0.0.1")
    port = st.sidebar.number_input("Port", value=11111)
    client_id = st.sidebar.number_input("Client ID", value=1)

    if st.sidebar.button("Connect to Backend"):
        st.sidebar.write(connect_backend(host, port, client_id))

    # --- Account Selection ---
    st.sidebar.header("Account Selection")
    account_id = st.sidebar.text_input("Account ID", "54871")
    trd_env = st.sidebar.selectbox("Trading Env", ["SIMULATE", "REAL"])

    if st.sidebar.button("Select Account"):
        st.sidebar.write(select_account(account_id, trd_env))

    # --- Order Placement ---
    st.header("Place Order")
    symbol = st.text_input("Symbol", "US.AAPL")
    qty = st.number_input("Quantity", value=1)
    side = st.selectbox("Side", ["BUY", "SELL"])
    if st.button("Place Order"):
        st.write(place_order(symbol, qty, side))

    # --- Cancel Order ---
    st.header("Cancel Order")
    cancel_id = st.text_input("Order ID to Cancel")
    if st.button("Cancel Order"):
        st.write(cancel_order(cancel_id))

    # --- Positions ---
    st.header("Positions")
    if st.button("Refresh Positions"):
        st.write(get_positions())

    # --- Orders ---
    st.header("Orders")
    if st.button("Refresh Orders"):
        st.write(get_orders())

if __name__ == "__main__":
    main()
# --- Automation: MA Crossover ---
import json

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
            "symbol": s_symbol,
            "fast": int(s_fast),
            "slow": int(s_slow),
            "ktype": s_ktype,
            "qty": float(s_qty),
            "interval_sec": int(s_interval),
            "allow_real": bool(s_allow_real),
        }
        r = requests.post(f"{API_BASE}/automation/start/ma-crossover", json=payload)
        st.write(r.status_code, r.json())

with st.expander("Manage Strategies", expanded=False):
    if st.button("List Strategies", key="btn_list_strat"):
        r = requests.get(f"{API_BASE}/automation/strategies")
        st.session_state["strategies"] = r.json() if r.ok else []
        st.write(r.status_code)
    st.json(st.session_state.get("strategies", []))

    strat_id = st.text_input("Strategy ID", "", key="strat_id")
    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("Start", key="btn_start_id"):
            if strat_id.strip():
                r = requests.post(f"{API_BASE}/automation/start/{int(strat_id)}")
                st.write(r.status_code, r.json())
    with c2:
        if st.button("Stop", key="btn_stop_id"):
            if strat_id.strip():
                r = requests.post(f"{API_BASE}/automation/stop/{int(strat_id)}")
                st.write(r.status_code, r.json())
    with c3:
        if st.button("Recent Runs", key="btn_runs"):
            if strat_id.strip():
                r = requests.get(f"{API_BASE}/automation/strategies/{int(strat_id)}/runs?limit=20")
                st.write(r.status_code)
                st.json(r.json())


# --- Automation: Edit Strategy (MA Crossover) ---

st.header("Edit Strategy")
with st.expander("Load + Edit", expanded=False):
    es_id = st.text_input("Strategy ID", "")
    if st.button("Load Strategy", key="btn_load_strategy"):
        r = requests.get(f"{API_BASE}/automation/strategies/{int(es_id)}")
        st.session_state["edit_strategy"] = r.json() if r.ok else None
        st.write(r.status_code)

    s = st.session_state.get("edit_strategy")
    if s:
        s_params = s.get("params", {})
        col1, col2, col3 = st.columns(3)
        with col1:
            es_fast = st.number_input("Fast", value=int(s_params.get("fast", 20)), step=1)
            es_ktype = st.text_input("KType", value=str(s_params.get("ktype", "K_1M")))
            es_size_mode = st.selectbox("Size Mode", ["shares","usd"], index=0 if s_params.get("size_mode","shares")=="shares" else 1)
        with col2:
            es_slow = st.number_input("Slow", value=int(s_params.get("slow", 50)), step=1)
            es_qty = st.number_input("Qty (shares)", value=float(s_params.get("qty", 1.0)), step=1.0)
            es_dollar = st.number_input("Dollar Size", value=float(s_params.get("dollar_size", 0.0)), step=10.0)
        with col3:
            es_sl = st.number_input("Stop Loss %", value=float(s_params.get("stop_loss_pct", 0.0)), step=0.01, format="%.4f")
            es_tp = st.number_input("Take Profit %", value=float(s_params.get("take_profit_pct", 0.0)), step=0.01, format="%.4f")
            es_allow_real = st.checkbox("Allow Real", value=bool(s_params.get("allow_real", False)))

        es_interval = st.number_input("Interval (sec)", value=int(s.get("interval_sec", 15)), step=1)
        es_active = st.checkbox("Active", value=bool(s.get("active", True)))

        if st.button("Save Changes", key="btn_save_strategy"):
            payload = {
                "fast": int(es_fast),
                "slow": int(es_slow),
                "ktype": es_ktype,
                "qty": float(es_qty),
                "size_mode": es_size_mode,
                "dollar_size": float(es_dollar),
                "stop_loss_pct": float(es_sl),
                "take_profit_pct": float(es_tp),
                "allow_real": bool(es_allow_real),
                "interval_sec": int(es_interval),
                "active": bool(es_active),
            }
            r = requests.patch(f"{API_BASE}/automation/strategies/{int(es_id)}", json=payload)
            st.write(r.status_code, r.json())


# --- Backtest: MA Crossover ---
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
            "symbol": bt_symbol,
            "fast": int(bt_fast),
            "slow": int(bt_slow),
            "ktype": bt_ktype,
            "qty": float(bt_qty),
            "size_mode": bt_mode,
            "dollar_size": float(bt_dol),
            "stop_loss_pct": float(bt_sl),
            "take_profit_pct": float(bt_tp),
            "commission_per_share": float(bt_comm),
            "slippage_bps": float(bt_slip),
        }
        r = requests.post(f"{API_BASE}/backtest/ma-crossover", json=payload)
        st.write(r.status_code)
        st.json(r.json() if r.ok else r.text)
