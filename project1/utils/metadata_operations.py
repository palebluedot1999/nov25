"""
Security metadata operations using Yahoo Finance.

Handles:
- Fetching fundamental data (sector, industry, market cap, etc.)
- Storing metadata in security_metadata.csv
- Enriching securities with additional information
"""

import sys
from pathlib import Path
from typing import Optional, Dict, List
import pandas as pd
import yfinance as yf
import time
import json
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

METADATA_FILE = project_root / "data" / "raw" / "security_metadata.csv"
CUSIP_CACHE_FILE = project_root / "data" / "raw" / "cusip_cache.csv"
METADATA_FETCH_STATUS_FILE = project_root / "data" / "raw" / "metadata_fetch_status.json"


def fetch_security_metadata(ticker: str) -> Optional[Dict]:
    """
    Fetch fundamental data for a security from Yahoo Finance.

    Args:
        ticker: Stock ticker symbol

    Returns:
        Dict with metadata fields or None if fetch fails
    """
    try:
        stock = yf.Ticker(ticker)
        info = stock.info

        # Extract Tier 1 fields
        metadata = {
            'ticker': ticker,
            'company_name': info.get('longName') or info.get('shortName'),
            'sector': info.get('sector'),
            'industry': info.get('industry'),
            'market_cap': info.get('marketCap'),
            'beta': info.get('beta'),
            'pe_ratio': info.get('trailingPE'),
            'forward_pe': info.get('forwardPE'),
            'price_to_book': info.get('priceToBook'),
            'dividend_yield': info.get('dividendYield'),
            'dividend_rate': info.get('dividendRate'),
            'payout_ratio': info.get('payoutRatio'),
            'shares_outstanding': info.get('sharesOutstanding'),
            'float_shares': info.get('floatShares'),
            'held_percent_institutions': info.get('heldPercentInstitutions'),
            'held_percent_insiders': info.get('heldPercentInsiders'),
            'short_percent_float': info.get('shortPercentOfFloat'),
            'short_ratio': info.get('shortRatio'),
            'revenue': info.get('totalRevenue'),
            'ebitda': info.get('ebitda'),
            'profit_margin': info.get('profitMargins'),
            'operating_margin': info.get('operatingMargins'),
            'roe': info.get('returnOnEquity'),
            'roa': info.get('returnOnAssets'),
            'debt_to_equity': info.get('debtToEquity'),
            'current_ratio': info.get('currentRatio'),
            'website': info.get('website'),
            'business_summary': info.get('longBusinessSummary'),
            'exchange': info.get('exchange'),
            'currency': info.get('currency', 'USD'),
            'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }

        return metadata

    except Exception as e:
        print(f"Error fetching metadata for {ticker}: {e}")
        return None


def save_metadata(metadata_list: List[Dict]):
    """
    Save metadata to CSV file.

    Args:
        metadata_list: List of metadata dicts
    """
    try:
        # Convert to DataFrame
        df_new = pd.DataFrame(metadata_list)

        # Load existing data if file exists
        if METADATA_FILE.exists():
            df_existing = pd.read_csv(METADATA_FILE)

            # Merge with existing data (update if ticker exists, add if new)
            df_combined = pd.concat([df_existing, df_new], ignore_index=True)

            # Drop duplicates, keeping the latest (last occurrence)
            df_combined = df_combined.drop_duplicates(subset=['ticker'], keep='last')

            df = df_combined
        else:
            df = df_new

        # Ensure directory exists
        METADATA_FILE.parent.mkdir(parents=True, exist_ok=True)

        # Save to CSV
        df.to_csv(METADATA_FILE, index=False)
        print(f"Saved metadata for {len(metadata_list)} securities")

    except Exception as e:
        print(f"Error saving metadata: {e}")


def fetch_and_save_metadata(ticker: str) -> bool:
    """
    Fetch metadata for a single ticker and save to file.

    Args:
        ticker: Stock ticker symbol

    Returns:
        True if successful, False otherwise
    """
    metadata = fetch_security_metadata(ticker)

    if metadata:
        save_metadata([metadata])
        return True
    return False


def bulk_fetch_metadata(tickers: List[str], rate_limit_delay: float = 0.5, progress_callback=None) -> Dict:
    """
    Fetch metadata for multiple tickers.

    Args:
        tickers: List of ticker symbols
        rate_limit_delay: Delay between requests in seconds (default: 0.5)
        progress_callback: Optional callback function(current, total, ticker, message)

    Returns:
        Dict with success_count, failed_tickers
    """
    metadata_list = []
    failed_tickers = []

    print(f"Fetching metadata for {len(tickers)} securities...")

    for i, ticker in enumerate(tickers, 1):
        print(f"[{i}/{len(tickers)}] Fetching {ticker}...")

        # Update progress if callback provided
        if progress_callback:
            progress_callback(i, len(tickers), ticker, f"Fetching metadata...")

        metadata = fetch_security_metadata(ticker)

        if metadata:
            metadata_list.append(metadata)
        else:
            failed_tickers.append(ticker)

        # Rate limiting
        if i < len(tickers):
            time.sleep(rate_limit_delay)

    # Save all metadata
    if metadata_list:
        save_metadata(metadata_list)

    return {
        'success_count': len(metadata_list),
        'failed_count': len(failed_tickers),
        'failed_tickers': failed_tickers
    }


def get_metadata_summary() -> Dict:
    """
    Get summary statistics about the metadata file.

    Returns:
        Dict with total_entries, last_updated, etc.
    """
    if not METADATA_FILE.exists():
        return {
            'total_entries': 0,
            'last_updated': 'Never',
            'has_data': False
        }

    try:
        df = pd.read_csv(METADATA_FILE)

        # Get last update time
        if 'last_updated' in df.columns and not df['last_updated'].isna().all():
            last_updated = df['last_updated'].max()
        else:
            # Fallback to file modification time
            mtime = METADATA_FILE.stat().st_mtime
            last_updated = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')

        return {
            'total_entries': len(df),
            'last_updated': last_updated,
            'has_data': True,
            'sectors': df['sector'].nunique() if 'sector' in df.columns else 0,
            'industries': df['industry'].nunique() if 'industry' in df.columns else 0
        }

    except Exception as e:
        print(f"Error reading metadata: {e}")
        return {
            'total_entries': 0,
            'last_updated': 'Error',
            'has_data': False
        }


def get_all_cached_tickers() -> List[str]:
    """
    Get all tickers from CUSIP cache.

    Returns:
        List of ticker symbols
    """
    if not CUSIP_CACHE_FILE.exists():
        return []

    try:
        df = pd.read_csv(CUSIP_CACHE_FILE)
        return df['ticker'].dropna().unique().tolist()
    except Exception as e:
        print(f"Error reading CUSIP cache: {e}")
        return []


def save_metadata_fetch_status(status: Dict):
    """
    Save metadata fetch status to JSON file.

    Args:
        status: Dict with status information
    """
    try:
        # Ensure directory exists
        METADATA_FETCH_STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)

        with open(METADATA_FETCH_STATUS_FILE, 'w') as f:
            json.dump(status, f, indent=2)
    except Exception as e:
        print(f"Error saving metadata fetch status: {e}")


def get_metadata_fetch_status() -> Dict:
    """
    Read metadata fetch status from JSON file.

    Returns:
        Dict with status information, or default status if file doesn't exist
    """
    if not METADATA_FETCH_STATUS_FILE.exists():
        return {
            'running': False,
            'current': 0,
            'total': 0,
            'ticker': '',
            'message': 'Ready',
            'timestamp': '',
            'success_count': 0,
            'failed_tickers': []
        }

    try:
        with open(METADATA_FETCH_STATUS_FILE, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error reading metadata fetch status: {e}")
        return {
            'running': False,
            'current': 0,
            'total': 0,
            'ticker': '',
            'message': 'Error',
            'timestamp': '',
            'success_count': 0,
            'failed_tickers': []
        }


if __name__ == "__main__":
    # Test fetching metadata for a sample ticker
    print("Testing metadata_operations.py...")
    print()

    # Test single ticker
    print("Fetching metadata for AAPL...")
    metadata = fetch_security_metadata("AAPL")
    if metadata:
        print(f"Company: {metadata['company_name']}")
        print(f"Sector: {metadata['sector']}")
        print(f"Industry: {metadata['industry']}")
        print(f"Market Cap: ${metadata['market_cap']:,}" if metadata['market_cap'] else "Market Cap: N/A")
        print(f"Beta: {metadata['beta']}")
        print()

    # Test summary
    summary = get_metadata_summary()
    print(f"Metadata summary: {summary}")
