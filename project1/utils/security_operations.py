"""
Security addition operations with OpenFIGI API integration.

Handles:
- Bi-directional CUSIP<->ticker resolution via OpenFIGI
- Adding securities to cusip_cache.csv
- Cache statistics and management
- One-click security addition with full data pipeline
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
from utils.price_operations import fetch_incremental_prices
from utils.metadata_operations import fetch_security_metadata, save_metadata
from utils.security_consolidation import consolidate_securities

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


def add_security_with_full_data(ticker=None, cusip=None, auto_consolidate=True) -> Dict:
    """
    One-click security addition with full data pipeline.

    Steps:
    1. Resolve CUSIP/ticker via add_security_to_cache()
    2. Fetch 5-year price history via fetch_incremental_prices()
    3. Fetch 31 metadata fields via fetch_security_metadata()
    4. Save metadata via save_metadata()
    5. Consolidate into master table via consolidate_securities() (optional)

    Args:
        ticker: Optional ticker symbol
        cusip: Optional CUSIP (9 characters)
        auto_consolidate: Auto-merge into master securities table (default: True)

    Returns:
        Dict with keys:
        - success: bool (overall success, True even with partial failures)
        - message: str (summary message)
        - steps: Dict (detailed step-by-step results)
          - resolution: Dict (ticker, cusip)
          - cache_add: Dict (success, message)
          - price_fetch: Dict (success, records_added, message)
          - metadata_fetch: Dict (success, message)
          - consolidation: Dict (success, message) [if auto_consolidate=True]
        - ticker: str (resolved)
        - cusip: str (resolved)
        - needs_cusip: bool (True if manual CUSIP entry required)
    """
    steps = {}
    overall_success = False
    resolved_ticker = None
    resolved_cusip = None
    needs_cusip = False

    try:
        # Step 1: Add to cache (also resolves CUSIP/ticker)
        print(f"Step 1: Adding security to cache (ticker={ticker}, cusip={cusip})...")
        cache_result = add_security_to_cache(ticker=ticker, cusip=cusip)
        steps['cache_add'] = cache_result

        # Check if we need manual CUSIP entry
        if cache_result.get('needs_cusip'):
            return {
                'success': False,
                'message': cache_result['message'],
                'steps': steps,
                'ticker': cache_result.get('ticker'),
                'cusip': cache_result.get('cusip'),
                'needs_cusip': True
            }

        # If cache add failed, stop immediately
        if not cache_result['success']:
            return {
                'success': False,
                'message': f"Failed to add security to cache: {cache_result['message']}",
                'steps': steps,
                'ticker': cache_result.get('ticker'),
                'cusip': cache_result.get('cusip'),
                'needs_cusip': False
            }

        # Get resolved ticker and CUSIP
        resolved_ticker = cache_result['ticker']
        resolved_cusip = cache_result['cusip']
        steps['resolution'] = {'ticker': resolved_ticker, 'cusip': resolved_cusip}

        print(f"  [OK] Resolved: {resolved_ticker} <-> {resolved_cusip}")

        # Step 2: Fetch 5-year price history
        print(f"Step 2: Fetching 5-year price history for {resolved_ticker}...")
        try:
            price_result = fetch_incremental_prices(resolved_ticker, start_from="2020-01-01")
            steps['price_fetch'] = price_result
            if price_result['success']:
                print(f"  [OK] Fetched {price_result.get('records_added', 0)} price records")
            else:
                print(f"  [WARN] Price fetch failed: {price_result['message']}")
        except Exception as e:
            steps['price_fetch'] = {
                'success': False,
                'message': f"Exception during price fetch: {str(e)}",
                'records_added': 0
            }
            print(f"  [WARN] Price fetch error: {e}")

        # Step 3: Fetch metadata (31 fields)
        print(f"Step 3: Fetching metadata for {resolved_ticker}...")
        try:
            metadata = fetch_security_metadata(resolved_ticker)
            if metadata:
                # Save metadata to file
                save_metadata([metadata])
                steps['metadata_fetch'] = {
                    'success': True,
                    'message': 'Successfully fetched 31 metadata fields',
                    'fields': len(metadata)
                }
                print(f"  [OK] Fetched {len(metadata)} metadata fields")
            else:
                steps['metadata_fetch'] = {
                    'success': False,
                    'message': 'No metadata returned (API may have failed)',
                    'fields': 0
                }
                print(f"  [WARN] Metadata fetch failed: No data returned")
        except Exception as e:
            steps['metadata_fetch'] = {
                'success': False,
                'message': f"Exception during metadata fetch: {str(e)}",
                'fields': 0
            }
            print(f"  [WARN] Metadata fetch error: {e}")

        # Step 4: Consolidate into master table (optional)
        if auto_consolidate:
            print(f"Step 4: Consolidating into master securities table...")
            try:
                consolidate_result = consolidate_securities()
                steps['consolidation'] = consolidate_result
                if consolidate_result['success']:
                    print(f"  [OK] {consolidate_result['message']}")
                else:
                    print(f"  [WARN] Consolidation failed: {consolidate_result['message']}")
            except Exception as e:
                steps['consolidation'] = {
                    'success': False,
                    'message': f"Exception during consolidation: {str(e)}"
                }
                print(f"  [WARN] Consolidation error: {e}")

        # Determine overall success
        # Success if cache add succeeded (even if price/metadata partially failed)
        overall_success = cache_result['success']

        # Build summary message
        success_steps = []
        failed_steps = []

        if cache_result['success']:
            success_steps.append('cache')
        if steps.get('price_fetch', {}).get('success'):
            success_steps.append('prices')
        if steps.get('metadata_fetch', {}).get('success'):
            success_steps.append('metadata')
        if steps.get('consolidation', {}).get('success'):
            success_steps.append('consolidation')

        if not steps.get('price_fetch', {}).get('success'):
            failed_steps.append('prices')
        if not steps.get('metadata_fetch', {}).get('success'):
            failed_steps.append('metadata')
        if auto_consolidate and not steps.get('consolidation', {}).get('success'):
            failed_steps.append('consolidation')

        if overall_success and not failed_steps:
            message = f"Successfully added {resolved_ticker} with complete data (prices + metadata)"
        elif overall_success and failed_steps:
            message = f"Added {resolved_ticker} with partial data (failed: {', '.join(failed_steps)})"
        else:
            message = f"Failed to add security"

        return {
            'success': overall_success,
            'message': message,
            'steps': steps,
            'ticker': resolved_ticker,
            'cusip': resolved_cusip,
            'needs_cusip': needs_cusip
        }

    except Exception as e:
        return {
            'success': False,
            'message': f"Unexpected error: {str(e)}",
            'steps': steps,
            'ticker': resolved_ticker,
            'cusip': resolved_cusip,
            'needs_cusip': False
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
