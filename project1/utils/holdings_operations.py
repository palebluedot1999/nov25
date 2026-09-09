"""
Holdings processing utilities for portfolio size estimation.

This module processes quarterly 13F filings into daily holdings records,
joins with price data, and calculates position values.
"""

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
import logging

from utils.security_reference import enrich_holdings_with_reference

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# File paths
PROJECT_ROOT = Path(__file__).parent.parent
CUSIP_CACHE_FILE = PROJECT_ROOT / "data" / "raw" / "cusip_cache.csv"
FILINGS_DIR = PROJECT_ROOT / "data" / "raw" / "13f_filings"
PRICES_FILE = PROJECT_ROOT / "data" / "processed" / "prices.csv"


def resolve_tickers_from_reference(holdings_df: pd.DataFrame) -> pd.DataFrame:
    """
    Fill blank tickers and add name/resolution_status from security_reference.csv.

    Args:
        holdings_df: DataFrame with 'ticker' and 'cusip' columns

    Returns:
        DataFrame with blank tickers filled where possible (blank ticker stays "",
        never NaN) plus 'name' and 'resolution_status' columns.
    """
    return enrich_holdings_with_reference(holdings_df)


def detect_position_exits(current_filing_df: pd.DataFrame, next_filing_df: pd.DataFrame) -> List[str]:
    """
    Detect positions that exited between two consecutive filings.

    Args:
        current_filing_df: Holdings from filing N
        next_filing_df: Holdings from filing N+1

    Returns:
        List of CUSIPs that appear in current but not in next filing
    """
    current_cusips = set(current_filing_df['cusip'].dropna())
    next_cusips = set(next_filing_df['cusip'].dropna())

    exited_cusips = current_cusips - next_cusips

    if exited_cusips:
        logger.info(f"Detected {len(exited_cusips)} position exits: {sorted(exited_cusips)[:10]}...")

    return list(exited_cusips)


def process_quarterly_filings_to_daily_holdings(
    portfolio_id: str,
    start_date: str = "2020-12-31",
    end_date: Optional[str] = None
) -> pd.DataFrame:
    """
    Process quarterly 13F filings into daily holdings records.

    Logic:
    1. Load all 13F filing CSVs for portfolio
    2. Sort by period_end_date ascending
    3. For each filing:
        - Fill blank tickers from security_reference.csv (positions with no
          ticker are still kept, keyed by CUSIP)
        - Determine date range (period_end → next_period_end - 1 day)
        - Create daily records for all dates in range
        - For positions that exited: add shares=0 record on next period_end
    4. Concatenate all daily records

    Args:
        portfolio_id: Portfolio identifier (e.g., 'baker-bros')
        start_date: Start date for holdings (YYYY-MM-DD)
        end_date: End date for holdings (defaults to today)

    Returns:
        DataFrame with columns: portfolio, cusip, ticker, shares, filing_value, eod_date
    """
    logger.info(f"Processing {portfolio_id} filings to daily holdings...")

    # Default end_date to today
    if end_date is None:
        end_date = datetime.now().strftime('%Y-%m-%d')

    # Load all filing CSVs for this portfolio
    filing_files = sorted(FILINGS_DIR.glob(f"{portfolio_id}_*_holdings.csv"))

    if not filing_files:
        raise ValueError(f"No filing files found for portfolio: {portfolio_id}")

    logger.info(f"Found {len(filing_files)} filing files")

    # Load all filings
    filings = []
    for file in filing_files:
        df = pd.read_csv(file)
        df = resolve_tickers_from_reference(df)
        filings.append(df)

    # Sort by period_end_date
    filings = sorted(filings, key=lambda df: df['period_end_date'].iloc[0])

    # Process each filing to create daily holdings
    all_daily_holdings = []

    for i, filing_df in enumerate(filings):
        period_end = filing_df['period_end_date'].iloc[0]
        filing_date = filing_df['filing_date'].iloc[0]

        # Determine date range for this filing
        if i < len(filings) - 1:
            # Not the last filing - forward-fill until day before next period_end
            next_period_end = filings[i + 1]['period_end_date'].iloc[0]
            next_date = pd.to_datetime(next_period_end)
            range_end = (next_date - timedelta(days=1)).strftime('%Y-%m-%d')
        else:
            # Last filing - forward-fill through end_date
            range_end = end_date

        # Only process if period_end is within our date range
        if period_end < start_date:
            continue

        range_start = max(period_end, start_date)

        logger.info(f"Filing {i+1}/{len(filings)}: {period_end} (filing_date: {filing_date})")
        logger.info(f"  Forward-filling {len(filing_df)} positions from {range_start} to {range_end}")

        # Keep every position; unresolved ones carry a blank ticker + their filing value.
        valid_holdings = filing_df.copy()
        valid_holdings['ticker'] = valid_holdings['ticker'].fillna('').astype(str)
        unresolved = int((valid_holdings['ticker'] == '').sum())
        if unresolved:
            logger.info(f"  {unresolved} positions have no ticker yet (kept, keyed by CUSIP)")

        # Create date range
        date_range = pd.date_range(start=range_start, end=range_end, freq='D')

        # Create daily records for each position
        daily_records = []
        for _, row in valid_holdings.iterrows():
            ticker_df = pd.DataFrame({
                'portfolio': portfolio_id,
                'ticker': row['ticker'],
                'cusip': row['cusip'],
                'shares': row['shares'],
                'filing_value': row['value'],
                'eod_date': date_range
            })
            daily_records.append(ticker_df)

        if daily_records:
            filing_daily = pd.concat(daily_records, ignore_index=True)
            all_daily_holdings.append(filing_daily)

        # Detect position exits and add shares=0 records on next period_end
        if i < len(filings) - 1:
            next_filing_df = filings[i + 1]
            exited_cusips = detect_position_exits(valid_holdings, next_filing_df)

            if exited_cusips:
                next_period_end = next_filing_df['period_end_date'].iloc[0]

                # Create shares=0 records for exited positions
                exit_records = []
                for exited_cusip in exited_cusips:
                    exit_df = pd.DataFrame({
                        'portfolio': [portfolio_id],
                        'ticker': [''],
                        'cusip': [exited_cusip],
                        'shares': [0.0],
                        'filing_value': [0.0],
                        'eod_date': [pd.to_datetime(next_period_end)]
                    })
                    exit_records.append(exit_df)

                if exit_records:
                    exits_daily = pd.concat(exit_records, ignore_index=True)
                    all_daily_holdings.append(exits_daily)
                    logger.info(f"  Added {len(exit_records)} position exit records on {next_period_end}")

    # Concatenate all daily holdings
    if not all_daily_holdings:
        raise ValueError(f"No daily holdings generated for {portfolio_id}")

    holdings_df = pd.concat(all_daily_holdings, ignore_index=True)

    # Convert eod_date to string format (YYYY-MM-DD)
    holdings_df['eod_date'] = pd.to_datetime(holdings_df['eod_date']).dt.strftime('%Y-%m-%d')

    # Sort by date and ticker for efficient queries
    holdings_df = holdings_df.sort_values(['eod_date', 'ticker']).reset_index(drop=True)

    logger.info(f"Generated {len(holdings_df):,} daily holdings records")
    logger.info(f"  Date range: {holdings_df['eod_date'].min()} to {holdings_df['eod_date'].max()}")
    logger.info(f"  Unique tickers: {holdings_df['ticker'].nunique()}")

    return holdings_df


def get_forward_filled_prices(
    start_date: str = "2020-12-31",
    end_date: Optional[str] = None
) -> pd.DataFrame:
    """
    Load processed prices and forward-fill to cover all calendar days.

    Logic:
    1. Load data/processed/prices.csv
    2. Create complete date range (start_date → end_date, all days)
    3. For each ticker:
        - Create full date range DataFrame
        - Merge with existing prices (left join)
        - Forward-fill close price to cover gaps

    Args:
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (defaults to today)

    Returns:
        DataFrame with columns: ticker, date, close (forward-filled)
    """
    logger.info(f"Loading and forward-filling prices...")

    # Default end_date to today
    if end_date is None:
        end_date = datetime.now().strftime('%Y-%m-%d')

    # Load prices
    if not PRICES_FILE.exists():
        raise FileNotFoundError(f"Prices file not found: {PRICES_FILE}")

    prices_df = pd.read_csv(PRICES_FILE)
    prices_df['date'] = pd.to_datetime(prices_df['date'])

    # Create complete date range (all calendar days)
    full_date_range = pd.date_range(start=start_date, end=end_date, freq='D')

    logger.info(f"  Date range: {start_date} to {end_date} ({len(full_date_range)} days)")
    logger.info(f"  Tickers: {prices_df['ticker'].nunique()}")

    # Forward-fill prices for each ticker
    filled_prices = []
    tickers = prices_df['ticker'].unique()

    for ticker in tickers:
        # Get prices for this ticker
        ticker_prices = prices_df[prices_df['ticker'] == ticker][['date', 'close']].copy()

        # Create full date range for this ticker
        ticker_dates = pd.DataFrame({'date': full_date_range})

        # Merge with existing prices (left join)
        ticker_filled = ticker_dates.merge(ticker_prices, on='date', how='left')

        # Forward-fill close price
        ticker_filled['close'] = ticker_filled['close'].ffill()

        # Add ticker column
        ticker_filled['ticker'] = ticker

        filled_prices.append(ticker_filled)

    # Concatenate all tickers
    result = pd.concat(filled_prices, ignore_index=True)

    # Convert date to string format
    result['date'] = result['date'].dt.strftime('%Y-%m-%d')

    # Remove rows with NaN close (happens if first date has no price data)
    initial_rows = len(result)
    result = result.dropna(subset=['close'])
    dropped = initial_rows - len(result)

    if dropped > 0:
        logger.warning(f"  Dropped {dropped} rows with missing prices (no historical data)")

    logger.info(f"Generated {len(result):,} forward-filled price records")

    return result[['ticker', 'date', 'close']]


def calculate_portfolio_values(
    holdings_df: pd.DataFrame,
    prices_df: pd.DataFrame
) -> pd.DataFrame:
    """
    Join holdings with prices to calculate position values.

    Formula: position_value = shares × close_price

    Uses a LEFT join on [ticker, eod_date] so unpriced positions (price gaps,
    blank tickers) are kept rather than dropped. A boolean `has_price` column
    flags which rows matched a price; `position_value` is NaN where no close.

    Args:
        holdings_df: DataFrame with columns: portfolio, cusip, ticker, shares,
            filing_value, eod_date
        prices_df: DataFrame with columns: ticker, date, close

    Returns:
        DataFrame with columns: eod_date, cusip, ticker, shares, filing_value,
        close, has_price, position_value. Rows are never dropped.
    """
    logger.info("Calculating position values...")

    # Merge holdings × prices on [ticker, date]
    # Note: holdings has 'eod_date', prices has 'date'
    merged = holdings_df.merge(
        prices_df,
        left_on=['ticker', 'eod_date'],
        right_on=['ticker', 'date'],
        how='left',
    )

    merged['has_price'] = merged['close'].notna()
    merged['position_value'] = merged['shares'] * merged['close']   # NaN where no close

    total = len(holdings_df)
    unpriced = int((~merged['has_price']).sum())
    if total and (unpriced / total * 100) > 5:
        logger.warning(f"{unpriced} position-days unpriced (kept, position_value=NaN)")

    logger.info(f"Calculated {len(merged):,} position values")
    logger.info(f"  Holdings with prices: {total - unpriced:,} / {total:,}")

    cols = ['eod_date', 'cusip', 'ticker', 'shares', 'filing_value', 'close',
            'has_price', 'position_value']
    return merged[[c for c in cols if c in merged.columns]].copy()


def save_processed_holdings(holdings_df: pd.DataFrame, output_file: Path) -> None:
    """
    Save holdings DataFrame to CSV with optimizations.

    Optimizations:
    - Convert ticker to categorical dtype (reduces memory)
    - Sort by eod_date, ticker for efficient queries
    - Add metadata comment to file header

    Persisted columns (exactly, in this order): portfolio, cusip, ticker,
    shares, filing_value, eod_date. The file stays PRICE-FREE — has_price /
    close / position_value are produced by calculate_portfolio_values at
    consume time and never persisted. Blank ticker is written as '' never NaN.

    Args:
        holdings_df: DataFrame to save
        output_file: Output file path
    """
    logger.info(f"Saving processed holdings to {output_file}...")

    # Create output directory if needed
    output_file.parent.mkdir(parents=True, exist_ok=True)

    # Optimize data types
    df = holdings_df.copy()
    df['ticker'] = df['ticker'].fillna('').astype(str)
    assert not df['ticker'].isna().any(), "blank ticker must be '' not NaN"

    # Enforce the spec column order regardless of caller's column order.
    keep = ['portfolio', 'cusip', 'ticker', 'shares', 'filing_value', 'eod_date']
    df = df[keep]

    df['ticker'] = df['ticker'].astype('category')
    df['portfolio'] = df['portfolio'].astype('category')

    # Sort for efficient queries
    df = df.sort_values(['eod_date', 'ticker']).reset_index(drop=True)

    # Save to CSV
    df.to_csv(output_file, index=False)

    file_size_mb = output_file.stat().st_size / (1024 * 1024)
    logger.info(f"Saved {len(df):,} records ({file_size_mb:.2f} MB)")
    logger.info(f"  Columns: {list(df.columns)}")
    logger.info(f"  Date range: {df['eod_date'].min()} to {df['eod_date'].max()}")
    logger.info(f"  Unique tickers: {df['ticker'].nunique()}")
