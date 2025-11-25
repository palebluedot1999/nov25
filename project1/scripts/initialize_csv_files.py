"""
Initialize CSV data files from config.
Run this once to set up the CSV-based data structure.
"""

import json
import pandas as pd
from pathlib import Path

# Paths
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
FUNDS_CONFIG = PROJECT_ROOT / "config" / "funds.json"

# CSV files to create
PORTFOLIOS_FILE = DATA_DIR / "portfolios.csv"
STRATEGIES_FILE = DATA_DIR / "strategies.csv"
TAGS_FILE = DATA_DIR / "tags.csv"
TRANSACTIONS_FILE = DATA_DIR / "transactions.csv"


def load_funds_config():
    """Load funds configuration from JSON."""
    with open(FUNDS_CONFIG) as f:
        return json.load(f)


def initialize_portfolios():
    """Create portfolios.csv from funds.json."""
    print("Creating portfolios.csv...")

    funds_config = load_funds_config()
    portfolios_data = []

    for fund in funds_config.get('funds', []):
        # Add fund portfolio
        portfolios_data.append({
            'id': fund['id'],
            'name': fund['name'],
            'portfolio_type': 'fund',
            'cik': fund.get('cik', ''),
            'description': fund.get('description', ''),
            'benchmark': fund.get('benchmark', ''),
            'is_active': 1 if fund.get('active', True) else 0
        })

        # Add benchmark portfolio if specified
        if fund.get('benchmark'):
            benchmark_id = f"{fund['id']}-benchmark"
            portfolios_data.append({
                'id': benchmark_id,
                'name': f"{fund['benchmark']} Benchmark",
                'portfolio_type': 'benchmark',
                'cik': '',
                'description': f"Benchmark for {fund['name']}",
                'benchmark': fund['benchmark'],
                'is_active': 1
            })

    df = pd.DataFrame(portfolios_data)
    df.to_csv(PORTFOLIOS_FILE, index=False)
    print(f"  Created {PORTFOLIOS_FILE} with {len(df)} portfolios")


def initialize_strategies():
    """Create strategies.csv with default strategies."""
    print("Creating strategies.csv...")

    default_strategies = [
        {'code': 'LONG_EQUITY', 'name': 'Long Equity', 'description': 'Long equity position', 'category': 'Directional', 'is_active': 1},
        {'code': 'SHORT', 'name': 'Short', 'description': 'Short position', 'category': 'Directional', 'is_active': 1},
        {'code': 'MOMENTUM', 'name': 'Momentum', 'description': 'Momentum strategy', 'category': 'Factor', 'is_active': 1},
        {'code': 'VALUE', 'name': 'Value', 'description': 'Value investing', 'category': 'Factor', 'is_active': 1},
        {'code': 'EVENT_DRIVEN', 'name': 'Event Driven', 'description': 'Event driven strategy', 'category': 'Special Situations', 'is_active': 1},
        {'code': 'MEAN_REVERSION', 'name': 'Mean Reversion', 'description': 'Mean reversion strategy', 'category': 'Statistical', 'is_active': 1},
        {'code': 'PAIRS_TRADE', 'name': 'Pairs Trade', 'description': 'Pairs trading strategy', 'category': 'Statistical', 'is_active': 1},
    ]

    df = pd.DataFrame(default_strategies)
    df.to_csv(STRATEGIES_FILE, index=False)
    print(f"  Created {STRATEGIES_FILE} with {len(df)} strategies")


def initialize_tags():
    """Create empty tags.csv."""
    print("Creating tags.csv...")

    # Create empty file with header
    df = pd.DataFrame(columns=['name', 'tag_type', 'color', 'description'])
    df.to_csv(TAGS_FILE, index=False)
    print(f"  Created {TAGS_FILE} (empty)")


def initialize_transactions():
    """Create empty transactions.csv."""
    print("Creating transactions.csv...")

    # Create empty file with header
    columns = [
        'id', 'portfolio_id', 'ticker', 'cusip',
        'transaction_date', 'transaction_time', 'transaction_type',
        'quantity', 'price', 'fees', 'total_value',
        'strategy', 'source', 'filing_date', 'notes', 'created_at'
    ]
    df = pd.DataFrame(columns=columns)
    df.to_csv(TRANSACTIONS_FILE, index=False)
    print(f"  Created {TRANSACTIONS_FILE} (empty)")


def create_directories():
    """Create necessary data directories."""
    print("Creating data directories...")

    directories = [
        DATA_DIR,
        DATA_DIR / "holdings",
        DATA_DIR / "prices",
    ]

    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)
        print(f"  Created {directory}")


def main():
    """Initialize all CSV files."""
    print("=" * 60)
    print("Initializing CSV Data Files")
    print("=" * 60)
    print()

    # Create directories
    create_directories()
    print()

    # Initialize CSV files
    initialize_portfolios()
    initialize_strategies()
    initialize_tags()
    initialize_transactions()

    print()
    print("=" * 60)
    print("Initialization Complete!")
    print("=" * 60)
    print()
    print("Next steps:")
    print("1. Run: python scripts/backfill_historical_holdings.py")
    print("2. Then start the dashboard: streamlit run dashboard/app.py")


if __name__ == "__main__":
    main()
