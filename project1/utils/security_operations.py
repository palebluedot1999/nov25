"""
Security addition operations with OpenFIGI API integration.

Handles:
- Bi-directional CUSIP<->ticker resolution via OpenFIGI
- Adding securities to cusip_cache.csv
- Cache statistics and management
"""

import sys
from pathlib import Path
from typing import Optional, Dict, List
import pandas as pd
import requests
import time
import re
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utils.cusip_mapping import CUSIPMapper, cusip_to_ticker
from config.settings import OPENFIGI_API_KEY

CUSIP_CACHE_FILE = project_root / "data" / "raw" / "cusip_cache.csv"
OPENFIGI_URL = "https://api.openfigi.com/v3/mapping"


def ticker_to_cusip_from_cache(ticker: str) -> Optional[str]:
    """
    Reverse lookup: ticker -> CUSIP using local cache only.
    OpenFIGI API doesn't provide CUSIP data, so we rely on cache.

    Args:
        ticker: Stock ticker symbol

    Returns:
        CUSIP string (9 characters) or None if not found in cache
    """
    try:
        ticker = ticker.upper().strip()

        if not CUSIP_CACHE_FILE.exists():
            return None

        # Read cache and search for ticker
        df = pd.read_csv(CUSIP_CACHE_FILE)

        # Find matching ticker
        matches = df[df['ticker'].str.upper() == ticker]

        if len(matches) > 0:
            return matches.iloc[0]['cusip']

        return None

    except Exception as e:
        print(f"Error searching cache for ticker {ticker}: {e}")
        return None


def add_security_to_cache(ticker=None, cusip=None) -> Dict:
    """
    Add security to cusip_cache.csv with auto-resolution.

    Resolution logic:
    - If CUSIP provided: Auto-resolve ticker via OpenFIGI API
    - If ticker provided: Check cache first, otherwise require CUSIP
    - If both provided: Validate and add directly

    Args:
        ticker: Optional ticker symbol
        cusip: Optional CUSIP (9 characters)

    Returns:
        Dict with keys:
        - success: bool
        - message: str
        - ticker: str (resolved)
        - cusip: str (resolved)
        - needs_cusip: bool (True if ticker provided but CUSIP needed)
    """
    # Validation: at least one field required
    if not ticker and not cusip:
        return {
            'success': False,
            'message': 'At least ticker or CUSIP required',
            'ticker': None,
            'cusip': None,
            'needs_cusip': False
        }

    # Normalize inputs
    if ticker:
        ticker = ticker.upper().strip()

        # Validate ticker format
        if not re.match(r'^[A-Z0-9]{1,6}$', ticker):
            return {
                'success': False,
                'message': 'Invalid ticker format (1-6 alphanumeric characters)',
                'ticker': ticker,
                'cusip': None,
                'needs_cusip': False
            }

    if cusip:
        cusip = cusip.upper().strip()

        # Validate CUSIP format
        if len(cusip) != 9:
            return {
                'success': False,
                'message': 'Invalid CUSIP format (must be 9 characters)',
                'ticker': None,
                'cusip': cusip,
                'needs_cusip': False
            }

    # Resolution logic
    try:
        if ticker and not cusip:
            # Try cache first
            cusip = ticker_to_cusip_from_cache(ticker)

            if not cusip:
                # CUSIP not in cache and OpenFIGI doesn't provide it
                # User needs to provide CUSIP manually
                return {
                    'success': False,
                    'message': f'CUSIP not found for {ticker}. Please provide CUSIP manually.',
                    'ticker': ticker,
                    'cusip': None,
                    'needs_cusip': True
                }

        elif cusip and not ticker:
            # Lookup ticker via OpenFIGI (this works well)
            ticker = cusip_to_ticker(cusip, company_name=None)

            if not ticker:
                return {
                    'success': False,
                    'message': f'Could not resolve ticker for CUSIP {cusip}',
                    'ticker': None,
                    'cusip': cusip,
                    'needs_cusip': False
                }

        # Both fields now populated, add to cache
        mapper = CUSIPMapper()
        mapper.add_manual_mapping(cusip, ticker)

        return {
            'success': True,
            'message': f'Successfully added {ticker} <-> {cusip}',
            'ticker': ticker,
            'cusip': cusip,
            'needs_cusip': False
        }

    except Exception as e:
        return {
            'success': False,
            'message': f'Error adding security: {str(e)}',
            'ticker': ticker,
            'cusip': cusip,
            'needs_cusip': False
        }


def get_cusip_cache_summary() -> Dict:
    """
    Get cache statistics for display.

    Returns:
        Dict with keys:
        - total_entries: int
        - recent_entries: List[Dict] (last 5 rows)
        - last_modified: str (file mtime)
    """
    if not CUSIP_CACHE_FILE.exists():
        return {
            'total_entries': 0,
            'recent_entries': [],
            'last_modified': 'Never'
        }

    try:
        df = pd.read_csv(CUSIP_CACHE_FILE)

        # Get file modification time
        mtime = CUSIP_CACHE_FILE.stat().st_mtime
        mtime_str = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')

        # Get last 5 entries
        recent = df.tail(5).to_dict('records')

        return {
            'total_entries': len(df),
            'recent_entries': recent,
            'last_modified': mtime_str
        }

    except Exception as e:
        print(f"Error reading cusip cache: {e}")
        return {
            'total_entries': 0,
            'recent_entries': [],
            'last_modified': 'Error'
        }


if __name__ == "__main__":
    # Test functions
    print("Testing security_operations.py...")
    print()

    # Test get_cusip_cache_summary
    summary = get_cusip_cache_summary()
    print(f"Cache summary:")
    print(f"  Total entries: {summary['total_entries']}")
    print(f"  Last modified: {summary['last_modified']}")
    print(f"  Recent entries: {len(summary['recent_entries'])}")
    print()

    # Test ticker_to_cusip (commented to avoid API call)
    # cusip = ticker_to_cusip_via_openfigi("TSLA")
    # print(f"TSLA CUSIP: {cusip}")
