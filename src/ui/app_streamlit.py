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
