"""
Consolidate quarterly 13F filings into daily holdings table.

This script processes all quarterly 13F filings for a portfolio and creates
a daily holdings table at data/processed/holdings.csv.

Usage:
    python scripts/consolidate_holdings.py
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utils.holdings_operations import (
    process_quarterly_filings_to_daily_holdings,
    save_processed_holdings
)


def main():
    """Main consolidation logic."""
    print("=" * 60)
    print("Holdings Consolidation Script")
    print("=" * 60)
    print()

    # Configuration
    portfolio_id = 'baker-bros'
    start_date = '2020-12-31'
    output_file = project_root / "data" / "processed" / "holdings.csv"

    print(f"Portfolio: {portfolio_id}")
    print(f"Start date: {start_date}")
    print(f"Output file: {output_file}")
    print()

    # Process filings
    print("Processing quarterly filings to daily holdings...")
    print("-" * 60)
    holdings_df = process_quarterly_filings_to_daily_holdings(
        portfolio_id=portfolio_id,
        start_date=start_date
    )

    print()
    print("=" * 60)
    print("Summary Statistics")
    print("=" * 60)
    print(f"Total records: {len(holdings_df):,}")
    print(f"Date range: {holdings_df['eod_date'].min()} to {holdings_df['eod_date'].max()}")
    print(f"Unique tickers: {holdings_df['ticker'].nunique()}")
    print(f"Portfolio: {holdings_df['portfolio'].unique()[0]}")
    print()

    # Validate
    print("Validation Checks:")
    print("-" * 60)

    # Check for missing dates
    dates = pd.to_datetime(holdings_df['eod_date'])
    date_range = pd.date_range(start=dates.min(), end=dates.max(), freq='D')
    unique_dates = holdings_df['eod_date'].nunique()
    expected_dates = len(date_range)

    print(f"Unique dates: {unique_dates:,}")
    print(f"Expected dates: {expected_dates:,}")

    if unique_dates == expected_dates:
        print("[OK] No missing dates in sequence")
    else:
        print(f"[WARNING] {expected_dates - unique_dates} dates missing")

    # Check for null/negative shares
    null_shares = holdings_df['shares'].isna().sum()
    negative_shares = (holdings_df['shares'] < 0).sum()

    if null_shares == 0:
        print("[OK] No null shares")
    else:
        print(f"[WARNING] {null_shares} null shares")

    if negative_shares == 0:
        print("[OK] No negative shares")
    else:
        print(f"[WARNING] {negative_shares} negative shares")

    print()

    # Save
    print("Saving to CSV...")
    print("-" * 60)
    save_processed_holdings(holdings_df, output_file)

    print()
    print("=" * 60)
    print("Consolidation Complete!")
    print("=" * 60)
    print(f"Output file: {output_file}")
    print()


if __name__ == "__main__":
    import pandas as pd
    main()
