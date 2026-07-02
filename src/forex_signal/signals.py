"""Aggregate scored headlines into per-pair BUY/SELL/HOLD signals.

Pair detection is context-aware: if a headline mentions both ``EUR``
and ``USD``, it resolves to ``EUR/USD`` — *not* ``USD/JPY`` (the
fallback default when ``USD`` appears alone).
"""

import logging

from . import config
from .models import Headline, Signal, Run
from .detector import detect_currencies

logger = logging.getLogger(__name__)


def resolve_pairs(codes: list[str]) -> list[str]:
    """Given detected currency codes, return the most likely pairs.

    Strategy
    --------
    1. Scan ``config.PAIR_COMBOS`` for any pair whose *both* codes
       appear in *codes*.  Those codes are consumed.
    2. Any remaining single code falls back to ``config.CURRENCY_PAIRS``.

    Examples
    --------
    ``["EUR", "USD"]``          → ``["EUR/USD"]``          (combo)
    ``["USD", "JPY"]``          → ``["USD/JPY"]``          (combo)
    ``["EUR", "USD", "GBP"]``   → ``["EUR/USD", "GBP/USD"]`` (combo + combo)
    ``["USD"]``                 → ``["USD/JPY"]``          (fallback)
    ``["EUR"]``                 → ``["EUR/USD"]``          (fallback)
    """
    if not codes:
        return []

    used = set()
    pairs: list[str] = []

    # 1. Try known combos (both base + quote mentioned)
    for pair_codes, pair_name in config.PAIR_COMBOS.items():
        if pair_codes.issubset(codes):
            pairs.append(pair_name)
            used.update(pair_codes)

    # 2. Remaining single codes → fallback mapping
    for code in codes:
        if code not in used:
            pair = config.CURRENCY_PAIRS.get(code)
            if pair and pair not in pairs:
                pairs.append(pair)

    return pairs


def generate_signals(headlines: list[Headline]) -> list[Signal]:
    """Group headline scores by **pair** (not by currency code) and classify.

    The algorithm:
        1. For every headline, detect mentioned currency codes via
           word-boundary regex.
        2. Resolve those codes to pairs using ``resolve_pairs()``
           (combos first, then single-code fallback).
        3. Collect all scores per *pair*.
        4. Average the scores per pair → BUY / SELL / HOLD.

    Returns:
        Signals sorted by absolute average score (strongest first).
    """
    pair_scores: dict[str, list[float]] = {}

    for h in headlines:
        codes = detect_currencies(h.title)
        h.currencies = codes
        pairs = resolve_pairs(codes)

        for pair in pairs:
            pair_scores.setdefault(pair, []).append(h.score)

    signals: list[Signal] = []
    for pair, scores in pair_scores.items():
        avg = sum(scores) / len(scores)
        if avg >= config.SIGNAL_THRESHOLD:
            signal = "BUY"
        elif avg <= -config.SIGNAL_THRESHOLD:
            signal = "SELL"
        else:
            signal = "HOLD"

        signals.append(Signal(
            pair=pair,
            signal=signal,
            avg_score=avg,
            headline_count=len(scores),
        ))

    signals.sort(key=lambda s: abs(s.avg_score), reverse=True)
    logger.info("Generated %d signals from %d headlines", len(signals), len(headlines))
    return signals
