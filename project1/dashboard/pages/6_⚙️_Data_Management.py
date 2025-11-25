"""
Data management page for fetching and updating data.
"""

import streamlit as st
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from scrapers.sec_edgar import SECEdgarScraper
from scrapers.yahoo_finance import YahooFinanceFetcher
from utils.csv_data import load_portfolios, PORTFOLIOS_FILE, STRATEGIES_FILE
import pandas as pd

st.title("Data Management")

# CSV initialization
st.subheader("Data Files Setup")

col1, col2 = st.columns(2)

with col1:
    if st.button("Initialize Data Files"):
        with st.spinner("Initializing CSV files..."):
            import subprocess
            result = subprocess.run(
                ["python", "scripts/initialize_csv_files.py"],
                cwd=project_root,
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                st.success("Data files initialized!")
                st.code(result.stdout)
            else:
                st.error("Initialization failed")
                st.code(result.stderr)

with col2:
    with st.expander("Create User Portfolio"):
        portfolio_id = st.text_input("Portfolio ID", placeholder="my-portfolio")
        portfolio_name = st.text_input("Portfolio Name", placeholder="My Portfolio")
        if st.button("Create"):
            if portfolio_id and portfolio_name:
                # Load existing portfolios
                if PORTFOLIOS_FILE.exists():
                    df = pd.read_csv(PORTFOLIOS_FILE)
                else:
                    df = pd.DataFrame()

                # Add new portfolio
                new_portfolio = pd.DataFrame([{
                    'id': portfolio_id,
                    'name': portfolio_name,
                    'portfolio_type': 'user',
                    'cik': '',
                    'description': 'User portfolio',
                    'benchmark': '',
                    'is_active': 1
                }])

                df = pd.concat([df, new_portfolio], ignore_index=True)
                df.to_csv(PORTFOLIOS_FILE, index=False)
                st.success(f"Created portfolio: {portfolio_name}")
                st.rerun()
            else:
                st.error("Please provide both ID and name")

st.divider()

# Portfolio selection
portfolios = load_portfolios(portfolio_type='fund').to_dict('records')
if not portfolios:
    st.warning("No fund portfolios found. Please initialize data files first.")
    st.stop()

portfolio_options = {p['name']: p for p in portfolios}
selected_portfolio_name = st.selectbox("Select Portfolio", list(portfolio_options.keys()))
selected_portfolio = portfolio_options[selected_portfolio_name]

st.divider()

# Fetch SEC filings
st.subheader("SEC EDGAR Data")

num_filings = st.number_input("Number of filings to fetch", 1, 20, 5)

if st.button("Fetch 13F Filings"):
    with st.spinner("Fetching filings from SEC EDGAR..."):
        scraper = SECEdgarScraper()
        filings = scraper.fetch_and_save_filings(
            cik=selected_portfolio['cik'],
            portfolio_id=selected_portfolio['id'],
            limit=num_filings
        )
        st.success(f"Fetched {len(filings)} filings and saved to data/raw/13f_filings/")
        st.info("Holdings CSVs saved with filing_date and period_end_date columns")

st.divider()

# Fetch price data
st.subheader("Price Data")

if st.button("Fetch Benchmark Prices"):
    with st.spinner("Fetching benchmark data..."):
        from utils.csv_data import save_prices
        fetcher = YahooFinanceFetcher()
        benchmark_ticker = selected_portfolio.get('benchmark', 'XBI')

        df = fetcher.get_stock_prices(ticker=benchmark_ticker, period="1y")
        if not df.empty:
            # Save to CSV
            save_prices(benchmark_ticker, df)
            st.success(f"Fetched {len(df)} price records for {benchmark_ticker}!")
            st.info(f"Saved to data/prices/{benchmark_ticker}.csv")
        else:
            st.error(f"No data found for {benchmark_ticker}")
