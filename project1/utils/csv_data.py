"""
CSV-based data layer for portfolio tracking.
Replaces database.py with simple CSV file operations.
"""

import pandas as pd
from pathlib import Path
from typing import Optional, List, Dict
from datetime import datetime

from utils.security_reference import enrich_holdings_with_reference

# Paths
DATA_DIR = Path(__file__).parent.parent / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"
HOLDINGS_DIR = RAW_DATA_DIR / "13f_filings"
PRICES_DIR = RAW_DATA_DIR / "yahoo_prices"
PROCESSED_HOLDINGS_FILE = PROCESSED_DATA_DIR / "holdings.csv"
PORTFOLIOS_FILE = RAW_DATA_DIR / "portfolios.csv"
STRATEGIES_FILE = RAW_DATA_DIR / "strategies.csv"
TAGS_FILE = RAW_DATA_DIR / "tags.csv"
TRANSACTIONS_FILE = RAW_DATA_DIR / "transactions.csv"

# ============================================================================
# PORTFOLIOS
# ============================================================================

def load_portfolios(portfolio_type: Optional[str] = None) -> pd.DataFrame:
    """
    Load portfolios from CSV.

    Args:
        portfolio_type: Filter by type ('fund', 'user', 'benchmark') or None for all

    Returns:
        DataFrame with portfolio data
    """
    if not PORTFOLIOS_FILE.exists():
        return pd.DataFrame()

    df = pd.read_csv(PORTFOLIOS_FILE)

    if portfolio_type:
        df = df[df['portfolio_type'] == portfolio_type]

    return df[df['is_active'] == 1]


def get_portfolio(portfolio_id: str) -> Optional[Dict]:
    """Get single portfolio by ID."""
    df = load_portfolios()
    portfolio = df[df['id'] == portfolio_id]

    if portfolio.empty:
        return None

    return portfolio.iloc[0].to_dict()


def get_all_portfolios(portfolio_type: Optional[str] = None) -> List[Dict]:
    """
    Get all portfolios as list of dicts (for compatibility with old database API).

    Args:
        portfolio_type: Filter by type ('fund', 'user', 'benchmark') or None for all

    Returns:
        List of portfolio dictionaries
    """
    df = load_portfolios(portfolio_type)
    return df.to_dict('records')


# ============================================================================
# HOLDINGS
# ============================================================================

def get_holdings_files(portfolio_id: str) -> List[Path]:
    """
    Get all holdings CSV files for a portfolio, sorted by filing date (newest first).

    Args:
        portfolio_id: Portfolio ID

    Returns:
        List of Path objects sorted by filing date descending
    """
    if not HOLDINGS_DIR.exists():
        return []

    pattern = f"{portfolio_id}_*_holdings.csv"
    files = list(HOLDINGS_DIR.glob(pattern))

    # Sort by filing date extracted from filename
    # Format: baker-bros_2025-11-14_holdings.csv
    def extract_date(path):
        parts = path.stem.split('_')
        if len(parts) >= 2:
            return parts[1]  # YYYY-MM-DD
        return "1970-01-01"

    files.sort(key=extract_date, reverse=True)
    return files


def load_latest_holdings(portfolio_id: str) -> pd.DataFrame:
    """
    Load most recent holdings for a portfolio.

    Returns:
        DataFrame with latest holdings, including calculated weight and value_millions
    """
    files = get_holdings_files(portfolio_id)

    if not files:
        return pd.DataFrame()

    latest_file = files[0]
    df = pd.read_csv(latest_file)

    if df.empty:
        return df

    # Calculate weight
    total_value = df['value'].sum()
    if total_value > 0:
        df['weight'] = (df['value'] / total_value * 100).round(2)
    else:
        df['weight'] = 0.0

    df['value_millions'] = (df['value'] / 1_000_000).round(2)

    return df


def load_holdings_by_date(portfolio_id: str, filing_date: str) -> pd.DataFrame:
    """
    Load holdings for a specific filing date.

    Args:
        portfolio_id: Portfolio ID
        filing_date: Filing date (YYYY-MM-DD)

    Returns:
        DataFrame with holdings for that date
    """
    filename = f"{portfolio_id}_{filing_date}_holdings.csv"
    filepath = HOLDINGS_DIR / filename

    if not filepath.exists():
        return pd.DataFrame()

    df = pd.read_csv(filepath)

    if not df.empty:
        df = enrich_holdings_with_reference(df)

    # Calculate weight and value_millions
    if not df.empty:
        total_value = df['value'].sum()
        if total_value > 0:
            df['weight'] = (df['value'] / total_value * 100).round(2)
        else:
            df['weight'] = 0.0
        df['value_millions'] = (df['value'] / 1_000_000).round(2)

    return df


def load_qoq_changes(portfolio_id: str, filing_date: Optional[str] = None) -> pd.DataFrame:
    """
    Load pre-computed QoQ changes from processed/qoq_changes.csv.

    Args:
        portfolio_id: Portfolio ID to filter by
        filing_date: Optional filing date (YYYY-MM-DD) to filter to a single period

    Returns:
        DataFrame with QoQ metrics (empty if file not found or no data)
    """
    qoq_path = PROCESSED_DATA_DIR / "qoq_changes.csv"
    if not qoq_path.exists():
        return pd.DataFrame()
    df = pd.read_csv(qoq_path)
    df = df[df["portfolio_id"] == portfolio_id]
    if filing_date:
        df = df[df["filing_date"] == filing_date]
    return df.reset_index(drop=True)


def load_processed_holdings(portfolio_id: str, start_date: Optional[str] = None) -> pd.DataFrame:
    """
    Load consolidated daily holdings from processed/holdings.csv.

    This function loads the daily holdings table that has been generated
    by the consolidation script (scripts/consolidate_holdings.py).

    Args:
        portfolio_id: Portfolio ID to filter by
        start_date: Optional start date (YYYY-MM-DD) to filter from

    Returns:
        DataFrame with columns: portfolio, cusip, ticker, shares, filing_value, eod_date,
        plus name and resolution_status left-joined from security_reference.csv.
        Degrades gracefully when security_reference.csv is absent: name is present but
        empty and resolution_status is "unresolved" (never raises).
    """
    if not PROCESSED_HOLDINGS_FILE.exists():
        return pd.DataFrame()

    df = pd.read_csv(PROCESSED_HOLDINGS_FILE)

    # Filter by portfolio
    df = df[df['portfolio'] == portfolio_id]

    # Filter by start date if provided
    if start_date:
        df = df[df['eod_date'] >= start_date]

    if not df.empty:
        df = enrich_holdings_with_reference(df)

    return df


def get_all_filings(portfolio_id: str) -> pd.DataFrame:
    """
    Get metadata for all filings (filing dates and period ends).

    Returns:
        DataFrame with columns: filing_date, period_end_date, total_value, num_positions
    """
    files = get_holdings_files(portfolio_id)

    filings_list = []
    for file in files:
        df = pd.read_csv(file)
        if not df.empty:
            filing_data = {
                'filing_date': df['filing_date'].iloc[0],
                'period_end_date': df['period_end_date'].iloc[0],
                'total_value': df['value'].sum(),
                'num_positions': len(df)
            }
            filings_list.append(filing_data)

    return pd.DataFrame(filings_list)


# ============================================================================
# PRICES
# ============================================================================

def load_prices(ticker: str, start_date: Optional[str] = None) -> pd.DataFrame:
    """
    Load price history for a ticker.

    Args:
        ticker: Stock ticker
        start_date: Optional start date filter (YYYY-MM-DD)

    Returns:
        DataFrame with price history
    """
    if not PRICES_DIR.exists():
        return pd.DataFrame()

    filepath = PRICES_DIR / f"{ticker}.csv"

    if not filepath.exists():
        return pd.DataFrame()

    df = pd.read_csv(filepath)
    df['date'] = pd.to_datetime(df['date'])

    if start_date:
        df = df[df['date'] >= start_date]

    return df.sort_values('date')


def save_prices(ticker: str, prices_df: pd.DataFrame):
    """
    Save or update price data for a ticker.

    Merges with existing data, updating duplicates and adding new rows.

    Args:
        ticker: Stock ticker
        prices_df: DataFrame with columns: date, open, high, low, close, adj_close, volume
    """
    PRICES_DIR.mkdir(parents=True, exist_ok=True)
    filepath = PRICES_DIR / f"{ticker}.csv"

    # Add ticker column and fetched_at
    prices_df = prices_df.copy()
    prices_df['ticker'] = ticker
    prices_df['fetched_at'] = datetime.now().isoformat()

    # Load existing if present
    if filepath.exists():
        existing = pd.read_csv(filepath)
        existing['date'] = pd.to_datetime(existing['date'])
        prices_df['date'] = pd.to_datetime(prices_df['date'])

        # Merge: update existing dates, add new dates
        combined = pd.concat([existing, prices_df])
        combined = combined.drop_duplicates(subset=['ticker', 'date'], keep='last')
        combined = combined.sort_values('date')
    else:
        combined = prices_df

    combined.to_csv(filepath, index=False)


def get_missing_price_dates(ticker: str, start_date: str = "2025-01-01") -> List[str]:
    """
    Get list of dates missing price data since start_date.

    Returns:
        List of date strings (YYYY-MM-DD) with missing data
    """
    existing = load_prices(ticker, start_date)

    if existing.empty:
        # All dates missing
        start = datetime.strptime(start_date, '%Y-%m-%d')
        today = datetime.now()
        all_dates = pd.date_range(start, today, freq='D')
        return [d.strftime('%Y-%m-%d') for d in all_dates]

    # Find gaps
    existing_dates = set(existing['date'].dt.strftime('%Y-%m-%d'))
    start = datetime.strptime(start_date, '%Y-%m-%d')
    today = datetime.now()
    all_dates = pd.date_range(start, today, freq='D')
    all_date_strs = set(d.strftime('%Y-%m-%d') for d in all_dates)

    missing = all_date_strs - existing_dates
    return sorted(list(missing))


# ============================================================================
# TRANSACTIONS
# ============================================================================

def load_transactions(portfolio_id: Optional[str] = None) -> pd.DataFrame:
    """
    Load transactions from CSV.

    Args:
        portfolio_id: Optional filter by portfolio

    Returns:
        DataFrame with transactions
    """
    if not TRANSACTIONS_FILE.exists():
        return pd.DataFrame()

    df = pd.read_csv(TRANSACTIONS_FILE)

    if portfolio_id:
        df = df[df['portfolio_id'] == portfolio_id]

    return df.sort_values(['transaction_date', 'transaction_time'], ascending=False)


def add_transaction(transaction_data: Dict) -> int:
    """
    Add a transaction to CSV.

    Args:
        transaction_data: Dict with transaction fields

    Returns:
        New transaction ID
    """
    TRANSACTIONS_FILE.parent.mkdir(parents=True, exist_ok=True)

    # Load existing or create new
    if TRANSACTIONS_FILE.exists():
        df = pd.read_csv(TRANSACTIONS_FILE)
        new_id = int(df['id'].max() + 1) if not df.empty else 1
    else:
        df = pd.DataFrame()
        new_id = 1

    # Add ID and timestamp
    transaction_data['id'] = new_id
    transaction_data['created_at'] = datetime.now().isoformat()

    # Append
    new_row = pd.DataFrame([transaction_data])
    df = pd.concat([df, new_row], ignore_index=True)

    df.to_csv(TRANSACTIONS_FILE, index=False)
    return new_id


def delete_transaction(transaction_id: int):
    """Delete a transaction by ID."""
    if not TRANSACTIONS_FILE.exists():
        return

    df = pd.read_csv(TRANSACTIONS_FILE)
    df = df[df['id'] != transaction_id]
    df.to_csv(TRANSACTIONS_FILE, index=False)


def get_transactions(portfolio_id: Optional[str] = None) -> List[Dict]:
    """
    Get transactions as list of dicts (for compatibility with old database API).

    Args:
        portfolio_id: Optional filter by portfolio

    Returns:
        List of transaction dictionaries
    """
    df = load_transactions(portfolio_id)
    return df.to_dict('records')


# ============================================================================
# STRATEGIES & TAGS
# ============================================================================

def load_strategies() -> pd.DataFrame:
    """Load strategies from CSV."""
    if not STRATEGIES_FILE.exists():
        return pd.DataFrame()

    df = pd.read_csv(STRATEGIES_FILE)
    return df[df['is_active'] == 1]


def get_all_strategies() -> List[Dict]:
    """
    Get all strategies as list of dicts (for compatibility with old database API).

    Returns:
        List of strategy dictionaries
    """
    df = load_strategies()
    return df.to_dict('records')


def load_tags(tag_type: Optional[str] = None) -> pd.DataFrame:
    """Load tags from CSV."""
    if not TAGS_FILE.exists():
        return pd.DataFrame()

    df = pd.read_csv(TAGS_FILE)

    if tag_type:
        df = df[df['tag_type'] == tag_type]

    return df
