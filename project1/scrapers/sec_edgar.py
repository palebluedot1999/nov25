"""
SEC EDGAR scraper for 13F filings.
Updated to work with new database schema (portfolios, securities, holdings).
"""

import requests
import xml.etree.ElementTree as ET
import pandas as pd
import time
import re
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict

from config.settings import (
    SEC_EDGAR_API_URL,
    SEC_EDGAR_BASE_URL,
    SEC_USER_AGENT,
    RAW_DATA_DIR
)
from utils.cusip_mapping import cusip_to_ticker


class SECEdgarScraper:
    """Scraper for SEC EDGAR 13F filings."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': SEC_USER_AGENT,
            'Accept': 'application/json'
        })
        # SEC rate limit: max 10 requests per second
        self.request_delay = 0.1

    def _make_request(self, url: str) -> requests.Response:
        """Make a rate-limited request to SEC."""
        time.sleep(self.request_delay)
        response = self.session.get(url)
        response.raise_for_status()
        return response

    def get_company_filings(self, cik: str) -> dict:
        """Get all filings for a company by CIK."""
        # Pad CIK to 10 digits
        cik_padded = cik.zfill(10)
        url = f"{SEC_EDGAR_API_URL}/submissions/CIK{cik_padded}.json"

        response = self._make_request(url)
        return response.json()

    def get_13f_filings(self, cik: str, limit: int = None) -> list:
        """Get list of 13F filings for a company."""
        company_data = self.get_company_filings(cik)
        filings = company_data.get('filings', {}).get('recent', {})

        form_types = filings.get('form', [])
        accession_numbers = filings.get('accessionNumber', [])
        filing_dates = filings.get('filingDate', [])
        report_dates = filings.get('reportDate', [])
        primary_docs = filings.get('primaryDocument', [])

        results = []
        for i, form_type in enumerate(form_types):
            if '13F' in form_type:
                filing_info = {
                    'form_type': form_type,
                    'accession_number': accession_numbers[i],
                    'filing_date': filing_dates[i],
                    'report_date': report_dates[i],
                    'primary_document': primary_docs[i],
                    'cik': cik
                }
                results.append(filing_info)

                if limit and len(results) >= limit:
                    break

        return results

    def get_13f_holdings(self, cik: str, accession_number: str) -> list:
        """Parse holdings from a 13F information table."""
        # Format accession number for URL (remove dashes)
        acc_formatted = accession_number.replace('-', '')
        cik_padded = cik.zfill(10)

        # First, get the filing index to find the information table
        index_url = f"{SEC_EDGAR_BASE_URL}/Archives/edgar/data/{cik_padded}/{acc_formatted}/index.json"

        try:
            response = self._make_request(index_url)
            index_data = response.json()

            # Find the information table XML file
            info_table_file = None
            for item in index_data.get('directory', {}).get('item', []):
                name = item.get('name', '').lower()
                if 'infotable' in name and name.endswith('.xml'):
                    info_table_file = item.get('name')
                    break

            if not info_table_file:
                # Try alternative naming
                for item in index_data.get('directory', {}).get('item', []):
                    name = item.get('name', '').lower()
                    if name.endswith('.xml') and 'form13f' in name:
                        info_table_file = item.get('name')
                        break

            if not info_table_file:
                print(f"Could not find information table for {accession_number}")
                return []

            # Fetch the information table XML
            table_url = f"{SEC_EDGAR_BASE_URL}/Archives/edgar/data/{cik_padded}/{acc_formatted}/{info_table_file}"
            response = self._make_request(table_url)

            return self._parse_info_table(response.text)

        except Exception as e:
            print(f"Error fetching holdings for {accession_number}: {e}")
            return []

    def _parse_info_table(self, xml_content: str) -> list:
        """Parse the 13F information table XML."""
        holdings = []

        try:
            # Remove namespace prefixes and declarations for easier parsing
            # Remove all namespace declarations (xmlns:prefix="..." and xmlns="...")
            xml_content = re.sub(r' xmlns[:\w]*="[^"]*"', '', xml_content)
            # Remove namespace prefixes from attributes (e.g., xsi:schemaLocation -> schemaLocation)
            xml_content = re.sub(r'(\s)([a-zA-Z0-9]+):([a-zA-Z0-9]+)=', r'\1\3=', xml_content)
            # Remove namespace prefixes from tags (e.g., ns1:tag -> tag)
            xml_content = re.sub(r'<([a-zA-Z0-9]+):([a-zA-Z0-9]+)', r'<\2', xml_content)
            xml_content = re.sub(r'</([a-zA-Z0-9]+):([a-zA-Z0-9]+)', r'</\2', xml_content)

            root = ET.fromstring(xml_content)

            # Find all infoTable entries
            for ns_prefix in ['', '{http://www.sec.gov/edgar/document/thirteenf/informationtable}']:
                entries = root.findall(f'.//{ns_prefix}infoTable')
                if entries:
                    break

            if not entries:
                # Try without namespace
                entries = root.findall('.//infoTable')

            for entry in entries:
                holding = self._parse_holding_entry(entry)
                if holding:
                    holdings.append(holding)

        except ET.ParseError as e:
            print(f"XML parsing error: {e}")

        return holdings

    def _parse_holding_entry(self, entry) -> dict:
        """Parse a single holding entry from XML."""
        def get_text(element, tag):
            """Get text from child element, trying with and without namespace."""
            for ns_prefix in ['', '{http://www.sec.gov/edgar/document/thirteenf/informationtable}']:
                elem = element.find(f'{ns_prefix}{tag}')
                if elem is not None and elem.text:
                    return elem.text.strip()
            return None

        def get_nested_text(element, parent_tag, child_tag):
            """Get text from nested element."""
            for ns_prefix in ['', '{http://www.sec.gov/edgar/document/thirteenf/informationtable}']:
                parent = element.find(f'{ns_prefix}{parent_tag}')
                if parent is not None:
                    child = parent.find(f'{ns_prefix}{child_tag}')
                    if child is not None and child.text:
                        return child.text.strip()
            return None

        try:
            holding = {
                'company_name': get_text(entry, 'nameOfIssuer'),
                'share_class': get_text(entry, 'titleOfClass'),
                'cusip': get_text(entry, 'cusip'),
                'value': float(get_text(entry, 'value') or 0),  # Value already in correct scale
                'shares': float(get_nested_text(entry, 'shrsOrPrnAmt', 'sshPrnamt') or 0),
                'option_type': get_nested_text(entry, 'shrsOrPrnAmt', 'sshPrnamtType'),
                'investment_discretion': get_text(entry, 'investmentDiscretion'),
                'voting_authority_sole': float(get_nested_text(entry, 'votingAuthority', 'Sole') or 0),
                'voting_authority_shared': float(get_nested_text(entry, 'votingAuthority', 'Shared') or 0),
                'voting_authority_none': float(get_nested_text(entry, 'votingAuthority', 'None') or 0),
                'ticker': None  # Will be populated later via CUSIP lookup
            }

            return holding

        except Exception as e:
            print(f"Error parsing holding entry: {e}")
            return None

    def fetch_and_save_filings(self, cik: str, portfolio_id: str, limit: int = None,
                               start_date: str = None, save_to_csv: bool = True):
        """
        Fetch filings and save to CSV files.

        Args:
            cik: Company CIK number
            portfolio_id: Portfolio ID
            limit: Optional limit on number of filings to fetch (ignored if start_date provided)
            start_date: Optional start date filter (YYYY-MM-DD format) - fetches all filings since this date
            save_to_csv: Whether to save to CSV files (default True)

        Returns:
            List of filing metadata dicts
        """
        # Fetch all filings
        all_filings = self.get_13f_filings(cik, limit=None)

        # Filter by start_date if provided
        if start_date:
            all_filings = [f for f in all_filings if f['filing_date'] >= start_date]
            print(f"Found {len(all_filings)} filings since {start_date}")
        elif limit:
            all_filings = all_filings[:limit]

        if not save_to_csv:
            return all_filings

        # Create 13F filings directory
        holdings_dir = RAW_DATA_DIR / "13f_filings"
        holdings_dir.mkdir(parents=True, exist_ok=True)

        # Process each filing
        for filing in all_filings:
            print(f"\nFetching {filing['form_type']} from {filing['filing_date']}...")

            filing_date = filing['filing_date']
            period_end = filing['report_date']
            holdings = self.get_13f_holdings(cik, filing['accession_number'])

            if holdings:
                # Try to resolve tickers via CUSIP mapper for each holding
                for holding in holdings:
                    cusip = holding.get('cusip')
                    if cusip and not holding.get('ticker'):
                        ticker = cusip_to_ticker(cusip, holding.get('company_name'))
                        holding['ticker'] = ticker

                    # Add metadata to each holding row
                    holding['portfolio_id'] = portfolio_id
                    holding['filing_date'] = filing_date
                    holding['period_end_date'] = period_end

                # Save single CSV with all holdings
                filename = f"{portfolio_id}_{filing_date}_holdings.csv"
                holdings_csv = holdings_dir / filename
                holdings_df = pd.DataFrame(holdings)
                holdings_df.to_csv(holdings_csv, index=False)
                print(f"  Saved {len(holdings)} holdings to {filename}")
            else:
                print(f"  No holdings found for {filing['accession_number']}")

        return all_filings


def fetch_baker_bros_filings(limit: int = 5):
    """Convenience function to fetch Baker Bros filings."""
    scraper = SECEdgarScraper()
    return scraper.fetch_and_save_filings(
        cik='1263508',
        portfolio_id='baker-bros',
        limit=limit
    )


if __name__ == "__main__":
    # Test fetching Baker Bros filings
    fetch_baker_bros_filings(limit=3)
