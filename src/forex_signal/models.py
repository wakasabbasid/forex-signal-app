"""Consistent data structures — dataclasses, no more ad-hoc dicts/tuples."""

from dataclasses import dataclass, field


@dataclass
class Headline:
    """A single news headline with its sentiment analysis results."""

    title: str
    source: str
    score: float = 0.0          # compound sentiment score (-1 to +1)
    label: str = "neutral"       # bullish / bearish / neutral
    currencies: list[str] = field(default_factory=list)


@dataclass
class Signal:
    """Aggregated signal for a single currency pair."""

    pair: str                     # e.g. "EUR/USD"
    signal: str                   # "BUY" | "SELL" | "HOLD"
    avg_score: float             # average compound score across headlines
    headline_count: int           # number of headlines mentioning this pair


@dataclass
class BacktestTrade:
    """A single simulated trade: entry → exit with profit/loss."""

    pair: str
    signal: str                   # "BUY" | "SELL" | "HOLD"
    engine: str                   # "vader" | "finbert"
    entry_price: float
    exit_price: float | None
    entry_time: str
    exit_time: str
    profit_pct: float             # e.g. 0.5 means +0.5%
    window_hours: int


@dataclass
class BacktestMetrics:
    """Aggregated performance stats for a backtest window."""

    window_hours: int
    total_trades: int
    win_rate: float               # 0.0 – 1.0
    total_return_pct: float
    avg_profit_pct: float
    max_profit_pct: float
    max_loss_pct: float
    trades: list[BacktestTrade] = field(default_factory=list)


@dataclass
class Run:
    """Metadata + results from a single pipeline execution."""

    id: int
    engine: str                   # "vader" | "finbert"
    headline_count: int
    source_count: int
    created_at: str               # ISO-8601 timestamp
    signals: list[Signal] = field(default_factory=list)
    headlines: list[Headline] = field(default_factory=list)
