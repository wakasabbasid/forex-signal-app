"""RSS headline fetching with deduplication and error handling."""

import logging

import feedparser

from . import config
from .models import Headline

logger = logging.getLogger(__name__)


def fetch_headlines(
    sources: list[tuple[str, str]] | None = None,
    max_per_source: int | None = None,
) -> list[Headline]:
    """Fetch headlines from all RSS sources.

    Each source is tried independently.  A single source failure is logged
    as a warning; only if *every* source fails is a ``RuntimeError`` raised.

    Returns:
        Deduplicated list of :class:`Headline` instances.
    """
    if sources is None:
        sources = config.RSS_SOURCES
    if max_per_source is None:
        max_per_source = config.MAX_PER_SOURCE

    seen: set[str] = set()
    headlines: list[Headline] = []
    successes = 0

    for name, url in sources:
        try:
            feed = feedparser.parse(url)
            count = 0
            for entry in feed.entries:
                title = (entry.get("title") or "").strip()
                if not title or title in seen:
                    continue
                seen.add(title)
                headlines.append(Headline(title=title, source=name))
                count += 1
                if count >= max_per_source:
                    break
            successes += 1
            logger.info("Fetched %d headlines from %s", count, name)
        except Exception as exc:
            logger.warning("Failed to fetch %s: %s", name, exc)

    if not successes:
        raise RuntimeError("All RSS sources failed — no headlines to analyse.")

    logger.info(
        "Total: %d headlines from %d/%d sources",
        len(headlines), successes, len(sources),
    )
    return headlines
