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

    st.title("Portfolio Overview")

    config = load_funds_config()
    default_fund = config.get('default_fund', 'baker-bros')

    summary = get_portfolio_summary(default_fund)

    if not summary:
        st.warning("No portfolio data available. Please fetch data first from the Data Management page.")
        return

    # Key metrics
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            "Total Value",
            f"${summary['total_value'] / 1e9:.2f}B"
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
        df['value_millions'] = (df['value'] / 1_000_000).round(2)
        df['weight'] = (df['value'] / summary['total_value'] * 100).round(2)

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
            values='value',
            names='company_name',
            title='Portfolio Composition (Top 10)'
        )
        st.plotly_chart(fig, use_container_width=True)


def show_positions():
    """Positions page - shows all current holdings and trade entry."""
    from utils.data_processing import get_holdings_dataframe, load_funds_config
    from utils.database import insert_trade, get_all_trades, delete_trade
    import pandas as pd
    from datetime import date, datetime

    st.title("Portfolio Positions")

    config = load_funds_config()
    default_fund = config.get('default_fund', 'baker-bros')

    df = get_holdings_dataframe(default_fund)

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
        display_df = filtered_df[display_cols].copy()
        display_df.columns = ['Company', 'Ticker', 'CUSIP', 'Shares', 'Value ($M)', 'Weight (%)']

        st.dataframe(
            display_df.sort_values('Value ($M)', ascending=False),
            use_container_width=True,
            hide_index=True
        )

        st.info(f"Showing {len(filtered_df)} of {len(df)} positions")
    else:
        st.warning("No 13F position data available.")

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
            strategy = st.text_input("Strategy", placeholder="e.g., Momentum")

        submitted = st.form_submit_button("Add Trade")

        if submitted:
            if ticker and quantity > 0 and price > 0:
                trade_data = {
                    'date': trade_date.isoformat(),
                    'time': trade_time.strftime('%H:%M:%S'),
                    'ticker': ticker.upper(),
                    'direction': direction,
                    'quantity': quantity,
                    'price': price,
                    'cost': cost,
                    'strategy': strategy
                }
                insert_trade(trade_data)
                st.success(f"Trade added: {direction} {quantity} {ticker.upper()} @ ${price}")
                st.rerun()
            else:
                st.error("Please fill in ticker, quantity, and price.")

    # Display trades table
    st.subheader("Trade History")

    trades = get_all_trades()

    if trades:
        trades_df = pd.DataFrame([dict(t) for t in trades])
        display_trades = trades_df[['id', 'date', 'time', 'ticker', 'direction', 'quantity', 'price', 'cost', 'strategy']].copy()
        display_trades.columns = ['ID', 'Date', 'Time', 'Ticker', 'Direction', 'Qty', 'Price', 'Cost', 'Strategy']

        st.dataframe(
            display_trades,
            use_container_width=True,
            hide_index=True
        )

        # Delete trade option
        col1, col2 = st.columns([3, 1])
        with col1:
            trade_to_delete = st.number_input("Trade ID to delete", min_value=1, step=1)
        with col2:
            if st.button("Delete Trade"):
                delete_trade(trade_to_delete)
                st.success(f"Trade {trade_to_delete} deleted")
                st.rerun()
    else:
        st.info("No trades recorded yet.")


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
    from utils.data_processing import get_historical_filings_dataframe, load_funds_config

    st.title("Filing Calendar")

    config = load_funds_config()
    default_fund = config.get('default_fund', 'baker-bros')

    df = get_historical_filings_dataframe(default_fund)

    if df.empty:
        st.warning("No filing data available.")
        return

    # Display filings table
    display_df = df[['form_type', 'filing_date', 'report_date', 'total_value', 'num_holdings']].copy()
    display_df['total_value'] = (display_df['total_value'] / 1e9).round(2)
    display_df.columns = ['Form', 'Filing Date', 'Report Date', 'Total Value ($B)', 'Holdings']

    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True
    )


def show_data_management():
    """Data management page for fetching and updating data."""
    from scrapers.sec_edgar import SECEdgarScraper
    from scrapers.yahoo_finance import YahooFinanceFetcher
    from utils.data_processing import initialize_funds, process_raw_filings, load_funds_config
    from utils.database import init_database

    st.title("Data Management")

    config = load_funds_config()
    funds = config.get('funds', [])

    # Initialize database
    if st.button("Initialize Database"):
        init_database()
        initialize_funds()
        st.success("Database initialized!")

    st.divider()

    # Fund selection
    fund_options = {f['name']: f for f in funds}
    selected_fund_name = st.selectbox("Select Fund", list(fund_options.keys()))
    selected_fund = fund_options[selected_fund_name]

    st.divider()

    # Fetch SEC filings
    st.subheader("SEC EDGAR Data")

    num_filings = st.number_input("Number of filings to fetch", 1, 20, 5)

    if st.button("Fetch 13F Filings"):
        with st.spinner("Fetching filings from SEC EDGAR..."):
            scraper = SECEdgarScraper()
            filings = scraper.fetch_and_save_filings(
                cik=selected_fund['cik'],
                fund_id=selected_fund['id'],
                limit=num_filings
            )
            st.success(f"Fetched {len(filings)} filings!")

    if st.button("Process Raw Filings"):
        with st.spinner("Processing raw filings..."):
            process_raw_filings(selected_fund['id'])
            st.success("Filings processed and saved to database!")

    st.divider()

    # Fetch price data
    st.subheader("Price Data")

    if st.button("Fetch Benchmark Prices (XBI)"):
        with st.spinner("Fetching benchmark data..."):
            fetcher = YahooFinanceFetcher()
            df = fetcher.get_benchmark_data(period="1y")
            fetcher.save_prices_to_db(df)
            st.success(f"Fetched {len(df)} price records for XBI!")


if __name__ == "__main__":
    main()
