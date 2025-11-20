"""
Data processing and transformation utilities.
"""

import json
import pandas as pd
from pathlib import Path
from datetime import datetime

from config.settings import RAW_DATA_DIR, PROCESSED_DATA_DIR
from utils.database import (
    init_database,
    insert_fund,
    insert_filing,
    insert_holdings,
    get_all_filings,
    get_holdings_for_filing,
    get_latest_filing
)


def load_funds_config():
    """Load fund configuration from JSON."""
    config_path = Path(__file__).parent.parent / "config" / "funds.json"
    with open(config_path) as f:
        return json.load(f)


def initialize_funds():
    """Initialize funds in database from config."""
    init_database()
    config = load_funds_config()

    for fund in config.get('funds', []):
        insert_fund({
            'id': fund['id'],
            'name': fund['name'],
            'cik': fund['cik'],
            'description': fund.get('description'),
            'benchmark': fund.get('benchmark'),
            'active': 1 if fund.get('active', True) else 0
        })
        print(f"Initialized fund: {fund['name']}")


def process_raw_filings(fund_id: str):
    """Process raw filing JSON files into database."""
    raw_files = list(RAW_DATA_DIR.glob(f"{fund_id}_*.json"))

    if not raw_files:
        print(f"No raw files found for {fund_id}")
        return

    for file_path in raw_files:
        print(f"Processing {file_path.name}...")

        with open(file_path) as f:
            data = json.load(f)

        filing_info = data.get('filing', {})
        holdings = data.get('holdings', [])

        # Calculate totals
        total_value = sum(h.get('value', 0) for h in holdings)
        num_holdings = len(holdings)

        # Insert filing
        filing_data = {
            'fund_id': fund_id,
            'accession_number': filing_info.get('accession_number'),
            'filing_date': filing_info.get('filing_date'),
            'report_date': filing_info.get('report_date'),
            'form_type': filing_info.get('form_type', '13F-HR'),
            'total_value': total_value,
            'num_holdings': num_holdings,
            'source': 'SEC EDGAR'
        }

        filing_id = insert_filing(filing_data)

        if filing_id:
            # Prepare holdings for insert
            processed_holdings = []
            for h in holdings:
                processed_holdings.append({
                    'cusip': h.get('cusip'),
                    'ticker': h.get('ticker'),
                    'company_name': h.get('company_name'),
                    'share_class': h.get('share_class'),
                    'shares': h.get('shares', 0),
                    'value': h.get('value', 0),
                    'option_type': h.get('option_type'),
                    'investment_discretion': h.get('investment_discretion'),
                    'voting_authority_sole': h.get('voting_authority_sole', 0),
                    'voting_authority_shared': h.get('voting_authority_shared', 0),
                    'voting_authority_none': h.get('voting_authority_none', 0)
                })

            insert_holdings(processed_holdings, filing_id)
            print(f"  Inserted {num_holdings} holdings for filing {filing_id}")


def get_portfolio_summary(fund_id: str) -> dict:
    """Get summary of current portfolio."""
    latest_filing = get_latest_filing(fund_id)

    if not latest_filing:
        return None

    holdings = get_holdings_for_filing(latest_filing['id'])

    # Convert to list of dicts
    holdings_list = [dict(h) for h in holdings]

    # Calculate summary stats
    total_value = sum(h['value'] for h in holdings_list)
    num_positions = len(holdings_list)

    # Top holdings
    top_holdings = sorted(holdings_list, key=lambda x: x['value'], reverse=True)[:10]

    return {
        'filing_date': latest_filing['filing_date'],
        'report_date': latest_filing['report_date'],
        'total_value': total_value,
        'num_positions': num_positions,
        'holdings': holdings_list,
        'top_holdings': top_holdings
    }


def get_holdings_dataframe(fund_id: str) -> pd.DataFrame:
    """Get holdings as a pandas DataFrame."""
    summary = get_portfolio_summary(fund_id)

    if not summary:
        return pd.DataFrame()

    df = pd.DataFrame(summary['holdings'])

    if df.empty:
        return pd.DataFrame()

    # Calculate weight
    total_value = summary['total_value']
    if total_value > 0:
        df['weight'] = (df['value'] / total_value * 100).round(2)
    else:
        df['weight'] = 0

    # Format value in millions
    df['value_millions'] = (df['value'] / 1_000_000).round(2)

    return df


def get_historical_filings_dataframe(fund_id: str) -> pd.DataFrame:
    """Get all filings as a DataFrame."""
    filings = get_all_filings(fund_id)

    if not filings:
        return pd.DataFrame()

    return pd.DataFrame([dict(f) for f in filings])


if __name__ == "__main__":
    # Initialize and process data
    initialize_funds()

    # Process any raw files
    process_raw_filings('baker-bros')

    # Get summary
    summary = get_portfolio_summary('baker-bros')
    if summary:
        print(f"\nPortfolio Summary:")
        print(f"  Report Date: {summary['report_date']}")
        print(f"  Total Value: ${summary['total_value']:,.0f}")
        print(f"  Positions: {summary['num_positions']}")
