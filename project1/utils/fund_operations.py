"""
Fund portfolio operations for batch CIK processing.

Handles:
- CIK input parsing and validation
- Fetching fund names from SEC EDGAR
- Creating portfolio entries
- Batch loading 13F filings with progress tracking
"""

import sys
from pathlib import Path
from typing import List, Dict, Optional
import pandas as pd
import requests
import time
import re
from datetime import datetime, timedelta

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utils.csv_data import load_portfolios, get_holdings_files, PORTFOLIOS_FILE, RAW_DATA_DIR
from scrapers.sec_edgar import SECEdgarScraper
from utils.cusip_mapping import cusip_to_ticker
from config.settings import SEC_USER_AGENT

CUSIP_CACHE_FILE = project_root / "data" / "raw" / "cusip_cache.csv"


def parse_cik_input(cik_string: str) -> List[str]:
    """
    Parse comma-separated CIK string.

    Args:
        cik_string: Comma-separated CIK values

    Returns:
        List of validated, unique CIK strings (sorted)
    """
    if not cik_string:
        return []

    # Split by comma
    ciks = [c.strip() for c in cik_string.split(',')]

    # Validate and filter
    valid_ciks = []
    for cik in ciks:
        # Remove any non-digit characters
        cik_clean = re.sub(r'\D', '', cik)

        # Validate: numeric, 1-10 digits
        if cik_clean and 1 <= len(cik_clean) <= 10:
            valid_ciks.append(cik_clean)

    # Remove duplicates and sort
    return sorted(list(set(valid_ciks)))


def fetch_fund_name_from_sec(cik: str) -> Optional[str]:
    """
    Fetch official fund name from SEC EDGAR.

    Args:
        cik: CIK number (will be padded to 10 digits)

    Returns:
        Fund name string or None if not found
    """
    try:
        # Pad CIK to 10 digits
        cik_padded = cik.zfill(10)

        # Build URL
        url = f"https://data.sec.gov/submissions/CIK{cik_padded}.json"

        # Set headers (SEC requires User-Agent)
        headers = {
            'User-Agent': SEC_USER_AGENT
        }

        # Make request
        response = requests.get(url, headers=headers, timeout=10)

        # Handle 404 (CIK not found)
        if response.status_code == 404:
            return None

        response.raise_for_status()

        # Parse JSON
        data = response.json()

        # Extract name
        name = data.get('name')

        # Rate limiting (SEC limit: 10 req/sec)
        time.sleep(0.1)

        return name

    except requests.exceptions.RequestException as e:
        print(f"SEC API error for CIK {cik}: {e}")
        return None
    except Exception as e:
        print(f"Error fetching fund name for CIK {cik}: {e}")
        return None


def create_portfolio_entry(cik: str, fund_name: str, portfolio_type="fund") -> Dict:
    """
    Create portfolio entry in portfolios.csv.

    Args:
        cik: CIK number
        fund_name: Official fund name
        portfolio_type: Type of portfolio (default: "fund")

    Returns:
        Dict with keys:
        - success: bool
        - message: str
        - portfolio_id: str or None
    """
    try:
        # Generate portfolio_id (slugify name)
        portfolio_id = fund_name.lower()
        portfolio_id = re.sub(r'[^\w\s-]', '', portfolio_id)  # Remove special chars
        portfolio_id = re.sub(r'[-\s]+', '-', portfolio_id)   # Replace spaces/hyphens with single hyphen
        portfolio_id = portfolio_id.strip('-')                 # Remove leading/trailing hyphens

        # Load existing portfolios
        if PORTFOLIOS_FILE.exists():
            df = pd.read_csv(PORTFOLIOS_FILE)
        else:
            df = pd.DataFrame(columns=['id', 'name', 'portfolio_type', 'cik', 'description', 'benchmark', 'is_active'])

        # Check for duplicates
        if not df.empty:
            if cik in df['cik'].values:
                existing_name = df[df['cik'] == cik]['name'].iloc[0]
                return {
                    'success': False,
                    'message': f'CIK {cik} already exists ({existing_name})',
                    'portfolio_id': None
                }

            if portfolio_id in df['id'].values:
                # Append CIK to make unique
                portfolio_id = f"{portfolio_id}-{cik}"

        # Create new row
        new_portfolio = pd.DataFrame([{
            'id': portfolio_id,
            'name': fund_name,
            'portfolio_type': portfolio_type,
            'cik': cik,
            'description': f'Fund portfolio (CIK: {cik})',
            'benchmark': '',  # Empty benchmark
            'is_active': 1
        }])

        # Append to CSV
        df = pd.concat([df, new_portfolio], ignore_index=True)
        PORTFOLIOS_FILE.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(PORTFOLIOS_FILE, index=False)

        return {
            'success': True,
            'message': f'Created portfolio: {portfolio_id}',
            'portfolio_id': portfolio_id
        }

    except Exception as e:
        return {
            'success': False,
            'message': f'Error creating portfolio: {str(e)}',
            'portfolio_id': None
        }


def batch_add_funds(ciks: List[str], start_date="2020-01-01",
                   progress_callback=None) -> Dict:
    """
    Batch process CIKs: create portfolios and fetch filings.

    Args:
        ciks: List of CIK strings
        start_date: Start date for filing fetch (YYYY-MM-DD)
        progress_callback: Optional function(stage, current, total, status)

    Returns:
        Dict with keys:
        - total_ciks: int
        - success_count: int
        - failed_ciks: List[str]
        - portfolios_created: List[str] (portfolio IDs)
        - new_cusips: int (count of new cache entries)
    """
    if not ciks:
        return {
            'total_ciks': 0,
            'success_count': 0,
            'failed_ciks': [],
            'portfolios_created': [],
            'new_cusips': 0
        }

    # Track cusip_cache size before
    cache_before = 0
    if CUSIP_CACHE_FILE.exists():
        cache_before = len(pd.read_csv(CUSIP_CACHE_FILE))

    failed_ciks = []
    portfolios_created = []
    fund_info = {}  # Map CIK -> (fund_name, portfolio_id)

    # Stage 1: Fetch fund names
    for i, cik in enumerate(ciks, 1):
        if progress_callback:
            progress_callback("Fetching fund names", i, len(ciks), f"CIK {cik}")

        fund_name = fetch_fund_name_from_sec(cik)

        if not fund_name:
            failed_ciks.append(cik)
            if progress_callback:
                progress_callback("Fetching fund names", i, len(ciks), f"CIK {cik} - FAILED (not found)")
        else:
            fund_info[cik] = {'name': fund_name, 'portfolio_id': None}
            if progress_callback:
                progress_callback("Fetching fund names", i, len(ciks), f"CIK {cik} - {fund_name}")

    # Stage 2: Create portfolios
    successful_ciks = [cik for cik in ciks if cik in fund_info]

    for i, cik in enumerate(successful_ciks, 1):
        fund_name = fund_info[cik]['name']

        if progress_callback:
            progress_callback("Creating portfolios", i, len(successful_ciks), fund_name)

        result = create_portfolio_entry(cik, fund_name)

        if result['success']:
            portfolio_id = result['portfolio_id']
            fund_info[cik]['portfolio_id'] = portfolio_id
            portfolios_created.append(portfolio_id)

            if progress_callback:
                progress_callback("Creating portfolios", i, len(successful_ciks), f"{fund_name} - {portfolio_id}")
        else:
            failed_ciks.append(cik)
            if progress_callback:
                progress_callback("Creating portfolios", i, len(successful_ciks), f"{fund_name} - FAILED")

    # Stage 3: Load 13F filings
    scraper = SECEdgarScraper()
    portfolios_to_load = [cik for cik in successful_ciks if fund_info[cik]['portfolio_id']]

    # Calculate number of quarters from start_date to today
    start_dt = datetime.strptime(start_date, '%Y-%m-%d')
    today = datetime.now()
    quarters = ((today.year - start_dt.year) * 4 + (today.month - start_dt.month) // 3) + 4  # Add buffer
    quarters = max(quarters, 20)  # At least 20 filings

    for i, cik in enumerate(portfolios_to_load, 1):
        portfolio_id = fund_info[cik]['portfolio_id']
        fund_name = fund_info[cik]['name']

        if progress_callback:
            progress_callback("Loading 13F filings", i, len(portfolios_to_load), f"{fund_name}")

        try:
            # Fetch filings (this auto-updates cusip_cache.csv)
            filings = scraper.fetch_and_save_filings(
                cik=cik,
                portfolio_id=portfolio_id,
                limit=quarters
            )

            if progress_callback:
                progress_callback("Loading 13F filings", i, len(portfolios_to_load),
                                f"{fund_name} - {len(filings)} filings loaded")

        except Exception as e:
            failed_ciks.append(cik)
            if progress_callback:
                progress_callback("Loading 13F filings", i, len(portfolios_to_load),
                                f"{fund_name} - FAILED: {str(e)}")

    # Count new CUSIPs
    cache_after = 0
    if CUSIP_CACHE_FILE.exists():
        cache_after = len(pd.read_csv(CUSIP_CACHE_FILE))

    new_cusips = cache_after - cache_before

    # Remove duplicates from failed_ciks
    failed_ciks = list(set(failed_ciks))

    return {
        'total_ciks': len(ciks),
        'success_count': len(portfolios_created),
        'failed_ciks': failed_ciks,
        'portfolios_created': portfolios_created,
        'new_cusips': new_cusips
    }


def fetch_incremental_filings_for_fund(portfolio_id: str, cik: str) -> Dict:
    """
    Fetch only new 13F filings for a fund (those not already saved locally).

    Compares local filing dates against what SEC has available and downloads
    only the filings whose filing_date is not already saved.

    Args:
        portfolio_id: Portfolio ID (used for filename pattern)
        cik: CIK number

    Returns:
        Dict with keys:
        - new_count: int (number of new filings downloaded)
        - downloaded: List[str] (filing dates downloaded)
        - errors: List[Dict] (any errors encountered)
    """
    # Get existing local filing dates
    local_files = get_holdings_files(portfolio_id)
    prefix = f"{portfolio_id}_"
    suffix = "_holdings.csv"
    local_dates = set()
    for f in local_files:
        name = f.name
        if name.startswith(prefix) and name.endswith(suffix):
            date_str = name[len(prefix):-len(suffix)]
            local_dates.add(date_str)

    # Get all available filings from SEC (metadata only — fast)
    scraper = SECEdgarScraper()
    sec_filings = scraper.get_13f_filings(cik, limit=None)

    # Identify new filings
    new_filings = [f for f in sec_filings if f['filing_date'] not in local_dates]

    if not new_filings:
        return {'new_count': 0, 'downloaded': [], 'errors': []}

    # Download each new filing individually (same logic as fetch_and_save_filings)
    holdings_dir = RAW_DATA_DIR / "13f_filings"
    holdings_dir.mkdir(parents=True, exist_ok=True)

    downloaded = []
    errors = []

    for filing in new_filings:
        filing_date = filing['filing_date']
        period_end = filing['report_date']
        try:
            holdings = scraper.get_13f_holdings(cik, filing['accession_number'], period_end)
            if holdings:
                for holding in holdings:
                    cusip = holding.get('cusip')
                    if cusip and not holding.get('ticker'):
                        holding['ticker'] = cusip_to_ticker(cusip, holding.get('company_name'))
                    holding['portfolio_id'] = portfolio_id
                    holding['filing_date'] = filing_date
                    holding['period_end_date'] = period_end

                filename = f"{portfolio_id}_{filing_date}_holdings.csv"
                pd.DataFrame(holdings).to_csv(holdings_dir / filename, index=False)
                downloaded.append(filing_date)
            else:
                errors.append({'filing_date': filing_date, 'error': 'No holdings found'})
        except Exception as e:
            errors.append({'filing_date': filing_date, 'error': str(e)})

    return {'new_count': len(downloaded), 'downloaded': downloaded, 'errors': errors}


def pull_latest_13fs_all_funds() -> Dict:
    """
    Check SEC for new 13F filings for all tracked funds and download any not yet saved.

    Returns:
        Dict with keys:
        - funds_checked: int
        - total_new_filings: int
        - details: List[Dict] (per-fund results including fund_name, portfolio_id, new_count, etc.)
    """
    portfolios_df = load_portfolios(portfolio_type='fund')

    # Only process fund portfolios that have a CIK
    fund_rows = portfolios_df[
        portfolios_df['cik'].notna() & (portfolios_df['cik'].astype(str).str.strip() != '')
    ]

    results = []
    total_new = 0

    for _, row in fund_rows.iterrows():
        portfolio_id = row['id']
        cik = str(int(float(str(row['cik']).strip())))
        fund_name = row['name']

        result = fetch_incremental_filings_for_fund(portfolio_id, cik)
        result['portfolio_id'] = portfolio_id
        result['fund_name'] = fund_name
        total_new += result['new_count']
        results.append(result)

    return {
        'funds_checked': len(results),
        'total_new_filings': total_new,
        'details': results
    }


if __name__ == "__main__":
    # Test functions
    print("Testing fund_operations.py...")
    print()

    # Test parse_cik_input
    test_input = "1263508, 123456, 98765"
    ciks = parse_cik_input(test_input)
    print(f"Parsed CIKs: {ciks}")
    print()

    # Test fetch_fund_name_from_sec (commented to avoid API call)
    # name = fetch_fund_name_from_sec("1263508")
    # print(f"Fund name for 1263508: {name}")
