"""
Data processing and transformation utilities.
Updated to work with CSV-based data storage.
"""

import json
import pandas as pd
from pathlib import Path
from datetime import datetime
from typing import Optional

from config.settings import RAW_DATA_DIR, PROCESSED_DATA_DIR
from utils.csv_data import (
    load_portfolios,
    get_portfolio,
    load_latest_holdings,
    load_holdings_by_date,
    get_all_filings
)


# NOTE: load_funds_config() removed - funds.json migrated to data/portfolios.csv
# NOTE: initialize_portfolios() and process_raw_filings() have been removed
# Portfolio initialization is now done via scripts/initialize_csv_files.py
# Holdings are fetched directly to CSV format by SEC scraper (no processing needed)


def get_portfolio_summary(portfolio_id: str) -> Optional[dict]:
    """
    Get summary of current portfolio.

    Args:
        portfolio_id: Portfolio ID to get summary for

    Returns:
        Dictionary with portfolio summary or None if no data
    """
    df = load_latest_holdings(portfolio_id)

    if df.empty:
        return None

    # Extract metadata from first row
    filing_date = df['filing_date'].iloc[0]
    period_end = df['period_end_date'].iloc[0]

    # Calculate summary stats
    total_value = df['value'].sum()
    num_positions = len(df)

    # Top holdings (by value)
    top_df = df.nlargest(10, 'value')

    return {
        'filing_date': filing_date,
        'report_date': period_end,  # Keep for compatibility
        'total_value': total_value,
        'num_positions': num_positions,
        'holdings': df.to_dict('records'),
        'top_holdings': top_df.to_dict('records')
    }


def get_holdings_dataframe(portfolio_id: str, filing_date: Optional[str] = None) -> pd.DataFrame:
    """
    Get holdings as a pandas DataFrame.

    Args:
        portfolio_id: Portfolio ID to get holdings for
        filing_date: Optional filing date (YYYY-MM-DD) to get specific filing (default: latest)

    Returns:
        DataFrame with holdings data (empty if no holdings)
    """
    if filing_date:
        df = load_holdings_by_date(portfolio_id, filing_date)
    else:
        df = load_latest_holdings(portfolio_id)

    # load_latest_holdings and load_holdings_by_date already calculate weight and value_millions
    return df


def get_historical_filings_dataframe(portfolio_id: str) -> pd.DataFrame:
    """Get all filings as a DataFrame."""
    return get_all_filings(portfolio_id)


def get_portfolio_info(portfolio_id: str) -> Optional[dict]:
    """
    Get portfolio metadata.

    Args:
        portfolio_id: Portfolio ID

    Returns:
        Dictionary with portfolio info or None
    """
    return get_portfolio(portfolio_id)


def get_top_holdings_over_time(portfolio_id: str, top_n: int = 10) -> pd.DataFrame:
    """
    Get historical weight data for the top N holdings.

    Args:
        portfolio_id: Portfolio ID
        top_n: Number of top holdings to track (default: 10)

    Returns:
        DataFrame with columns: filing_date, ticker, company_name, weight
        Sorted by filing_date ascending
    """
    from utils.csv_data import get_holdings_files

    # Get latest holdings to identify top N
    latest_holdings = load_latest_holdings(portfolio_id)

    if latest_holdings.empty:
        return pd.DataFrame()

    # Get top N tickers by value in latest filing
    top_holdings = latest_holdings.nlargest(top_n, 'value')
    top_tickers = set(top_holdings['ticker'].tolist())

    # Load all historical holdings
    holdings_files = get_holdings_files(portfolio_id)

    historical_data = []

    for file in holdings_files:
        df = pd.read_csv(file)

        if df.empty:
            continue

        # Get filing date from the data
        filing_date = df['filing_date'].iloc[0]

        # Calculate weights for this filing
        total_value = df['value'].sum()

        for _, row in df.iterrows():
            ticker = row['ticker']

            # Only include top N holdings
            if ticker in top_tickers:
                weight = (row['value'] / total_value * 100) if total_value > 0 else 0

                historical_data.append({
                    'filing_date': filing_date,
                    'ticker': ticker,
                    'company_name': row['company_name'],
                    'weight': weight
                })

    if not historical_data:
        return pd.DataFrame()

    result_df = pd.DataFrame(historical_data)
    result_df['filing_date'] = pd.to_datetime(result_df['filing_date'])
    result_df = result_df.sort_values('filing_date')

    return result_df


if __name__ == "__main__":
    # Test CSV data functions
    print("Testing CSV data functions...")
    print()

    # Get summary
    summary = get_portfolio_summary('baker-bros')
    if summary:
        print(f"Portfolio Summary:")
        print(f"  Filing Date: {summary['filing_date']}")
        print(f"  Report Date: {summary['report_date']}")
        print(f"  Total Value: ${summary['total_value']:,.0f}")
        print(f"  Positions: {summary['num_positions']}")
    else:
        print("No holdings data found. Run backfill script first.")
