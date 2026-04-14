"""
Strategy 3: Active Accumulation, Conviction Rank — Drill-Down

Shows both Base (.0) and Enhanced (.1) variants with current holdings,
performance charts, sell/freeze alerts, trade history.
"""

import streamlit as st
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import pandas as pd
import plotly.graph_objects as go

from utils.strategy_operations import (
    backtest_data_exists,
    get_strategy_info,
    get_stream_positions,
    get_stream_performance,
    get_stream_transactions,
    get_sell_freeze_alerts,
    get_volume_spike_flags,
)

STRATEGY_ID = "3"

info = get_strategy_info(STRATEGY_ID)
st.title(f"Strategy {STRATEGY_ID}: {info['name']}")
st.caption(info["description"])

if not backtest_data_exists():
    st.warning("No backtest data. Run the simulation from the Strategy Dashboard page.")
    st.stop()

st.markdown("---")

tab_base, tab_enhanced = st.tabs(["Base (.0)", "Enhanced (.1)"])

for variant_tab, stream_id, variant_label in [
    (tab_base, f"{STRATEGY_ID}.0", "Base"),
    (tab_enhanced, f"{STRATEGY_ID}.1", "Enhanced"),
]:
    with variant_tab:
        positions = get_stream_positions(stream_id)
        perf = get_stream_performance(stream_id)

        if not perf.empty:
            latest = perf.iloc[-1]
            port_val = latest["portfolio_value"]
            invested = latest["cumulative_invested"]
            total_ret = latest["portfolio_return"] * 100
            xbi_ret = latest["xbi_return"] * 100
            active_ct = int(latest["active_positions"])
            frozen_ct = int(latest["frozen_positions"])
        else:
            port_val = invested = total_ret = xbi_ret = 0
            active_ct = frozen_ct = 0

        c1, c2, c3, c4, c5, c6 = st.columns(6)
        with c1:
            st.metric("Portfolio Value", f"${port_val:,.0f}")
        with c2:
            st.metric("Total Return", f"{total_ret:+.1f}%")
        with c3:
            st.metric("vs XBI", f"{total_ret - xbi_ret:+.1f}%")
        with c4:
            st.metric("Invested", f"${invested:,.0f}")
        with c5:
            st.metric("Active", f"{active_ct}")
        with c6:
            st.metric("Frozen", f"{frozen_ct}")

        st.markdown("---")

        sub1, sub2, sub3, sub4 = st.tabs([
            "Holdings", "Trade Recommendations", "Performance", "Trade History"
        ])

        with sub1:
            if positions.empty:
                st.info("No active positions.")
            else:
                with st.container(border=True):
                    st.subheader("Current Holdings")
                    display = positions[[
                        "ticker", "company_name", "entry_date", "entry_price",
                        "current_price", "total_return", "status", "days_held",
                    ]].copy()
                    display.columns = [
                        "Ticker", "Company", "Entry Date", "Entry Price",
                        "Current Price", "Total Return", "Status", "Days Held",
                    ]
                    display["Entry Price"] = display["Entry Price"].apply(lambda x: f"${x:,.2f}")
                    display["Current Price"] = display["Current Price"].apply(lambda x: f"${x:,.2f}")
                    display["Total Return"] = display["Total Return"].apply(lambda x: f"{x * 100:+.1f}%")
                    st.dataframe(display, use_container_width=True, hide_index=True)

                alerts = get_sell_freeze_alerts(stream_id)
                if not alerts.empty:
                    with st.container(border=True):
                        st.subheader("Sell/Freeze Alerts")
                        alert_display = alerts[[
                            "ticker", "status", "total_return",
                            "distance_to_hard_stop", "distance_to_freeze",
                            "days_held", "alert_level",
                        ]].copy()
                        alert_display.columns = [
                            "Ticker", "Status", "Return",
                            "To Hard Stop", "To Freeze",
                            "Days Held", "Alert",
                        ]
                        alert_display["Return"] = alert_display["Return"].apply(lambda x: f"{x * 100:+.1f}%")
                        alert_display["To Hard Stop"] = alert_display["To Hard Stop"].apply(lambda x: f"{x * 100:+.1f}pp")
                        alert_display["To Freeze"] = alert_display["To Freeze"].apply(lambda x: f"{x * 100:+.1f}pp")
                        st.dataframe(alert_display, use_container_width=True, hide_index=True)

                if stream_id.endswith(".1"):
                    vol_flags = get_volume_spike_flags(stream_id)
                    if not vol_flags.empty:
                        with st.container(border=True):
                            st.subheader("Volume Spike Flags")
                            st.dataframe(vol_flags, use_container_width=True, hide_index=True)

        with sub2:
            st.info("Trade recommendations will project the next trade day based on current data.")
            recent_txns = get_stream_transactions(stream_id)
            if not recent_txns.empty:
                latest_date = recent_txns["date"].max()
                latest_trades = recent_txns[recent_txns["date"] == latest_date]
                st.subheader(f"Latest Trades ({latest_date})")
                trade_display = latest_trades[[
                    "ticker", "action", "shares", "price", "dollar_amount", "reason",
                ]].copy()
                trade_display.columns = ["Ticker", "Action", "Shares", "Price", "Amount", "Reason"]
                trade_display["Shares"] = trade_display["Shares"].apply(lambda x: f"{x:,.2f}")
                trade_display["Price"] = trade_display["Price"].apply(lambda x: f"${x:,.2f}")
                trade_display["Amount"] = trade_display["Amount"].apply(lambda x: f"${x:,.2f}")
                st.dataframe(trade_display, use_container_width=True, hide_index=True)

        with sub3:
            if perf.empty:
                st.info("No performance data.")
            else:
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=perf["date"], y=perf["portfolio_return"] * 100,
                    name=f"{stream_id} Portfolio", line=dict(color="#1f77b4", width=2),
                ))
                fig.add_trace(go.Scatter(
                    x=perf["date"], y=perf["xbi_return"] * 100,
                    name="XBI Benchmark", line=dict(color="#f5a623", width=2, dash="dot"),
                ))
                fig.update_layout(title="Cumulative Return", hovermode="x unified",
                                  yaxis_title="Return (%)", yaxis_ticksuffix="%", height=400)
                st.plotly_chart(fig, use_container_width=True)

                values = perf["portfolio_value"].values
                cummax = pd.Series(values).cummax()
                drawdown = ((pd.Series(values) - cummax) / cummax * 100).fillna(0)
                fig_dd = go.Figure()
                fig_dd.add_trace(go.Scatter(
                    x=perf["date"].values, y=drawdown.values, name="Drawdown",
                    line=dict(color="#d62728", width=1.5),
                    fill="tozeroy", fillcolor="rgba(214,39,40,0.1)",
                ))
                fig_dd.update_layout(title="Drawdown", yaxis_title="Drawdown (%)",
                                     yaxis_ticksuffix="%", height=300)
                st.plotly_chart(fig_dd, use_container_width=True)

        with sub4:
            txns = get_stream_transactions(stream_id)
            if txns.empty:
                st.info("No trade history.")
            else:
                st.subheader(f"Transaction Log ({len(txns)} trades)")
                hist_display = txns[["date", "ticker", "action", "shares", "price", "dollar_amount", "reason"]].copy()
                hist_display.columns = ["Date", "Ticker", "Action", "Shares", "Price", "Amount", "Reason"]
                hist_display["Shares"] = hist_display["Shares"].apply(lambda x: f"{x:,.2f}" if x > 0 else "—")
                hist_display["Price"] = hist_display["Price"].apply(lambda x: f"${x:,.2f}" if x > 0 else "—")
                hist_display["Amount"] = hist_display["Amount"].apply(lambda x: f"${x:,.2f}" if x > 0 else "—")
                st.dataframe(hist_display, use_container_width=True, hide_index=True, height=500)

                csv_bytes = txns.to_csv(index=False).encode("utf-8")
                st.download_button("Export Trade History to CSV", data=csv_bytes,
                    file_name=f"strategy_{STRATEGY_ID}_{variant_label.lower()}_trades.csv",
                    mime="text/csv", key=f"export_{stream_id}")
