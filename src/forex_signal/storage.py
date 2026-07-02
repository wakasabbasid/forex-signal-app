"""SQLite storage — save/load runs using dataclass models.

Backward-compatible: the existing ``signals.db`` schema is unchanged.
"""

import logging
import sqlite3
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any

from . import config
from .models import BacktestMetrics, BacktestTrade, Headline, Run, Signal

logger = logging.getLogger(__name__)


# ── Connection helpers ────────────────────────────────────────────────────────────


def _get_conn() -> sqlite3.Connection:
    """Open a connection, enable dict-like row access + WAL mode."""
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(config.DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


# ── Schema ────────────────────────────────────────────────────────────────────────


def init_db() -> None:
    """Create tables iff they don't already exist (idempotent)."""
    try:
        conn = _get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS signal_runs (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                headline_count INTEGER NOT NULL,
                source_count   INTEGER NOT NULL,
                engine         TEXT NOT NULL,
                created_at     TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS signals (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id         INTEGER NOT NULL,
                pair           TEXT NOT NULL,
                signal         TEXT NOT NULL,
                avg_score      REAL NOT NULL,
                headline_count INTEGER NOT NULL,
                FOREIGN KEY (run_id) REFERENCES signal_runs(id)
            );
            CREATE TABLE IF NOT EXISTS headlines (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id           INTEGER NOT NULL,
                title            TEXT NOT NULL,
                source           TEXT NOT NULL,
                sentiment_label  TEXT NOT NULL,
                sentiment_score  REAL NOT NULL,
                currencies       TEXT,
                FOREIGN KEY (run_id) REFERENCES signal_runs(id)
            );
            CREATE TABLE IF NOT EXISTS price_cache (
                pair         TEXT NOT NULL,
                date         TEXT NOT NULL,
                close_price  REAL NOT NULL,
                PRIMARY KEY (pair, date)
            );
            CREATE TABLE IF NOT EXISTS price_cache_hourly (
                pair         TEXT NOT NULL,
                ts           TEXT NOT NULL,
                close_price  REAL NOT NULL,
                PRIMARY KEY (pair, ts)
            );
            CREATE TABLE IF NOT EXISTS backtest_trades (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                signal_run_id INTEGER,
                pair          TEXT NOT NULL,
                signal        TEXT NOT NULL,
                engine        TEXT NOT NULL DEFAULT '',
                window_hours  INTEGER NOT NULL,
                entry_price   REAL NOT NULL,
                exit_price    REAL,
                entry_time    TEXT NOT NULL,
                exit_time     TEXT,
                profit_pct    REAL,
                FOREIGN KEY (signal_run_id) REFERENCES signal_runs(id)
            );
            CREATE INDEX IF NOT EXISTS idx_backtest_run_window ON backtest_trades(signal_run_id, window_hours);
            PRAGMA journal_mode=WAL;
        """)
        conn.commit()
        logger.info("Database initialised at %s", config.DB_PATH)
    except sqlite3.Error as exc:
        logger.error("Failed to initialise DB: %s", exc)
        raise RuntimeError(f"Database initialisation failed: {exc}") from exc
    finally:
        conn.close()


# ── Write ─────────────────────────────────────────────────────────────────────────


def save_run(
    signals: Sequence[Signal],
    headlines: Sequence[Headline],
    engine: str,
) -> int:
    """Persist a pipeline run and return its ``run_id``."""
    init_db()
    now = datetime.now(timezone.utc).isoformat()

    source_count = len({h.source for h in headlines})

    try:
        conn = _get_conn()
        cur = conn.execute(
            "INSERT INTO signal_runs (headline_count, source_count, engine, created_at) VALUES (?, ?, ?, ?)",
            (len(headlines), source_count, engine, now),
        )
        run_id = cur.lastrowid

        conn.executemany(
            "INSERT INTO signals (run_id, pair, signal, avg_score, headline_count) VALUES (?, ?, ?, ?, ?)",
            [(run_id, s.pair, s.signal, s.avg_score, s.headline_count) for s in signals],
        )

        conn.executemany(
            "INSERT INTO headlines (run_id, title, source, sentiment_label, sentiment_score, currencies) VALUES (?, ?, ?, ?, ?, ?)",
            [(run_id, h.title, h.source, h.label, h.score, ",".join(h.currencies)) for h in headlines],
        )

        conn.commit()
        logger.info("Saved run #%d (%s) — %d signals, %d headlines", run_id, engine, len(signals), len(headlines))
        return run_id
    except sqlite3.Error as exc:
        logger.error("Failed to save run: %s", exc)
        raise RuntimeError(f"Database save failed: {exc}") from exc
    finally:
        conn.close()


# ── Read helpers ──────────────────────────────────────────────────────────────────


def _row_to_run(row: sqlite3.Row) -> Run:
    return Run(
        id=row["id"],
        engine=row["engine"],
        headline_count=row["headline_count"],
        source_count=row["source_count"],
        created_at=row["created_at"],
    )


def _row_to_signal(row: sqlite3.Row) -> Signal:
    return Signal(
        pair=row["pair"],
        signal=row["signal"],
        avg_score=row["avg_score"],
        headline_count=row["headline_count"],
    )


def _row_to_headline(row: sqlite3.Row) -> Headline:
    raw = row["currencies"] or ""
    currencies = [c.strip() for c in raw.split(",") if c.strip()]
    return Headline(
        title=row["title"],
        source=row["source"],
        label=row["sentiment_label"],
        score=row["sentiment_score"],
        currencies=currencies,
    )


# ── Read queries ──────────────────────────────────────────────────────────────────


def get_latest_run() -> Run | None:
    try:
        conn = _get_conn()
        row = conn.execute(
            "SELECT id, headline_count, source_count, engine, created_at FROM signal_runs ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return _row_to_run(row) if row else None
    except sqlite3.Error as exc:
        logger.error("Failed to get latest run: %s", exc)
        return None
    finally:
        conn.close()


def get_history(limit: int = 168) -> list[Run]:
    try:
        conn = _get_conn()
        rows = conn.execute(
            "SELECT id, headline_count, source_count, engine, created_at FROM signal_runs ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [_row_to_run(r) for r in rows]
    except sqlite3.Error as exc:
        logger.error("Failed to get history: %s", exc)
        return []
    finally:
        conn.close()


def get_signals_for_run(run_id: int) -> list[Signal]:
    try:
        conn = _get_conn()
        rows = conn.execute(
            "SELECT pair, signal, avg_score, headline_count FROM signals WHERE run_id = ?",
            (run_id,),
        ).fetchall()
        return [_row_to_signal(r) for r in rows]
    except sqlite3.Error as exc:
        logger.error("Failed to get signals for run %d: %s", run_id, exc)
        return []
    finally:
        conn.close()


def get_headlines_for_run(run_id: int) -> list[Headline]:
    try:
        conn = _get_conn()
        rows = conn.execute(
            "SELECT title, source, sentiment_label, sentiment_score, currencies FROM headlines WHERE run_id = ?",
            (run_id,),
        ).fetchall()
        return [_row_to_headline(r) for r in rows]
    except sqlite3.Error as exc:
        logger.error("Failed to get headlines for run %d: %s", run_id, exc)
        return []
    finally:
        conn.close()


def get_signal_time_series(pair: str, limit: int = 168) -> list[dict[str, Any]]:
    try:
        conn = _get_conn()
        rows = conn.execute("""
            SELECT s.avg_score AS score, r.created_at AS time
            FROM signals s
            JOIN signal_runs r ON s.run_id = r.id
            WHERE s.pair = ?
            ORDER BY r.id ASC
            LIMIT ?
        """, (pair, limit)).fetchall()
        return [{"score": r["score"], "time": r["time"]} for r in rows]
    except sqlite3.Error as exc:
        logger.error("Failed to get time series for %s: %s", pair, exc)
        return []
    finally:
        conn.close()


# ── Price cache (daily) ───────────────────────────────────────────────────────────


def cache_price(pair: str, date: str, close_price: float) -> None:
    """Store a single daily price (idempotent)."""
    try:
        conn = _get_conn()
        conn.execute(
            "INSERT OR REPLACE INTO price_cache (pair, date, close_price) VALUES (?, ?, ?)",
            (pair, date, close_price),
        )
        conn.commit()
    except sqlite3.Error as exc:
        logger.warning("Failed to cache price %s %s: %s", pair, date, exc)
    finally:
        conn.close()


def get_cached_price(pair: str, date: str) -> float | None:
    """Return cached daily close price or None."""
    try:
        conn = _get_conn()
        row = conn.execute(
            "SELECT close_price FROM price_cache WHERE pair = ? AND date = ?",
            (pair, date),
        ).fetchone()
        return row["close_price"] if row else None
    except sqlite3.Error:
        return None
    finally:
        conn.close()


def get_cached_dates(pair: str) -> set[str]:
    """Return set of dates for which we have cached daily prices."""
    try:
        conn = _get_conn()
        rows = conn.execute(
            "SELECT date FROM price_cache WHERE pair = ?", (pair,),
        ).fetchall()
        return {r["date"] for r in rows}
    except sqlite3.Error:
        return set()
    finally:
        conn.close()


# ── Price cache (hourly) ─────────────────────────────────────────────────────────


def cache_hourly_price(pair: str, ts: str, close_price: float) -> None:
    """Store a single hourly price (idempotent).  *ts* is ISO-8601 ``YYYY-MM-DDTHH``."""
    try:
        conn = _get_conn()
        conn.execute(
            "INSERT OR REPLACE INTO price_cache_hourly (pair, ts, close_price) VALUES (?, ?, ?)",
            (pair, ts, close_price),
        )
        conn.commit()
    except sqlite3.Error as exc:
        logger.warning("Failed to cache hourly price %s %s: %s", pair, ts, exc)
    finally:
        conn.close()


def get_cached_hourly_price(pair: str, ts: str) -> float | None:
    """Return cached hourly price or None."""
    try:
        conn = _get_conn()
        row = conn.execute(
            "SELECT close_price FROM price_cache_hourly WHERE pair = ? AND ts = ?",
            (pair, ts),
        ).fetchone()
        return row["close_price"] if row else None
    except sqlite3.Error:
        return None
    finally:
        conn.close()


def cache_hourly_prices_bulk(pair: str, prices: dict[str, float]) -> None:
    """Bulk-insert hourly prices for a single pair."""
    try:
        conn = _get_conn()
        conn.executemany(
            "INSERT OR REPLACE INTO price_cache_hourly (pair, ts, close_price) VALUES (?, ?, ?)",
            [(pair, ts, price) for ts, price in prices.items()],
        )
        conn.commit()
        logger.info("Cached %d hourly prices for %s", len(prices), pair)
    except sqlite3.Error as exc:
        logger.warning("Failed to cache hourly prices for %s: %s", pair, exc)
    finally:
        conn.close()


def get_cached_hourly_range(pair: str, start_ts: str, end_ts: str) -> dict[str, float]:
    """Return ``{ts: close_price}`` for a time range (inclusive)."""
    try:
        conn = _get_conn()
        rows = conn.execute(
            "SELECT ts, close_price FROM price_cache_hourly WHERE pair = ? AND ts >= ? AND ts <= ? ORDER BY ts",
            (pair, start_ts, end_ts),
        ).fetchall()
        return {r["ts"]: r["close_price"] for r in rows}
    except sqlite3.Error:
        return {}
    finally:
        conn.close()


# ── Backtest storage ──────────────────────────────────────────────────────────────


def clear_backtest_trades() -> None:
    """Delete all backtest trades (idempotent — safe to call before re-running)."""
    try:
        conn = _get_conn()
        conn.execute("DELETE FROM backtest_trades")
        conn.commit()
        logger.info("Cleared all backtest trades")
    except sqlite3.Error as exc:
        logger.warning("Failed to clear backtest trades: %s", exc)
    finally:
        conn.close()


def save_backtest_trades(trades: list[BacktestTrade]) -> int:
    """Persist backtest trades, return count saved."""
    if not trades:
        return 0
    try:
        conn = _get_conn()
        conn.executemany("""
            INSERT INTO backtest_trades
                (signal_run_id, pair, signal, engine, window_hours, entry_price, exit_price, entry_time, exit_time, profit_pct)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            (None, t.pair, t.signal, t.engine, t.window_hours, t.entry_price,
             t.exit_price, t.entry_time, t.exit_time, t.profit_pct)
            for t in trades
        ])
        conn.commit()
        logger.info("Saved %d backtest trades", len(trades))
        return len(trades)
    except sqlite3.Error as exc:
        logger.error("Failed to save backtest trades: %s", exc)
        return 0
    finally:
        conn.close()


def get_backtest_trades(window_hours: int | None = None) -> list[BacktestTrade]:
    """Return all backtest trades, optionally filtered by window."""
    try:
        conn = _get_conn()
        if window_hours is not None:
            rows = conn.execute(
                "SELECT * FROM backtest_trades WHERE window_hours = ? ORDER BY entry_time",
                (window_hours,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM backtest_trades ORDER BY entry_time"
            ).fetchall()
        return [
            BacktestTrade(
                pair=r["pair"],
                signal=r["signal"],
                engine=r["engine"],
                entry_price=r["entry_price"],
                exit_price=r["exit_price"],
                entry_time=r["entry_time"],
                exit_time=r["exit_time"],
                profit_pct=r["profit_pct"],
                window_hours=r["window_hours"],
            )
            for r in rows
        ]
    except sqlite3.Error as exc:
        logger.error("Failed to get backtest trades: %s", exc)
        return []
    finally:
        conn.close()


def get_all_signal_runs_with_signals() -> list[Run]:
    """Return all signal runs that have signals attached, ordered oldest-first."""
    try:
        conn = _get_conn()
        rows = conn.execute(
            "SELECT id, headline_count, source_count, engine, created_at FROM signal_runs ORDER BY id ASC"
        ).fetchall()
        runs = [_row_to_run(r) for r in rows]
        for run in runs:
            run.signals = get_signals_for_run(run.id)
        return runs
    except sqlite3.Error as exc:
        logger.error("Failed to get signal runs: %s", exc)
        return []
    finally:
        conn.close()


def get_backtest_summary_by_pair(window_hours: int) -> dict[str, dict[str, float]]:
    """Aggregate backtest results per pair for a given window."""
    try:
        conn = _get_conn()
        rows = conn.execute("""
            SELECT
                pair,
                COUNT(*)                                            AS trades,
                ROUND(AVG(CASE WHEN profit_pct > 0 THEN 1.0 ELSE 0.0 END), 4) AS win_rate,
                ROUND(SUM(profit_pct), 4)                           AS total_return,
                ROUND(AVG(profit_pct), 4)                           AS avg_profit,
                ROUND(MAX(profit_pct), 4)                           AS max_profit,
                ROUND(MIN(profit_pct), 4)                           AS max_loss
            FROM backtest_trades
            WHERE window_hours = ? AND profit_pct IS NOT NULL
            GROUP BY pair
            ORDER BY total_return DESC
        """, (window_hours,)).fetchall()
        return {
            r["pair"]: {
                "trades": r["trades"],
                "win_rate": r["win_rate"],
                "total_return": r["total_return"],
                "avg_profit": r["avg_profit"],
                "max_profit": r["max_profit"],
                "max_loss": r["max_loss"],
            }
            for r in rows
        }
    except sqlite3.Error as exc:
        logger.error("Failed to get backtest summary: %s", exc)
        return {}
    finally:
        conn.close()


def get_engine_comparison(window_hours: int) -> dict[str, dict[str, Any]]:
    """Return backtest metrics grouped by engine for a given window."""
    try:
        conn = _get_conn()
        rows = conn.execute("""
            SELECT
                engine,
                COUNT(*)                                            AS trades,
                ROUND(AVG(CASE WHEN profit_pct > 0 THEN 1.0 ELSE 0.0 END), 4) AS win_rate,
                ROUND(SUM(profit_pct), 4)                           AS total_return,
                ROUND(AVG(profit_pct), 4)                           AS avg_profit,
                ROUND(MAX(profit_pct), 4)                           AS max_profit,
                ROUND(MIN(profit_pct), 4)                           AS max_loss
            FROM backtest_trades
            WHERE window_hours = ? AND profit_pct IS NOT NULL AND engine != ''
            GROUP BY engine
            ORDER BY total_return DESC
        """, (window_hours,)).fetchall()
        return {
            r["engine"]: {
                "trades": r["trades"],
                "win_rate": r["win_rate"],
                "total_return": r["total_return"],
                "avg_profit": r["avg_profit"],
                "max_profit": r["max_profit"],
                "max_loss": r["max_loss"],
            }
            for r in rows
        }
    except sqlite3.Error as exc:
        logger.error("Failed to get engine comparison: %s", exc)
        return {}
    finally:
        conn.close()
