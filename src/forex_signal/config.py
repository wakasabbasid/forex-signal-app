"""Centralised configuration — single source of truth for all constants."""

import os
from pathlib import Path

# ── RSS sources ──────────────────────────────────────────────────────────────────

RSS_SOURCES: list[tuple[str, str]] = [
    ("Google News", "https://news.google.com/rss/search?q=forex+currency&hl=en-US&gl=US&ceid=US:en"),
    ("Investing.com", "https://www.investing.com/rss/news.rss"),
    ("ForexLive", "https://www.forexlive.com/feed/"),
    ("FXStreet", "https://www.fxstreet.com/rss/news"),
    ("Yahoo Finance", "https://finance.yahoo.com/news/rssindex"),
    ("Bloomberg", "https://feeds.bloomberg.com/markets/news.rss"),
]

MAX_PER_SOURCE: int = 12

# ── Currency codes & pair mappings ───────────────────────────────────────────────

CURRENCY_CODES: list[str] = ["USD", "EUR", "GBP", "JPY", "CAD", "AUD", "NZD", "CHF"]

CURRENCY_PAIRS: dict[str, str] = {
    "EUR": "EUR/USD",
    "USD": "USD/JPY",
    "GBP": "GBP/USD",
    "JPY": "USD/JPY",
    "CAD": "USD/CAD",
    "AUD": "AUD/USD",
    "NZD": "NZD/USD",
    "CHF": "USD/CHF",
}

# Combo pairs — when both base + quote appear in a headline, use this pair
# instead of the fallback CURRENCY_PAIRS mapping (which always maps USD to
# USD/JPY, even when EUR is also mentioned).
PAIR_COMBOS: dict[frozenset[str], str] = {
    frozenset({"EUR", "USD"}): "EUR/USD",
    frozenset({"GBP", "USD"}): "GBP/USD",
    frozenset({"USD", "JPY"}): "USD/JPY",
    frozenset({"USD", "CAD"}): "USD/CAD",
    frozenset({"AUD", "USD"}): "AUD/USD",
    frozenset({"NZD", "USD"}): "NZD/USD",
    frozenset({"USD", "CHF"}): "USD/CHF",
}

# ── Signal thresholds ────────────────────────────────────────────────────────────

SIGNAL_THRESHOLD: float = 0.15  # absolute avg_score above this → BUY/SELL

# ── VADER-specific ───────────────────────────────────────────────────────────────

FINANCIAL_LINGO: dict[str, float] = {
    "surge": 2.0, "surges": 2.0, "surged": 2.0,
    "rally": 1.5, "rallies": 1.5, "rallied": 1.5,
    "plunge": -2.0, "plunges": -2.0, "plunged": -2.0,
    "crash": -3.0, "crashes": -3.0, "crashed": -3.0,
    "soar": 2.0, "soars": 2.0, "soared": 2.0,
    "tumble": -2.0, "tumbles": -2.0, "tumbled": -2.0,
}

# ── FinBERT-specific ─────────────────────────────────────────────────────────────

FINBERT_MODEL: str = "ProsusAI/finbert"
FINBERT_BATCH_SIZE: int = 8

# ── Backtesting ──────────────────────────────────────────────────────────────────

YFINANCE_TICKERS: dict[str, str] = {
    "EUR/USD": "EURUSD=X",
    "USD/JPY": "USDJPY=X",
    "GBP/USD": "GBPUSD=X",
    "USD/CAD": "USDCAD=X",
    "AUD/USD": "AUDUSD=X",
    "NZD/USD": "NZDUSD=X",
    "USD/CHF": "USDCHF=X",
}

OANDA_INSTRUMENTS: dict[str, str] = {
    "EUR/USD": "EUR_USD",
    "USD/JPY": "USD_JPY",
    "GBP/USD": "GBP_USD",
    "USD/CAD": "USD_CAD",
    "AUD/USD": "AUD_USD",
    "NZD/USD": "NZD_USD",
    "USD/CHF": "USD_CHF",
}

OANDA_GRANULARITY: str = "H1"  # H1, H4, H8, H12, D, W
OANDA_API_URL: str = "https://api-fxpractice.oanda.com"  # demo / practice
OANDA_API_LIVE: str = "https://api-fxtrade.oanda.com"     # live

BACKTEST_WINDOWS: list[int] = [1, 4, 24]  # hours to hold a signal
BACKTEST_MIN_TRADES: int = 3              # minimum trades for meaningful metrics
YFINANCE_RETRIES: int = 3
YFINANCE_RETRY_DELAY: float = 2.0        # seconds between retries

# ── Alerts (Telegram) ────────────────────────────────────────────────────────────

TELEGRAM_BOT_TOKEN: str = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID: str = os.environ.get("TELEGRAM_CHAT_ID", "")

# ── OANDA API ────────────────────────────────────────────────────────────────────

OANDA_API_KEY: str = os.environ.get("OANDA_API_KEY", "")
OANDA_USE_LIVE: bool = os.environ.get("OANDA_USE_LIVE", "").lower() in ("1", "true", "yes")

# ── Twelve Data ───────────────────────────────────────────────────────────────────

TWELVEDATA_API_KEY: str = os.environ.get("TWELVEDATA_API_KEY", "")
TWELVEDATA_RETRIES: int = 3
TWELVEDATA_DELAY: float = 1.5  # seconds between retries

# ── Storage ──────────────────────────────────────────────────────────────────────

PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent.parent
DB_PATH: Path = PROJECT_ROOT / "data" / "signals.db"
