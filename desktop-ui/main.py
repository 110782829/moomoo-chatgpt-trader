"""Minimal desktop wrapper using pywebview."""
from pathlib import Path
import threading
import webview
import uvicorn


def start_api() -> None:
    uvicorn.run("src.server:app", host="127.0.0.1", port=8000, log_level="info")


if __name__ == "__main__":
    threading.Thread(target=start_api, daemon=True).start()
    html = Path(__file__).with_name("index.html").resolve().as_uri()
    webview.create_window("Moomoo Trader", html)
    webview.start()
