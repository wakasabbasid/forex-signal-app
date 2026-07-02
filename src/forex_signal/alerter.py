"""Alerts — push notifications when signals fire.

Currently supports Telegram.  Add new backends by subclassing ``Alerter``.
"""

import logging
from abc import ABC, abstractmethod
from typing import Any

from . import config
from .models import Run

logger = logging.getLogger(__name__)


# ── Abstract base ─────────────────────────────────────────────────────────────────


class Alerter(ABC):
    """Base class for push-notification backends."""

    @abstractmethod
    def send(self, run: Run) -> bool:
        """Send an alert for the given run. Return True on success."""
        ...


# ── Telegram ──────────────────────────────────────────────────────────────────────


def _fmt(run: Run) -> str:
    """Build a concise alert message.

    Example::

        📊 Forex Signal Alert

        🟢 BUY   EUR/USD  (+0.350 · 5 news)
        🔴 SELL  USD/JPY  (-0.280 · 3 news)

        Run #42 · vader · 55 headlines
    """
    lines: list[str] = ["📊 Forex Signal Alert\n"]
    for s in run.signals:
        if s.signal == "HOLD":
            continue
        emoji = {"BUY": "🟢", "SELL": "🔴"}.get(s.signal, "⚪")
        lines.append(
            f"{emoji} {s.signal:5}  {s.pair:10}  "
            f"({s.avg_score:+.3f} · {s.headline_count} news)"
        )
    if len(lines) == 1:
        lines.append("No strong signals this run.")
    lines.append(
        f"\nRun #{run.id} · {run.engine} · {run.headline_count} headlines"
    )
    return "\n".join(lines)


class TelegramAlerter(Alerter):
    """Sends alerts via a Telegram bot.

    Requires ``TELEGRAM_BOT_TOKEN`` and ``TELEGRAM_CHAT_ID`` env vars.
    """

    def __init__(self) -> None:
        self._token = config.TELEGRAM_BOT_TOKEN
        self._chat_id = config.TELEGRAM_CHAT_ID
        self._session: Any = None

    @property
    def configured(self) -> bool:
        return bool(self._token and self._chat_id)

    def _import(self) -> Any:
        import requests
        return requests

    def send(self, run: Run) -> bool:
        if not self.configured:
            logger.debug("Telegram not configured — skipping alert")
            return False

        text = _fmt(run)
        url = f"https://api.telegram.org/bot{self._token}/sendMessage"

        try:
            reqs = self._import()
            resp = reqs.post(url, json={
                "chat_id": self._chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            }, timeout=15)
            resp.raise_for_status()
            logger.info("Telegram alert sent for run #%d", run.id)
            return True
        except Exception as exc:
            logger.warning("Failed to send Telegram alert: %s", exc)
            return False


# ── Factory ───────────────────────────────────────────────────────────────────────


def get_alerter() -> Alerter | None:
    """Return a configured alerter, or None if none is available."""
    tg = TelegramAlerter()
    if tg.configured:
        return tg
    return None
