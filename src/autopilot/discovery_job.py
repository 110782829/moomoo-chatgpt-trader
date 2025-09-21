from __future__ import annotations

"""Daily discovery pipeline backed by GPT web search and technical filters."""

import json
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List

import requests

from autopilot.discovery import (
    DEFAULT_SEED,
    compute_symbol_universe,
    _normalize_symbols,
    stamp_now,
)

try:
    from autopilot.news import get_news_bulk  # type: ignore
except Exception:  # pragma: no cover
    def get_news_bulk(*_args, **_kwargs):  # type: ignore
        return []

try:
    from core.storage import get_setting, set_setting, insert_action_log  # type: ignore
except Exception:  # pragma: no cover
    get_setting = None  # type: ignore
    set_setting = None  # type: ignore
    insert_action_log = None  # type: ignore


def _load_json_setting(name: str) -> Any:
    if get_setting is None:
        return None
    try:
        raw = get_setting(name)
        if not raw:
            return None
        return json.loads(raw)
    except Exception:
        return None


def _style_summary_text() -> str:
    val = _load_json_setting("autopilot.style_summary")
    if isinstance(val, str):
        return val.strip()
    return ""


def _prefs_dict() -> Dict[str, Any]:
    val = _load_json_setting("autopilot.prefs")
    return val if isinstance(val, dict) else {}


def _manual_seed() -> List[str]:
    val = _load_json_setting("autopilot.discovery_seed")
    if isinstance(val, list):
        return _normalize_symbols(val)
    return []


def _existing_report() -> Dict[str, Any]:
    val = _load_json_setting("autopilot.discovery_report")
    return val if isinstance(val, dict) else {}


def _today_local() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _gpt_web_candidates(style_summary: str, prefs: Dict[str, Any], seed: List[str], limit: int) -> Dict[str, Any]:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return {}
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()
    timeout = float(os.getenv("OPENAI_TIMEOUT", "20"))
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    style_text = style_summary or "None provided"
    pref_bits = []
    for key in ("stop_loss_pct", "take_profit_pct", "measured_move_atr_mult", "target_rr"):
        if prefs.get(key) is not None:
            pref_bits.append(f"{key}={prefs[key]}")
    pref_text = ", ".join(pref_bits) if pref_bits else "None"
    seed_text = ", ".join(seed[:12]) if seed else "(default universe)"
    user_prompt = (
        "You are an equities scout. Use the web_search tool to gather the most active US-listed stocks today, "
        "focusing on catalysts, high relative volume, or strong momentum. Incorporate the user's style summary "
        "and preferences when selecting names. Respond with JSON only."
        "\n- Style summary: " + style_text +
        "\n- Explicit prefs: " + pref_text +
        "\n- Starting seed for context: " + seed_text +
        f"\nReturn JSON with keys: tickers (array, up to {limit}, format 'US.TICKER'), highlights (array of short strings), summary (string)."
    )
    payload: Dict[str, Any] = {
        "model": model,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": "Always call web_search before answering. Output compact professional writing."},
            {"role": "user", "content": user_prompt},
        ],
        "tools": [{"type": "web_search"}],
        "response_format": {"type": "json_object"},
    }
    try:
        resp = requests.post(f"{base_url}/chat/completions", headers=headers, json=payload, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        content = (data.get("choices") or [{}])[0].get("message", {}).get("content")
        if not content:
            return {}
        parsed = json.loads(content)
        tickers = parsed.get("tickers") or parsed.get("symbols") or []
        highlights = parsed.get("highlights") or parsed.get("insights") or []
        summary = parsed.get("summary") or parsed.get("notes") or ""
        return {
            "tickers": _normalize_symbols(tickers)[:limit],
            "highlights": [str(x) for x in highlights if x],
            "summary": str(summary or "").strip(),
            "raw": parsed,
        }
    except Exception:
        return {}


def _merged_seed(base_seed: List[str], extra: List[str], cap: int) -> List[str]:
    merged: List[str] = []
    seen = set()
    for source in (extra, base_seed, DEFAULT_SEED):
        for sym in _normalize_symbols(source):
            if sym in seen:
                continue
            seen.add(sym)
            merged.append(sym)
            if len(merged) >= cap:
                return merged
    return merged


def run_daily_discovery(
    client,
    *,
    force: bool = False,
    reason: str = "auto",
) -> Dict[str, Any]:
    """Run discovery once per day (idempotent unless force=True)."""
    existing = _existing_report()
    today = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d")
    if (not force) and existing.get("run_day") == today:
        return existing

    limit = int(os.getenv("AUTOPILOT_DISCOVERY_LIMIT", "20") or "20")
    seed_cap = int(os.getenv("AUTOPILOT_DISCOVERY_SEED_CAP", "60") or "60")
    ktype = os.getenv("AUTOPILOT_DISCOVERY_KTYPE", "K_DAY")

    manual_seed = _manual_seed()
    style_summary = _style_summary_text()
    prefs = _prefs_dict()

    gpt_block = _gpt_web_candidates(style_summary, prefs, manual_seed or DEFAULT_SEED, seed_cap)
    gpt_seed = gpt_block.get("tickers") or []
    combined_seed = _merged_seed(manual_seed or DEFAULT_SEED, gpt_seed, seed_cap)

    t0 = time.perf_counter()
    universe = compute_symbol_universe(client, combined_seed, ktype=ktype, lookback=60)
    elapsed_ms = int((time.perf_counter() - t0) * 1000)

    trimmed = universe[:limit]
    symbols = [row["symbol"] for row in trimmed]

    news_rows: List[Dict[str, Any]] = []
    if symbols:
        try:
            news_rows = get_news_bulk(symbols, ttl_sec=3600, max_items=2, cap=min(10, len(symbols)))
        except Exception:
            news_rows = []
    news_map = {str(n.get("sym") or n.get("symbol")): n for n in news_rows}

    items: List[Dict[str, Any]] = []
    for idx, row in enumerate(trimmed, start=1):
        feats = row.get("features") or {}
        entry: Dict[str, Any] = {
            "symbol": row["symbol"],
            "rank": idx,
            "score": round(float(row.get("score") or 0.0), 3),
        }
        for key in ("px", "atr", "atr_pct", "rel_vol", "change_1d_pct"):
            val = feats.get(key)
            if val is None:
                continue
            entry[key] = round(float(val), 4 if key.endswith("pct") else 2)
        news = news_map.get(row["symbol"])
        if news:
            if news.get("summary"):
                entry["news_summary"] = str(news.get("summary"))
            if news.get("tone"):
                entry["news_tone"] = str(news.get("tone"))
            if news.get("ts"):
                entry["news_ts"] = int(news.get("ts"))
        items.append(entry)

    report: Dict[str, Any] = {
        **stamp_now(),
        "reason": reason,
        "elapsed_ms": elapsed_ms,
        "seed": combined_seed,
        "seed_manual": manual_seed,
        "seed_gpt": gpt_seed,
        "style_summary": style_summary,
        "prefs": prefs,
        "top_symbols": symbols,
        "items": items,
        "ktype": ktype,
        "gpt": {k: v for k, v in gpt_block.items() if k != "tickers"} if gpt_block else {},
    }

    if set_setting is not None:
        try:
            set_setting("autopilot.discovery_report", report)
            set_setting("autopilot.discovery_watchlist", symbols)
        except Exception:
            pass
    if insert_action_log is not None:
        try:
            insert_action_log(
                "discovery_refresh",
                mode="auto",
                reason=reason,
                status="ok",
                extra={
                    "count": len(symbols),
                    "elapsed_ms": elapsed_ms,
                    "used_gpt": bool(gpt_seed),
                },
            )
        except Exception:
            pass
    report["run_day"] = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d")
    return report


__all__ = ["run_daily_discovery"]

