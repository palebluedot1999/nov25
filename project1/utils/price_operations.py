"""
Smart incremental price fetching operations.

Handles intelligent price data fetching with:
- Latest date detection (raw files first, processed fallback)
- Incremental updates (only fetch missing dates)
- Bulk processing with progress callbacks
"""

import sys
from pathlib import Path
from typing import Optional, List, Dict
from datetime import datetime, timedelta
import pandas as pd
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import json

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utils.csv_data import load_prices, save_prices, PRICES_DIR
from scrapers.yahoo_finance import YahooFinanceFetcher


PROCESSED_PRICES_FILE = project_root / "data" / "processed" / "prices.csv"
CUSIP_CACHE_FILE = project_root / "data" / "raw" / "cusip_cache.csv"
PRICE_FETCH_STATUS_FILE = project_root / "data" / "raw" / "price_fetch_status.json"


def get_latest_price_date(ticker: str) -> Optional[str]:
    """
    Get latest date in price data for a ticker.
    Priority: raw files first, then processed/prices.csv.

    Args:
        ticker: Stock ticker symbol

    Returns:
        Latest date string (YYYY-MM-DD) or None if no data exists
    """
    # Try raw file first
    df = load_prices(ticker)

    if not df.empty and 'date' in df.columns:
        # Convert to datetime if string, then get max
        df['date'] = pd.to_datetime(df['date'])
        latest = df['date'].max()
        return latest.strftime('%Y-%m-%d')

    # Fallback to processed/prices.csv
    if PROCESSED_PRICES_FILE.exists():
        try:
            df_processed = pd.read_csv(PROCESSED_PRICES_FILE)
            df_ticker = df_processed[df_processed['ticker'] == ticker]

            if not df_ticker.empty:
                df_ticker['date'] = pd.to_datetime(df_ticker['date'])
                latest = df_ticker['date'].max()
                return latest.strftime('%Y-%m-%d')
        except Exception as e:
            print(f"Error reading processed prices: {e}")

    return None


def get_all_cached_tickers() -> List[str]:
    """
    Read cusip_cache.csv and return all non-null ticker values.

    Returns:
        List of unique ticker symbols
    """
    if not CUSIP_CACHE_FILE.exists():
        return []

    try:
        df = pd.read_csv(CUSIP_CACHE_FILE)
        tickers = df['ticker'].dropna().unique().tolist()
        return sorted(tickers)
    except Exception as e:
        print(f"Error reading cusip cache: {e}")
        return []


def fetch_incremental_prices(ticker: str, start_from="2020-01-01") -> Dict:
    """
    Fetch only missing price data for a single ticker.

    Args:
        ticker: Stock ticker symbol
        start_from: Default start date if no existing data (YYYY-MM-DD)

    Returns:
        Dict with keys:
        - success: bool
        - message: str
        - records_added: int
        - date_range: tuple(start, end) or None
        - latest_date: str or None
    """
    try:
        # Get latest date in existing data
        latest_date = get_latest_price_date(ticker)

        # Determine fetch range
        if latest_date is None:
            # No existing data, fetch from start_from to today
            start_date = start_from
            message_prefix = "No existing data"
        else:
            # Existing data, fetch from day after latest to today
            latest_dt = datetime.strptime(latest_date, '%Y-%m-%d')
            start_dt = latest_dt + timedelta(days=1)
            start_date = start_dt.strftime('%Y-%m-%d')
            message_prefix = f"Latest date: {latest_date}"

        end_date = datetime.now().strftime('%Y-%m-%d')

        # Check if we need to fetch
        if start_date >= end_date:
            return {
                'success': True,
                'message': f"Up to date ({latest_date})",
                'records_added': 0,
                'date_range': None,
                'latest_date': latest_date
            }

        # Fetch price data
        fetcher = YahooFinanceFetcher()
        df = fetcher.get_stock_prices(ticker, start_date=start_date, end_date=end_date)

        if df.empty:
            return {
                'success': True,
                'message': f"{message_prefix}, no new data available",
                'records_added': 0,
                'date_range': (start_date, end_date),
                'latest_date': latest_date
            }

        # Save to raw file (merges with existing)
        save_prices(ticker, df)

        records_added = len(df)
        new_latest = df['date'].max() if 'date' in df.columns else end_date

        return {
            'success': True,
            'message': f"Fetched {records_added} records ({start_date} to {end_date})",
            'records_added': records_added,
            'date_range': (start_date, end_date),
            'latest_date': new_latest
        }

    except Exception as e:
        return {
            'success': False,
            'message': f"Error: {str(e)}",
            'records_added': 0,
            'date_range': None,
            'latest_date': None
        }


def fetch_all_incremental_prices(progress_callback=None, max_workers=10) -> Dict:
    """
    Fetch incremental prices for all tickers in cusip_cache using parallel processing.

    Args:
        progress_callback: Optional function(current, total, ticker, status_msg)
        max_workers: Number of parallel workers (default: 10)

    Returns:
        Dict with keys:
        - total_tickers: int
        - success_count: int
        - failed_tickers: List[str]
        - total_records_added: int
    """
    tickers = get_all_cached_tickers()

    if not tickers:
        return {
            'total_tickers': 0,
            'success_count': 0,
            'failed_tickers': [],
            'total_records_added': 0
        }

    success_count = 0
    failed_tickers = []
    total_records = 0
    completed = 0

    # Use ThreadPoolExecutor for parallel fetching
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_ticker = {
            executor.submit(fetch_incremental_prices, ticker): ticker
            for ticker in tickers
        }

        # Process completed tasks
        for future in as_completed(future_to_ticker):
            ticker = future_to_ticker[future]
            completed += 1

            try:
                result = future.result()

                if result['success']:
                    success_count += 1
                    total_records += result['records_added']

                    if progress_callback:
                        progress_callback(completed, len(tickers), ticker, result['message'])
                else:
                    failed_tickers.append(ticker)

                    if progress_callback:
                        progress_callback(completed, len(tickers), ticker, f"FAILED: {result['message']}")

            except Exception as e:
                failed_tickers.append(ticker)
                if progress_callback:
                    progress_callback(completed, len(tickers), ticker, f"ERROR: {str(e)}")

    return {
        'total_tickers': len(tickers),
        'success_count': success_count,
        'failed_tickers': failed_tickers,
        'total_records_added': total_records
    }


def save_fetch_status(status: Dict):
    """
    Save price fetch status to file.

    Args:
        status: Dict with status information
    """
    try:
        PRICE_FETCH_STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(PRICE_FETCH_STATUS_FILE, 'w') as f:
            json.dump(status, f, indent=2)
    except Exception as e:
        print(f"Error saving fetch status: {e}")


def load_fetch_status() -> Optional[Dict]:
    """
    Load price fetch status from file.

    Returns:
        Status dict or None if file doesn't exist
    """
    try:
        if PRICE_FETCH_STATUS_FILE.exists():
            with open(PRICE_FETCH_STATUS_FILE, 'r') as f:
                return json.load(f)
    except Exception as e:
        print(f"Error loading fetch status: {e}")
    return None


def get_fetch_status() -> Dict:
    """
    Get current fetch status with default values.

    Returns:
        Dict with keys: running, completed, current, total, ticker, message, timestamp
    """
    status = load_fetch_status()
    if status:
        return status

    return {
        'running': False,
        'completed': 0,
        'current': 0,
        'total': 0,
        'ticker': '',
        'message': 'Not started',
        'timestamp': datetime.now().isoformat(),
        'success_count': 0,
        'failed_tickers': [],
        'total_records_added': 0
    }


if __name__ == "__main__":
    # Test functions
    print("Testing price_operations.py...")
    print()

    # Test get_all_cached_tickers
    tickers = get_all_cached_tickers()
    print(f"Found {len(tickers)} tickers in cache")
    print(f"Sample: {tickers[:5]}")
    print()

    # Test get_latest_price_date
    if tickers:
        test_ticker = tickers[0]
        latest = get_latest_price_date(test_ticker)
        print(f"Latest date for {test_ticker}: {latest}")
        print()

    # Test fetch_incremental_prices (commented out to avoid API calls)
    # result = fetch_incremental_prices("AAPL")
    # print(f"Incremental fetch result: {result}")
