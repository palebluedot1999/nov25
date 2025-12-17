"""
Data Management page - Redesigned with one-click security addition.

Sections:
1. Add New Security - One-click workflow with auto data fetch
2. Securities Master Table - Full display with all metadata
3. Bulk Operations - Advanced bulk processing (collapsed)
4. Advanced Tools - Batch CIK processing (collapsed)
"""

import streamlit as st
import sys
from pathlib import Path
from datetime import datetime, timedelta
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
    add_security_with_full_data,
    get_cusip_cache_summary
)
from utils.security_consolidation import get_securities_summary
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
# BACKGROUND INITIALIZATION (runs on page load)
# ============================================================================

# Auto-start background fetch on page load if not already running
fetch_status = get_fetch_status()

# Check if we should auto-start (only if not running and not recently completed)
if 'background_fetch_initialized' not in st.session_state:
    st.session_state.background_fetch_initialized = True

    # Only auto-start if not already running and not completed recently
    if not fetch_status['running']:
        # Check if last completion was more than 5 minutes ago
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

# ============================================================================
# SECTION 1: ADD NEW SECURITY (One-Click Workflow)
# ============================================================================

with st.container(border=True):
    st.subheader("Add New Security")
    st.caption("Automatically fetch prices and metadata for a new security")

    # Input form
    col1, col2 = st.columns(2)

    with col1:
        ticker_input = st.text_input(
            "Ticker",
            placeholder="AAPL",
            key="ticker_single"
        )

    with col2:
        cusip_input = st.text_input(
            "CUSIP (optional)",
            placeholder="037833100",
            key="cusip_single",
            help="Leave blank to auto-resolve from ticker"
        )

    # Execute button
    if st.button(
        "Execute",
        disabled=(not ticker_input and not cusip_input),
        type="primary",
        key="add_security_full"
    ):
        with st.spinner("Adding security and fetching data (prices + metadata)... This may take ~7-10 seconds"):
            result = add_security_with_full_data(
                ticker=ticker_input.upper() if ticker_input else None,
                cusip=cusip_input.upper() if cusip_input else None,
                auto_consolidate=True
            )

        # Display results
        if result['success']:
            st.success(result['message'])

            # Show detailed steps
            with st.expander("View Details"):
                st.json(result['steps'])

            # Refresh page to show in table
            time.sleep(0.5)
            st.rerun()

        elif result.get('needs_cusip'):
            # Handle manual CUSIP entry flow
            st.warning(result['message'])
            st.info("Please re-enter with both ticker and CUSIP")

        else:
            st.error(result['message'])

            # Show error details
            if result.get('steps'):
                with st.expander("Error Details"):
                    st.json(result['steps'])

st.divider()

# ============================================================================
# SECTION 2: VIEW SECURITIES (Prominent Display)
# ============================================================================

with st.container(border=True):
    st.subheader("View Securities")
    st.caption("Browse all securities with their metadata")

    try:
        securities_file = project_root / "data" / "processed" / "securities.csv"

        if securities_file.exists():
            df_securities = pd.read_csv(securities_file)

            # Single metric
            st.metric("Number of Securities", len(df_securities))

            # Column selector for display
            with st.expander("Columns"):
                default_cols = ['ticker', 'company_name', 'sector', 'industry', 'market_cap', 'pe_ratio']
                # Filter default cols to only include existing columns
                available_default_cols = [c for c in default_cols if c in df_securities.columns]

                selected_cols = st.multiselect(
                    "Columns",
                    options=df_securities.columns.tolist(),
                    default=available_default_cols if available_default_cols else df_securities.columns[:6].tolist()
                )

            # Determine which dataframe to display
            if selected_cols:
                df_display = df_securities[selected_cols]
            else:
                # If no columns selected, show default or all
                if available_default_cols:
                    df_display = df_securities[available_default_cols]
                else:
                    df_display = df_securities

            # Display dataframe with search/filter
            st.dataframe(
                df_display,
                use_container_width=True,
                hide_index=True,
                height=400
            )

            # Export button
            csv = df_securities.to_csv(index=False)
            st.download_button(
                label="Export Securities to CSV",
                data=csv,
                file_name=f"securities_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv"
            )

        else:
            st.info("No securities data available. Add a security above or click 'Consolidate Securities' in Bulk Operations below.")

    except Exception as e:
        st.error(f"Error loading securities: {e}")

st.divider()

# ============================================================================
# SECTION 3: BULK OPERATIONS (Collapsible for Power Users)
# ============================================================================

with st.expander("Bulk Operations (Advanced)", expanded=False):

    # ========================================================================
    # SUBSECTION 3.1: BULK PRICE FETCH
    # ========================================================================

    st.markdown("### Bulk Price Fetch")
    st.caption("Fetch incremental price updates for all securities in cache (10x parallel processing)")

    # Get current status
    fetch_status = get_fetch_status()
    tickers = get_all_cached_tickers()

    # Show status timestamp
    status_time = fetch_status.get('timestamp', '')
    if status_time:
        try:
            status_dt = datetime.fromisoformat(status_time)
            status_display = status_dt.strftime('%H:%M:%S')
            st.caption(f"Status as of: {status_display}")
        except:
            pass

    if fetch_status['running']:
        st.info(f"Fetching prices for {len(tickers)} securities (10x parallel)")

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

        # Check if there are new tickers
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

            # Start background fetch
            subprocess.Popen(
                [sys.executable, "scripts/background_price_fetch.py"],
                cwd=project_root,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            st.toast("Price fetch started!")
            time.sleep(0.5)
            st.rerun()

    with col2:
        if st.button("Refresh Status", key="refresh_price_status", help="Clear completed status and reset"):
            # Clear completed status
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
            st.toast("Status cleared!")
            time.sleep(0.3)
            st.rerun()

    st.markdown("---")

    # ========================================================================
    # SUBSECTION 3.2: BULK METADATA FETCH
    # ========================================================================

    st.markdown("### Bulk Metadata Fetch")
    st.caption("Fetch 31 fundamental data fields for all securities (sequential with rate limiting)")

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
        st.info(f"Fetching metadata for {len(tickers)} securities")

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
        if st.button("Refresh Status", key="refresh_metadata_status", help="Clear completed status and reset"):
            # Clear completed status
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

    st.markdown("---")

    # ========================================================================
    # SUBSECTION 3.3: PROCESS RAW DATA
    # ========================================================================

    st.markdown("### Process Raw Data")
    st.caption("Consolidate raw data files into master tables")

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

    if st.button("Consolidate Holdings", key="consolidate_holdings"):
        with st.spinner("Processing quarterly 13F filings into daily holdings..."):
            result = subprocess.run(
                [sys.executable, "scripts/consolidate_holdings.py"],
                cwd=project_root,
                capture_output=True,
                text=True
            )

        if result.returncode == 0:
            st.success("Holdings consolidation complete!")
            st.code(result.stdout)
        else:
            st.error("Holdings consolidation failed")
            st.code(result.stderr)

st.divider()

# ============================================================================
# SECTION 4: ADVANCED TOOLS (Collapsible)
# ============================================================================

with st.expander("Advanced Tools", expanded=False):

    # ========================================================================
    # SUBSECTION 4.1: ADD FUND PORTFOLIO (BATCH MODE)
    # ========================================================================

    st.markdown("### Add Fund Portfolio (Batch Mode)")
    st.caption("Load multiple funds at once via CIK numbers")

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
        st.warning("Please expand 'Bulk Operations' above and click 'Fetch Prices Now' to fetch prices for newly added securities.")

# Footer
st.divider()
st.caption("Tip: Use the one-click 'Add Security with Data' button above for quick ad-hoc security additions")
