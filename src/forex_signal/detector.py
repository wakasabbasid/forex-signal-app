"""Currency code detection using word-boundary matching.

Fixes the substring false-positive issue: ``"USD" in "USMCA"`` is
``True``, but ``\\bUSD\\b`` in ``"USMCA"`` is correctly ``False``.
"""

import re
import logging

from . import config

logger = logging.getLogger(__name__)

# Pre-compiled pattern: \b(USD|EUR|GBP|...)\b
_PATTERN: re.Pattern[str] | None = None


def _get_pattern() -> re.Pattern[str]:
    global _PATTERN
    if _PATTERN is None:
        codes = sorted(config.CURRENCY_CODES, key=len, reverse=True)
        _PATTERN = re.compile(r"\b(" + "|".join(codes) + r")\b")
    return _PATTERN


def detect_currencies(text: str) -> list[str]:
    """Return currency codes mentioned in *text* (e.g. ``["USD", "EUR"]``).

    Uses word-boundary regex so that ``"US"`` does not match inside
    ``"focused"`` and ``"CHF"`` does not match inside ``"Frankfurt"``.
    """
    matches = _get_pattern().findall(text.upper())
    logger.debug("detect_currencies(%r) → %s", text[:60], matches)
    return matches
