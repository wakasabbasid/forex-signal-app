"""FinBERT sentiment engine — accurate but requires a one-time model download."""

import logging

from .. import config
from ..models import Headline
from .base import SentimentEngine

logger = logging.getLogger(__name__)


class FinBertEngine(SentimentEngine):
    """FinBERT-based engine using ``ProsusAI/finbert``."""

    def __init__(self) -> None:
        self._pipeline = None  # lazy-loaded on first analyse()

    @property
    def name(self) -> str:
        return "finbert"

    def _load(self) -> None:
        from transformers import pipeline

        logger.info("Loading FinBERT model %s …", config.FINBERT_MODEL)
        self._pipeline = pipeline(
            "text-classification",
            model=config.FINBERT_MODEL,
        )
        logger.info("FinBERT model loaded")

    def analyze(self, headlines: list[Headline]) -> list[Headline]:
        if not headlines:
            return headlines

        if self._pipeline is None:
            self._load()

        texts = [h.title for h in headlines]
        try:
            results = self._pipeline(texts, batch_size=config.FINBERT_BATCH_SIZE)
        except Exception as exc:
            logger.error("FinBERT inference failed: %s", exc)
            raise RuntimeError(f"FinBERT inference error: {exc}") from exc

        for h, result in zip(headlines, results):
            label = result["label"]
            score = result["score"]

            if label == "positive":
                h.score = score
                h.label = "bullish"
            elif label == "negative":
                h.score = -score
                h.label = "bearish"
            else:
                h.score = 0.0
                h.label = "neutral"

        logger.info("FinBERT scored %d headlines", len(headlines))
        return headlines
