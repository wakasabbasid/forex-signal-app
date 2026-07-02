"""Abstract base class for sentiment engines."""

from abc import ABC, abstractmethod

from ..models import Headline


class SentimentEngine(ABC):
    """Plug-in sentiment engine — VADER and FinBERT both implement this."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Short identifier, e.g. ``"vader"`` or ``"finbert"``."""
        ...

    @abstractmethod
    def analyze(self, headlines: list[Headline]) -> list[Headline]:
        """Score each headline and attach ``.score`` and ``.label``.

        Should mutate the list in place for performance, but also return it.
        """
        ...
