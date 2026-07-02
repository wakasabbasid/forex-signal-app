"""VADER sentiment engine — fast, no model download needed."""

import logging

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from .. import config
from ..models import Headline
from .base import SentimentEngine

logger = logging.getLogger(__name__)


class VaderEngine(SentimentEngine):
    """VADER-based engine with financial-lexicon augmentations."""

    def __init__(self) -> None:
        self._analyzer = SentimentIntensityAnalyzer()
        self._analyzer.lexicon.update(config.FINANCIAL_LINGO)
        logger.info("VADER engine initialised (%d custom lexicon entries)", len(config.FINANCIAL_LINGO))

    @property
    def name(self) -> str:
        return "vader"

    def analyze(self, headlines: list[Headline]) -> list[Headline]:
        if not headlines:
            return headlines

        for h in headlines:
            try:
                scores = self._analyzer.polarity_scores(h.title)
                compound = scores["compound"]
            except Exception:
                logger.warning("VADER failed on headline %r, defaulting to 0.0", h.title[:60])
                compound = 0.0

            h.score = compound
            if compound >= config.SIGNAL_THRESHOLD:
                h.label = "bullish"
            elif compound <= -config.SIGNAL_THRESHOLD:
                h.label = "bearish"
            else:
                h.label = "neutral"

        logger.info("VADER scored %d headlines", len(headlines))
        return headlines
