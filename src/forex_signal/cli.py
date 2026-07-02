"""CLI entry point — ``forex-signal`` (installed via ``pyproject.toml``).

Usage::

    forex-signal --engine vader
    forex-signal --engine finbert
"""

import argparse
import logging
import time
import sys
from datetime import datetime, timezone

from . import config
from .fetcher import fetch_headlines
from .sentiment import get_engine
from .signals import generate_signals
from .storage import save_run
from .detector import detect_currencies
from .backtest import backtest_all_runs
from .alerter import get_alerter, Run


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%H:%M:%S",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="forex-signal",
        description="News-driven forex signal generator.",
    )
    parser.add_argument(
        "--engine", "-e",
        default="vader",
        choices=["vader", "finbert"],
        help="Sentiment engine (default: vader)",
    )
    parser.add_argument(
        "--backtest", "-b",
        action="store_true",
        help="Run backtest on all historical signals (instead of fetching new data)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show debug-level logs",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    _setup_logging(args.verbose)
    logger = logging.getLogger("forex-signal")

    # ── Backtest mode ──────────────────────────────────────────────────────────────
    if args.backtest:
        logger.info("Running backtest on all historical signals …")
        t0 = time.perf_counter()
        try:
            metrics_list = backtest_all_runs()
        except Exception as exc:
            logger.error("Backtest failed — %s", exc)
            return 1
        elapsed = time.perf_counter() - t0
        print(f"\nBacktest complete in {elapsed:.1f}s\n")
        for m in metrics_list:
            if m.total_trades == 0:
                print(f"[{m.window_hours}h window]  No trades (need at least 2 runs in DB)")
                continue
            print(f"[{m.window_hours}h window]  "
                  f"{m.total_trades} trades  |  "
                  f"Win rate: {m.win_rate:.0%}  |  "
                  f"Total return: {m.total_return_pct:+.2%}  |  "
                  f"Avg profit: {m.avg_profit_pct:+.2%}  |  "
                  f"Best: {m.max_profit_pct:+.2%}  |  "
                  f"Worst: {m.max_loss_pct:+.2%}")
        print()
        return 0

    # ── Normal pipeline mode ───────────────────────────────────────────────────────
    logger.info("Starting pipeline — engine=%s", args.engine)
    t0 = time.perf_counter()

    # 1. Fetch
    try:
        headlines = fetch_headlines()
    except RuntimeError as exc:
        logger.error("Aborting — %s", exc)
        return 1

    # 2. Detect currencies
    for h in headlines:
        h.currencies = detect_currencies(h.title)

    # 3. Analyse sentiment
    engine = get_engine(args.engine)
    try:
        headlines = engine.analyze(headlines)
    except RuntimeError as exc:
        logger.error("Aborting — %s", exc)
        return 1

    # 4. Generate signals
    signals = generate_signals(headlines)

    # 5. Save to DB
    try:
        run_id = save_run(signals, headlines, engine=engine.name)
    except RuntimeError as exc:
        logger.error("Failed to save run — %s", exc)
        return 1

    # 6. Print results
    elapsed = time.perf_counter() - t0
    print(f"\nRun #{run_id}  |  {engine.name}  |  {len(headlines)} headlines  |  {elapsed:.1f}s\n")
    print(f"{'Pair':>10} {'Signal':>7} {'Avg Score':>10}  {'#News':>5}")
    print("-" * 50)
    for s in signals:
        print(f"{s.pair:>10} {s.signal:>7} {s.avg_score:10.3f}  {s.headline_count:>5}")
    print()

    # 7. Send alert (no-op if not configured)
    alerter = get_alerter()
    if alerter:
        run = Run(
            id=run_id,
            engine=engine.name,
            headline_count=len(headlines),
            source_count=len({h.source for h in headlines}),
            created_at=datetime.utcnow().isoformat(),
            signals=signals,
        )
        alerter.send(run)

    logger.info("Done — run #%d in %.1fs", run_id, elapsed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
