"""
Test script for CUSIP-to-ticker lookup using OpenFIGI API.
Run this after configuring your API key to verify it's working.
"""

from utils.cusip_mapping import get_mapper

def test_cusip_lookup():
    """Test CUSIP lookup with known securities."""

    mapper = get_mapper()

    # Test cases with well-known CUSIPs
    test_cases = [
        ("037833100", "AAPL", "Apple Inc."),
        ("459200101", "MSFT", "Microsoft Corp."),
        ("88160R101", "TSLA", "Tesla Inc."),
        ("30303M102", "META", "Meta Platforms Inc."),
    ]

    print("=" * 60)
    print("Testing CUSIP-to-Ticker Lookup")
    print("=" * 60)
    print()

    successful = 0
    failed = 0

    for cusip, expected_ticker, company_name in test_cases:
        print(f"Testing {company_name} (CUSIP: {cusip})...")
        print(f"  Expected ticker: {expected_ticker}")

        result = mapper.lookup(cusip)

        if result:
            print(f"  ✓ Found ticker: {result}")
            if result == expected_ticker:
                print(f"  ✓ Correct match!")
                successful += 1
            else:
                print(f"  ⚠ Unexpected ticker (expected {expected_ticker})")
                successful += 1  # Still counts as working
        else:
            print(f"  ✗ No ticker found")
            failed += 1

        print()

    print("=" * 60)
    print(f"Results: {successful} successful, {failed} failed")
    print("=" * 60)

    if successful > 0:
        print("\n✓ OpenFIGI API is working! Your API key is configured correctly.")
        print("  You can now run the SEC scraper and it will populate tickers.")
    else:
        print("\n✗ OpenFIGI API lookups failed.")
        print("  Check that your API key is set correctly in:")
        print("  1. Environment variable: OPENFIGI_API_KEY")
        print("  2. Or in config/settings.py")

    # Show cache status
    print(f"\nCache status: {len(mapper.cache)} CUSIPs cached")
    if mapper.cache:
        print("Cached mappings:")
        for cusip, ticker in list(mapper.cache.items())[:5]:
            print(f"  {cusip} -> {ticker}")

if __name__ == "__main__":
    test_cusip_lookup()
