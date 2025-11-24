"""
CUSIP to ticker mapping service.
Handles conversion between CUSIP identifiers and stock tickers.
"""

import requests
import json
import time
from typing import Optional, Dict
from pathlib import Path
from config.settings import DATA_DIR, SEC_USER_AGENT as USER_AGENT, OPENFIGI_API_KEY

# Cache file for CUSIP mappings
CACHE_FILE = DATA_DIR / "cusip_cache.csv"


class CUSIPMapper:
    """
    Service for mapping CUSIP identifiers to ticker symbols.
    Uses multiple strategies:
    1. Local cache (for previously resolved CUSIPs)
    2. SEC company tickers JSON (free, no API key needed)
    3. Yahoo Finance search (as fallback)
    """

    def __init__(self):
        self.cache = self._load_cache()
        self.sec_tickers_data = None

    def _load_cache(self) -> Dict[str, str]:
        """Load cached CUSIP to ticker mappings from CSV."""
        if CACHE_FILE.exists():
            try:
                cache = {}
                with open(CACHE_FILE, 'r') as f:
                    # Skip header
                    next(f, None)
                    for line in f:
                        line = line.strip()
                        if line:
                            cusip, ticker = line.split(',')
                            cache[cusip] = ticker
                return cache
            except Exception as e:
                print(f"Warning: Could not load CUSIP cache: {e}")
                return {}
        return {}

    def _save_cache(self):
        """Save cache to disk as CSV."""
        try:
            CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(CACHE_FILE, 'w') as f:
                f.write("cusip,ticker\n")
                for cusip, ticker in sorted(self.cache.items()):
                    f.write(f"{cusip},{ticker}\n")
        except Exception as e:
            print(f"Warning: Could not save CUSIP cache: {e}")

    def _fetch_sec_tickers(self) -> Dict:
        """
        Fetch SEC company tickers JSON file.
        Contains mapping of CIK to ticker, company name, and exchange.
        """
        if self.sec_tickers_data is not None:
            return self.sec_tickers_data

        try:
            url = "https://www.sec.gov/files/company_tickers.json"
            headers = {'User-Agent': USER_AGENT}
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()

            self.sec_tickers_data = response.json()
            return self.sec_tickers_data
        except Exception as e:
            print(f"Warning: Could not fetch SEC tickers data: {e}")
            return {}

    def _lookup_via_sec(self, cusip: str) -> Optional[str]:
        """
        Attempt to map CUSIP to ticker using SEC data.
        Note: SEC company_tickers.json doesn't directly have CUSIP,
        so this method has limited effectiveness.
        """
        # This is a placeholder - SEC's company_tickers.json doesn't
        # directly provide CUSIP mappings. We would need to use
        # SEC's submissions API for individual companies.
        return None

    def _lookup_via_openfigi(self, cusip: str) -> Optional[str]:
        """
        Lookup CUSIP via OpenFIGI API.
        Requires API key for production use, but has a free tier.
        https://www.openfigi.com/api
        """
        try:
            url = "https://api.openfigi.com/v3/mapping"
            headers = {
                'Content-Type': 'application/json',
            }

            # Add API key if configured
            if OPENFIGI_API_KEY:
                headers['X-OPENFIGI-APIKEY'] = OPENFIGI_API_KEY
            else:
                print(f"Warning: No OpenFIGI API key configured. Using unauthenticated requests (limited rate).")

            payload = [{
                "idType": "ID_CUSIP",
                "idValue": cusip,
                "exchCode": "US"
            }]

            response = requests.post(url, headers=headers, json=payload, timeout=10)
            response.raise_for_status()

            data = response.json()
            if data and len(data) > 0 and 'data' in data[0]:
                results = data[0]['data']
                if results and len(results) > 0:
                    ticker = results[0].get('ticker')
                    if ticker:
                        return ticker

            return None
        except Exception as e:
            print(f"Warning: OpenFIGI lookup failed for {cusip}: {e}")
            return None

    def _lookup_via_sec_lookup(self, cusip: str) -> Optional[str]:
        """
        Lookup CUSIP via SEC's EDGAR search.
        This is a best-effort approach using SEC's search endpoint.
        """
        try:
            # SEC EDGAR search by CUSIP
            # Note: This may not always work reliably
            url = f"https://www.sec.gov/cgi-bin/browse-edgar"
            params = {
                'action': 'getcompany',
                'CIK': cusip,
                'type': '',
                'dateb': '',
                'owner': 'exclude',
                'count': '1',
                'output': 'json'
            }
            headers = {'User-Agent': USER_AGENT}

            response = requests.get(url, params=params, headers=headers, timeout=10)
            # SEC doesn't return JSON for this endpoint in a useful way
            # This is a placeholder for future implementation
            return None
        except Exception as e:
            print(f"Warning: SEC lookup failed for {cusip}: {e}")
            return None

    def lookup(self, cusip: str, company_name: Optional[str] = None) -> Optional[str]:
        """
        Lookup ticker for a given CUSIP.

        Args:
            cusip: The CUSIP identifier (9 characters)
            company_name: Optional company name to help with matching

        Returns:
            Ticker symbol if found, None otherwise
        """
        if not cusip:
            return None

        # Normalize CUSIP (remove spaces, uppercase)
        cusip = cusip.strip().upper()

        # Check cache first
        if cusip in self.cache:
            return self.cache[cusip]

        # Try OpenFIGI (most reliable for CUSIP->ticker)
        ticker = self._lookup_via_openfigi(cusip)

        if ticker:
            # Cache successful lookup
            self.cache[cusip] = ticker
            self._save_cache()
            return ticker

        # If OpenFIGI fails and we have company name, we could try
        # other methods or manual mapping

        return None

    def bulk_lookup(self, cusips: list[str]) -> Dict[str, Optional[str]]:
        """
        Lookup multiple CUSIPs at once.
        Returns a dictionary mapping CUSIP to ticker.

        Args:
            cusips: List of CUSIP identifiers

        Returns:
            Dictionary of {cusip: ticker or None}
        """
        results = {}

        for i, cusip in enumerate(cusips):
            # Rate limiting: small delay between requests
            if i > 0 and i % 10 == 0:
                time.sleep(1)

            results[cusip] = self.lookup(cusip)

        return results

    def add_manual_mapping(self, cusip: str, ticker: str):
        """
        Manually add a CUSIP to ticker mapping to the cache.
        Useful for handling known mappings or corrections.

        Args:
            cusip: The CUSIP identifier
            ticker: The corresponding ticker symbol
        """
        cusip = cusip.strip().upper()
        ticker = ticker.strip().upper()

        self.cache[cusip] = ticker
        self._save_cache()
        print(f"Added manual mapping: {cusip} -> {ticker}")

    def load_manual_mappings(self, mappings: Dict[str, str]):
        """
        Load multiple manual mappings at once.

        Args:
            mappings: Dictionary of {cusip: ticker}
        """
        for cusip, ticker in mappings.items():
            cusip = cusip.strip().upper()
            ticker = ticker.strip().upper()
            self.cache[cusip] = ticker

        self._save_cache()
        print(f"Loaded {len(mappings)} manual mappings")


# Global instance
_mapper = None


def get_mapper() -> CUSIPMapper:
    """Get the global CUSIP mapper instance."""
    global _mapper
    if _mapper is None:
        _mapper = CUSIPMapper()
    return _mapper


def cusip_to_ticker(cusip: str, company_name: Optional[str] = None) -> Optional[str]:
    """
    Convenience function to lookup a single CUSIP.

    Args:
        cusip: The CUSIP identifier
        company_name: Optional company name for better matching

    Returns:
        Ticker symbol if found, None otherwise
    """
    mapper = get_mapper()
    return mapper.lookup(cusip, company_name)


def ticker_to_cusip_fallback(ticker: str) -> Optional[str]:
    """
    Reverse lookup: ticker to CUSIP.
    This is less common but can be useful.
    Uses the cache only (no external API).

    Args:
        ticker: Stock ticker symbol

    Returns:
        CUSIP if found in cache, None otherwise
    """
    mapper = get_mapper()
    ticker = ticker.strip().upper()

    # Search cache in reverse
    for cusip, cached_ticker in mapper.cache.items():
        if cached_ticker == ticker:
            return cusip

    return None


if __name__ == "__main__":
    # Example usage
    mapper = get_mapper()

    # Test with a known CUSIP (Apple Inc.)
    apple_cusip = "037833100"
    ticker = mapper.lookup(apple_cusip)
    print(f"CUSIP {apple_cusip} maps to ticker: {ticker}")

    # Example of adding manual mapping
    # mapper.add_manual_mapping("000000000", "TEST")
