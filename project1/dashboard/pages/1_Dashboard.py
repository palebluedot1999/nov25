# dashboard/pages/1_Dashboard.py
import sys
import streamlit as st
import pandas as pd
import plotly.express as px
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from utils.strategy_registry import discover_strategies
from utils.brokerage import load_brokerage_holdings, load_trade_log
from utils.drift import calculate_drift
from utils.csv_data import load_portfolios, load_prices, get_all_filings, load_processed_holdings
from utils.holdings_operations import get_forward_filled_prices, calculate_portfolio_values

st.set_page_config(page_title="Dashboard", layout="wide")
st.title("Dashboard")

# ── Strategy selector ──────────────────────────────────────────────────────────
strategies = discover_strategies()

if not strategies:
    st.warning("No strategies found. Create a strategy file in `strategies/` and register it.")
    st.stop()

strategy_options = {s["name"]: s for s in strategies}
default_idx = next(
    (i for i, s in enumerate(strategies) if s["status"] == "Live"), 0
)
selected_name = st.selectbox("Strategy", list(strategy_options.keys()), index=default_idx, key="dash_strategy")
strategy = strategy_options[selected_name]

# ── Header strip ───────────────────────────────────────────────────────────────
portfolios = load_portfolios(portfolio_type="fund")
if portfolios.empty:
    st.warning("No fund portfolios. Add one in Admin.")
    st.stop()

portfolio_id = portfolios.iloc[0]["id"]

trade_log = load_trade_log()
last_trade_date = "Never"
drift_age_str = "—"
if not trade_log.empty and strategy["name"] in trade_log["strategy"].values:
    strat_log = trade_log[trade_log["strategy"] == strategy["name"]]
    last_ts = pd.to_datetime(strat_log["executed_at"]).max()
    last_trade_date = last_ts.strftime("%Y-%m-%d")
    drift_age = (datetime.now() - last_ts).days
    drift_age_str = f"{drift_age} day{'s' if drift_age != 1 else ''}"

filings = get_all_filings(portfolio_id)
targets_updated = filings.iloc[0]["filing_date"] if not filings.empty else "—"

col1, col2, col3 = st.columns(3)
col1.metric("Targets last updated", str(targets_updated))
col2.metric("My last trade", last_trade_date)
col3.metric("Drift age", drift_age_str)

st.divider()

# ── Compute drift ──────────────────────────────────────────────────────────────
brokerage = load_brokerage_holdings()
target_weights = strategy["generate_targets"](portfolio_id=portfolio_id)

prices_df = pd.DataFrame(columns=["ticker", "close"])
brokerage_tickers = set(brokerage["ticker"].tolist()) if not brokerage.empty else set()
all_tickers = list(brokerage_tickers | set(target_weights.keys()))
if all_tickers:
    price_rows = []
    for ticker in all_tickers:
        p = load_prices(ticker)
        if p is not None and not p.empty:
            latest = p.sort_values("date").iloc[-1]
            price_rows.append({"ticker": ticker, "close": float(latest["close"])})
    if price_rows:
        prices_df = pd.DataFrame(price_rows)

drift_df = calculate_drift(target_weights, brokerage, prices_df)

# ── Two-column layout ──────────────────────────────────────────────────────────
col_left, col_right = st.columns([1, 1])

with col_left:
    st.subheader("Positions & Drift")

    total_value = 0.0
    if not brokerage.empty and not prices_df.empty:
        merged = brokerage.merge(prices_df, on="ticker", how="left")
        merged["value"] = merged["shares"] * merged["close"].fillna(0)
        total_value = merged["value"].sum()

    col_a, col_b = st.columns(2)
    col_a.metric("Total Value", f"${total_value/1e6:.1f}M" if total_value >= 1e6 else f"${total_value:,.0f}")
    col_b.metric("Positions", len(brokerage))

    needs_rebal = drift_df[drift_df["drift_bp"].abs() >= 100] if not drift_df.empty else pd.DataFrame()
    if not needs_rebal.empty:
        st.warning(f"⚠ {len(needs_rebal)} position(s) need rebalancing → [Go to Trades](/2_Trades)")

    if not drift_df.empty:
        display = drift_df[["ticker", "target_weight", "actual_weight", "drift_bp", "action"]].copy()
        display.columns = ["Ticker", "Target (%)", "Actual (%)", "Drift (bp)", "Action"]
        st.dataframe(display, use_container_width=True, hide_index=True)
    else:
        st.info("No positions yet. Enter your brokerage holdings in the Trades page.")

with col_right:
    st.subheader("Performance")
    st.multiselect("vs.", ["XBI", "SPY", "Baker Bros"], default=["XBI", "SPY"], key="dash_bench")
    st.radio("View", ["Chart", "Table"], horizontal=True, key="dash_perf_view")
    st.caption("Performance chart will populate once backtest results are available.")

st.divider()

# ── Portfolio value over time ──────────────────────────────────────────────────
st.subheader("Portfolio Value Over Time")
port_view = st.radio("View", ["Chart", "Table"], horizontal=True, key="dash_port_view")

try:
    holdings_hist = load_processed_holdings(portfolio_id, start_date="2025-01-01")
    if holdings_hist is not None and not holdings_hist.empty:
        start = pd.Timestamp("2025-01-01")
        end = pd.Timestamp.today()
        ff_prices = get_forward_filled_prices(str(start.date()), str(end.date()))
        port_values = calculate_portfolio_values(holdings_hist, ff_prices)

        if port_view == "Chart":
            daily_total = port_values.groupby("eod_date")["position_value"].sum().reset_index()
            daily_total.columns = ["date", "value"]
            fig = px.line(daily_total, x="date", y="value", title="Total Portfolio Value",
                          labels={"value": "Value ($)", "date": "Date"})
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.dataframe(port_values, use_container_width=True)
    else:
        st.info("No processed holdings. Run 'Consolidate holdings' in Admin.")
except Exception as e:
    st.info(f"Portfolio history unavailable: {e}")
