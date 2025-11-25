"""
NOTE: This script is obsolete after CSV migration.
Tickers are now populated directly by SEC scraper during holdings fetch.
Database no longer exists - holdings stored in CSV files with tickers included.

Original purpose: Backfill missing tickers for securities in the database.
"""

# from utils.database import get_connection  # Removed - database deleted
from utils.cusip_mapping import get_mapper
import time

def backfill_tickers(batch_size=25):
    """
    Find securities without tickers and populate them via CUSIP lookup.

    Args:
        batch_size: Number of lookups to attempt (default 25 for free tier rate limit)
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Get securities without tickers
    cursor.execute('''
        SELECT id, cusip, company_name
        FROM securities
        WHERE ticker IS NULL
        AND cusip IS NOT NULL
        LIMIT ?
    ''', (batch_size,))

    missing = cursor.fetchall()

    if not missing:
        print("All securities have tickers!")
        conn.close()
        return

    print(f"Found {len(missing)} securities without tickers")
    print(f"Attempting to lookup up to {batch_size} tickers...")
    print("-" * 60)

    mapper = get_mapper()
    successful = 0
    failed = 0

    for security_id, cusip, company_name in missing:
        print(f"Looking up {company_name[:40]:40} (CUSIP: {cusip})... ", end='', flush=True)

        ticker = mapper.lookup(cusip, company_name)

        if ticker:
            # Update the security with the ticker
            cursor.execute('''
                UPDATE securities
                SET ticker = ?
                WHERE id = ?
            ''', (ticker, security_id))
            conn.commit()
            print(f"✓ {ticker}")
            successful += 1
        else:
            print("✗ Not found")
            failed += 1

        # Small delay between requests to be polite to the API
        time.sleep(0.1)

    conn.close()

    print("-" * 60)
    print(f"Results: {successful} successful, {failed} failed")

    # Check remaining
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM securities WHERE ticker IS NULL AND cusip IS NOT NULL')
    remaining = cursor.fetchone()[0]
    conn.close()

    print(f"Remaining securities without tickers: {remaining}")

    if remaining > 0:
        print(f"\nTo continue populating tickers:")
        print(f"  - Wait 1 hour (rate limit resets)")
        print(f"  - Run this script again: python backfill_tickers.py")
        print(f"  - Estimated time to complete: {(remaining // batch_size) + 1} hours")
    else:
        print("\n✓ All securities now have tickers!")

if __name__ == "__main__":
    backfill_tickers()
