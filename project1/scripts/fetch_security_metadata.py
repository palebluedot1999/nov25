"""
Fetch and save security metadata (fundamentals) from Yahoo Finance.

This script:
1. Reads all tickers from cusip_cache.csv
2. Fetches fundamental data from Yahoo Finance
3. Saves to data/raw/security_metadata.csv

Run this periodically to keep metadata up to date.
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utils.metadata_operations import (
    get_all_cached_tickers,
    bulk_fetch_metadata,
    get_metadata_summary
)


def main():
    """Fetch metadata for all securities in CUSIP cache."""
    print("=" * 60)
    print("Security Metadata Fetcher")
    print("=" * 60)
    print()

    # Get all tickers from CUSIP cache
    tickers = get_all_cached_tickers()

    if not tickers:
        print("No tickers found in CUSIP cache.")
        print("Please run backfill_historical_holdings.py first.")
        return

    print(f"Found {len(tickers)} tickers in CUSIP cache")
    print()

    # Check existing metadata
    summary = get_metadata_summary()
    if summary['has_data']:
        print(f"Existing metadata: {summary['total_entries']} entries")
        print(f"Last updated: {summary['last_updated']}")
        print()

        response = input("Update all metadata? This will take a few minutes. (y/n): ")
        if response.lower() != 'y':
            print("Cancelled.")
            return
        print()

    # Fetch metadata for all tickers
    result = bulk_fetch_metadata(tickers, rate_limit_delay=0.5)

    # Display results
    print()
    print("=" * 60)
    print("Results")
    print("=" * 60)
    print(f"Successfully fetched: {result['success_count']}/{len(tickers)}")

    if result['failed_tickers']:
        print(f"Failed: {result['failed_count']}")
        print(f"  Tickers: {', '.join(result['failed_tickers'][:10])}")
        if len(result['failed_tickers']) > 10:
            print(f"  ... and {len(result['failed_tickers']) - 10} more")

    # Show updated summary
    print()
    summary = get_metadata_summary()
    print(f"Total metadata entries: {summary['total_entries']}")
    print(f"Unique sectors: {summary.get('sectors', 0)}")
    print(f"Unique industries: {summary.get('industries', 0)}")
    print()
    print("Metadata saved to: data/raw/security_metadata.csv")


if __name__ == "__main__":
    main()
