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
import time

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from utils.price_operations import (
    get_all_cached_tickers,
    get_fetch_status,
    save_fetch_status
)
from utils.security_operations import (
    add_security_to_cache,
    get_cusip_cache_summary
)
from utils.fund_operations import (
    parse_cik_input,
    batch_add_funds
)
from utils.metadata_operations import (
    get_metadata_fetch_status,
    save_metadata_fetch_status
)

st.title("Data Management")

# ============================================================================
# SECTION 1: SMART PRICE PULL (Background Task)
# ============================================================================

st.subheader("Smart Price Pull (Auto-Running in Background)")

# Auto-start background fetch on page load if not already running
fetch_status = get_fetch_status()

# Check if we should auto-start (only if not running and not recently completed)
if 'background_fetch_initialized' not in st.session_state:
    st.session_state.background_fetch_initialized = True

    # Only auto-start if not already running and not completed recently
    if not fetch_status['running']:
        # Check if last completion was more than 5 minutes ago
        from datetime import datetime, timedelta
        should_start = True

        if fetch_status.get('timestamp'):
            try:
                last_update = datetime.fromisoformat(fetch_status['timestamp'])
                if datetime.now() - last_update < timedelta(minutes=5):
                    # Recently completed, don't auto-start
                    should_start = False
            except:
                pass

        # Don't auto-start if status is 'Complete' or 'Ready' (user manually cleared)
        status_message = fetch_status.get('message', '')
        if should_start and status_message not in ['Complete', 'Ready']:
            # Start background fetch using current Python executable
            subprocess.Popen(
                [sys.executable, "scripts/background_price_fetch.py"],
                cwd=project_root,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            time.sleep(0.5)  # Give it a moment to start
            fetch_status = get_fetch_status()

# Display current status
tickers = get_all_cached_tickers()

# Show status timestamp and last refresh
status_time = fetch_status.get('timestamp', '')
if status_time:
    try:
        status_dt = datetime.fromisoformat(status_time)
        status_display = status_dt.strftime('%H:%M:%S')
        st.caption(f"Status as of: {status_display}")
    except:
        pass

if st.session_state.get('last_refresh'):
    st.caption(f"Page refreshed: {st.session_state.last_refresh}")

if fetch_status['running']:
    st.info(f"Fetching prices for {len(tickers)} securities (running in background, **10x faster with parallel processing**)")

    # Progress bar
    progress_value = fetch_status['current'] / fetch_status['total'] if fetch_status['total'] > 0 else 0
    st.progress(progress_value)

    # Status text
    st.text(f"[{fetch_status['current']}/{fetch_status['total']}] {fetch_status['ticker']}: {fetch_status['message']}")
    st.caption("Auto-refreshing every 2 seconds...")

    # Auto-refresh every 2 seconds
    time.sleep(2)
    st.rerun()

elif fetch_status.get('success_count', 0) > 0:
    # Completed - show summary
    records_added = fetch_status.get('total_records_added', 0)
    success_count = fetch_status.get('success_count', 0)
    failed_count = len(fetch_status.get('failed_tickers', []))

    # Check if there are new tickers that weren't in the last run
    tickers_in_cache = len(tickers)
    tickers_processed = success_count + failed_count
    new_tickers = tickers_in_cache - tickers_processed

    if new_tickers > 0:
        st.info(f"{len(tickers)} securities in cache ({new_tickers} added since last fetch)")
        st.warning(f"Click 'Fetch Prices Now' to update prices for newly added securities")
    else:
        st.success(f"Completed: Fetched {records_added} new records for {success_count} tickers")

        if fetch_status.get('failed_tickers'):
            with st.expander(f"{failed_count} Failed Tickers"):
                st.write(', '.join(fetch_status['failed_tickers']))

else:
    # Not running, not completed - ready state
    st.info(f"Ready to fetch prices for {len(tickers)} securities")

# Manual trigger button
col1, col2 = st.columns([2, 1])

with col1:
    if st.button("Fetch Prices Now", key="fetch_prices_manual", disabled=fetch_status['running']):
        # Clear old status and start fresh
        save_fetch_status({
            'running': True,
            'completed': 0,
            'current': 0,
            'total': len(tickers),
            'ticker': 'Starting...',
            'message': 'Initializing...',
            'timestamp': datetime.now().isoformat(),
            'success_count': 0,
            'failed_tickers': [],
            'total_records_added': 0
        })

        # Start background fetch using current Python executable
        subprocess.Popen(
            [sys.executable, "scripts/background_price_fetch.py"],
            cwd=project_root,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        st.session_state.last_refresh = datetime.now().strftime('%H:%M:%S')
        st.toast("Price fetch started!")
        time.sleep(0.5)
        st.rerun()

with col2:
    if st.button("Refresh Status", key="refresh_status", help="Clear completed status and reset to ready state"):
        # Clear completed status and reset to ready state
        save_fetch_status({
            'running': False,
            'completed': 0,
            'current': 0,
            'total': 0,
            'ticker': '',
            'message': 'Ready',
            'timestamp': datetime.now().isoformat(),
            'success_count': 0,
            'failed_tickers': [],
            'total_records_added': 0
        })
        st.session_state.last_refresh = datetime.now().strftime('%H:%M:%S')
        st.toast("Status cleared!")
        time.sleep(0.3)  # Brief pause so user sees the toast
        st.rerun()

st.divider()

# ============================================================================
# SECTION 2: ADD NEW SECURITY
# ============================================================================

st.subheader("Add New Security")

cache_summary = get_cusip_cache_summary()
st.info(f"{cache_summary['total_entries']} securities in cache • Last updated: {cache_summary['last_modified']}")

st.markdown("""
**How it works:**
- **CUSIP → Ticker**: Auto-resolved via OpenFIGI API
- **Ticker → CUSIP**: Checked in cache (manual entry required if not found)
- **Both provided**: Added directly to cache
""")

col1, col2 = st.columns(2)

with col1:
    ticker_input = st.text_input(
        "Ticker (optional)",
        placeholder="AAPL",
        key="ticker_input"
    )

with col2:
    cusip_input = st.text_input(
        "CUSIP (optional)",
        placeholder="037833100",
        key="cusip_input"
    )

# Show session state for manual CUSIP entry flow
if st.session_state.get('awaiting_cusip'):
    st.warning(f"Please enter CUSIP for {st.session_state.get('pending_ticker')}")

if st.button("Add to Cache", disabled=(not ticker_input and not cusip_input), key="add_security"):
    with st.spinner("Resolving..."):
        result = add_security_to_cache(
            ticker=ticker_input.upper() if ticker_input else None,
            cusip=cusip_input.upper() if cusip_input else None
        )

    if result['success']:
        st.success(f"{result['message']}")
        # Clear any pending state
        st.session_state.awaiting_cusip = False
        st.session_state.pending_ticker = None
        st.rerun()
    elif result.get('needs_cusip'):
        # Ticker provided but CUSIP not in cache
        st.warning(f"{result['message']}")
        st.session_state.awaiting_cusip = True
        st.session_state.pending_ticker = result['ticker']
    else:
        st.error(f"{result['message']}")
        st.session_state.awaiting_cusip = False
        st.session_state.pending_ticker = None

with st.expander("Securities"):
    try:
        securities_file = project_root / "data" / "processed" / "securities.csv"
        if securities_file.exists():
            df_securities = pd.read_csv(securities_file)
            st.dataframe(df_securities, use_container_width=True, hide_index=True)
            st.caption(f"Total securities: {len(df_securities)}")
        else:
            st.info("No securities data available. Click 'Consolidate Securities' in the Process Raw Data section below.")
    except Exception as e:
        st.error(f"Error loading securities: {e}")

st.divider()

# ============================================================================
# SECTION 3: ADD FUND PORTFOLIO (BATCH MODE)
# ============================================================================

st.subheader("Add Fund Portfolio (Batch Mode)")

cik_input = st.text_area(
    "Enter CIKs (comma-separated)",
    height=100,
    placeholder="1263508, 1234567, 9876543",
    key="cik_input"
)

ciks = parse_cik_input(cik_input) if cik_input else []

if ciks:
    st.success(f"{len(ciks)} valid CIKs entered: {', '.join(ciks)}")

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
    st.success(f"Successfully loaded {result['success_count']}/{result['total_ciks']} funds")

    if result['portfolios_created']:
        st.info(f"Created portfolios: {', '.join(result['portfolios_created'])}")

    if result['new_cusips'] > 0:
        st.info(f"Discovered {result['new_cusips']} new securities")

    if result['failed_ciks']:
        st.warning(f"Failed CIKs: {', '.join(result['failed_ciks'])}")

    # Auto-fetch prices if checkbox was checked and new securities discovered
    if auto_fetch and result['new_cusips'] > 0:
        st.info("Auto-fetching prices for new securities...")
        st.session_state.trigger_price_fetch = True
        st.rerun()

# Handle auto-fetch trigger
if st.session_state.get('trigger_price_fetch'):
    st.session_state.trigger_price_fetch = False
    st.warning("Please click 'Fetch All Prices' button above to fetch prices for newly added securities.")

st.divider()

# ============================================================================
# SECTION 3.5: FETCH SECURITY METADATA
# ============================================================================

st.subheader("Fetch Security Metadata")

# Get metadata fetch status
metadata_status = get_metadata_fetch_status()
tickers = get_all_cached_tickers()

# Show status timestamp
status_time = metadata_status.get('timestamp', '')
if status_time:
    try:
        status_dt = datetime.fromisoformat(status_time)
        status_display = status_dt.strftime('%H:%M:%S')
        st.caption(f"Metadata status as of: {status_display}")
    except:
        pass

if metadata_status['running']:
    st.info(f"Fetching metadata for {len(tickers)} securities (running in background)")

    # Progress bar
    progress_value = metadata_status['current'] / metadata_status['total'] if metadata_status['total'] > 0 else 0
    st.progress(progress_value)

    # Status text
    st.text(f"[{metadata_status['current']}/{metadata_status['total']}] {metadata_status['ticker']}: {metadata_status['message']}")
    st.caption("Auto-refreshing every 2 seconds...")

    # Auto-refresh every 2 seconds
    time.sleep(2)
    st.rerun()

elif metadata_status.get('success_count', 0) > 0:
    # Completed - show summary
    success_count = metadata_status.get('success_count', 0)
    failed_count = len(metadata_status.get('failed_tickers', []))

    st.success(f"Completed: Fetched metadata for {success_count} securities")

    if metadata_status.get('failed_tickers'):
        with st.expander(f"{failed_count} Failed Tickers"):
            st.write(', '.join(metadata_status['failed_tickers']))

else:
    # Not running, not completed - ready state
    st.info(f"Ready to fetch metadata for {len(tickers)} securities (31 fields per security)")

# Manual trigger button
col1, col2 = st.columns([2, 1])

with col1:
    if st.button("Fetch Metadata Now", key="fetch_metadata_manual", disabled=metadata_status['running']):
        # Clear old status and start fresh
        save_metadata_fetch_status({
            'running': True,
            'current': 0,
            'total': len(tickers),
            'ticker': 'Starting...',
            'message': 'Initializing...',
            'timestamp': datetime.now().isoformat(),
            'success_count': 0,
            'failed_tickers': []
        })

        # Start background fetch
        subprocess.Popen(
            [sys.executable, "scripts/background_metadata_fetch.py"],
            cwd=project_root,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        st.toast("Metadata fetch started!")
        time.sleep(0.5)
        st.rerun()

with col2:
    if st.button("Refresh Status", key="refresh_metadata_status", help="Clear completed status and reset to ready state"):
        # Clear completed status and reset to ready state
        save_metadata_fetch_status({
            'running': False,
            'current': 0,
            'total': 0,
            'ticker': '',
            'message': 'Ready',
            'timestamp': datetime.now().isoformat(),
            'success_count': 0,
            'failed_tickers': []
        })
        st.toast("Status cleared!")
        time.sleep(0.3)
        st.rerun()

st.divider()

# ============================================================================
# SECTION 4: PROCESS RAW DATA
# ============================================================================

st.subheader("Process Raw Data")

st.info("Consolidate raw data files into master tables")

if st.button("Consolidate Securities", key="consolidate_securities"):
    with st.spinner("Merging CUSIP cache with security metadata..."):
        result = subprocess.run(
            [sys.executable, "scripts/consolidate_securities.py"],
            cwd=project_root,
            capture_output=True,
            text=True
        )

    if result.returncode == 0:
        st.success("Securities consolidation complete!")
        st.code(result.stdout)
    else:
        st.error("Securities consolidation failed")
        st.code(result.stderr)

if st.button("Consolidate Prices", key="consolidate_prices"):
    with st.spinner("Consolidating all price files..."):
        result = subprocess.run(
            [sys.executable, "scripts/consolidate_prices.py"],
            cwd=project_root,
            capture_output=True,
            text=True
        )

    if result.returncode == 0:
        st.success("Consolidation complete!")
        st.code(result.stdout)
    else:
        st.error("Consolidation failed")
        st.code(result.stderr)

# Footer
st.divider()
st.caption("Tip: Smart Price Pull only fetches missing dates to save time and API calls")
