"""
Backfill historical holdings for Baker Bros Advisors LP.
Fetches all 13F filings from the last 5 years.
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from scrapers.sec_edgar import SECEdgarScraper


def backfill_baker_bros():
    """Fetch all Baker Bros 13F filings from last 5 years."""
    print("=" * 60)
    print("Backfilling Baker Bros Historical Holdings")
    print("=" * 60)
    print()

    scraper = SECEdgarScraper()

    # Calculate date 5 years ago
    start_date = (datetime.now() - timedelta(days=5*365)).strftime('%Y-%m-%d')

    print(f"Fetching all filings since {start_date}...")
    print()

    filings = scraper.fetch_and_save_filings(
        cik='1263508',
        portfolio_id='baker-bros',
        start_date=start_date,
        limit=None  # Ignore limit when start_date is provided
    )

    print()
    print("=" * 60)
    print(f"Backfill Complete!")
    print("=" * 60)
    print(f"Fetched {len(filings)} filings")
    print(f"Holdings saved to: data/raw/13f_filings/")
    print()
    print("Next step: Start the dashboard")
    print("  streamlit run dashboard/app.py")


if __name__ == "__main__":
    backfill_baker_bros()
