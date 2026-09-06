"""
Consolidate all individual price CSV files into one master prices.csv file

This script:
- Reads all CSV files from data/raw/yahoo_prices/ (one per ticker)
- Adds a 'source' column tagged as 'yahoo' to all records
- Merges all files into a single master table
- Saves to data/processed/prices.csv (185K+ records, 160 tickers, 5 years)
- Sorted by ticker and date for easy querying

Run this whenever:
- New price data has been fetched for holdings
- You need to refresh the master price table
- Price data has been updated/corrected

Can be run manually or via Data Management page "Consolidate Prices to Master Table" button

Usage:
    python scripts/consolidate_prices.py
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import pandas as pd
from utils.csv_data import PRICES_DIR

# Output paths
PROCESSED_DIR = project_root / "data" / "processed"
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_FILE = PROCESSED_DIR / "prices.csv"

print("Consolidating price files...")
print("=" * 60)

# Get all CSV files in yahoo_prices directory
price_files = list(PRICES_DIR.glob("*.csv"))
print(f"Found {len(price_files)} price files to consolidate")

all_prices = []

for i, file in enumerate(price_files, 1):
    print(f"[{i}/{len(price_files)}] Reading {file.name}...")

    df = pd.read_csv(file)

    # Add source column
    df['source'] = 'yahoo'

    all_prices.append(df)

# Concatenate all dataframes
print("\nMerging all data...")
master_df = pd.concat(all_prices, ignore_index=True)

# Reorder columns to have source after ticker
columns = ['ticker', 'date', 'open', 'high', 'low', 'close', 'adj_close', 'volume', 'source', 'fetched_at']
master_df = master_df[columns]

# Sort by ticker and date
master_df = master_df.sort_values(['ticker', 'date'])

# Save consolidated file
print(f"\nSaving to {OUTPUT_FILE}...")
master_df.to_csv(OUTPUT_FILE, index=False)

print("=" * 60)
print(f"Completed!")
print(f"Total records: {len(master_df):,}")
print(f"Unique tickers: {master_df['ticker'].nunique()}")
print(f"Date range: {master_df['date'].min()} to {master_df['date'].max()}")
print(f"File size: {OUTPUT_FILE.stat().st_size / (1024*1024):.1f} MB")
