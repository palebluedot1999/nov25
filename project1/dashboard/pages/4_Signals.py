# dashboard/pages/4_Signals.py
import sys
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from pathlib import Path
from datetime import timedelta

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from utils.csv_data import (
    load_portfolios, get_all_filings, load_holdings_by_date, load_qoq_changes, load_prices
)
from utils.data_processing import get_top_holdings_over_time, compute_and_save_qoq_changes

st.set_page_config(page_title="Signals", layout="wide")
st.title("Signals")

tab_bb, tab_prices = st.tabs(["Baker Bros", "Prices & Markets"])

# ── Baker Bros ─────────────────────────────────────────────────────────────────
with tab_bb:
    portfolios = load_portfolios(portfolio_type="fund")
    if portfolios.empty:
        st.warning("No fund portfolios found. Add one in Admin.")
        st.stop()

    portfolio_options = dict(zip(portfolios["name"], portfolios["id"]))
    portfolio_name = st.selectbox("Fund", list(portfolio_options.keys()), key="sig_fund")
    portfolio_id = portfolio_options[portfolio_name]

    filings = get_all_filings(portfolio_id)
    if filings.empty:
        st.warning("No filings found for this fund.")
        st.stop()

    filing_labels = {
        f"{row['period_end_date']} (filed {row['filing_date']})": row["filing_date"]
        for _, row in filings.iterrows()
    }
    selected_label = st.selectbox("Filing period", list(filing_labels.keys()), key="sig_period")
    filing_date = filing_labels[selected_label]

    holdings = load_holdings_by_date(portfolio_id, filing_date)
    filing_row = filings[filings["filing_date"] == filing_date].iloc[0]

    col1, col2, col3 = st.columns(3)
    col1.metric("Holdings", int(filing_row.get("num_positions", len(holdings))))
    col2.metric("AUM ($B)", f"{filing_row.get('total_value', 0) / 1e9:.2f}")
    col3.metric("Filed", filing_date)

    # Holdings table with QoQ
    st.subheader("Holdings")
    qoq = load_qoq_changes(portfolio_id, filing_date)
    if qoq.empty:
        with st.spinner("Computing QoQ changes..."):
            compute_and_save_qoq_changes(portfolio_id)
        qoq = load_qoq_changes(portfolio_id, filing_date)

    if not holdings.empty and not qoq.empty:
        display = holdings.merge(
            qoq[["cusip", "shares_delta_pct", "value_delta_pct", "qoq_weight_delta", "is_new"]],
            on="cusip", how="left"
        )
        display["QoQ Shares Δ%"] = display.apply(
            lambda r: "NEW" if r.get("is_new") else (f"{r['shares_delta_pct']:+.2f}%" if pd.notna(r.get("shares_delta_pct")) else "—"), axis=1
        )
        display["QoQ Weight Δ"] = display.apply(
            lambda r: "NEW" if r.get("is_new") else (f"{int(r['qoq_weight_delta']):+d}bp" if pd.notna(r.get("qoq_weight_delta")) else "—"), axis=1
        )
        cols = ["ticker", "company_name", "shares", "value", "weight", "QoQ Shares Δ%", "QoQ Weight Δ"]
        show_cols = [c for c in cols if c in display.columns]
        st.dataframe(display[show_cols], use_container_width=True, hide_index=True)
        st.download_button("Export CSV", display[show_cols].to_csv(index=False), "holdings.csv", "text/csv")
    else:
        st.dataframe(holdings, use_container_width=True)

    # Charts
    st.subheader("Charts")
    chart_view = st.radio("View", ["Chart", "Table"], horizontal=True, key="sig_chart_view")

    top_over_time = get_top_holdings_over_time(portfolio_id, top_n=10)
    if not top_over_time.empty:
        if chart_view == "Chart":
            fig = px.line(top_over_time, x="filing_date", y="weight", color="ticker",
                          title="Top 10 Weight Over Time")
            st.plotly_chart(fig, use_container_width=True)

            if not holdings.empty:
                top10 = holdings.nlargest(10, "value")
                fig2 = px.pie(top10, values="value", names="ticker", title="Portfolio Concentration")
                st.plotly_chart(fig2, use_container_width=True)
        else:
            st.dataframe(top_over_time, use_container_width=True)
            if not holdings.empty:
                top10 = holdings.nlargest(10, "value")
                st.dataframe(top10[["ticker", "value"]].rename(columns={"value": "Value ($)"}),
                             use_container_width=True, hide_index=True)

# ── Prices & Markets ───────────────────────────────────────────────────────────
with tab_prices:
    prices_dir = Path(__file__).parent.parent.parent / "data" / "raw" / "yahoo_prices"

    @st.cache_data(ttl=300)
    def available_tickers() -> list[str]:
        if not prices_dir.exists():
            return []
        return sorted(p.stem for p in prices_dir.glob("*.csv"))

    all_tickers = available_tickers()
    if not all_tickers:
        st.warning("No price data found. Fetch prices in Admin.")
        st.stop()

    default_tickers = [t for t in ["XBI", "SPY"] if t in all_tickers]
    selected_tickers = st.multiselect("Ticker(s)", all_tickers, default=default_tickers, key="sig_tickers")

    timeframe = st.radio(
        "Timeframe", ["1M", "3M", "6M", "1Y", "3Y", "5Y", "ALL"],
        horizontal=True, index=3, key="sig_tf"
    )
    compare_as = st.radio("Compare as", ["Price", "% Return"], horizontal=True, key="sig_compare")

    tf_days = {"1M": 30, "3M": 90, "6M": 180, "1Y": 365, "3Y": 1095, "5Y": 1825, "ALL": 99999}

    if selected_tickers:
        all_price_data = []
        for ticker in selected_tickers:
            df = load_prices(ticker)
            if df is not None and not df.empty:
                df = df[["date", "close"]].copy()
                df["ticker"] = ticker
                df["date"] = pd.to_datetime(df["date"])
                all_price_data.append(df)

        if all_price_data:
            combined = pd.concat(all_price_data)
            if timeframe != "ALL":
                cutoff = combined["date"].max() - timedelta(days=tf_days[timeframe])
                combined = combined[combined["date"] >= cutoff]

            price_view = st.radio("View", ["Chart", "Table"], horizontal=True, key="sig_price_view")

            if compare_as == "% Return":
                # Normalize to % return from earliest date in filtered window
                start_prices = combined.sort_values("date").groupby("ticker")["close"].first()
                combined = combined.copy()
                combined["value"] = combined.apply(
                    lambda r: (r["close"] / start_prices[r["ticker"]] - 1) * 100, axis=1
                )
                y_col, y_label = "value", "Return (%)"
            else:
                combined["value"] = combined["close"]
                y_col, y_label = "value", "Price ($)"

            if price_view == "Chart":
                fig = px.line(combined, x="date", y=y_col, color="ticker",
                              labels={"date": "Date", y_col: y_label},
                              title=f"{'Return' if compare_as == '% Return' else 'Price'} — {', '.join(selected_tickers)}")
                st.plotly_chart(fig, use_container_width=True)
            else:
                pivot = combined.pivot(index="date", columns="ticker", values="value").reset_index()
                st.dataframe(pivot.sort_values("date", ascending=False), use_container_width=True)

            st.download_button(
                "Export CSV",
                combined.pivot(index="date", columns="ticker", values="value").reset_index().to_csv(index=False),
                "prices.csv", "text/csv"
            )
