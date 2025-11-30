"""
Unit tests for security_operations module.

Tests the Add New Security feature including:
- CUSIP to ticker resolution via OpenFIGI
- Ticker to CUSIP lookup from cache
- Adding securities to cache
"""

import sys
from pathlib import Path
import pytest

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utils.security_operations import (
    add_security_to_cache,
    ticker_to_cusip_from_cache,
    get_cusip_cache_summary
)


class TestSecurityOperations:
    """Test suite for security operations."""

    def test_add_by_cusip_only(self):
        """Test adding security by CUSIP only (should auto-resolve ticker)."""
        # This test requires OpenFIGI API access
        result = add_security_to_cache(cusip="037833100")

        assert result['success'] is True
        assert result['ticker'] == 'AAPL'
        assert result['cusip'] == '037833100'
        assert result['needs_cusip'] is False

    def test_add_by_ticker_not_in_cache(self):
        """Test adding ticker that's not in cache (should request CUSIP)."""
        # Use a ticker unlikely to be in cache
        result = add_security_to_cache(ticker="ZZZZ")

        assert result['success'] is False
        assert result['needs_cusip'] is True
        assert 'Please provide CUSIP manually' in result['message']

    def test_add_both_ticker_and_cusip(self):
        """Test adding with both ticker and CUSIP provided."""
        result = add_security_to_cache(ticker="GOOGL", cusip="02079K107")

        assert result['success'] is True
        assert result['ticker'] == 'GOOGL'
        assert result['cusip'] == '02079K107'
        assert result['needs_cusip'] is False

    def test_add_by_ticker_in_cache(self):
        """Test adding ticker that's already in cache."""
        # First add it
        add_security_to_cache(cusip="037833100")

        # Now try to add by ticker (should find in cache)
        result = add_security_to_cache(ticker="AAPL")

        assert result['success'] is True
        assert result['cusip'] == '037833100'

    def test_invalid_ticker_format(self):
        """Test that invalid ticker format is rejected."""
        result = add_security_to_cache(ticker="INVALID_TICKER_123")

        assert result['success'] is False
        assert 'Invalid ticker format' in result['message']

    def test_invalid_cusip_format(self):
        """Test that invalid CUSIP format is rejected."""
        result = add_security_to_cache(cusip="12345")  # Too short

        assert result['success'] is False
        assert 'Invalid CUSIP format' in result['message']

    def test_ticker_to_cusip_from_cache(self):
        """Test reverse lookup from cache."""
        # First add to cache
        add_security_to_cache(cusip="037833100")

        # Now test reverse lookup
        cusip = ticker_to_cusip_from_cache("AAPL")

        assert cusip == "037833100"

    def test_get_cache_summary(self):
        """Test cache summary function."""
        summary = get_cusip_cache_summary()

        assert 'total_entries' in summary
        assert 'recent_entries' in summary
        assert 'last_modified' in summary
        assert isinstance(summary['total_entries'], int)


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_no_inputs(self):
        """Test that function requires at least one input."""
        result = add_security_to_cache()

        assert result['success'] is False
        assert 'At least ticker or CUSIP required' in result['message']

    def test_whitespace_handling(self):
        """Test that whitespace is properly stripped."""
        result = add_security_to_cache(ticker="  AAPL  ", cusip="  037833100  ")

        assert result['success'] is True
        assert result['ticker'] == 'AAPL'
        assert result['cusip'] == '037833100'

    def test_lowercase_conversion(self):
        """Test that inputs are converted to uppercase."""
        result = add_security_to_cache(ticker="aapl", cusip="037833100")

        assert result['success'] is True
        assert result['ticker'] == 'AAPL'


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v"])
