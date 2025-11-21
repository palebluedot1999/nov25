"""
Main Streamlit dashboard application.
"""

import streamlit as st
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from config.settings import DASHBOARD_TITLE, DASHBOARD_PAGE_ICON

# Page configuration
st.set_page_config(
    page_title=DASHBOARD_TITLE,
    page_icon=DASHBOARD_PAGE_ICON,
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for better styling
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        margin-bottom: 1rem;
    }
    .metric-card {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 0.5rem;
    }
    .stMetric {
        background-color: #f8f9fa;
        padding: 1rem;
        border-radius: 0.5rem;
    }
</style>
""", unsafe_allow_html=True)


def main():
    """Main dashboard entry point."""

    # Sidebar navigation
    st.sidebar.title("Navigation")

    page = st.sidebar.radio(
        "Go to",
        ["Overview", "Positions", "P&L Analysis", "Tracking Error", "Calendar", "Data Management"]
    )

    # Route to appropriate page
    if page == "Overview":
        show_overview()
    elif page == "Positions":
        show_positions()
    elif page == "P&L Analysis":
        show_pnl()
    elif page == "Tracking Error":
        show_tracking_error()
    elif page == "Calendar":
        show_calendar()
    elif page == "Data Management":
        show_data_management()


def show_overview():
    """Overview/home page."""
    from utils.data_processing import get_portfolio_summary, load_funds_config
    from utils.database import get_all_portfolios

    st.title("Portfolio Overview")

    # Portfolio selector
    portfolios = get_all_portfolios(portfolio_type='fund')
    if not portfolios:
        st.warning("No portfolios found. Please initialize database from Data Management page.")
        return

    portfolio_options = {p['name']: p['id'] for p in portfolios}
    selected_name = st.selectbox("Select Portfolio", list(portfolio_options.keys()))
    portfolio_id = portfolio_options[selected_name]

    summary = get_portfolio_summary(portfolio_id)

    if not summary:
        st.warning("No portfolio data available. Please fetch data first from the Data Management page.")
        return

    # Key metrics
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            "Total Value",
            f"${summary['total_value'] / 1e9:.2f}B" if summary['total_value'] > 1e9
            else f"${summary['total_value'] / 1e6:.2f}M"
        )

    with col2:
        st.metric(
            "Positions",
            summary['num_positions']
        )

    with col3:
        st.metric(
            "Report Date",
            summary['report_date']
        )

    with col4:
        st.metric(
            "Filing Date",
            summary['filing_date']
        )

    st.divider()

    # Top holdings
    st.subheader("Top 10 Holdings")

    if summary['top_holdings']:
        import pandas as pd

        df = pd.DataFrame(summary['top_holdings'])
        df['value_millions'] = (df['market_value'] / 1_000_000).round(2)
        df['weight'] = (df['market_value'] / summary['total_value'] * 100).round(2)

        display_df = df[['company_name', 'ticker', 'shares', 'value_millions', 'weight']].copy()
        display_df.columns = ['Company', 'Ticker', 'Shares', 'Value ($M)', 'Weight (%)']

        st.dataframe(
            display_df,
            use_container_width=True,
            hide_index=True
        )

        # Pie chart of top holdings
        import plotly.express as px

        fig = px.pie(
            df,
            values='market_value',
            names='company_name',
            title='Portfolio Composition (Top 10)'
        )
        st.plotly_chart(fig, use_container_width=True)


def show_positions():
    """Positions page - shows all current holdings and trade entry."""
    from utils.data_processing import get_holdings_dataframe
    from utils.database import (
        get_all_portfolios,
        insert_transaction,
        get_transactions,
        delete_transaction,
        get_security_by_ticker,
        insert_security,
        get_all_strategies
    )
    import pandas as pd
    from datetime import date, datetime

    st.title("Portfolio Positions")

    # Portfolio selector
    portfolios = get_all_portfolios()
    if not portfolios:
        st.warning("No portfolios found.")
        return

    # Separate by type
    fund_portfolios = [p for p in portfolios if p['portfolio_type'] == 'fund']
    user_portfolios = [p for p in portfolios if p['portfolio_type'] == 'user']

    portfolio_options = {}
    if fund_portfolios:
        portfolio_options.update({f"[Fund] {p['name']}": p['id'] for p in fund_portfolios})
    if user_portfolios:
        portfolio_options.update({f"[User] {p['name']}": p['id'] for p in user_portfolios})

    if not portfolio_options:
        st.warning("No active portfolios found.")
        return

    selected_name = st.selectbox("Select Portfolio", list(portfolio_options.keys()))
    portfolio_id = portfolio_options[selected_name]

    # Holdings display
    df = get_holdings_dataframe(portfolio_id)

    if not df.empty:
        # Filters
        col1, col2 = st.columns(2)
        with col1:
            min_weight = st.slider("Minimum Weight (%)", 0.0, 10.0, 0.0, 0.1)
        with col2:
            search = st.text_input("Search Company")

        # Apply filters
        filtered_df = df[df['weight'] >= min_weight]
        if search:
            filtered_df = filtered_df[
                filtered_df['company_name'].str.contains(search, case=False, na=False)
            ]

        # Display
        display_cols = ['company_name', 'ticker', 'cusip', 'shares', 'value_millions', 'weight']
        available_cols = [col for col in display_cols if col in filtered_df.columns]
        display_df = filtered_df[available_cols].copy()

        col_names = {
            'company_name': 'Company',
            'ticker': 'Ticker',
            'cusip': 'CUSIP',
            'shares': 'Shares',
            'value_millions': 'Value ($M)',
            'weight': 'Weight (%)'
        }
        display_df.columns = [col_names.get(col, col) for col in available_cols]

        st.dataframe(
            display_df.sort_values('Value ($M)', ascending=False) if 'Value ($M)' in display_df.columns else display_df,
            use_container_width=True,
            hide_index=True
        )

        st.info(f"Showing {len(filtered_df)} of {len(df)} positions")
    else:
        st.warning("No position data available for this portfolio.")

    st.divider()

    # Trade Entry Section
    st.subheader("Trade Entry")

    with st.form("trade_form"):
        col1, col2, col3 = st.columns(3)

        with col1:
            trade_date = st.date_input("Date", value=date.today())
            trade_time = st.time_input("Time", value=datetime.now().time())
            ticker = st.text_input("Ticker", placeholder="e.g., AAPL")

        with col2:
            direction = st.selectbox("Direction", ["BUY", "SELL"])
            quantity = st.number_input("Quantity", min_value=0.0, step=1.0)
            price = st.number_input("Price", min_value=0.0, step=0.01)

        with col3:
            cost = st.number_input("Cost/Commission", min_value=0.0, step=0.01)

            # Strategy dropdown
            strategies = get_all_strategies()
            strategy_options = [""] + [s['name'] for s in strategies]
            strategy_name = st.selectbox("Strategy", strategy_options)

            notes = st.text_input("Notes", placeholder="Optional notes")

        submitted = st.form_submit_button("Add Trade")

        if submitted:
            if ticker and quantity > 0 and price > 0:
                # Get or create security
                security = get_security_by_ticker(ticker.upper())
                if not security:
                    # Create basic security entry
                    security_id = insert_security({
                        'cusip': None,
                        'ticker': ticker.upper(),
                        'company_name': ticker.upper(),
                        'share_class': None,
                        'asset_class': 'stock',
                        'sector': None,
                        'industry': None,
                        'exchange': None,
                        'is_active': 1
                    })
                else:
                    security_id = security['id']

                # Get strategy ID if selected
                strategy_id = None
                if strategy_name:
                    for s in strategies:
                        if s['name'] == strategy_name:
                            strategy_id = s['id']
                            break

                # Calculate total value
                total_value = quantity * price
                if direction == "SELL":
                    total_value = -total_value

                transaction_data = {
                    'portfolio_id': portfolio_id,
                    'security_id': security_id,
                    'transaction_date': trade_date.isoformat(),
                    'transaction_time': trade_time.strftime('%H:%M:%S'),
                    'transaction_type': direction,
                    'quantity': quantity if direction == "BUY" else -quantity,
                    'price': price,
                    'fees': cost,
                    'total_value': total_value,
                    'strategy_id': strategy_id,
                    'source': 'MANUAL',
                    'filing_id': None,
                    'notes': notes
                }
                insert_transaction(transaction_data)
                st.success(f"Transaction added: {direction} {quantity} {ticker.upper()} @ ${price}")
                st.rerun()
            else:
                st.error("Please fill in ticker, quantity, and price.")

    # Display transactions table
    st.subheader("Transaction History")

    transactions = get_transactions(portfolio_id)

    if transactions:
        trans_df = pd.DataFrame([dict(t) for t in transactions])
        display_cols = ['id', 'transaction_date', 'transaction_time', 'ticker', 'transaction_type',
                       'quantity', 'price', 'fees', 'strategy_name', 'source']
        available_cols = [col for col in display_cols if col in trans_df.columns]
        display_trans = trans_df[available_cols].copy()

        col_names = {
            'id': 'ID',
            'transaction_date': 'Date',
            'transaction_time': 'Time',
            'ticker': 'Ticker',
            'transaction_type': 'Type',
            'quantity': 'Qty',
            'price': 'Price',
            'fees': 'Fees',
            'strategy_name': 'Strategy',
            'source': 'Source'
        }
        display_trans.columns = [col_names.get(col, col) for col in available_cols]

        st.dataframe(
            display_trans,
            use_container_width=True,
            hide_index=True
        )

        # Delete transaction option
        col1, col2 = st.columns([3, 1])
        with col1:
            trans_to_delete = st.number_input("Transaction ID to delete", min_value=1, step=1)
        with col2:
            if st.button("Delete Transaction"):
                delete_transaction(trans_to_delete)
                st.success(f"Transaction {trans_to_delete} deleted")
                st.rerun()
    else:
        st.info("No transactions recorded yet for this portfolio.")


def show_pnl():
    """P&L Analysis page."""
    st.title("P&L Analysis")
    st.info("P&L analysis will be implemented in the next phase. This will show profit/loss calculations based on historical prices.")

    # Placeholder for future implementation
    st.subheader("Coming Soon")
    st.markdown("""
    - Daily/Weekly/Monthly P&L
    - Position-level P&L attribution
    - Historical performance chart
    - Realized vs Unrealized gains
    """)


def show_tracking_error():
    """Tracking Error page."""
    st.title("Tracking Error")
    st.info("Tracking error analysis will compare portfolio returns against the benchmark (XBI).")

    st.subheader("Coming Soon")
    st.markdown("""
    - Portfolio vs Benchmark returns
    - Rolling tracking error
    - Information ratio
    - Beta and Alpha calculations
    """)


def show_calendar():
    """Calendar page showing filing dates and events."""
    from utils.data_processing import get_historical_filings_dataframe
    from utils.database import get_all_portfolios

    st.title("Filing Calendar")

    # Portfolio selector
    portfolios = get_all_portfolios(portfolio_type='fund')
    if not portfolios:
        st.warning("No fund portfolios found.")
        return

    portfolio_options = {p['name']: p['id'] for p in portfolios}
    selected_name = st.selectbox("Select Portfolio", list(portfolio_options.keys()))
    portfolio_id = portfolio_options[selected_name]

    df = get_historical_filings_dataframe(portfolio_id)

    if df.empty:
        st.warning("No filing data available for this portfolio.")
        return

    # Display filings table
    display_cols = ['form_type', 'filing_date', 'report_date', 'total_value', 'num_positions']
    available_cols = [col for col in display_cols if col in df.columns]
    display_df = df[available_cols].copy()

    # Format values
    if 'total_value' in display_df.columns:
        display_df['total_value'] = (display_df['total_value'] / 1e9).round(2)

    col_names = {
        'form_type': 'Form',
        'filing_date': 'Filing Date',
        'report_date': 'Report Date',
        'total_value': 'Total Value ($B)',
        'num_positions': 'Positions'
    }
    display_df.columns = [col_names.get(col, col) for col in available_cols]

    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True
    )


def show_data_management():
    """Data management page for fetching and updating data."""
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
        return

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


if __name__ == "__main__":
    main()
