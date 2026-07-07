"""Export latest signal results to JSON files for static hosting.

Usage::
    python src/export.py                    # VADER (fast)
    python src/export.py --engine finbert   # FinBERT (accurate)

History is accumulated in data/runs.json (restored from gh-pages before each run).
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
from src.forex_signal.signals import generate_signals, resolve_pairs
from src.forex_signal.storage import save_run

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def load_run_history() -> list[dict]:
    """Load existing runs from data/runs.json (restored from gh-pages)."""
    path = DATA_DIR / "runs.json"
    if path.exists():
        try:
            data = json.loads(path.read_text())
            return data.get("runs", [])
        except Exception:
            pass
    return []


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
    run_obj = {
        "id": run_id,
        "engine": engine.name,
        "headline_count": len(headlines),
        "source_count": len({h.source for h in headlines}),
        "created_at": now,
        "signals": [
            {"pair": s.pair, "signal": s.signal, "avg_score": round(s.avg_score, 4), "headline_count": s.headline_count}
            for s in signals
        ],
    }

    # Write latest
    (DATA_DIR / "latest.json").write_text(json.dumps(run_obj, indent=2))
    print(f"Wrote {DATA_DIR / 'latest.json'}")

    # Write pair headline breakdown
    pair_h_map: dict[str, list[dict]] = {}
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

    # Write headlines export
    h_data = [
        {"title": h.title, "source": h.source, "label": h.label, "score": round(h.score, 4), "currencies": h.currencies}
        for h in headlines[:20]
    ]
    (DATA_DIR / "headlines.json").write_text(json.dumps({"headlines": h_data, "run_id": run_id}, indent=2))
    print(f"Wrote {DATA_DIR / 'headlines.json'}")

    # Accumulate run history (preserve across deploys)
    existing = load_run_history()
    existing.append(run_obj)
    # Keep last 200 runs max
    existing = existing[-200:]
    (DATA_DIR / "runs.json").write_text(json.dumps({"runs": existing}, indent=2))
    print(f"Wrote {DATA_DIR / 'runs.json'} ({len(existing)} runs accumulated)")

    print(f"\nDone — run #{run_id}, {engine_name}, {len(signals)} signals, {len(headlines)} headlines")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", "-e", default="vader", choices=["vader", "finbert"])
    args = parser.parse_args()
    export_latest(args.engine)
