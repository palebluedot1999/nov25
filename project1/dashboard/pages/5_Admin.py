# dashboard/pages/5_Admin.py
import sys
import time
import subprocess
import streamlit as st
import pandas as pd
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from utils.csv_data import load_portfolios, PROCESSED_DATA_DIR
from utils.price_operations import get_all_cached_tickers, get_fetch_status, save_fetch_status
from utils.security_operations import add_security_with_full_data, get_cusip_cache_summary
from utils.security_consolidation import get_securities_summary
from utils.fund_operations import parse_cik_input, batch_add_funds
from utils.metadata_operations import get_metadata_fetch_status, save_metadata_fetch_status

st.set_page_config(page_title="Admin", layout="wide")
st.title("Admin")

tab_fetch, tab_securities, tab_processing, tab_advanced = st.tabs(
    ["Data Fetch", "Securities", "Processing", "Advanced"]
)

# ── Data Fetch ─────────────────────────────────────────────────────────────────
with tab_fetch:
    st.subheader("13F Filings")
    portfolios = load_portfolios(portfolio_type="fund")
    if not portfolios.empty:
        fund_options = dict(zip(portfolios["name"], portfolios["id"]))
        selected_fund = st.selectbox("Fund", list(fund_options.keys()), key="admin_fund")
        portfolio_id = fund_options[selected_fund]
        col1, col2 = st.columns([1, 3])
        with col1:
            if st.button("Fetch latest 13Fs", key="fetch_13f"):
                from utils.fund_operations import pull_latest_13fs_all_funds
                with st.spinner("Fetching..."):
                    pull_latest_13fs_all_funds()
                st.success("Done")
    else:
        st.info("No funds configured. Add one in the Advanced tab.")

    st.divider()
    st.subheader("Prices")
    fetch_status = get_fetch_status()
    tickers = get_all_cached_tickers()
    fetched = fetch_status.get("fetched_count", 0)
    last_updated = fetch_status.get("last_updated", "Never")
    st.caption(f"{fetched}/{len(tickers)} tickers fetched · Last updated: {last_updated}")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Fetch incremental prices", key="fetch_prices_incr"):
            scripts_dir = Path(__file__).parent.parent.parent / "scripts"
            subprocess.Popen(["python", str(scripts_dir / "background_price_fetch.py")])
            st.info("Price fetch started in background. Refresh to see progress.")
    with col2:
        if st.button("Refresh status", key="refresh_price_status"):
            st.rerun()

    fetch_pct = fetched / len(tickers) if tickers else 0
    st.progress(fetch_pct)

    st.divider()
    st.subheader("Metadata")
    meta_status = get_metadata_fetch_status()
    meta_fetched = meta_status.get("fetched_count", 0)
    st.caption(f"{meta_fetched}/{len(tickers)} securities have metadata")

    if st.button("Fetch all metadata", key="fetch_meta"):
        scripts_dir = Path(__file__).parent.parent.parent / "scripts"
        subprocess.Popen(["python", str(scripts_dir / "background_metadata_fetch.py")])
        st.info("Metadata fetch started in background.")

# ── Securities ─────────────────────────────────────────────────────────────────
with tab_securities:
    summary = get_securities_summary()
    total = summary.get("total_count", 0)
    col1, col2 = st.columns([2, 1])
    with col1:
        st.metric("Securities", total)
    with col2:
        securities_path = PROCESSED_DATA_DIR / "securities.csv"
        if securities_path.exists():
            sec_df = pd.read_csv(securities_path)
            st.download_button("Export CSV", sec_df.to_csv(index=False), "securities.csv", "text/csv")

    st.subheader("Add Security")
    with st.form("add_security_form"):
        ticker_in = st.text_input("Ticker (required)")
        cusip_in = st.text_input("CUSIP (optional)")
        submitted = st.form_submit_button("Execute")
        if submitted and ticker_in:
            with st.spinner("Fetching prices and metadata..."):
                result = add_security_with_full_data(ticker_in.upper(), cusip_in or None, auto_consolidate=True)
            if result.get("success"):
                st.success(f"Added {ticker_in.upper()}")
            else:
                st.error(result.get("error", "Unknown error"))

    st.subheader("All Securities")
    if securities_path.exists():
        sec_df = pd.read_csv(securities_path)
        default_cols = ["ticker", "company_name", "sector", "industry", "market_cap", "pe_ratio"]
        available = [c for c in default_cols if c in sec_df.columns]
        with st.expander("Columns"):
            selected_cols = st.multiselect("Show columns", sec_df.columns.tolist(), default=available)
        if selected_cols:
            st.dataframe(sec_df[selected_cols], use_container_width=True)

# ── Processing ─────────────────────────────────────────────────────────────────
with tab_processing:
    scripts_dir = Path(__file__).parent.parent.parent / "scripts"

    def run_script(script_name: str, label: str):
        with st.spinner(f"Running {label}..."):
            result = subprocess.run(["python", str(scripts_dir / script_name)], capture_output=True, text=True)
        if result.returncode == 0:
            st.success(f"{label} complete")
        else:
            st.error(f"{label} failed: {result.stderr[:200]}")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Consolidate prices"):
            run_script("consolidate_prices.py", "Consolidate prices")
        if st.button("Consolidate holdings"):
            run_script("consolidate_holdings.py", "Consolidate holdings")
    with col2:
        if st.button("Consolidate securities"):
            run_script("consolidate_securities.py", "Consolidate securities")
        portfolios = load_portfolios(portfolio_type="fund")
        if not portfolios.empty:
            for _, p in portfolios.iterrows():
                if st.button(f"Compute QoQ — {p['name']}", key=f"qoq_{p['id']}"):
                    from utils.data_processing import compute_and_save_qoq_changes
                    with st.spinner("Computing..."):
                        compute_and_save_qoq_changes(p["id"])
                    st.success(f"QoQ changes computed for {p['name']}")

# ── Advanced ───────────────────────────────────────────────────────────────────
with tab_advanced:
    st.subheader("Batch Add Funds (CIK)")
    cik_text = st.text_area("CIK numbers (one per line or comma-separated)")
    start_date = st.date_input("Start date", value=pd.Timestamp("2020-01-01"))
    auto_fetch = st.checkbox("Auto-fetch prices after adding", value=True)

    if st.button("Process CIKs") and cik_text:
        ciks = parse_cik_input(cik_text)
        if ciks:
            with st.spinner(f"Adding {len(ciks)} fund(s)..."):
                batch_add_funds(ciks, str(start_date), callback=None)
            st.success(f"Added {len(ciks)} fund(s)")
        else:
            st.warning("No valid CIKs found")
