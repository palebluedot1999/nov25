"""
Prices - View historical price charts for individual securities.
"""

import streamlit as st
import sys
from pathlib import Path
from datetime import datetime, timedelta

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from utils.csv_data import load_prices, PRICES_DIR
import pandas as pd
import plotly.express as px

st.set_page_config(layout="wide")

# Compact header styling
st.markdown("""
<style>
    /* Smaller page title */
    .prices-title { font-size: 1.3rem; font-weight: 600; margin: 0 0 0.3rem 0; }
    /* Shrink selectbox labels and spacing */
    div[data-testid="stSelectbox"] label { font-size: 0.8rem; }
    div[data-testid="stSelectbox"] { margin-bottom: 0; }
    /* Shrink metric labels and values */
    div[data-testid="stMetric"] label { font-size: 0.75rem; }
    div[data-testid="stMetric"] div[data-testid="stMetricValue"] { font-size: 1rem; }
    div[data-testid="stMetric"] div[data-testid="stMetricDelta"] { font-size: 0.75rem; }
    /* Reduce vertical gaps */
    div[data-testid="stVerticalBlock"] > div:has(> div[data-testid="stMetric"]) { gap: 0; }
</style>
""", unsafe_allow_html=True)

st.markdown('<p class="prices-title">Prices</p>', unsafe_allow_html=True)

# --- Constants ---

TIMEFRAME_OPTIONS = [
    "Week to Date",
    "Month to Date",
    "Year to Date",
    "1 Week",
    "1 Month",
    "1 Year",
    "2 Year",
    "3 Year",
    "4 Year",
    "5 Year",
    "All Time",
]


# --- Helper functions ---

def calculate_start_date(timeframe: str, today: datetime) -> datetime:
    """Calculate the start date for a given timeframe relative to today."""
    if timeframe == "Week to Date":
        return today - timedelta(days=today.weekday())
    elif timeframe == "Month to Date":
        return today.replace(day=1)
    elif timeframe == "Year to Date":
        return today.replace(month=1, day=1)
    elif timeframe == "1 Week":
        return today - timedelta(weeks=1)
    elif timeframe == "1 Month":
        return today - timedelta(days=30)
    elif timeframe == "1 Year":
        return today - timedelta(days=365)
    elif timeframe == "2 Year":
        return today - timedelta(days=365 * 2)
    elif timeframe == "3 Year":
        return today - timedelta(days=365 * 3)
    elif timeframe == "4 Year":
        return today - timedelta(days=365 * 4)
    elif timeframe == "5 Year":
        return today - timedelta(days=365 * 5)
    elif timeframe == "All Time":
        return None
    return today


def get_xaxis_config(num_days: int) -> dict:
    """Return Plotly xaxis configuration based on data duration."""
    if num_days <= 7:
        return dict(dtick="D1", tickformat="%b %d")
    elif num_days <= 31:
        return dict(dtick="D7", tickformat="%b %d")
    elif num_days <= 365:
        return dict(dtick="M1", tickformat="%b %Y")
    elif num_days <= 730:
        return dict(dtick="M2", tickformat="%b %Y")
    else:
        return dict(dtick="M3", tickformat="%b %Y")


# --- Data loading ---

@st.cache_data
def get_available_tickers():
    """Get sorted list of tickers that have price data files."""
    if not PRICES_DIR.exists():
        return []
    return sorted([f.stem for f in PRICES_DIR.glob("*.csv")])


def load_ticker_prices(ticker: str):
    """Load all price data for a ticker (no cache - ensures fresh data on each page load)."""
    return load_prices(ticker)


# --- Page content ---

tickers = get_available_tickers()
if not tickers:
    st.warning("No price data found. Please fetch prices from the Data Management page.")
    st.stop()

# Compact dropdowns side-by-side
col1, col2, col3 = st.columns([1, 1, 2])
with col1:
    default_idx = tickers.index("XBI") if "XBI" in tickers else 0
    selected_ticker = st.selectbox("Ticker", tickers, index=default_idx)
with col2:
    selected_timeframe = st.selectbox("Timeframe", TIMEFRAME_OPTIONS, index=2)

# Load and filter data
df = load_ticker_prices(selected_ticker)

if df.empty:
    st.warning(f"No price data available for {selected_ticker}.")
    st.stop()

today = datetime.now()
start_date = calculate_start_date(selected_timeframe, today)

if start_date is not None:
    df = df[df['date'] >= pd.Timestamp(start_date)]

if df.empty:
    st.warning(f"No price data for {selected_ticker} in the selected timeframe.")
    st.stop()

# Compact metrics row
latest_price = df['close'].iloc[-1]
first_price = df['close'].iloc[0]
price_change = latest_price - first_price
pct_change = (price_change / first_price) * 100 if first_price != 0 else 0
price_high = df['close'].max()
price_low = df['close'].min()

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Latest Price", f"${latest_price:,.2f}")
with col2:
    st.metric("Change", f"${price_change:+,.2f}", delta=f"{pct_change:+.2f}%")
with col3:
    st.metric("High", f"${price_high:,.2f}")
with col4:
    st.metric("Low", f"${price_low:,.2f}")

# Chart - takes up most of the page
fig = px.line(
    df,
    x='date',
    y='close',
    title=f"{selected_ticker} - {selected_timeframe}",
    labels={'date': 'Date', 'close': 'Price ($)'}
)

# Smart Y-axis: tight fit with 5% padding
price_range = price_high - price_low
padding = price_range * 0.05 if price_range > 0 else price_high * 0.05

fig.update_yaxes(
    range=[price_low - padding, price_high + padding],
    tickformat='$,.2f',
)

# Smart X-axis: adaptive tick spacing
num_days = (df['date'].max() - df['date'].min()).days
xaxis_config = get_xaxis_config(num_days)
fig.update_xaxes(**xaxis_config)

fig.update_layout(
    hovermode='x unified',
    xaxis_title='Date',
    yaxis_title='Price ($)',
    showlegend=False,
    height=700,
    margin=dict(t=40, b=40),
)

fig.update_traces(line_color='#1f77b4', line_width=2)

st.plotly_chart(fig, use_container_width=True)
