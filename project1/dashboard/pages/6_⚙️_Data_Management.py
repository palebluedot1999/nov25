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
from utils.data_processing import initialize_portfolios, process_raw_filings, load_funds_config
from utils.database import (
    init_database,
    get_all_portfolios,
    insert_portfolio,
    insert_strategy
)

st.title("Data Management")

# Initialize database
st.subheader("Database Setup")

col1, col2, col3 = st.columns(3)

with col1:
    if st.button("Initialize Database"):
        init_database()
        initialize_portfolios()
        st.success("Database initialized!")

with col2:
    if st.button("Initialize Default Strategies"):
        # Add some default strategies
        default_strategies = [
            {'code': 'LONG_EQUITY', 'name': 'Long Equity', 'description': 'Long equity position', 'category': 'Directional', 'is_active': 1},
            {'code': 'SHORT', 'name': 'Short', 'description': 'Short position', 'category': 'Directional', 'is_active': 1},
            {'code': 'MOMENTUM', 'name': 'Momentum', 'description': 'Momentum strategy', 'category': 'Factor', 'is_active': 1},
            {'code': 'VALUE', 'name': 'Value', 'description': 'Value investing', 'category': 'Factor', 'is_active': 1},
            {'code': 'EVENT_DRIVEN', 'name': 'Event Driven', 'description': 'Event driven strategy', 'category': 'Special Situations', 'is_active': 1},
        ]
        for strategy in default_strategies:
            insert_strategy(strategy)
        st.success("Default strategies created!")

with col3:
    with st.expander("Create User Portfolio"):
        portfolio_id = st.text_input("Portfolio ID", placeholder="my-portfolio")
        portfolio_name = st.text_input("Portfolio Name", placeholder="My Portfolio")
        if st.button("Create"):
            if portfolio_id and portfolio_name:
                insert_portfolio({
                    'id': portfolio_id,
                    'name': portfolio_name,
                    'portfolio_type': 'user',
                    'cik': None,
                    'description': 'User portfolio',
                    'benchmark_id': None,
                    'is_active': 1
                })
                st.success(f"Created portfolio: {portfolio_name}")
            else:
                st.error("Please provide both ID and name")

st.divider()

# Portfolio selection
portfolios = get_all_portfolios(portfolio_type='fund')
if not portfolios:
    st.warning("No fund portfolios found. Please initialize database first.")
    st.stop()

portfolio_options = {p['name']: p for p in portfolios}
selected_portfolio_name = st.selectbox("Select Portfolio", list(portfolio_options.keys()))
selected_portfolio = portfolio_options[selected_portfolio_name]

st.divider()

# Fetch SEC filings
st.subheader("SEC EDGAR Data")

num_filings = st.number_input("Number of filings to fetch", 1, 20, 5)

col1, col2 = st.columns(2)

with col1:
    if st.button("Fetch 13F Filings"):
        with st.spinner("Fetching filings from SEC EDGAR..."):
            scraper = SECEdgarScraper()
            filings = scraper.fetch_and_save_filings(
                cik=selected_portfolio['cik'],
                portfolio_id=selected_portfolio['id'],
                limit=num_filings
            )
            st.success(f"Fetched {len(filings)} filings!")

with col2:
    if st.button("Process Raw Filings"):
        with st.spinner("Processing raw filings..."):
            process_raw_filings(selected_portfolio['id'])
            st.success("Filings processed and saved to database!")

st.divider()

# Fetch price data
st.subheader("Price Data")

col1, col2 = st.columns(2)

with col1:
    if st.button("Fetch Benchmark Prices"):
        with st.spinner("Fetching benchmark data..."):
            fetcher = YahooFinanceFetcher()
            benchmark_ticker = selected_portfolio.get('benchmark_id', 'XBI')

            # Try to extract ticker from benchmark_id if it's a portfolio ID
            if '-benchmark-' in str(benchmark_ticker):
                benchmark_ticker = benchmark_ticker.split('-benchmark-')[-1].upper()

            df = fetcher.get_benchmark_data(benchmark=benchmark_ticker, period="1y")
            if not df.empty:
                # Save as benchmark prices
                fetcher.save_benchmark_prices_to_db(df, selected_portfolio['id'])
                st.success(f"Fetched {len(df)} price records for {benchmark_ticker}!")
            else:
                st.error(f"No data found for {benchmark_ticker}")

with col2:
    if st.button("Enrich Securities"):
        with st.spinner("Enriching securities with Yahoo Finance data..."):
            from utils.database import get_holdings
            fetcher = YahooFinanceFetcher()

            # Get unique tickers from holdings
            holdings = get_holdings(selected_portfolio['id'])
            tickers = list(set([h['ticker'] for h in holdings if h.get('ticker')]))

            if tickers:
                fetcher.bulk_enrich_securities(tickers)
                st.success(f"Enriched {len(tickers)} securities!")
            else:
                st.warning("No tickers found to enrich")
