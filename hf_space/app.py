"""
Hugging Face Space — forex signal dashboard reading from GitHub Pages.
Reads: https://<user>.github.io/forex-signal-app/latest.json

Set the env var GH_USER to your GitHub username in Space Secrets.
"""

import json
import os
from urllib.request import urlopen

import streamlit as st

GH_USER = os.environ.get("GH_USER", "wakasabbasid")
GH_PAGES = f"https://{GH_USER}.github.io/forex-signal-app"


def fetch_json(path: str) -> dict | list:
    url = f"{GH_PAGES}/{path}"
    try:
        with urlopen(url, timeout=10) as r:
            return json.loads(r.read())
    except Exception as exc:
        st.error(f"Failed to fetch {url}: {exc}")
        return {}


st.set_page_config(page_title="Forex Signals", layout="wide")
st.title("📊 Forex Signal App")
st.caption("Powered by GitHub Actions + Hugging Face Spaces")

col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("🔴🟢 Current Signals")
    latest = fetch_json("latest.json")
    if isinstance(latest, dict) and latest.get("signals"):
        for s in latest["signals"]:
            emoji = {"BUY": "🟢 BUY", "SELL": "🔴 SELL", "HOLD": "⚪ HOLD"}[s["signal"]]
            st.metric(label=s["pair"], value=emoji,
                      delta=f"{s['avg_score']:+.3f} avg · {s['headline_count']} news")
        st.caption(f"Run #{latest.get('run_id', '?')} · {latest.get('engine', '?')} · "
                   f"{latest.get('headline_count', 0)} headlines")
    else:
        st.info("No data yet. The pipeline runs via GitHub Actions on schedule.")

with col2:
    st.subheader("📰 Headlines")
    h_data = fetch_json("headlines.json")
    if isinstance(h_data, dict) and h_data.get("headlines"):
        for h in h_data["headlines"][:15]:
            tag = {"bullish": "🟢 Bullish", "bearish": "🔴 Bearish", "neutral": "⚪ Neutral"}.get(h.get("label", ""), h.get("label", ""))
            st.markdown(f"**{tag}** — {h['title'][:90]}...\n<sub>{h['source']} · {', '.join(h.get('currencies',[])) if h.get('currencies') else '—'}</sub>", unsafe_allow_html=True)
            st.divider()
    else:
        st.info("No headlines yet.")

st.divider()
st.subheader("⏰ Schedule")
st.markdown("Runs every hour Mon-Fri via GitHub Actions. Data updates within minutes.")
