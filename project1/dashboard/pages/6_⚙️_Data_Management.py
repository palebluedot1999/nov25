"""
Data Management page - Complete redesign with smart features.

Sections:
1. Smart Price Pull - Incremental price updates
2. Add New Security - Ticker/CUSIP resolution via OpenFIGI
3. Add Fund Portfolio - Batch CIK processing
4. Process Raw Data - Consolidation operations
"""

import streamlit as st
import sys
from pathlib import Path
from datetime import datetime
import subprocess
import pandas as pd

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from utils.price_operations import (
    get_all_cached_tickers,
    fetch_all_incremental_prices
)
from utils.security_operations import (
    add_security_to_cache,
    get_cusip_cache_summary
)
from utils.fund_operations import (
    parse_cik_input,
    batch_add_funds
)

st.title("Data Management")

# ============================================================================
# SECTION 1: SMART PRICE PULL
# ============================================================================

st.subheader("📊 Smart Price Pull")

tickers = get_all_cached_tickers()
st.info(f"Fetch incremental prices for {len(tickers)} securities (only missing dates)")

if st.button("Fetch All Prices", key="fetch_prices"):
    progress_bar = st.progress(0)
    status_text = st.empty()

    def update_progress(current, total, ticker, status):
        progress_bar.progress(current / total)
        status_text.text(f"[{current}/{total}] {ticker}: {status}")

    with st.spinner("Fetching prices..."):
        result = fetch_all_incremental_prices(update_progress)

    if result['success_count'] > 0:
        st.success(f"✓ Fetched {result['total_records_added']} new records for {result['success_count']}/{result['total_tickers']} tickers")
        st.session_state.price_fetch_complete = True
    else:
        st.info("All prices are up to date!")

    if result['failed_tickers']:
        st.warning(f"Failed tickers: {', '.join(result['failed_tickers'])}")

# Prompt for consolidation after fetch
if st.session_state.get('price_fetch_complete'):
    st.info("💡 Price data updated. Update master table?")
    col1, col2 = st.columns(2)

    with col1:
        if st.button("✓ Yes, Update Master Table", key="update_master"):
            with st.spinner("Consolidating..."):
                result = subprocess.run(
                    ["python", "scripts/consolidate_prices.py"],
                    cwd=project_root,
                    capture_output=True,
                    text=True
                )
                if result.returncode == 0:
                    st.success("✓ Master table updated!")
                    st.code(result.stdout[-500:] if len(result.stdout) > 500 else result.stdout)
                    st.session_state.price_fetch_complete = False
                    st.rerun()
                else:
                    st.error("✗ Consolidation failed")
                    st.code(result.stderr)

    with col2:
        if st.button("✗ Skip for Now", key="skip_consolidate"):
            st.session_state.price_fetch_complete = False
            st.rerun()

st.divider()

# ============================================================================
# SECTION 2: ADD NEW SECURITY
# ============================================================================

st.subheader("🔍 Add New Security")

cache_summary = get_cusip_cache_summary()
st.info(f"{cache_summary['total_entries']} securities in cache • Last updated: {cache_summary['last_modified']}")

col1, col2 = st.columns([3, 1])

with col1:
    security_input = st.text_input(
        "Enter Ticker or CUSIP",
        placeholder="AAPL or 037833100",
        key="security_input"
    )

with col2:
    input_type = st.radio(
        "Type:",
        ["Ticker", "CUSIP"],
        horizontal=True,
        label_visibility="collapsed",
        key="input_type"
    )

if st.button("Add to Cache", disabled=not security_input, key="add_security"):
    with st.spinner("Resolving via OpenFIGI..."):
        if input_type == "Ticker":
            result = add_security_to_cache(ticker=security_input.upper())
        else:
            result = add_security_to_cache(cusip=security_input.upper())

    if result['success']:
        st.success(f"✓ {result['message']}")
        st.rerun()
    else:
        st.error(f"✗ {result['message']}")

with st.expander("📋 View Recent Entries"):
    if cache_summary['recent_entries']:
        df_recent = pd.DataFrame(cache_summary['recent_entries'])
        st.dataframe(df_recent, width="stretch", hide_index=True)
    else:
        st.info("No entries in cache")

st.divider()

# ============================================================================
# SECTION 3: ADD FUND PORTFOLIO (BATCH MODE)
# ============================================================================

st.subheader("📈 Add Fund Portfolio (Batch Mode)")

cik_input = st.text_area(
    "Enter CIKs (comma-separated)",
    height=100,
    placeholder="1263508, 1234567, 9876543",
    key="cik_input"
)

ciks = parse_cik_input(cik_input) if cik_input else []

if ciks:
    st.success(f"✓ {len(ciks)} valid CIKs entered: {', '.join(ciks)}")

col1, col2 = st.columns(2)

with col1:
    start_date = st.date_input(
        "Start Date (for filings)",
        value=datetime(2020, 1, 1),
        key="start_date"
    )

with col2:
    auto_fetch = st.checkbox(
        "Auto-fetch prices after load",
        value=True,
        key="auto_fetch"
    )

if st.button(f"Load Holdings for {len(ciks)} CIKs", disabled=len(ciks)==0, key="load_holdings"):
    # Track cusip_cache size before
    cache_before = cache_summary['total_entries']

    progress_bar = st.progress(0)
    stage_text = st.empty()
    status_text = st.empty()

    def update_progress(stage, current, total, status):
        progress_bar.progress(current / total)
        stage_text.info(f"**{stage}** ({current}/{total})")
        status_text.text(status)

    with st.spinner("Processing CIKs..."):
        result = batch_add_funds(
            ciks,
            start_date.strftime('%Y-%m-%d'),
            update_progress
        )

    # Display results
    st.success(f"✓ Successfully loaded {result['success_count']}/{result['total_ciks']} funds")

    if result['portfolios_created']:
        st.info(f"📁 Created portfolios: {', '.join(result['portfolios_created'])}")

    if result['new_cusips'] > 0:
        st.info(f"🔍 Discovered {result['new_cusips']} new securities")

    if result['failed_ciks']:
        st.warning(f"⚠ Failed CIKs: {', '.join(result['failed_ciks'])}")

    # Auto-fetch prices if checkbox was checked and new securities discovered
    if auto_fetch and result['new_cusips'] > 0:
        st.info("🚀 Auto-fetching prices for new securities...")
        st.session_state.trigger_price_fetch = True
        st.rerun()

# Handle auto-fetch trigger
if st.session_state.get('trigger_price_fetch'):
    st.session_state.trigger_price_fetch = False
    st.warning("Please click 'Fetch All Prices' button above to fetch prices for newly added securities.")

st.divider()

# ============================================================================
# SECTION 4: PROCESS RAW DATA
# ============================================================================

st.subheader("⚙️ Process Raw Data")

st.info("Consolidate all raw price files into master prices.csv table")

if st.button("Consolidate Prices", key="consolidate_prices"):
    with st.spinner("Consolidating all price files..."):
        result = subprocess.run(
            ["python", "scripts/consolidate_prices.py"],
            cwd=project_root,
            capture_output=True,
            text=True
        )

    if result.returncode == 0:
        st.success("✓ Consolidation complete!")
        st.code(result.stdout)
    else:
        st.error("✗ Consolidation failed")
        st.code(result.stderr)

# Footer
st.divider()
st.caption("💡 Tip: Smart Price Pull only fetches missing dates to save time and API calls")
