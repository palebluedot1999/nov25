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
