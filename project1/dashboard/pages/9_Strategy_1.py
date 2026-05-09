"""
Strategy 1 — Baker Bros Top-10 Equal-Weight
Displays simulation results from strategy_1_*.csv files.
Run the simulation from the sidebar before viewing results.
"""

import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from utils.strategy_engine import (
    STRATEGY_1_PERFORMANCE_CSV,
    STRATEGY_1_POSITIONS_CSV,
    STRATEGY_1_TRANSACTIONS_CSV,
    StrategyConfig,
    run_simulation,
)
from utils.csv_data import get_all_filings, load_holdings_by_date

st.set_page_config(page_title="Strategy 1", layout="wide")


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

def _mtime(path: Path) -> float:
    return path.stat().st_mtime if path.exists() else 0.0


def _csv_mtime() -> float:
    return max(_mtime(p) for p in [
        STRATEGY_1_POSITIONS_CSV,
        STRATEGY_1_TRANSACTIONS_CSV,
        STRATEGY_1_PERFORMANCE_CSV,
    ])


@st.cache_data
def load_positions(mtime: float) -> pd.DataFrame:
    return pd.read_csv(STRATEGY_1_POSITIONS_CSV)


@st.cache_data
def load_transactions(mtime: float) -> pd.DataFrame:
    return pd.read_csv(STRATEGY_1_TRANSACTIONS_CSV)


@st.cache_data
def load_performance(mtime: float) -> pd.DataFrame:
    return pd.read_csv(STRATEGY_1_PERFORMANCE_CSV)


@st.cache_data
def load_latest_top10(portfolio_id: str) -> pd.DataFrame:
    """Load the most recent filing's top-10 holdings."""
    filings = get_all_filings(portfolio_id).sort_values("filing_date")
    if filings.empty:
        return pd.DataFrame()
    latest_filing_date = filings.iloc[-1]["filing_date"]
    df = load_holdings_by_date(portfolio_id, latest_filing_date)
    if df.empty:
        return pd.DataFrame()
    df = df[df["ticker"].notna() & (df["ticker"] != "") & (df["value"] > 0)].copy()
    df["weight_pct"] = df["value"] / df["value"].sum() * 100
    return df.nlargest(10, "weight_pct")[["ticker", "company_name", "weight_pct"]].reset_index(drop=True)


# ---------------------------------------------------------------------------
# Sidebar — configuration + run button
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("Strategy 1 Config")
    st.caption("Top 10 Baker Bros holdings, equal weight monthly allocation.")

    monthly = st.number_input("Monthly Contribution ($)", min_value=100.0, max_value=100_000.0,
                              value=1_000.0, step=100.0)
    max_pos = st.slider("Max Positions", min_value=3, max_value=20, value=10)
    min_hold = st.slider("Min Hold Period (months)", min_value=1, max_value=12, value=3)
    trade_day = st.slider("Trade Day (Nth of month)", min_value=1, max_value=5, value=1)

    st.divider()
    st.subheader("Sell Rules")
    hard_stop = st.slider("Hard Stop (%)", min_value=-80, max_value=-5, value=-40, step=5) / 100
    rel_bleed = st.slider("Relative Bleed — Abs (%)", min_value=-60, max_value=-5, value=-25, step=5) / 100
    rel_bleed_xbi = st.slider("Relative Bleed — vs XBI (%)", min_value=-40, max_value=-5, value=-15, step=5) / 100

    st.divider()
    st.subheader("Freeze Rules")
    freeze_thr = st.slider("Freeze Threshold (%)", min_value=-40, max_value=-1, value=-10, step=1) / 100

    st.divider()
    if st.button("Run Simulation", type="primary", use_container_width=True):
        config = StrategyConfig(
            monthly_contribution=monthly,
            max_positions=max_pos,
            min_hold_months=min_hold,
            trade_day=trade_day,
            hard_stop_return=hard_stop,
            relative_bleed_return=rel_bleed,
            relative_bleed_xbi_underperformance=rel_bleed_xbi,
            freeze_return_threshold=freeze_thr,
        )
        with st.spinner("Running simulation (takes ~10 seconds)..."):
            run_simulation(config)
        st.success("Done! Results updated.")
        st.rerun()


# ---------------------------------------------------------------------------
# Page title
# ---------------------------------------------------------------------------

st.title("Strategy 1: Baker Bros Top-10 Equal-Weight")
st.caption(
    "Clones Baker Brothers' top 10 holdings by 13F portfolio weight. "
    "Allocates equal capital monthly to active (non-frozen) positions. "
    "Benchmarked against XBI (SPDR S&P Biotech ETF)."
)

# ---------------------------------------------------------------------------
# Data guard
# ---------------------------------------------------------------------------

csvs_exist = all(p.exists() for p in [
    STRATEGY_1_POSITIONS_CSV,
    STRATEGY_1_TRANSACTIONS_CSV,
    STRATEGY_1_PERFORMANCE_CSV,
])

if not csvs_exist:
    st.warning(
        "No simulation results found. Configure parameters in the sidebar "
        "and click **Run Simulation** to generate results."
    )
    st.stop()

mtime = _csv_mtime()
positions_df = load_positions(mtime)
transactions_df = load_transactions(mtime)
performance_df = load_performance(mtime)

# ---------------------------------------------------------------------------
# Summary metrics row
# ---------------------------------------------------------------------------

last = performance_df.iloc[-1]
port_val = last["portfolio_value"]
invested = last["cumulative_invested"]
port_ret = last["portfolio_return"] * 100
xbi_ret = last["xbi_return"] * 100
vs_xbi = port_ret - xbi_ret
active_ct = int(last["active_positions"])
frozen_ct = int(last["frozen_positions"])

c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric("Portfolio Value", f"${port_val:,.0f}")
c2.metric("Total Return", f"{port_ret:+.1f}%")
c3.metric("vs XBI", f"{vs_xbi:+.1f}pp",
          delta=f"{vs_xbi:+.1f}pp", delta_color="normal")
c4.metric("Invested", f"${invested:,.0f}")
c5.metric("Active Positions", active_ct)
c6.metric("Frozen Positions", frozen_ct)

st.markdown("---")

# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------

tab_holdings, tab_recs, tab_perf, tab_hist = st.tabs([
    "Holdings", "Trade Recommendations", "Performance", "Trade History"
])


# ── Holdings ────────────────────────────────────────────────────────────────

with tab_holdings:
    current = positions_df[positions_df["status"].isin(["active", "frozen"])].copy()

    if current.empty:
        st.info("No active or frozen positions.")
    else:
        with st.container(border=True):
            st.subheader("Current Holdings")
            display = current[[
                "ticker", "company_name", "status", "entry_date",
                "avg_cost", "current_price", "total_return",
                "xbi_return_since_entry", "days_held",
            ]].copy()
            display.columns = [
                "Ticker", "Company", "Status", "Entry Date",
                "Avg Cost", "Current Price", "Return",
                "XBI Return (same period)", "Days Held",
            ]
            display["Avg Cost"] = display["Avg Cost"].apply(lambda x: f"${x:,.2f}")
            display["Current Price"] = display["Current Price"].apply(lambda x: f"${x:,.2f}")
            display["Return"] = display["Return"].apply(lambda x: f"{x*100:+.1f}%")
            display["XBI Return (same period)"] = display["XBI Return (same period)"].apply(
                lambda x: f"{x*100:+.1f}%"
            )
            st.dataframe(display, use_container_width=True, hide_index=True)

        # Alerts: positions approaching thresholds
        alert_threshold = 0.10  # within 10pp of hard stop or freeze
        alerts = current[
            (current["distance_to_hard_stop"] < alert_threshold) |
            (current["distance_to_freeze"] < 0.05)
        ].copy()

        if not alerts.empty:
            with st.container(border=True):
                st.subheader("Threshold Alerts")
                st.caption(f"Positions within {alert_threshold*100:.0f}pp of hard stop or 5pp of freeze threshold.")
                alert_display = alerts[[
                    "ticker", "status", "total_return",
                    "distance_to_hard_stop", "distance_to_freeze", "days_held", "sell_eligible",
                ]].copy()
                alert_display.columns = [
                    "Ticker", "Status", "Return",
                    "Distance to Hard Stop", "Distance to Freeze", "Days Held", "Sell Eligible",
                ]
                alert_display["Return"] = alert_display["Return"].apply(lambda x: f"{x*100:+.1f}%")
                alert_display["Distance to Hard Stop"] = alert_display["Distance to Hard Stop"].apply(
                    lambda x: f"{x*100:+.1f}pp"
                )
                alert_display["Distance to Freeze"] = alert_display["Distance to Freeze"].apply(
                    lambda x: f"{x*100:+.1f}pp"
                )
                st.dataframe(alert_display, use_container_width=True, hide_index=True)


# ── Trade Recommendations ───────────────────────────────────────────────────

with tab_recs:
    st.subheader("Next Trade Day Projection")
    st.caption(
        "Based on the current filing and portfolio state. Actual results depend on "
        "prices on the next trade day."
    )

    top10 = load_latest_top10("baker-bros")
    active_positions = positions_df[positions_df["status"] == "active"]
    n_active = len(active_positions)

    # Capital allocation estimate
    if n_active > 0:
        per_name = monthly / n_active
        col1, col2 = st.columns(2)
        with col1:
            with st.container(border=True):
                st.subheader("Capital Allocation")
                st.metric("Monthly Contribution", f"${monthly:,.0f}")
                st.metric("Active Positions", n_active)
                st.metric("Per Position", f"${per_name:,.2f}")

                alloc_data = active_positions[["ticker", "company_name"]].copy()
                alloc_data["Allocation"] = f"${per_name:,.2f}"
                alloc_data.columns = ["Ticker", "Company", "Allocation"]
                st.dataframe(alloc_data, use_container_width=True, hide_index=True)

        with col2:
            with st.container(border=True):
                st.subheader("Current Top-10 Filing")
                if not top10.empty:
                    top10_display = top10.copy()
                    top10_display["weight_pct"] = top10_display["weight_pct"].apply(lambda x: f"{x:.1f}%")
                    top10_display.columns = ["Ticker", "Company", "13F Weight"]
                    # Flag changes vs current active positions
                    active_tickers = set(active_positions["ticker"].tolist())
                    top10_display["In Portfolio"] = top10_display["Ticker"].apply(
                        lambda t: "Yes" if t in active_tickers else "New"
                    )
                    st.dataframe(top10_display, use_container_width=True, hide_index=True)
    else:
        st.info("No active positions. Run the simulation to generate portfolio data.")

    # Risk alerts
    current_holdings = positions_df[positions_df["status"].isin(["active", "frozen"])]
    at_risk = current_holdings[current_holdings["distance_to_hard_stop"] < 0.15].copy()
    if not at_risk.empty:
        st.divider()
        st.subheader("Risk Alerts (within 15pp of hard stop)")
        risk_display = at_risk[["ticker", "status", "total_return", "distance_to_hard_stop", "sell_eligible"]].copy()
        risk_display["total_return"] = risk_display["total_return"].apply(lambda x: f"{x*100:+.1f}%")
        risk_display["distance_to_hard_stop"] = risk_display["distance_to_hard_stop"].apply(lambda x: f"{x*100:+.1f}pp")
        risk_display.columns = ["Ticker", "Status", "Return", "Distance to Stop", "Sell Eligible"]
        st.dataframe(risk_display, use_container_width=True, hide_index=True)


# ── Performance ─────────────────────────────────────────────────────────────

with tab_perf:
    if performance_df.empty:
        st.info("No performance data.")
    else:
        perf = performance_df[performance_df["cumulative_invested"] > 0].copy()

        # Chart 1: Cumulative return
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=perf["date"],
            y=(perf["portfolio_return"] * 100).round(2),
            name="Strategy 1",
            line=dict(color="#4caf50", width=2),
        ))
        fig.add_trace(go.Scatter(
            x=perf["date"],
            y=(perf["xbi_return"] * 100).round(2),
            name="XBI (equal investment schedule)",
            line=dict(color="#f5a623", width=2, dash="dot"),
        ))
        fig.add_hline(y=0, line_color="rgba(255,255,255,0.2)", line_width=1)
        fig.update_layout(
            title="Cumulative Return — Strategy 1 vs XBI",
            hovermode="x unified",
            yaxis_title="Return (%)",
            yaxis_ticksuffix="%",
            height=400,
            legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01),
        )
        st.plotly_chart(fig, use_container_width=True)

        # Chart 2: Drawdown
        port_dd = (1 + perf["portfolio_return"]) / (1 + perf["portfolio_return"]).cummax() - 1
        xbi_dd = (1 + perf["xbi_return"]) / (1 + perf["xbi_return"]).cummax() - 1

        fig_dd = go.Figure()
        fig_dd.add_trace(go.Scatter(
            x=perf["date"],
            y=(port_dd * 100).round(2),
            name="Strategy 1 Drawdown",
            line=dict(color="#e53935", width=1.5),
            fill="tozeroy",
            fillcolor="rgba(229,57,53,0.15)",
        ))
        fig_dd.add_trace(go.Scatter(
            x=perf["date"],
            y=(xbi_dd * 100).round(2),
            name="XBI Drawdown",
            line=dict(color="#f5a623", width=1, dash="dot"),
            fill="tozeroy",
            fillcolor="rgba(245,166,35,0.08)",
        ))
        fig_dd.update_layout(
            title="Drawdown",
            hovermode="x unified",
            yaxis_title="Drawdown (%)",
            yaxis_ticksuffix="%",
            height=280,
            legend=dict(yanchor="bottom", y=0.01, xanchor="left", x=0.01),
        )
        st.plotly_chart(fig_dd, use_container_width=True)

        # Summary stats
        with st.expander("Performance Statistics"):
            non_zero = perf[perf["portfolio_return"] != 0]
            if len(non_zero) > 1:
                daily_rets = non_zero["portfolio_return"].diff().dropna()
                sharpe = (daily_rets.mean() / daily_rets.std() * (252 ** 0.5)) if daily_rets.std() > 0 else 0

                xbi_daily = non_zero["xbi_return"].diff().dropna()
                xbi_sharpe = (xbi_daily.mean() / xbi_daily.std() * (252 ** 0.5)) if xbi_daily.std() > 0 else 0

                col1, col2, col3, col4 = st.columns(4)
                col1.metric("Strategy Sharpe", f"{sharpe:.2f}")
                col2.metric("XBI Sharpe", f"{xbi_sharpe:.2f}")
                col3.metric("Max Drawdown (Strategy)", f"{port_dd.min()*100:.1f}%")
                col4.metric("Max Drawdown (XBI)", f"{xbi_dd.min()*100:.1f}%")


# ── Trade History ────────────────────────────────────────────────────────────

with tab_hist:
    if transactions_df.empty:
        st.info("No transaction history.")
    else:
        # Filter controls
        action_filter = st.multiselect(
            "Filter by action",
            options=sorted(transactions_df["action"].unique()),
            default=["buy", "sell", "freeze", "unfreeze"],
        )
        filtered = transactions_df[transactions_df["action"].isin(action_filter)].copy()
        filtered = filtered.sort_values("date", ascending=False)

        st.subheader(f"Transaction Log ({len(filtered):,} records)")

        display = filtered[["date", "ticker", "company_name", "action", "shares", "price", "dollar_amount", "reason"]].copy()
        display.columns = ["Date", "Ticker", "Company", "Action", "Shares", "Price", "Amount", "Reason"]
        display["Shares"] = display["Shares"].apply(lambda x: f"{x:,.4f}" if pd.notna(x) and x > 0 else "—")
        display["Price"] = display["Price"].apply(lambda x: f"${x:,.2f}" if pd.notna(x) and x > 0 else "—")
        display["Amount"] = display["Amount"].apply(lambda x: f"${x:,.2f}" if pd.notna(x) and x > 0 else "—")
        st.dataframe(display, use_container_width=True, hide_index=True, height=500)

        csv_bytes = transactions_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            "Export Trade History to CSV",
            data=csv_bytes,
            file_name="strategy_1_trade_history.csv",
            mime="text/csv",
        )
