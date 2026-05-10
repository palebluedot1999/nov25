# dashboard/pages/2_Trades.py
import sys
import streamlit as st
import pandas as pd
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from utils.strategy_registry import discover_strategies
from utils.brokerage import (
    load_brokerage_holdings, save_brokerage_holdings,
    load_staged_trades, save_staged_trades, clear_staged_trades,
    confirm_execution, load_trade_log,
)
from utils.drift import calculate_drift, generate_trade_recommendations
from utils.csv_data import load_portfolios, load_prices, get_all_filings

st.set_page_config(page_title="Trades", layout="wide")
st.title("Trades")

portfolios = load_portfolios(portfolio_type="fund")
if portfolios.empty:
    st.warning("No fund portfolios configured. Add one in Admin.")
    st.stop()
portfolio_id = portfolios.iloc[0]["id"]

strategies = discover_strategies()
if not strategies:
    st.warning("No strategies found in `strategies/`. Create a strategy file first.")
    st.stop()

# ── Stage 1: Configure ─────────────────────────────────────────────────────────
st.subheader("Configure")
strategy_options = {s["name"]: s for s in strategies}
selected_name = st.selectbox("Strategy", list(strategy_options.keys()), key="tr_strategy")
strategy = strategy_options[selected_name]

# Load brokerage holdings and prices
brokerage = load_brokerage_holdings()
price_rows = []
all_tickers_needed = list(brokerage["ticker"].tolist()) if not brokerage.empty else []
for ticker in all_tickers_needed:
    p = load_prices(ticker)
    if p is not None and not p.empty:
        latest = p.sort_values("date").iloc[-1]
        price_rows.append({"ticker": ticker, "close": float(latest["close"])})
prices_df = pd.DataFrame(price_rows) if price_rows else pd.DataFrame(columns=["ticker", "close"])

target_weights = strategy["generate_targets"](portfolio_id=portfolio_id)

# Add any target tickers missing from prices
for ticker in target_weights:
    if not prices_df.empty and ticker in prices_df["ticker"].values:
        continue
    p = load_prices(ticker)
    if p is not None and not p.empty:
        latest = p.sort_values("date").iloc[-1]
        prices_df = pd.concat(
            [prices_df, pd.DataFrame([{"ticker": ticker, "close": float(latest["close"])}])],
            ignore_index=True,
        )

drift_df = calculate_drift(target_weights, brokerage, prices_df)

if not brokerage.empty and not prices_df.empty:
    merged = brokerage.merge(prices_df, on="ticker", how="left")
    merged["value"] = merged["shares"] * merged["close"].fillna(0)
    default_capital = merged["value"].sum()
else:
    default_capital = 10000.0

capital = st.number_input(
    "Capital to deploy ($)",
    min_value=0.0,
    value=round(default_capital, 2),
    step=100.0,
    format="%.2f",
    key="tr_capital",
    help="Pre-populated from total portfolio value. Edit to deploy more or less capital.",
)

# Strategy parameter sliders
params = {}
if strategy.get("parameters"):
    with st.expander("Strategy parameters"):
        for param_key, param_cfg in strategy["parameters"].items():
            if param_cfg["type"] == "int":
                params[param_key] = st.slider(
                    param_cfg["label"], param_cfg["min"], param_cfg["max"],
                    param_cfg["default"], key=f"tr_{param_key}"
                )
            elif param_cfg["type"] == "float":
                params[param_key] = st.slider(
                    param_cfg["label"], float(param_cfg["min"]), float(param_cfg["max"]),
                    float(param_cfg["default"]), key=f"tr_{param_key}"
                )

# Recompute with current params
if params:
    target_weights = strategy["generate_targets"](portfolio_id=portfolio_id, **params)
    drift_df = calculate_drift(target_weights, brokerage, prices_df)

# ── Stage 2: Prospective Trades ────────────────────────────────────────────────
st.divider()
st.subheader("Prospective Trades")

recs = generate_trade_recommendations(drift_df, total_portfolio_value=capital, prices=prices_df)

if recs.empty:
    st.success("No rebalancing needed — all positions within threshold.")
else:
    display_recs = recs[["ticker", "action", "suggested_shares", "delta_value", "price", "drift_bp", "priority"]].copy()
    display_recs.columns = ["Ticker", "Action", "Suggested Shares", "Delta ($)", "Price", "Drift (bp)", "Priority"]
    st.dataframe(display_recs, use_container_width=True, hide_index=True)

    net_capital = recs["delta_value"].sum()
    st.caption(f"Net capital needed: ${net_capital:,.0f}")

    if st.button("→ Move to staging", type="primary"):
        staged = pd.DataFrame({
            "ticker": recs["ticker"],
            "action": recs["action"],
            "suggested_shares": recs["suggested_shares"].abs(),
            "actual_shares": recs["suggested_shares"].abs(),
            "exec_price": recs["price"],
            "notes": "",
        })
        save_staged_trades(staged)
        st.success("Trades staged. Review and confirm below.")
        st.rerun()

# ── Stage 3: Staging Area ──────────────────────────────────────────────────────
staged = load_staged_trades()
if not staged.empty:
    st.divider()
    st.subheader("Staging Area")
    st.caption("Adjust actual shares and execution price before confirming.")

    edited = st.data_editor(
        staged[["ticker", "action", "suggested_shares", "actual_shares", "exec_price", "notes"]],
        column_config={
            "ticker": st.column_config.TextColumn("Ticker", disabled=True),
            "action": st.column_config.TextColumn("Action", disabled=True),
            "suggested_shares": st.column_config.NumberColumn("Suggested", disabled=True),
            "actual_shares": st.column_config.NumberColumn("Actual Shares"),
            "exec_price": st.column_config.NumberColumn("Exec Price ($)", format="$%.2f"),
            "notes": st.column_config.TextColumn("Notes"),
        },
        use_container_width=True,
        hide_index=True,
        key="staging_editor",
    )

    col1, col2 = st.columns([1, 4])
    with col1:
        if st.button("✓ Confirm execution", type="primary"):
            confirm_execution(edited, strategy_name=strategy["name"])
            st.success("Trades confirmed and logged.")
            st.rerun()
    with col2:
        if st.button("✕ Clear staging"):
            clear_staged_trades()
            st.rerun()

# ── My Holdings ────────────────────────────────────────────────────────────────
st.divider()
with st.expander("My Holdings"):
    st.caption("Enter your current brokerage positions. Used to calculate drift on Dashboard and Trades.")
    if brokerage.empty:
        st.info("No holdings entered yet.")

    with st.form("holdings_form"):
        if not brokerage.empty:
            edited_holdings = st.data_editor(
                brokerage[["ticker", "shares"]],
                num_rows="dynamic",
                use_container_width=True,
                key="holdings_editor",
            )
        else:
            edited_holdings = st.data_editor(
                pd.DataFrame({"ticker": [""], "shares": [0.0]}),
                num_rows="dynamic",
                use_container_width=True,
                key="holdings_editor_empty",
            )

        uploaded = st.file_uploader("Import CSV from brokerage (ticker, shares columns)", type="csv")
        save_btn = st.form_submit_button("Save holdings")

        if save_btn:
            if uploaded is not None:
                imported = pd.read_csv(uploaded)
                if "ticker" in imported.columns and "shares" in imported.columns:
                    save_brokerage_holdings(imported[["ticker", "shares"]])
                    st.success(f"Imported {len(imported)} positions.")
                else:
                    st.error("CSV must have 'ticker' and 'shares' columns.")
            else:
                clean = edited_holdings[edited_holdings["ticker"].str.strip() != ""].copy()
                save_brokerage_holdings(clean)
                st.success("Holdings saved.")
            st.rerun()

# ── Trade History ──────────────────────────────────────────────────────────────
st.divider()
st.subheader("Trade History")
trade_log = load_trade_log()
hist_view = st.radio("View", ["Table", "Chart"], horizontal=True, key="tr_hist_view")

if trade_log.empty:
    st.info("No trade history yet. Confirm your first execution above.")
else:
    strat_log = trade_log[trade_log["strategy"] == strategy["name"]].copy()
    if strat_log.empty:
        st.info(f"No trade history for {strategy['name']} yet.")
    else:
        if hist_view == "Table":
            st.dataframe(strat_log.sort_values("executed_at", ascending=False), use_container_width=True, hide_index=True)
            st.download_button("Export CSV", strat_log.to_csv(index=False), "trade_history.csv", "text/csv")
        else:
            import plotly.express as px
            strat_log["executed_at"] = pd.to_datetime(strat_log["executed_at"])
            daily = strat_log.groupby(strat_log["executed_at"].dt.date)["total_value"].sum().reset_index()
            daily.columns = ["date", "value"]
            fig = px.bar(daily, x="date", y="value", title=f"Trade Volume — {strategy['name']}")
            st.plotly_chart(fig, use_container_width=True)
