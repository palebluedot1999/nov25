# dashboard/pages/3_Research.py
import sys
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from utils.strategy_registry import discover_strategies, set_live, get_live_strategy
from utils.csv_data import load_portfolios, get_all_filings, load_holdings_by_date

st.set_page_config(page_title="Research", layout="wide")
st.title("Research")

strategies = discover_strategies()
if not strategies:
    st.warning("No strategies found in `strategies/` directory.")
    st.stop()

strategy_options = {s["name"]: s for s in strategies}
selected_name = st.selectbox("Strategy", list(strategy_options.keys()), key="res_strategy")
strategy = strategy_options[selected_name]

live = get_live_strategy()
is_live = live is not None and live["module"] == strategy["module"]

col1, col2 = st.columns([3, 1])
with col1:
    badge = "🟢 Live" if is_live else "⚪ Research"
    st.caption(f"Status: {badge}")
with col2:
    if not is_live:
        if st.button("Set as Live"):
            set_live(strategy["module"])
            st.success(f"{strategy['name']} is now Live")
            st.rerun()
    else:
        st.caption("Currently Live strategy")

st.divider()

tab_backtest, tab_compare = st.tabs(["Backtest", "Compare"])

# ── Backtest ───────────────────────────────────────────────────────────────────
with tab_backtest:
    portfolios = load_portfolios(portfolio_type="fund")
    if portfolios.empty:
        st.warning("No fund portfolios. Add one in Admin.")
    else:
        portfolio_options = dict(zip(portfolios["name"], portfolios["id"]))
        portfolio_name = st.selectbox("Fund", list(portfolio_options.keys()), key="res_fund")
        portfolio_id = portfolio_options[portfolio_name]

        col1, col2, col3 = st.columns(3)
        with col1:
            start_date = st.date_input("From", value=pd.Timestamp("2020-01-01"), key="res_start")
        with col2:
            end_date = st.date_input("To", value=pd.Timestamp.today(), key="res_end")
        with col3:
            initial_capital = st.number_input("Initial capital ($)", min_value=1000, value=100000, step=1000, key="res_capital")

        # Strategy parameter sliders
        params = {}
        if strategy.get("parameters"):
            with st.expander("Strategy parameters"):
                for param_key, param_cfg in strategy["parameters"].items():
                    if param_cfg["type"] == "int":
                        params[param_key] = st.slider(
                            param_cfg["label"], param_cfg["min"], param_cfg["max"], param_cfg["default"], key=f"res_{param_key}"
                        )
                    elif param_cfg["type"] == "float":
                        params[param_key] = st.slider(
                            param_cfg["label"], float(param_cfg["min"]), float(param_cfg["max"]),
                            float(param_cfg["default"]), key=f"res_{param_key}"
                        )

        if st.button("▶ Run backtest", type="primary"):
            try:
                from utils.strategy_engine import StrategyConfig, run_simulation
                config = StrategyConfig(
                    portfolio_id=portfolio_id,
                    start_date=str(start_date),
                    end_date=str(end_date),
                    initial_capital=float(initial_capital),
                    **params,
                )
                with st.spinner("Running backtest..."):
                    results = run_simulation(config)
                st.session_state["res_results"] = results
                st.session_state["res_config"] = config
            except Exception as e:
                st.error(f"Backtest failed: {e}")

        if "res_results" in st.session_state:
            results = st.session_state["res_results"]
            perf = results.get("performance", {})

            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Total Return", f"{perf.get('total_return', 0):+.1f}%")
            col2.metric("vs XBI", f"{perf.get('vs_xbi', 0):+.1f}%")
            col3.metric("Sharpe", f"{perf.get('sharpe', 0):.2f}")
            col4.metric("Max Drawdown", f"{perf.get('max_drawdown', 0):.1f}%")

            bench_show = st.multiselect(
                "Benchmarks", ["XBI", "SPY", "Baker Bros"], default=["XBI", "SPY"], key="res_bench"
            )
            view = st.radio("View", ["Chart", "Table"], horizontal=True, key="res_view")

            returns_df = results.get("returns_df", pd.DataFrame())
            if not returns_df.empty:
                if view == "Chart":
                    fig = go.Figure()
                    fig.add_trace(go.Scatter(x=returns_df["date"], y=returns_df["strategy_return"],
                                             name=strategy["name"], line=dict(color="#1f77b4")))
                    if "XBI" in bench_show and "xbi_return" in returns_df.columns:
                        fig.add_trace(go.Scatter(x=returns_df["date"], y=returns_df["xbi_return"],
                                                 name="XBI", line=dict(color="#ff7f0e", dash="dash")))
                    if "SPY" in bench_show and "spy_return" in returns_df.columns:
                        fig.add_trace(go.Scatter(x=returns_df["date"], y=returns_df["spy_return"],
                                                 name="SPY", line=dict(color="#2ca02c", dash="dot")))
                    fig.update_layout(title="Cumulative Return", xaxis_title="Date", yaxis_title="Return (%)")
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.dataframe(returns_df, use_container_width=True)

# ── Compare ────────────────────────────────────────────────────────────────────
with tab_compare:
    st.info("Run backtests for each strategy first, then use this tab to compare results side by side.")
    if len(strategies) > 1:
        selected_for_compare = st.multiselect(
            "Strategies to compare",
            [s["name"] for s in strategies],
            default=[s["name"] for s in strategies[:2]],
            key="res_compare_strats"
        )
        bench_compare = st.multiselect("Benchmarks", ["XBI", "SPY", "Baker Bros"], default=["XBI"], key="res_compare_bench")
        st.caption("Comparison view requires cached backtest results. Run each strategy's backtest first.")
    else:
        st.caption("Add more strategies to `strategies/` to enable comparison.")
