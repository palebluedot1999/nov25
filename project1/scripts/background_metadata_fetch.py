"""
Background security metadata fetching script.

Runs independently to fetch fundamental data for all cached tickers.
Updates status file for monitoring by dashboard.
"""

import sys
from pathlib import Path
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utils.metadata_operations import (
    get_all_cached_tickers,
    bulk_fetch_metadata,
    save_metadata_fetch_status
)


def run_background_fetch():
    """Run metadata fetch in background with status updates."""
    tickers = get_all_cached_tickers()

    # Initialize status
    status = {
        'running': True,
        'current': 0,
        'total': len(tickers),
        'ticker': '',
        'message': 'Starting...',
        'timestamp': datetime.now().isoformat(),
        'success_count': 0,
        'failed_tickers': []
    }
    save_metadata_fetch_status(status)

    def update_progress(current, total, ticker, message):
        """Update status file with progress."""
        status['current'] = current
        status['ticker'] = ticker
        status['message'] = message
        status['timestamp'] = datetime.now().isoformat()
        save_metadata_fetch_status(status)

    try:
        # Fetch all metadata with rate limiting (0.5s between requests)
        result = bulk_fetch_metadata(
            tickers,
            rate_limit_delay=0.5,
            progress_callback=update_progress
        )

        # Final status
        status.update({
            'running': False,
            'current': result['success_count'],
            'total': len(tickers),
            'ticker': 'Complete',
            'message': f"Fetched metadata for {result['success_count']}/{len(tickers)} securities",
            'timestamp': datetime.now().isoformat(),
            'success_count': result['success_count'],
            'failed_tickers': result['failed_tickers']
        })
        save_metadata_fetch_status(status)

        print(f"OK Metadata fetch complete!")
        print(f"  Success: {result['success_count']}/{len(tickers)}")
        if result['failed_tickers']:
            print(f"  Failed: {', '.join(result['failed_tickers'][:10])}")
            if len(result['failed_tickers']) > 10:
                print(f"  ... and {len(result['failed_tickers']) - 10} more")

    except Exception as e:
        # Error status
        status.update({
            'running': False,
            'message': f'Error: {str(e)}',
            'timestamp': datetime.now().isoformat()
        })
        save_metadata_fetch_status(status)
        print(f"ERROR: {e}")
        raise


if __name__ == "__main__":
    print("Starting background metadata fetch...")
    run_background_fetch()
