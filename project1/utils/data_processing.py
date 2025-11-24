"""
Data processing and transformation utilities.
Updated to work with new database schema (portfolios, securities, holdings).
"""

import json
import pandas as pd
from pathlib import Path
from datetime import datetime
from typing import Optional

from config.settings import RAW_DATA_DIR, PROCESSED_DATA_DIR
from utils.database import (
    init_database,
    insert_portfolio,
    insert_filing,
    insert_holding,
    insert_security,
    get_all_filings,
    get_holdings,
    get_holdings_for_filing,
    get_latest_filing,
    get_portfolio,
    get_security_by_cusip
)


def load_funds_config():
    """Load fund configuration from JSON."""
    config_path = Path(__file__).parent.parent / "config" / "funds.json"
    with open(config_path) as f:
        return json.load(f)


def initialize_portfolios():
    """
    Initialize portfolios in database from config.
    Converts funds.json to portfolios table.
    """
    init_database()
    config = load_funds_config()

    for fund in config.get('funds', []):
        # Convert fund to portfolio
        portfolio_data = {
            'id': fund['id'],
            'name': fund['name'],
            'portfolio_type': 'fund',  # Mark as hedge fund type
            'cik': fund['cik'],
            'description': fund.get('description'),
            'benchmark_id': None,  # Can be set later
            'is_active': 1 if fund.get('active', True) else 0
        }
        insert_portfolio(portfolio_data)
        print(f"Initialized portfolio: {fund['name']}")

        # Also create benchmark portfolio if specified
        benchmark = fund.get('benchmark')
        if benchmark:
            benchmark_id = f"{fund['id']}-benchmark-{benchmark.lower()}"
            benchmark_data = {
                'id': benchmark_id,
                'name': f"{benchmark} (Benchmark for {fund['name']})",
                'portfolio_type': 'benchmark',
                'cik': None,
                'description': f"Benchmark index for {fund['name']}",
                'benchmark_id': None,
                'is_active': 1
            }
            insert_portfolio(benchmark_data)
            print(f"  Created benchmark portfolio: {benchmark}")

            # Update fund portfolio to link to benchmark
            portfolio_data['benchmark_id'] = benchmark_id
            insert_portfolio(portfolio_data)


def process_raw_filings(portfolio_id: str):
    """
    Process raw filing CSV files into database.
    Handles conversion to new schema with securities and holdings.

    Args:
        portfolio_id: Portfolio ID to process filings for
    """
    raw_files = list(RAW_DATA_DIR.glob(f"{portfolio_id}_*_filing.csv"))

    if not raw_files:
        print(f"No raw filing files found for {portfolio_id}")
        return

    for file_path in raw_files:
        print(f"Processing {file_path.name}...")

        # Read filing metadata
        filing_df = pd.read_csv(file_path)
        filing_info = filing_df.iloc[0].to_dict()

        # Read holdings (if holdings file exists)
        holdings_file = file_path.parent / file_path.name.replace('_filing.csv', '_holdings.csv')
        if holdings_file.exists():
            holdings_df = pd.read_csv(holdings_file)
            holdings_data = holdings_df.to_dict('records')
        else:
            holdings_data = []

        # Calculate totals
        total_value = sum(h.get('value', 0) for h in holdings_data)
        num_positions = len(holdings_data)

        # Insert filing
        filing_data = {
            'portfolio_id': portfolio_id,
            'accession_number': filing_info.get('accession_number'),
            'filing_date': filing_info.get('filing_date'),
            'report_date': filing_info.get('report_date'),
            'form_type': filing_info.get('form_type', '13F-HR'),
            'total_value': total_value,
            'num_positions': num_positions,
            'source': 'SEC EDGAR'
        }

        filing_id = insert_filing(filing_data)

        if filing_id:
            # Process each holding
            for h in holdings_data:
                cusip = h.get('cusip')
                if not cusip:
                    continue

                # Get or create security
                security = get_security_by_cusip(cusip)
                if not security:
                    security_data = {
                        'cusip': cusip,
                        'ticker': h.get('ticker'),
                        'company_name': h.get('company_name', ''),
                        'share_class': h.get('share_class'),
                        'asset_class': 'stock',
                        'sector': None,
                        'industry': None,
                        'exchange': None,
                        'is_active': 1
                    }
                    security_id = insert_security(security_data)
                else:
                    security_id = security['id']

                # Insert holding
                holding_data = {
                    'portfolio_id': portfolio_id,
                    'security_id': security_id,
                    'as_of_date': filing_info.get('report_date'),
                    'shares': h.get('shares', 0),
                    'cost_basis': None,
                    'market_value': h.get('value', 0),
                    'filing_id': filing_id,
                    'source': '13F'
                }
                insert_holding(holding_data)

            print(f"  Inserted {num_positions} holdings for filing {filing_id}")


def get_portfolio_summary(portfolio_id: str) -> Optional[dict]:
    """
    Get summary of current portfolio.

    Args:
        portfolio_id: Portfolio ID to get summary for

    Returns:
        Dictionary with portfolio summary or None if no data
    """
    latest_filing = get_latest_filing(portfolio_id)

    if not latest_filing:
        return None

    # Get holdings for this filing
    holdings = get_holdings_for_filing(latest_filing['id'])

    if not holdings:
        # Return empty summary with filing metadata
        return {
            'filing_date': latest_filing['filing_date'],
            'report_date': latest_filing['report_date'],
            'total_value': 0,
            'num_positions': 0,
            'holdings': [],
            'top_holdings': []
        }

    # Convert to list of dicts
    holdings_list = [dict(h) for h in holdings]

    # Calculate summary stats
    total_value = sum(h['market_value'] for h in holdings_list)
    num_positions = len(holdings_list)

    # Top holdings (by market value)
    top_holdings = sorted(holdings_list, key=lambda x: x['market_value'], reverse=True)[:10]

    return {
        'filing_date': latest_filing['filing_date'],
        'report_date': latest_filing['report_date'],
        'total_value': total_value,
        'num_positions': num_positions,
        'holdings': holdings_list,
        'top_holdings': top_holdings
    }


def get_holdings_dataframe(portfolio_id: str, as_of_date: Optional[str] = None) -> pd.DataFrame:
    """
    Get holdings as a pandas DataFrame.
    Fixed to handle empty holdings gracefully.

    Args:
        portfolio_id: Portfolio ID to get holdings for
        as_of_date: Optional date to get holdings as of (default: latest)

    Returns:
        DataFrame with holdings data (empty if no holdings)
    """
    if as_of_date:
        holdings = get_holdings(portfolio_id, as_of_date)
    else:
        summary = get_portfolio_summary(portfolio_id)
        if not summary or not summary.get('holdings'):
            return pd.DataFrame()
        holdings = summary['holdings']

    if not holdings:
        return pd.DataFrame()

    df = pd.DataFrame([dict(h) for h in holdings])

    if df.empty:
        return pd.DataFrame()

    # Calculate weight
    total_value = df['market_value'].sum()
    if total_value > 0:
        df['weight'] = (df['market_value'] / total_value * 100).round(2)
    else:
        df['weight'] = 0

    # Format value in millions
    df['value_millions'] = (df['market_value'] / 1_000_000).round(2)

    # Rename for display
    df = df.rename(columns={'market_value': 'value'})

    return df


def get_historical_filings_dataframe(portfolio_id: str) -> pd.DataFrame:
    """Get all filings as a DataFrame."""
    filings = get_all_filings(portfolio_id)

    if not filings:
        return pd.DataFrame()

    return pd.DataFrame([dict(f) for f in filings])


def get_portfolio_info(portfolio_id: str) -> Optional[dict]:
    """
    Get portfolio metadata.

    Args:
        portfolio_id: Portfolio ID

    Returns:
        Dictionary with portfolio info or None
    """
    portfolio = get_portfolio(portfolio_id)
    if not portfolio:
        return None

    return dict(portfolio)


if __name__ == "__main__":
    # Initialize and process data
    initialize_portfolios()

    # Process any raw files
    process_raw_filings('baker-bros')

    # Get summary
    summary = get_portfolio_summary('baker-bros')
    if summary:
        print(f"\nPortfolio Summary:")
        print(f"  Report Date: {summary['report_date']}")
        print(f"  Total Value: ${summary['total_value']:,.0f}")
        print(f"  Positions: {summary['num_positions']}")
