"""
Prices - Bloomberg-style price chart.
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from utils.csv_data import load_prices, PRICES_DIR

st.set_page_config(layout="wide")

# ── Bloomberg dark theme ──────────────────────────────────────────────────────
st.markdown("""
<style>
  /* Page background */
  .stApp, [data-testid="stAppViewContainer"], .main { background-color:#0f0f0f !important; }
  [data-testid="stSidebar"] { background-color:#111111 !important; }
  .block-container { padding-top:0.8rem !important; padding-bottom:0 !important; }

  /* Selectbox */
  [data-testid="stSelectbox"] > div > div {
    background-color:#1a1a1a !important;
    color:#ffffff !important;
    border-color:#333 !important;
  }

  /* Radio (timeframe) */
  [data-testid="stRadio"] { margin-top:4px; }
  [data-testid="stRadio"] label { color:#666 !important; font-size:0.78rem !important;
    padding:2px 6px !important; }
  [data-testid="stRadio"] div[role=radio][aria-checked=true] + div > p {
    color:#f5a623 !important; font-weight:700 !important; }

  /* Remove default Streamlit spacing around plotly chart */
  [data-testid="stPlotlyChart"] { margin-top:-8px; margin-bottom:-8px; }
</style>
""", unsafe_allow_html=True)


# ── Timeframes ────────────────────────────────────────────────────────────────

TIMEFRAMES = ["WTD", "MTD", "YTD", "1M", "3M", "6M", "1Y", "2Y", "3Y", "5Y", "ALL"]


def start_date_for(key: str, today: datetime):
    return {
        "WTD":  today - timedelta(days=today.weekday()),
        "MTD":  today.replace(day=1),
        "YTD":  today.replace(month=1, day=1),
        "1M":   today - timedelta(days=30),
        "3M":   today - timedelta(days=91),
        "6M":   today - timedelta(days=182),
        "1Y":   today - timedelta(days=365),
        "2Y":   today - timedelta(days=730),
        "3Y":   today - timedelta(days=1095),
        "5Y":   today - timedelta(days=1825),
        "ALL":  None,
    }.get(key)


def xaxis_fmt(num_days: int) -> str:
    if num_days <= 31:   return "%b %d"
    if num_days <= 365:  return "%b '%y"
    return "%Y"


# ── Data ─────────────────────────────────────────────────────────────────────

@st.cache_data
def available_tickers():
    if not PRICES_DIR.exists():
        return []
    return sorted(f.stem for f in PRICES_DIR.glob("*.csv"))


tickers = available_tickers()
if not tickers:
    st.warning("No price data found. Fetch prices from the Data Management page.")
    st.stop()

# ── Read current control values (default if first run) ───────────────────────
# Controls are rendered BELOW the chart; values are read from session_state.

ticker = st.session_state.get("bbg_ticker", tickers[tickers.index("XBI")] if "XBI" in tickers else tickers[0])
tf     = st.session_state.get("bbg_tf", "YTD")

# ── Load & filter ─────────────────────────────────────────────────────────────

df = load_prices(ticker)
if df.empty:
    st.warning(f"No price data for {ticker}.")
    st.stop()

df = df.sort_values("date").reset_index(drop=True)
today = datetime.now()
start = start_date_for(tf, today)

if start is not None:
    df = df[df["date"] >= pd.Timestamp(start)]

if df.empty:
    st.warning(f"No data for {ticker} in selected timeframe.")
    st.stop()

# ── Stats ─────────────────────────────────────────────────────────────────────

latest    = df["close"].iloc[-1]
first     = df["close"].iloc[0]
chg       = latest - first
pct       = (chg / first * 100) if first else 0
hi        = df["close"].max()
lo        = df["close"].min()
hi_date   = df.loc[df["close"].idxmax(), "date"]
lo_date   = df.loc[df["close"].idxmin(), "date"]
last_date = df["date"].iloc[-1]

pos  = chg >= 0
clr  = "#4caf50" if pos else "#f44336"
sign = "+" if pos else ""

def fmtd(d):
    return pd.Timestamp(d).strftime("%m/%d/%y")

num_days = (df["date"].max() - df["date"].min()).days
date_range_str = (
    f"{fmtd(df['date'].iloc[0])} - {fmtd(last_date)}"
    if start else "All Time"
)

# ── Bloomberg header ──────────────────────────────────────────────────────────

st.markdown(f"""
<div style="line-height:1.35; padding-bottom:4px;">

  <div style="font-size:1.25rem; font-weight:600; color:#ffffff; letter-spacing:.5px;">
    {ticker} US Equity
  </div>

  <div style="margin-top:3px;">
    <span style="font-size:1.85rem; font-weight:700; color:#fff;">{latest:.2f}</span>
    <span style="font-size:1.85rem; font-weight:700; color:{clr}; margin-left:.7rem;">{sign}{chg:.2f}</span>
    <span style="font-size:1.85rem; font-weight:700; color:{clr}; margin-left:.4rem;">{sign}{abs(pct):.2f}%</span>
    <span style="font-size:.85rem; color:#666; margin-left:1rem;">At {fmtd(last_date)}</span>
  </div>

  <div style="margin-top:5px; font-size:.8rem; color:#aaa;">
    <span style="color:#f5a623; font-weight:700;">Price Chart</span>
    &nbsp;&nbsp;{tf}&nbsp;&nbsp;{date_range_str}&nbsp;&nbsp;Period: 1D
  </div>

  <div style="margin-top:4px; font-size:.78rem; color:#aaa;
              display:flex; flex-wrap:wrap; gap:0 2.5rem;">
    <span><span style="color:#f5a623;">■</span>&nbsp;Start&nbsp;
          <strong style="color:#fff;">{first:.2f}</strong></span>
    <span><span style="color:#ccc;">■</span>&nbsp;Change&nbsp;
          <strong style="color:#fff;">{sign}{chg:.2f} ({sign}{abs(pct):.2f}%)</strong></span>
    <span><span style="color:#ccc;">■</span>&nbsp;High on {fmtd(hi_date)}&nbsp;
          <strong style="color:#fff;">{hi:.2f}</strong></span>
    <span><span style="color:#ccc;">■</span>&nbsp;Low on {fmtd(lo_date)}&nbsp;
          <strong style="color:#fff;">{lo:.2f}</strong></span>
  </div>

</div>
""", unsafe_allow_html=True)

# ── Chart ─────────────────────────────────────────────────────────────────────

price_range = hi - lo
pad = max(price_range * 0.05, 0.5)
y_min = lo - pad
y_max = hi + pad

fig = go.Figure()

# Area trace
fig.add_trace(go.Scatter(
    x=df["date"],
    y=df["close"],
    fill="tozeroy",
    fillcolor="rgba(18, 48, 110, 0.88)",
    line=dict(color="white", width=1.5),
    mode="lines",
    hovertemplate="%{x|%b %d, %Y}  %{y:.2f}<extra></extra>",
))

# Orange dashed start-price reference line
fig.add_hline(
    y=first,
    line=dict(color="#f5a623", width=1, dash="dot"),
    opacity=0.85,
)

# Current price label box pinned to right edge
fig.add_annotation(
    x=1, y=latest,
    xref="paper", yref="y",
    text=f"  {latest:.2f}  ",
    showarrow=False,
    xanchor="left", yanchor="middle",
    bgcolor="white",
    font=dict(color="black", size=10.5),
    borderpad=2,
)

fig.update_layout(
    plot_bgcolor="#0f0f0f",
    paper_bgcolor="#0f0f0f",
    font=dict(color="white"),
    height=520,
    margin=dict(l=10, r=75, t=6, b=30),
    hovermode="x",
    hoverlabel=dict(
        bgcolor="#1a1a1a",
        bordercolor="#444",
        font=dict(color="white", size=11),
    ),
    showlegend=False,
    xaxis=dict(
        showgrid=False,
        zeroline=False,
        showline=False,
        tickfont=dict(color="#666", size=9.5),
        tickformat=xaxis_fmt(num_days),
    ),
    yaxis=dict(
        side="right",
        showgrid=True,
        gridcolor="#222",
        gridwidth=1,
        zeroline=False,
        showline=False,
        tickfont=dict(color="#aaa", size=9.5),
        tickformat=".2f",
        range=[y_min, y_max],
    ),
)

st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

# ── Controls (below chart) ────────────────────────────────────────────────────

c1, c2 = st.columns([2, 10])
with c1:
    default_idx = tickers.index("XBI") if "XBI" in tickers else 0
    st.selectbox("", tickers, index=default_idx,
                 label_visibility="collapsed", key="bbg_ticker")
with c2:
    st.radio("", TIMEFRAMES, index=TIMEFRAMES.index(tf), horizontal=True,
             label_visibility="collapsed", key="bbg_tf")
