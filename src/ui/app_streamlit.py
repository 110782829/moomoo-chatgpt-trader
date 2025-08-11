"""
Streamlit UI app for controlling the trading bot.
"""

from typing import Any, Dict

import streamlit as st


def main() -> None:
    """
    Launch the Streamlit user interface for the trading bot. This function constructs
    a simple sidebar for adjusting strategy parameters and displays placeholder
    outputs for the bot's status. Additional controls and real-time updates
    should be implemented here.
    """
    st.set_page_config(page_title="Moomoo ChatGPT Trading Bot", layout="wide")
    st.title("Moomoo ChatGPT Trading Bot")

    st.sidebar.header("Strategy Parameters")
    # Parameter inputs with sensible defaults
    fast_ma: int = st.sidebar.number_input(
        "Fast MA window", min_value=1, max_value=100, value=10, step=1
    )
    slow_ma: int = st.sidebar.number_input(
        "Slow MA window", min_value=1, max_value=300, value=30, step=1
    )
    position_size: int = st.sidebar.slider(
        "Position size (%)", min_value=1, max_value=100, value=10
    )
    stop_loss: float = st.sidebar.slider(
        "Stop loss (%)", min_value=0.5, max_value=10.0, value=2.0
    )
    take_profit: float = st.sidebar.slider(
        "Take profit (%)", min_value=0.5, max_value=20.0, value=5.0
    )

    if st.sidebar.button("Apply Settings"):
        # TODO: Send updated parameters to backend service
        st.success("Settings applied (stub)")

    st.header("Bot Status")
    st.write(
        "This is a placeholder for live positions, orders, and logs. Integrate with the"
        " backend to display real-time trading information."
    )
    st.metric("Fast MA", fast_ma)
    st.metric("Slow MA", slow_ma)
    st.metric("Position size (%)", position_size)
    st.metric("Stop loss (%)", stop_loss)
    st.metric("Take profit (%)", take_profit)


if __name__ == "__main__":
    main()
