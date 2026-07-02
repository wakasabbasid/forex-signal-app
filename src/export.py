"""Export latest signal results to JSON files for static hosting (Hugging Face Spaces).

Usage::
    python src/export.py

Writes:
    data/latest.json   — current signals + metadata
    data/runs.json     — last 48 runs
    data/headlines.json — headlines for the latest run
"""

import json
import sys
from pathlib import Path

# Ensure the package is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.forex_signal import config
from src.forex_signal.fetcher import fetch_headlines
from src.forex_signal.detector import detect_currencies
from src.forex_signal.sentiment import get_engine
from src.forex_signal.signals import generate_signals
from src.forex_signal.storage import save_run, get_latest_run, get_signals_for_run, get_headlines_for_run, get_history

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def export_latest() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Run pipeline
    print("Fetching headlines...")
    headlines = fetch_headlines()

    print("Detecting currencies...")
    for h in headlines:
        h.currencies = detect_currencies(h.title)

    print("Analyzing sentiment with VADER...")
    engine = get_engine("vader")
    headlines = engine.analyze(headlines)

    print("Generating signals...")
    signals = generate_signals(headlines)

    print("Saving to DB...")
    run_id = save_run(signals, headlines, engine=engine.name)

    # Export latest
    latest = {
        "run_id": run_id,
        "engine": engine.name,
        "headline_count": len(headlines),
        "source_count": len({h.source for h in headlines}),
        "created_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "signals": [
            {"pair": s.pair, "signal": s.signal, "avg_score": s.avg_score, "headline_count": s.headline_count}
            for s in signals
        ],
    }
    (DATA_DIR / "latest.json").write_text(json.dumps(latest, indent=2))
    print(f"Wrote {DATA_DIR / 'latest.json'}")

    # Export headlines
    h_data = [
        {"title": h.title, "source": h.source, "label": h.label, "score": h.score, "currencies": h.currencies}
        for h in headlines[:20]
    ]
    (DATA_DIR / "headlines.json").write_text(json.dumps({"headlines": h_data, "run_id": run_id}, indent=2))
    print(f"Wrote {DATA_DIR / 'headlines.json'}")

    # Export run history
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
                {"pair": s.pair, "signal": s.signal, "avg_score": s.avg_score, "headline_count": s.headline_count}
                for s in sigs
            ],
        })
    (DATA_DIR / "runs.json").write_text(json.dumps({"runs": runs_data}, indent=2))
    print(f"Wrote {DATA_DIR / 'runs.json'}")

    print(f"\nDone — run #{run_id}, {len(signals)} signals, {len(headlines)} headlines")


if __name__ == "__main__":
    export_latest()
