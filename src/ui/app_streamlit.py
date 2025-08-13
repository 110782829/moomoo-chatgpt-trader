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
