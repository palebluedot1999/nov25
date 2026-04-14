"""
Strategy Dashboard

Summary of all 8 strategy streams (4 strategies × 2 variants).
Shows performance comparison, cumulative return overlay, and filing comparison.
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
    get_all_streams_summary,
    load_performance,
    get_filing_comparison,
    get_strategy_info,
)
from utils.strategy_config import STRATEGY_REGISTRY, STREAM_IDS

st.title("Strategy Dashboard")

# Sidebar: Re-run simulation
with st.sidebar:
    st.markdown("---")
    st.subheader("Backtest Controls")
    if st.button("Re-run Simulation", type="primary"):
        with st.spinner("Running backtest (~30s)..."):
            from utils.strategy_config import StrategyConfig
            from utils.strategy_engine import run_backtest
            from utils.csv_data import PROCESSED_DATA_DIR

            config = StrategyConfig()
            pos_df, txn_df, perf_df = run_backtest(config)
            pos_df.to_csv(PROCESSED_DATA_DIR / "strategy_positions.csv", index=False)
            txn_df.to_csv(PROCESSED_DATA_DIR / "strategy_transactions.csv", index=False)
            perf_df.to_csv(PROCESSED_DATA_DIR / "strategy_performance.csv", index=False)
        st.success("Backtest complete!")
        st.rerun()

if not backtest_data_exists():
    st.warning("No backtest data found. Click **Re-run Simulation** in the sidebar.")
    st.stop()

# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------

tab_summary, tab_perf, tab_filing = st.tabs(["Summary", "Performance Charts", "Filing Comparison"])

# ── Tab 1: Summary Table ────────────────────────────────────────────────────
with tab_summary:
    summary = get_all_streams_summary()

    if summary.empty:
        st.info("No summary data available.")
    else:
        # Top-level metrics
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            best = summary.loc[summary["total_return"].idxmax()] if "total_return" in summary.columns else None
            if best is not None:
                st.metric("Best Strategy", f"{best['stream_id']}", f"{best['total_return']:+.1f}%")
        with col2:
            avg_ret = summary["total_return"].mean() if "total_return" in summary.columns else 0
            st.metric("Avg Return", f"{avg_ret:+.1f}%")
        with col3:
            total_invested = summary["total_invested"].sum() if "total_invested" in summary.columns else 0
            st.metric("Total Invested", f"${total_invested:,.0f}")
        with col4:
            total_value = summary["portfolio_value"].sum() if "portfolio_value" in summary.columns else 0
            st.metric("Total Value", f"${total_value:,.0f}")

        st.markdown("---")

        # Format summary table
        display_cols = ["stream_id", "strategy_name", "variant", "active", "frozen", "total"]
        if "total_return" in summary.columns:
            display_cols.extend(["total_return"])
        if "return_ytd" in summary.columns:
            display_cols.append("return_ytd")
        if "vs_xbi_ytd" in summary.columns:
            display_cols.append("vs_xbi_ytd")
        if "sharpe" in summary.columns:
            display_cols.append("sharpe")

        # Only include columns that exist
        display_cols = [c for c in display_cols if c in summary.columns]
        display_df = summary[display_cols].copy()

        rename_map = {
            "stream_id": "Stream",
            "strategy_name": "Strategy",
            "variant": "Variant",
            "active": "Active",
            "frozen": "Frozen",
            "total": "Total",
            "total_return": "Total Return (%)",
            "return_ytd": "YTD (%)",
            "vs_xbi_ytd": "vs XBI YTD",
            "sharpe": "Sharpe",
        }
        display_df = display_df.rename(columns=rename_map)

        # Format numbers
        for col in ["Total Return (%)", "YTD (%)", "vs XBI YTD"]:
            if col in display_df.columns:
                display_df[col] = display_df[col].apply(
                    lambda x: f"{x:+.1f}%" if pd.notna(x) else "—"
                )
        if "Sharpe" in display_df.columns:
            display_df["Sharpe"] = display_df["Sharpe"].apply(
                lambda x: f"{x:.2f}" if pd.notna(x) else "—"
            )

        st.dataframe(display_df, use_container_width=True, hide_index=True)

# ── Tab 2: Performance Charts ───────────────────────────────────────────────
with tab_perf:
    perf_df = load_performance()

    if perf_df.empty:
        st.info("No performance data available.")
    else:
        # Stream selector
        selected_streams = st.multiselect(
            "Select Streams",
            STREAM_IDS,
            default=STREAM_IDS,
            key="perf_streams",
        )

        if not selected_streams:
            st.warning("Select at least one stream.")
        else:
            # Cumulative return chart
            st.subheader("Cumulative Return (%)")
            fig = go.Figure()

            colors = [
                "#1f77b4", "#2ca02c",  # 1.0, 1.1
                "#ff7f0e", "#d62728",  # 2.0, 2.1
                "#9467bd", "#8c564b",  # 3.0, 3.1
                "#e377c2", "#7f7f7f",  # 4.0, 4.1
            ]
            stream_colors = dict(zip(STREAM_IDS, colors))

            for sid in selected_streams:
                stream_data = perf_df[perf_df["stream_id"] == sid].copy()
                if stream_data.empty:
                    continue
                stream_data = stream_data.sort_values("date")
                meta = get_strategy_info(sid.split(".")[0])
                variant = "Enhanced" if sid.endswith(".1") else "Base"
                label = f"{sid} {meta['short_name']} ({variant})"

                fig.add_trace(go.Scatter(
                    x=stream_data["date"],
                    y=stream_data["portfolio_return"] * 100,
                    name=label,
                    line=dict(color=stream_colors.get(sid, "#999"), width=1.5,
                              dash="dot" if sid.endswith(".1") else "solid"),
                ))

            # XBI benchmark line (from first selected stream)
            first_stream = perf_df[perf_df["stream_id"] == selected_streams[0]].sort_values("date")
            if not first_stream.empty:
                fig.add_trace(go.Scatter(
                    x=first_stream["date"],
                    y=first_stream["xbi_return"] * 100,
                    name="XBI (Benchmark)",
                    line=dict(color="#f5a623", width=2, dash="dash"),
                ))

            fig.update_layout(
                hovermode="x unified",
                yaxis_title="Return (%)",
                yaxis_ticksuffix="%",
                xaxis_title="Date",
                legend=dict(orientation="h", yanchor="bottom", y=-0.3, xanchor="center", x=0.5),
                height=500,
            )
            st.plotly_chart(fig, use_container_width=True)

            # Drawdown chart
            st.subheader("Drawdown (%)")
            fig_dd = go.Figure()

            for sid in selected_streams:
                stream_data = perf_df[perf_df["stream_id"] == sid].sort_values("date")
                if stream_data.empty:
                    continue

                values = stream_data["portfolio_value"].values
                if len(values) == 0:
                    continue

                # Calculate drawdown
                cummax = pd.Series(values).cummax()
                drawdown = (pd.Series(values) - cummax) / cummax * 100
                drawdown = drawdown.fillna(0)

                meta = get_strategy_info(sid.split(".")[0])
                variant = "Enhanced" if sid.endswith(".1") else "Base"
                label = f"{sid} {meta['short_name']} ({variant})"

                fig_dd.add_trace(go.Scatter(
                    x=stream_data["date"].values,
                    y=drawdown.values,
                    name=label,
                    line=dict(color=stream_colors.get(sid, "#999"), width=1.5,
                              dash="dot" if sid.endswith(".1") else "solid"),
                    fill="tozeroy",
                    fillcolor=f"rgba(255,0,0,0.03)",
                ))

            fig_dd.update_layout(
                hovermode="x unified",
                yaxis_title="Drawdown (%)",
                yaxis_ticksuffix="%",
                xaxis_title="Date",
                legend=dict(orientation="h", yanchor="bottom", y=-0.3, xanchor="center", x=0.5),
                height=400,
            )
            st.plotly_chart(fig_dd, use_container_width=True)

# ── Tab 3: Filing Comparison ────────────────────────────────────────────────
with tab_filing:
    st.subheader("Filing Comparison")
    st.caption("Compare how a new 13F filing changes each strategy's target portfolio.")

    txn_df_raw = load_performance()  # just to check if data exists
    if txn_df_raw.empty:
        st.info("No data available.")
    else:
        from utils.strategy_operations import load_transactions
        txn_all = load_transactions()
        if txn_all.empty:
            st.info("No transaction data.")
        else:
            filing_dates = sorted(txn_all["filing_date"].dropna().unique())
            if len(filing_dates) < 2:
                st.info("Need at least 2 filing dates for comparison.")
            else:
                col1, col2 = st.columns(2)
                with col1:
                    old_filing = st.selectbox("Old Filing", filing_dates[:-1], index=len(filing_dates) - 2)
                with col2:
                    new_filing = st.selectbox("New Filing", filing_dates[1:], index=len(filing_dates) - 2)

                for strategy_id, meta in STRATEGY_REGISTRY.items():
                    with st.expander(f"Strategy {strategy_id}: {meta['name']}", expanded=False):
                        diff = get_filing_comparison(strategy_id, old_filing, new_filing)
                        if diff.empty:
                            st.write("No changes detected.")
                        else:
                            st.dataframe(diff, use_container_width=True, hide_index=True)
