"""
Background price fetching script.

Runs independently to fetch incremental prices for all cached tickers.
Updates status file for monitoring by dashboard.
"""

import sys
from pathlib import Path
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utils.price_operations import (
    get_all_cached_tickers,
    fetch_all_incremental_prices,
    save_fetch_status
)


def run_background_fetch():
    """Run price fetch in background with status updates."""
    tickers = get_all_cached_tickers()

    # Initialize status
    status = {
        'running': True,
        'completed': 0,
        'current': 0,
        'total': len(tickers),
        'ticker': '',
        'message': 'Starting...',
        'timestamp': datetime.now().isoformat(),
        'success_count': 0,
        'failed_tickers': [],
        'total_records_added': 0
    }
    save_fetch_status(status)

    def update_progress(current, total, ticker, message):
        """Update status file with progress."""
        status['current'] = current
        status['ticker'] = ticker
        status['message'] = message
        status['timestamp'] = datetime.now().isoformat()
        save_fetch_status(status)

    try:
        # Fetch all prices with parallel processing (10 workers)
        result = fetch_all_incremental_prices(
            progress_callback=update_progress,
            max_workers=10
        )

        # Final status
        status.update({
            'running': False,
            'completed': result['total_tickers'],
            'current': result['total_tickers'],
            'total': result['total_tickers'],
            'ticker': 'Complete',
            'message': f"Fetched {result['total_records_added']} new records for {result['success_count']}/{result['total_tickers']} tickers",
            'timestamp': datetime.now().isoformat(),
            'success_count': result['success_count'],
            'failed_tickers': result['failed_tickers'],
            'total_records_added': result['total_records_added']
        })
        save_fetch_status(status)

        print(f"OK Price fetch complete!")
        print(f"  Success: {result['success_count']}/{result['total_tickers']}")
        print(f"  Records added: {result['total_records_added']}")
        if result['failed_tickers']:
            print(f"  Failed: {', '.join(result['failed_tickers'])}")

    except Exception as e:
        # Error status
        status.update({
            'running': False,
            'message': f'Error: {str(e)}',
            'timestamp': datetime.now().isoformat()
        })
        save_fetch_status(status)
        print(f"ERROR: {e}")
        raise


if __name__ == "__main__":
    print("Starting background price fetch...")
    run_background_fetch()
