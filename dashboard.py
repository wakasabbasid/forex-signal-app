"""
Forex Signal Dashboard — single app that works with VADER or FinBERT.
Run: streamlit run dashboard.py
"""

import streamlit as st
import pandas as pd

from src.forex_signal import config
from src.forex_signal.fetcher import fetch_headlines
from src.forex_signal.detector import detect_currencies
from src.forex_signal.sentiment import get_engine
from src.forex_signal.signals import generate_signals
from src.forex_signal.storage import (
    save_run,
    get_latest_run,
    get_history,
    get_signals_for_run,
    get_headlines_for_run,
    get_signal_time_series,
    get_backtest_trades,
    get_backtest_summary_by_pair,
    get_engine_comparison,
)
from src.forex_signal.backtest import backtest_all_runs, compute_metrics

ALL_PAIRS = sorted(set(config.CURRENCY_PAIRS.values()))


def strength_bar(avg_score: float) -> str:
    bar = "█" * int(abs(avg_score) * 10) or "▏"
    color = "🟢" if avg_score > 0 else "🔴" if avg_score < 0 else "⚪"
    return f"{color} {bar}"


def signal_emoji(signal: str) -> str:
    return {"BUY": "🟢", "SELL": "🔴", "HOLD": "⚪"}[signal]


def pair_color(avg_score: float) -> str:
    if avg_score >= config.SIGNAL_THRESHOLD:
        return "green"
    if avg_score <= -config.SIGNAL_THRESHOLD:
        return "red"
    return "gray"


# ── UI ────────────────────────────────────────────────────────────────────────────

st.set_page_config(page_title="Forex Signals", layout="wide")
st.title("📊 Forex Signal App")
st.caption("FinBERT or VADER sentiment — live + historical view")

# ── Sidebar ───────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.header("Controls")
    engine_choice = st.selectbox("Sentiment engine", ["vader", "finbert"], index=0)
    run_now = st.button("▶ Run Now")

    st.divider()
    st.header("Backtest")
    run_backtest = st.button("📊 Run Backtest")
    bt_window = st.selectbox("Window", config.BACKTEST_WINDOWS, index=2,
                             help="Holding window in hours. Use 24h with daily price data.")
    st.caption("Evaluates all historical non-HOLD signals against real price data via yfinance.")

    st.divider()
    st.header("Historical View")
    selected_pair = st.selectbox("Pair", ALL_PAIRS, index=0)
    chart_range = st.selectbox("Range", ["24 hours", "3 days", "7 days"], index=2)
    range_map = {"24 hours": 24, "3 days": 72, "7 days": 168}
    chart_limit = range_map[chart_range]

# ── Run on demand ─────────────────────────────────────────────────────────────────

if run_now:
    with st.spinner(f"Running {engine_choice} pipeline …"):
        try:
            headlines = fetch_headlines()
            for h in headlines:
                h.currencies = detect_currencies(h.title)
            engine = get_engine(engine_choice)
            headlines = engine.analyze(headlines)
            signals = generate_signals(headlines)
            run_id = save_run(signals, headlines, engine=engine.name)
            st.sidebar.success(f"Run #{run_id} saved")
        except Exception as exc:
            st.sidebar.error(str(exc))
    st.rerun()

# ── Read latest from DB ──────────────────────────────────────────────────────────

latest = get_latest_run()
if latest is None:
    st.warning("No data yet. Select an engine and click **▶ Run Now** in the sidebar.")
    st.stop()

latest_signals = get_signals_for_run(latest.id)
latest_headlines = get_headlines_for_run(latest.id)

# ── Row 1: Current signals ────────────────────────────────────────────────────────

st.subheader("🔴🟢 Current Signals")
n_cols = max(len(latest_signals), 1)
cols = st.columns(n_cols)
for i, s in enumerate(latest_signals):
    with cols[i]:
        color = pair_color(s.avg_score)
        st.markdown(
            f"<h3 style='margin:0; color:{color}'>{signal_emoji(s.signal)} {s.pair}</h3>",
            unsafe_allow_html=True,
        )
        st.markdown(f"**{s.signal}** · avg `{s.avg_score:+.3f}` · {s.headline_count} headlines")
        st.markdown(
            f"<span style='font-size:1.2em'>{strength_bar(s.avg_score)}</span>",
            unsafe_allow_html=True,
        )

st.caption(
    f"Run #{latest.id} · {latest.engine} · "
    f"{latest.headline_count} headlines · {latest.source_count} sources · "
    f"{latest.created_at[:19].replace('T', ' ')}"
)
st.divider()

# ── Row 2: Chart + Headlines ──────────────────────────────────────────────────────

chart_col, hl_col = st.columns([1.4, 1])

with chart_col:
    st.subheader(f"📈 {selected_pair} Score Over Time")
    ts = get_signal_time_series(selected_pair, chart_limit)
    if ts:
        df = pd.DataFrame(ts)
        df["time"] = pd.to_datetime(df["time"])
        df.set_index("time", inplace=True)

        st.line_chart(df, color="#00cc66")

        latest_val = df["score"].iloc[-1]
        avg = df["score"].mean()
        min_val = df["score"].min()
        max_val = df["score"].max()
        trend = (
            "bullish 📈" if latest_val > avg else
            "bearish 📉" if latest_val < avg else
            "flat ➡"
        )

        ca, cb, cc, cd = st.columns(4)
        ca.metric("Latest", f"{latest_val:+.3f}")
        cb.metric("Avg", f"{avg:+.3f}")
        cc.metric("Range", f"{min_val:+.2f} – {max_val:+.2f}")
        cd.metric("Trend", trend)
    else:
        st.info(f"No history yet for {selected_pair}.")

with hl_col:
    st.subheader("📰 Top Headlines")
    for h in latest_headlines[:15]:
        label_tag = {
            "bullish": "🟢 Bullish",
            "bearish": "🔴 Bearish",
            "neutral": "⚪ Neutral",
        }.get(h.label, h.label)
        st.markdown(
            f"**{label_tag}** — {h.title[:90]}{'…' if len(h.title) > 90 else ''}  \n"
            f"<sub>{h.source} · {', '.join(h.currencies) if h.currencies else '—'}</sub>",
            unsafe_allow_html=True,
        )
        st.divider()

# ── Row 3: Run history ────────────────────────────────────────────────────────────

st.divider()
st.subheader("Run History")
history = get_history(limit=24)
if history:
    hist_df = pd.DataFrame(
        {
            "Run #": [r.id for r in history],
            "Time": [r.created_at[:19].replace("T", " ") for r in history],
            "Engine": [r.engine for r in history],
            "Headlines": [r.headline_count for r in history],
            "Sources": [r.source_count for r in history],
        }
    )
    st.dataframe(hist_df, use_container_width=True, hide_index=True)

# ── Row 4: Backtest results ──────────────────────────────────────────────────────

st.divider()
st.subheader("📊 Backtest Results")

if run_backtest:
    with st.spinner("Running backtest against yfinance data …"):
        try:
            backtest_all_runs(windows=[bt_window])
            st.success("Backtest complete")
        except Exception as exc:
            st.error(str(exc))
    st.rerun()

bt_trades = get_backtest_trades(window_hours=bt_window)
if not bt_trades:
    st.info(f"No backtest data for {bt_window}h window. Click **📊 Run Backtest** in the sidebar.")
else:
    metrics = compute_metrics(bt_trades, bt_window)
    summary_by_pair = get_backtest_summary_by_pair(bt_window)

    # Summary row
    ca, cb, cc, cd, ce, cf = st.columns(6)
    ca.metric("Trades", metrics.total_trades)
    cb.metric("Win Rate", f"{metrics.win_rate:.0%}")
    cc.metric("Total Return", f"{metrics.total_return_pct:+.2%}")
    cd.metric("Avg / Trade", f"{metrics.avg_profit_pct:+.2%}")
    ce.metric("Best Trade", f"{metrics.max_profit_pct:+.2%}")
    cf.metric("Worst Trade", f"{metrics.max_loss_pct:+.2%}")

    # Per-pair breakdown
    if summary_by_pair:
        st.subheader("By Pair")
        pair_df = pd.DataFrame([
            {
                "Pair": pair,
                "Trades": info["trades"],
                "Win Rate": f"{info['win_rate']:.0%}",
                "Total Return": f"{info['total_return']:+.2%}",
                "Avg / Trade": f"{info['avg_profit']:+.2%}",
                "Best": f"{info['max_profit']:+.2%}",
                "Worst": f"{info['max_loss']:+.2%}",
            }
            for pair, info in sorted(summary_by_pair.items())
        ])
        st.dataframe(pair_df, use_container_width=True, hide_index=True)

    # Engine comparison
    engine_comp = get_engine_comparison(bt_window)
    if len(engine_comp) > 1:
        st.subheader("VADER vs FinBERT")
        comp_df = pd.DataFrame([
            {
                "Engine": engine.upper(),
                "Trades": info["trades"],
                "Win Rate": f"{info['win_rate']:.0%}",
                "Total Return": f"{info['total_return']:+.2%}",
                "Avg / Trade": f"{info['avg_profit']:+.2%}",
                "Best": f"{info['max_profit']:+.2%}",
                "Worst": f"{info['max_loss']:+.2%}",
            }
            for engine, info in sorted(engine_comp.items())
        ])
        st.dataframe(comp_df, use_container_width=True, hide_index=True)
