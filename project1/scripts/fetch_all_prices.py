"""
Fetch historical price data for all tickers in cusip_cache.csv

This script:
- Reads all unique tickers from data/raw/cusip_cache.csv
- Fetches 5 years of price history for each ticker via Yahoo Finance
- Saves each ticker to its own CSV file in data/raw/yahoo_prices/
- Can be run manually or via Data Management page "Fetch All Holdings Prices" button

Usage:
    python scripts/fetch_all_prices.py
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import pandas as pd
from scrapers.yahoo_finance import YahooFinanceFetcher
from utils.csv_data import save_prices
import time

# Read all tickers from cusip cache
cusip_cache_path = project_root / "data" / "raw" / "cusip_cache.csv"
cusip_df = pd.read_csv(cusip_cache_path)
tickers = cusip_df['ticker'].dropna().unique().tolist()

print(f"Found {len(tickers)} unique tickers to fetch")
print("=" * 60)

fetcher = YahooFinanceFetcher()

success_count = 0
failed_tickers = []

for i, ticker in enumerate(tickers, 1):
    try:
        print(f"[{i}/{len(tickers)}] Fetching {ticker}...", end=" ")

        df = fetcher.get_stock_prices(ticker=ticker, period="5y")

        if not df.empty:
            save_prices(ticker, df)
            success_count += 1
            print(f"OK ({len(df)} records)")
        else:
            print(f"FAILED - No data")
            failed_tickers.append(ticker)

        # Small delay to avoid rate limiting
        time.sleep(0.2)

    except Exception as e:
        print(f"ERROR: {e}")
        failed_tickers.append(ticker)

print("=" * 60)
print(f"\nCompleted!")
print(f"Success: {success_count}/{len(tickers)}")
print(f"Failed: {len(failed_tickers)}/{len(tickers)}")

if failed_tickers:
    print(f"\nFailed tickers: {', '.join(failed_tickers)}")
