"""Forex dashboard — live RSS headlines, live prices, auto-refresh, glowing cards."""

import json
import os
from datetime import datetime, timezone
from urllib.request import urlopen

import streamlit as st
import feedparser
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

GH_USER = os.environ.get("GH_USER", "wakasabbasid")
GH_PAGES = f"https://{GH_USER}.github.io/forex-signal-app"

CURRENCY_CODES = ["USD", "EUR", "GBP", "JPY", "CAD", "AUD", "NZD", "CHF"]
ALL_PAIRS = ["EUR/USD", "USD/JPY", "GBP/USD", "USD/CAD", "AUD/USD", "NZD/USD", "USD/CHF"]

# Which parser for signal scores: "score" for FinBERT numeric, "compound" for VADER
# FinBERT returns label+score, VADER returns compound. Both are stored as "score" in export.
ENGINE_META = {"vader": "VADER (fast)", "finbert": "FinBERT (accurate)"}

RSS_SOURCES = [
    ("Google News", "https://news.google.com/rss/search?q=forex+currency&hl=en-US&gl=US&ceid=US:en"),
    ("ForexLive", "https://www.forexlive.com/feed/"),
    ("FXStreet", "https://www.fxstreet.com/rss/news"),
]

FINANCIAL_LINGO = {
    "surge": 2.0, "surges": 2.0, "surged": 2.0,
    "rally": 1.5, "rallies": 1.5, "rallied": 1.5,
    "plunge": -2.0, "plunges": -2.0, "plunged": -2.0,
    "crash": -3.0, "crashes": -3.0, "crashed": -3.0,
    "soar": 2.0, "soars": 2.0, "soared": 2.0,
    "tumble": -2.0, "tumbles": -2.0, "tumbled": -2.0,
}

# ── CSS ───────────────────────────────────────────────────────────────────────────

ANIM_CSS = """
<style>
@keyframes pulse-green {
  0% { box-shadow: 0 0 5px #00ff88; }
  50% { box-shadow: 0 0 25px #00ff88, 0 0 50px #00ff8844; }
  100% { box-shadow: 0 0 5px #00ff88; }
}
@keyframes pulse-red {
  0% { box-shadow: 0 0 5px #ff3344; }
  50% { box-shadow: 0 0 25px #ff3344, 0 0 50px #ff334444; }
  100% { box-shadow: 0 0 5px #ff3344; }
}
@keyframes pulse-gray {
  0% { box-shadow: 0 0 3px #666; }
  50% { box-shadow: 0 0 10px #666; }
  100% { box-shadow: 0 0 3px #666; }
}
@keyframes fade-in {
  0% { opacity: 0; transform: translateY(8px); }
  100% { opacity: 1; transform: translateY(0); }
}
@keyframes scroll {
  0% { transform: translateX(100%); }
  100% { transform: translateX(-100%); }
}
.ticker-wrap {
  overflow: hidden; white-space: nowrap; background: #111;
  border: 1px solid #333; border-radius: 8px;
  padding: 8px 0; margin-bottom: 8px;
}
.ticker-text {
  display: inline-block;
  animation: scroll 140s linear infinite;
  font-size: 13px; color: #ccc;
}
.ticker-bull { color: #00ff88; }
.ticker-bear { color: #ff3344; }
.ticker-neut { color: #aaa; }
.buy-card {
  background: linear-gradient(135deg, #003d1a 0%, #001a0a 100%);
  border: 1px solid #00ff8844; border-radius: 12px;
  padding: 10px; margin-bottom: 8px;
  animation: pulse-green 2s ease-in-out infinite, fade-in 0.5s ease-out;
}
.sell-card {
  background: linear-gradient(135deg, #3d000a 0%, #1a0000 100%);
  border: 1px solid #ff334444; border-radius: 12px;
  padding: 10px; margin-bottom: 8px;
  animation: pulse-red 2s ease-in-out infinite, fade-in 0.5s ease-out;
}
.hold-card {
  background: linear-gradient(135deg, #1a1a1a 0%, #0a0a0a 100%);
  border: 1px solid #555; border-radius: 12px;
  padding: 10px; margin-bottom: 8px;
  animation: pulse-gray 3s ease-in-out infinite, fade-in 0.5s ease-out;
}
.price-up { color: #00ff88; }
.price-down { color: #ff3344; }
.price-flat { color: #aaa; }
.headline-item { animation: fade-in 0.4s ease-out; }
.meta { font-size: 12px; opacity: 0.6; }
.stButton button { width: 100%; }
</style>
"""


# ── Helpers ───────────────────────────────────────────────────────────────────────


@st.cache_data(ttl=600)
def fetch_signals():
    try:
        with urlopen(f"{GH_PAGES}/latest.json", timeout=10) as r:
            return json.loads(r.read())
    except Exception:
        return {}


@st.cache_data(ttl=0)
def fetch_live_headlines():
    analyzer = SentimentIntensityAnalyzer()
    analyzer.lexicon.update(FINANCIAL_LINGO)

    seen = set()
    headlines = []
    for name, url in RSS_SOURCES:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:10]:
                title = (entry.get("title") or "").strip()
                if not title or title in seen:
                    continue
                seen.add(title)
                scores = analyzer.polarity_scores(title)
                compound = scores["compound"]
                label = "bullish" if compound >= 0.2 else "bearish" if compound <= -0.2 else "neutral"
                currencies = [c for c in CURRENCY_CODES if c in title.upper()]
                headlines.append({"title": title[:130], "source": name, "label": label, "score": compound, "currencies": currencies})
        except Exception:
            pass
    return headlines


@st.cache_data(ttl=120)
def fetch_live_prices():
    """Fetch latest close for each pair from Twelve Data free endpoint."""
    prices = {}
    for pair in ALL_PAIRS:
        sym = pair.replace("/", "")
        try:
            with urlopen(f"https://api.twelvedata.com/price?symbol={sym}&apikey=demo", timeout=8) as r:
                data = json.loads(r.read())
                if "price" in data:
                    prices[pair] = float(data["price"])
        except Exception:
            pass
    return prices


def signal_label(signal):
    return {"BUY": "🟢 BUY", "SELL": "🔴 SELL", "HOLD": "⚪ HOLD"}[signal]


def card_class(signal):
    return {"BUY": "buy-card", "SELL": "sell-card", "HOLD": "hold-card"}[signal]


def signal_arrow(signal):
    return {"BUY": "📈", "SELL": "📉", "HOLD": "➡"}[signal]


def next_pipeline_txt():
    now = datetime.now(timezone.utc)
    hour = now.hour
    if hour >= 23 or now.weekday() >= 5:
        return "Next run: Mon 01:00 UTC"
    remaining = 60 - now.minute
    return f"Next pipeline: ~{remaining} min"


# ── UI ────────────────────────────────────────────────────────────────────────────

st.set_page_config(page_title="Forex Signals", layout="wide")
st.markdown(ANIM_CSS, unsafe_allow_html=True)

# Top bar
title_col, refresh_col, clock_col = st.columns([2, 1, 1])
with title_col:
    st.title("📊 Forex Signal App")
    st.caption("Live headlines · Live prices · Hourly signals")
with refresh_col:
    st.markdown(f"<div class='meta' style='text-align:right;padding-top:18px;'>{next_pipeline_txt()}</div>", unsafe_allow_html=True)
with clock_col:
    if st.button("🔄 Refresh Now", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# ── Live prices bar ───────────────────────────────────────────────────────────────

live_prices = fetch_live_prices()
if live_prices:
    price_cells = []
    for pair in ALL_PAIRS:
        p = live_prices.get(pair)
        if p:
            price_cells.append(f"<b>{pair}</b> {p:.5f}")
    if price_cells:
        st.markdown(
            f"<div style='display:flex;gap:20px;flex-wrap:wrap;justify-content:center;"
            f"background:#0a0a0a;border:1px solid #222;border-radius:8px;padding:6px 12px;margin-bottom:4px;"
            f"font-size:13px;'>"
            + "".join(f"<span>{c}</span>" for c in price_cells)
            + "</div>",
            unsafe_allow_html=True,
        )

# ── Ticker ────────────────────────────────────────────────────────────────────────

headlines = fetch_live_headlines()
ticker_parts = []
if headlines:
    for h in headlines[:12]:
        cls = {"bullish": "ticker-bull", "bearish": "ticker-bear", "neutral": "ticker-neut"}.get(h["label"], "")
        ticker_parts.append(f'<span class="{cls}">{h["title"][:60]}</span>')

if ticker_parts:
    st.markdown(
        f'<div class="ticker-wrap"><div class="ticker-text">'
        f'  {" &nbsp;▎&nbsp; ".join(ticker_parts)} &nbsp;▎&nbsp; '
        f'  {" &nbsp;▎&nbsp; ".join(ticker_parts)}'
        f'</div></div>',
        unsafe_allow_html=True,
    )

# ── Main content ──────────────────────────────────────────────────────────────────

col1, col2 = st.columns([1.1, 1.3])

with col1:
    st.subheader("🔴🟢 Live Signals")
    latest = fetch_signals()
    if isinstance(latest, dict) and latest.get("signals"):
        sigs = latest["signals"]
        sub_cols = st.columns(2)
        for idx, s in enumerate(sigs):
            with sub_cols[idx % 2]:
                st.markdown(
                    f'<div class="{card_class(s["signal"])}">'
                    f'  <div style="font-size:18px;font-weight:700;">{signal_arrow(s["signal"])} {s["pair"]}</div>'
                    f'  <div style="font-size:22px;font-weight:800;margin:2px 0;">{signal_label(s["signal"])}</div>'
                    f'  <div class="meta">score {s["avg_score"]:+.3f} · {s["headline_count"]} news</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
        st.caption(
            f"Run #{latest.get('run_id', '?')} · {ENGINE_META.get(latest.get('engine', ''), latest.get('engine', '?'))} · "
            f"{latest.get('headline_count', 0)} headlines · {latest.get('source_count', 0)} sources"
        )

        # Mini stats
        total = len(sigs)
        buys = sum(1 for s in sigs if s["signal"] == "BUY")
        sells = sum(1 for s in sigs if s["signal"] == "SELL")
        st.markdown(
            f"<div class='meta' style='text-align:center;'>"
            f"🟢 {buys} BUY &nbsp;&nbsp;🔴 {sells} SELL &nbsp;&nbsp;⚪ {total - buys - sells} HOLD"
            f"</div>",
            unsafe_allow_html=True,
        )
    else:
        st.info("No signals yet. Pipeline runs Mon–Fri hourly.")

with col2:
    st.subheader("📰 Live Headlines")
    st.caption("RSS → VADER sentiment, live on every page load")
    if headlines:
        for i, h in enumerate(headlines[:15]):
            delay = i * 0.05
            tag = {"bullish": "🟢 Bullish", "bearish": "🔴 Bearish", "neutral": "⚪ Neutral"}[h["label"]]
            score_cls = "price-up" if h["score"] > 0 else "price-down"
            currencies = ", ".join(h["currencies"]) if h["currencies"] else "—"
            st.markdown(
                f"<div class='headline-item' style='animation-delay:{delay}s'>"
                f"  <div style='display:flex;align-items:baseline;gap:8px;'>"
                f"    <span style='font-weight:600;'>{tag}</span>"
                f"    <span class='{score_cls}' style='font-size:13px;'>{h['score']:+.3f}</span>"
                f"  </div>"
                f"  <div style='margin:2px 0 4px 0;'>{h['title']}</div>"
                f"  <div class='meta'>{h['source']} · {currencies}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )
            st.divider()
    else:
        st.info("Could not fetch live headlines.")

# ── Footer ────────────────────────────────────────────────────────────────────────

st.divider()
st.markdown(
    "<div class='meta' style='text-align:center;'>"
    "Signals from GitHub Actions (hourly) · Prices from Twelve Data · Headlines live from RSS · "
    "Hosted free on Hugging Face Spaces"
    "</div>",
    unsafe_allow_html=True,
)
