"""Backtesting engine — evaluate signals against real market data.

Architecture
------------
* ``PriceProvider``             — abstract interface for price lookups
* ``YahooPriceProvider``        — daily close via yfinance
* ``OandaPriceProvider``        — hourly candles via OANDA v20 REST API
* ``backtest_all_runs()``       — orchestration
* ``compute_metrics()``         — aggregate trades into win rate, return, etc.
"""

import logging
import time as time_module
from datetime import datetime, timezone, timedelta
from typing import Any

from . import config
from .models import BacktestMetrics, BacktestTrade
from .storage import (
    init_db,
    clear_backtest_trades,
    cache_price,
    save_backtest_trades,
    get_all_signal_runs_with_signals,
    get_backtest_trades,
    get_backtest_summary_by_pair,
    cache_hourly_prices_bulk,
    get_cached_hourly_range,
)

logger = logging.getLogger(__name__)


# ── Price Provider ────────────────────────────────────────────────────────────────


class PriceProvider:
    """Abstract interface for fetching historical forex prices.

    All times are UTC.  Price maps are keyed by ISO-8601 hour string
    (``YYYY-MM-DDTHH:00:00``) for hourly, or ``YYYY-MM-DDT00:00:00``
    for daily data.
    """

    def fetch_prices(
        self, pair: str, start_dt: datetime, end_dt: datetime,
    ) -> dict[str, float]:
        """Return ``{iso_hour: close_price}`` for the interval [start, end]."""
        raise NotImplementedError

    @property
    def has_hourly(self) -> bool:
        """True if the provider supports sub-daily granularity."""
        return False


class YahooPriceProvider(PriceProvider):
    """Daily close via yfinance (free, no sign-up).

    Prices are stamped at ``T00:00:00`` — fine for 24h windows,
    meaningless for sub-daily windows.
    """

    def __init__(self) -> None:
        self._yf = None

    @property
    def has_hourly(self) -> bool:
        return False

    def _import(self):
        if self._yf is None:
            import yfinance as yf  # type: ignore[import-untyped]
            self._yf = yf
        return self._yf

    def fetch_prices(
        self, pair: str, start_dt: datetime, end_dt: datetime,
    ) -> dict[str, float]:
        ticker = config.YFINANCE_TICKERS.get(pair)
        if not ticker:
            logger.warning("No yfinance ticker for %s", pair)
            return {}

        # check cache first
        prices: dict[str, float] = {}
        for i in range((end_dt - start_dt).days + 2):
            day = (start_dt + timedelta(days=i)).strftime("%Y-%m-%d")
            ts = f"{day}T00:00:00"
            cached = get_cached_hourly_range(pair, ts, ts)
            if cached:
                prices.update(cached)

        yf = self._import()
        for attempt in range(1, config.YFINANCE_RETRIES + 1):
            try:
                hist = yf.Ticker(ticker).history(
                    start=start_dt.strftime("%Y-%m-%d"),
                    end=end_dt.strftime("%Y-%m-%d"),
                )
                if hist.empty:
                    return prices

                hourly: dict[str, float] = {}
                for idx, row in hist.iterrows():
                    day = idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx.date())
                    ts = f"{day}T00:00:00"
                    close = float(row["Close"])
                    prices[ts] = close
                    hourly[ts] = close

                if hourly:
                    cache_hourly_prices_bulk(pair, hourly)
                return prices
            except Exception as exc:
                logger.warning("yfinance attempt %d/%d for %s failed: %s",
                               attempt, config.YFINANCE_RETRIES, pair, exc)
                if attempt < config.YFINANCE_RETRIES:
                    time_module.sleep(config.YFINANCE_RETRY_DELAY)
        return prices


class OandaPriceProvider(PriceProvider):
    """Hourly candles via OANDA v20 REST API (requires free demo account).

    Configure via env vars:
        OANDA_API_KEY=your_bearer_token
        OANDA_USE_LIVE=1          # optional, defaults to practice
    """

    def __init__(self) -> None:
        self._token = config.OANDA_API_KEY
        self._base = config.OANDA_API_LIVE if config.OANDA_USE_LIVE else config.OANDA_API_URL

    @property
    def has_hourly(self) -> bool:
        return True

    @property
    def configured(self) -> bool:
        return bool(self._token)

    def fetch_prices(
        self, pair: str, start_dt: datetime, end_dt: datetime,
    ) -> dict[str, float]:
        instrument = config.OANDA_INSTRUMENTS.get(pair)
        if not instrument:
            logger.warning("No OANDA instrument for %s", pair)
            return {}

        # Try cache first
        start_ts = start_dt.strftime("%Y-%m-%dT%H:%M:%S")
        end_ts = end_dt.strftime("%Y-%m-%dT%H:%M:%S")
        cached = get_cached_hourly_range(pair, start_ts, end_ts)
        if len(cached) > 0:
            # Heuristic: if we have at least some data for the range, trust it
            logger.info("Using %d cached hourly prices for %s", len(cached), pair)
            return cached

        prices: dict[str, float] = {}
        import requests

        headers = {"Authorization": f"Bearer {self._token}"}
        params = {
            "granularity": config.OANDA_GRANULARITY,
            "from": start_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "to": end_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "price": "M",  # mid-point (no bid/ask spread)
        }

        try:
            url = f"{self._base}/v3/instruments/{instrument}/candles"
            resp = requests.get(url, headers=headers, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()

            for candle in data.get("candles", []):
                if candle.get("complete", True):
                    ts = candle["time"][:19]  # "2026-06-30T14:00:00.000Z" → cut Z
                    if ts.endswith("Z"):
                        ts = ts[:-1]
                    mid = candle.get("mid", {})
                    prices[ts] = float(mid.get("c", 0))

            logger.info("Fetched %d hourly candles for %s from OANDA", len(prices), pair)
        except Exception as exc:
            logger.warning("OANDA fetch failed for %s: %s", pair, exc)

        if prices:
            cache_hourly_prices_bulk(pair, prices)
        return prices


class TwelveDataProvider(PriceProvider):
    """Hourly forex data via Twelve Data (free API key, instant signup).

    Configure via env var:
        TWELVEDATA_API_KEY=your_key_here

    Get a free key at https://twelvedata.com/apikey (no credit card).
    """

    BASE = "https://api.twelvedata.com"

    def __init__(self) -> None:
        self._key = config.TWELVEDATA_API_KEY

    @property
    def has_hourly(self) -> bool:
        return True

    @property
    def configured(self) -> bool:
        return bool(self._key)

    def fetch_prices(
        self, pair: str, start_dt: datetime, end_dt: datetime,
    ) -> dict[str, float]:
        # Check cache first
        start_ts = start_dt.strftime("%Y-%m-%dT%H:%M:%S")
        end_ts = end_dt.strftime("%Y-%m-%dT%H:%M:%S")
        cached = get_cached_hourly_range(pair, start_ts, end_ts)
        if len(cached) > 0:
            logger.info("Using %d cached hourly prices for %s", len(cached), pair)
            return cached

        prices: dict[str, float] = {}
        import requests

        sym = pair.replace("/", "")
        params = {
            "symbol": sym,
            "interval": "1h",
            "apikey": self._key,
            "outputsize": "5000",
            "format": "JSON",
        }

        for attempt in range(1, config.TWELVEDATA_RETRIES + 1):
            try:
                url = f"{self.BASE}/time_series"
                resp = requests.get(url, params=params, timeout=30)
                resp.raise_for_status()
                data = resp.json()

                if data.get("status") != "ok":
                    msg = data.get("message", data.get("code", "unknown error"))
                    logger.warning("Twelve Data API error for %s: %s (%s)", pair, msg, data.get("code", ""))
                    return prices  # could be rate limit, just return what we have

                values = data.get("values", [])
                for v in values:
                    ts = v["datetime"]  # "2026-07-03 01:00:00"
                    ts_iso = ts.replace(" ", "T") + ":00"
                    prices[ts_iso] = float(v["close"])

                logger.info("Fetched %d hourly prices for %s from Twelve Data", len(prices), pair)
                break  # success

            except Exception as exc:
                logger.warning("Twelve Data attempt %d/%d for %s failed: %s",
                               attempt, config.TWELVEDATA_RETRIES, pair, exc)
                if attempt < config.TWELVEDATA_RETRIES:
                    time_module.sleep(config.TWELVEDATA_DELAY)

        if prices:
            cache_hourly_prices_bulk(pair, prices)
        return prices


# ── Provider factory ──────────────────────────────────────────────────────────────


def _get_provider() -> PriceProvider:
    """Return best available price provider."""
    td = TwelveDataProvider()
    if td.configured:
        logger.info("Using Twelve Data price provider (hourly)")
        return td
    o = OandaPriceProvider()
    if o.configured:
        logger.info("Using OANDA price provider (hourly)")
        return o
    logger.info("No hourly provider configured — using yfinance (daily only)")
    return YahooPriceProvider()


# ── Core backtest logic ──────────────────────────────────────────────────────────


def _to_hour_key(dt: datetime) -> str:
    """Round a datetime to the nearest hour, return ``YYYY-MM-DDTHH:00:00``."""
    return dt.replace(minute=0, second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M:%S")


def _compute_profit(entry: float, exit: float, signal: str) -> float:
    if signal == "BUY":
        return (exit / entry) - 1.0
    if signal == "SELL":
        return 1.0 - (exit / entry)
    return 0.0


def backtest_all_runs(
    windows: list[int] | None = None,
    provider: PriceProvider | None = None,
) -> list[BacktestMetrics]:
    """Run backtest across all signal runs.

    Parameters
    ----------
    windows: Holding windows in hours (default ``config.BACKTEST_WINDOWS``).
    provider: Price provider (auto-detected if None).

    Returns: One ``BacktestMetrics`` per window.
    """
    init_db()
    clear_backtest_trades()

    if windows is None:
        windows = config.BACKTEST_WINDOWS
    if provider is None:
        provider = _get_provider()

    runs = get_all_signal_runs_with_signals()
    if not runs:
        logger.warning("No signal runs found — nothing to backtest")
        return [BacktestMetrics(window_hours=w, total_trades=0, win_rate=0.0,
                                total_return_pct=0.0, avg_profit_pct=0.0,
                                max_profit_pct=0.0, max_loss_pct=0.0)
                for w in windows]

    all_trades: list[BacktestTrade] = []
    for window in windows:
        trades = backtest_window(runs, window, provider)
        all_trades.extend(trades)

    save_backtest_trades(all_trades)

    metrics_list: list[BacktestMetrics] = []
    for window in windows:
        trades = get_backtest_trades(window_hours=window)
        metrics_list.append(compute_metrics(trades, window))
    return metrics_list


def backtest_window(
    runs: list[Any],
    window_hours: int,
    provider: PriceProvider,
) -> list[BacktestTrade]:
    """Backtest all runs for a single holding window."""
    trades: list[BacktestTrade] = []
    price_cache: dict[str, dict[str, float]] = {}

    for run in runs:
        entry_dt = _parse_datetime(run.created_at)

        for sig in run.signals:
            if sig.signal == "HOLD":
                continue

            _ensure_prices(sig.pair, entry_dt, window_hours, provider, price_cache)

            entry_key = _to_hour_key(entry_dt)
            entry_price = _lookup_price(sig.pair, entry_key, price_cache, backward=True)
            if entry_price is None:
                logger.debug("No entry price for %s at %s", sig.pair, entry_key)
                continue

            exit_dt = entry_dt + timedelta(hours=window_hours)
            exit_key = _to_hour_key(exit_dt)
            exit_price = _lookup_price(sig.pair, exit_key, price_cache, backward=True)
            if exit_price is None:
                logger.debug("No exit price for %s at %s", sig.pair, exit_key)
                continue

            profit = _compute_profit(entry_price, exit_price, sig.signal)
            trades.append(BacktestTrade(
                pair=sig.pair,
                signal=sig.signal,
                engine=run.engine,
                entry_price=entry_price,
                exit_price=exit_price,
                entry_time=run.created_at,
                exit_time=exit_dt.isoformat(),
                profit_pct=profit,
                window_hours=window_hours,
            ))

    logger.info("Backtest window=%dh: %d trades from %d runs",
                window_hours, len(trades), len(runs))
    return trades


def _parse_datetime(iso_str: str) -> datetime:
    return datetime.fromisoformat(iso_str.replace("Z", "+00:00"))


def _ensure_prices(
    pair: str, entry_dt: datetime, window_hours: int,
    provider: PriceProvider, cache: dict[str, dict[str, float]],
) -> None:
    if pair in cache:
        return
    start = entry_dt - timedelta(hours=6)
    end = entry_dt + timedelta(hours=window_hours + 12)
    prices = provider.fetch_prices(pair, start, end)
    cache[pair] = prices


def _lookup_price(
    pair: str, key: str, cache: dict[str, dict[str, float]],
    backward: bool = False,
) -> float | None:
    """Return price at *key* (YYYY-MM-DDTHH:00:00), optionally walking back."""
    prices = cache.get(pair)
    if not prices:
        return None
    if key in prices:
        return prices[key]
    if not backward:
        return None

    # Walk back up to 48 hours (weekends, holidays)
    dt = datetime.fromisoformat(key)
    for i in range(1, 48):
        prev = (dt - timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M:%S")
        if prev in prices:
            return prices[prev]
    return None


# ── Metrics ───────────────────────────────────────────────────────────────────────


def compute_metrics(trades: list[BacktestTrade], window_hours: int) -> BacktestMetrics:
    if not trades:
        return BacktestMetrics(window_hours=window_hours, total_trades=0, win_rate=0.0,
                                total_return_pct=0.0, avg_profit_pct=0.0,
                                max_profit_pct=0.0, max_loss_pct=0.0)

    profits = [t.profit_pct for t in trades if t.profit_pct is not None and t.profit_pct != 0.0]
    if not profits:
        return BacktestMetrics(window_hours=window_hours, total_trades=len(trades),
                                win_rate=0.0, total_return_pct=0.0, avg_profit_pct=0.0,
                                max_profit_pct=0.0, max_loss_pct=0.0)

    wins = [p for p in profits if p > 0]
    return BacktestMetrics(
        window_hours=window_hours,
        total_trades=len(profits),
        win_rate=len(wins) / len(profits) if profits else 0.0,
        total_return_pct=sum(profits),
        avg_profit_pct=sum(profits) / len(profits),
        max_profit_pct=max(profits),
        max_loss_pct=min(profits),
        trades=sorted(trades, key=lambda t: t.entry_time),
    )


def get_pair_backtest_data(window_hours: int) -> dict[str, dict[str, float]]:
    return get_backtest_summary_by_pair(window_hours)
