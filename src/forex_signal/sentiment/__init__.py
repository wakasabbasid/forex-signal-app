"""Sentiment engine factory."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .base import SentimentEngine


def get_engine(name: str) -> "SentimentEngine":
    """Return a sentiment engine instance by name.

    Args:
        name: "vader" or "finbert".

    Returns:
        SentimentEngine instance.

    Raises:
        ValueError: If name is not recognised.
    """
    if name == "vader":
        from .vader import VaderEngine
        return VaderEngine()
    if name == "finbert":
        from .finbert import FinBertEngine
        return FinBertEngine()
    raise ValueError(f"Unknown sentiment engine: {name!r}. Use 'vader' or 'finbert'.")
