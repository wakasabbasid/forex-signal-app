"""Export latest signal results to JSON files for static hosting.

Usage::
    python src/export.py                    # VADER (fast)
    python src/export.py --engine finbert   # FinBERT (accurate)
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.forex_signal.fetcher import fetch_headlines
from src.forex_signal.detector import detect_currencies
from src.forex_signal.sentiment import get_engine
from src.forex_signal.signals import generate_signals
from src.forex_signal.storage import save_run, get_signals_for_run, get_headlines_for_run, get_history

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def export_latest(engine_name: str = "vader") -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Fetching headlines...")
    headlines = fetch_headlines()

    print(f"Detecting currencies...")
    for h in headlines:
        h.currencies = detect_currencies(h.title)

    print(f"Analyzing sentiment with {engine_name}...")
    engine = get_engine(engine_name)
    headlines = engine.analyze(headlines)

    print("Generating signals...")
    signals = generate_signals(headlines)

    print("Saving to DB...")
    run_id = save_run(signals, headlines, engine=engine.name)

    now = datetime.now(timezone.utc).isoformat()
    latest = {
        "run_id": run_id,
        "engine": engine.name,
        "headline_count": len(headlines),
        "source_count": len({h.source for h in headlines}),
        "created_at": now,
        "signals": [
            {"pair": s.pair, "signal": s.signal, "avg_score": round(s.avg_score, 4), "headline_count": s.headline_count}
            for s in signals
        ],
    }
    (DATA_DIR / "latest.json").write_text(json.dumps(latest, indent=2))
    print(f"Wrote {DATA_DIR / 'latest.json'}")

    # Per-pair headline breakdown for drill-down
    pair_h_map: dict[str, list[dict]] = {}
    for h in headlines:
        for code in h.currencies:
            # Map currency code back to pair (from signals logic)
            # Simple: use CURRENCY_PAIRS from config, but we only know codes
            # The cleanest: re-derive pairs from signals
            pass

    # Better approach: derive from signal generation — for each headline,
    # check which pairs it could belong to based on detected currencies
    from src.forex_signal.signals import resolve_pairs
    pair_h_map = {}
    for h in headlines:
        pairs = resolve_pairs(h.currencies)
        for p in pairs:
            pair_h_map.setdefault(p, []).append({
                "title": h.title,
                "source": h.source,
                "label": h.label,
                "score": round(h.score, 4),
            })
    (DATA_DIR / "pair_headlines.json").write_text(
        json.dumps({"run_id": run_id, "pairs": pair_h_map}, indent=2)
    )
    print(f"Wrote {DATA_DIR / 'pair_headlines.json'}")

    h_data = [
        {"title": h.title, "source": h.source, "label": h.label, "score": round(h.score, 4), "currencies": h.currencies}
        for h in headlines[:20]
    ]
    (DATA_DIR / "headlines.json").write_text(json.dumps({"headlines": h_data, "run_id": run_id}, indent=2))
    print(f"Wrote {DATA_DIR / 'headlines.json'}")

    runs = get_history(limit=48)
    runs_data = []
    for r in runs:
        sigs = get_signals_for_run(r.id)
        runs_data.append({
            "id": r.id,
            "engine": r.engine,
            "headline_count": r.headline_count,
            "source_count": r.source_count,
            "created_at": r.created_at,
            "signals": [
                {"pair": s.pair, "signal": s.signal, "avg_score": round(s.avg_score, 4), "headline_count": s.headline_count}
                for s in sigs
            ],
        })
    (DATA_DIR / "runs.json").write_text(json.dumps({"runs": runs_data}, indent=2))
    print(f"Wrote {DATA_DIR / 'runs.json'}")

    print(f"\nDone — run #{run_id}, {engine_name}, {len(signals)} signals, {len(headlines)} headlines")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", "-e", default="vader", choices=["vader", "finbert"])
    args = parser.parse_args()
    export_latest(args.engine)
