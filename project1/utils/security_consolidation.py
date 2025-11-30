"""
Security consolidation operations.

Handles:
- Merging CUSIP cache with security metadata
- Creating master securities table
- Providing consolidated security information
"""

import sys
from pathlib import Path
from typing import Dict
import pandas as pd

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

CUSIP_CACHE_FILE = project_root / "data" / "raw" / "cusip_cache.csv"
METADATA_FILE = project_root / "data" / "raw" / "security_metadata.csv"
SECURITIES_FILE = project_root / "data" / "processed" / "securities.csv"


def consolidate_securities() -> Dict:
    """
    Merge cusip_cache.csv with security_metadata.csv to create master securities table.

    Performs LEFT JOIN with cusip_cache as the base to preserve all CUSIP entries,
    even if metadata hasn't been fetched yet.

    Returns:
        Dict with keys:
        - success: bool
        - message: str
        - total_securities: int
        - with_metadata: int
        - without_metadata: int
    """
    try:
        # Check if CUSIP cache exists
        if not CUSIP_CACHE_FILE.exists():
            return {
                'success': False,
                'message': 'CUSIP cache file not found',
                'total_securities': 0,
                'with_metadata': 0,
                'without_metadata': 0
            }

        # Read CUSIP cache
        df_cusip = pd.read_csv(CUSIP_CACHE_FILE)

        if df_cusip.empty:
            return {
                'success': True,
                'message': 'CUSIP cache is empty',
                'total_securities': 0,
                'with_metadata': 0,
                'without_metadata': 0
            }

        # Validate ticker column exists
        if 'ticker' not in df_cusip.columns:
            return {
                'success': False,
                'message': 'CUSIP cache missing ticker column',
                'total_securities': 0,
                'with_metadata': 0,
                'without_metadata': 0
            }

        # Read security metadata if it exists
        if METADATA_FILE.exists():
            df_metadata = pd.read_csv(METADATA_FILE)

            # Validate ticker column exists in metadata
            if 'ticker' not in df_metadata.columns:
                return {
                    'success': False,
                    'message': 'Security metadata missing ticker column',
                    'total_securities': 0,
                    'with_metadata': 0,
                    'without_metadata': 0
                }

            # Perform LEFT JOIN (keep all CUSIPs, add metadata where available)
            df_merged = df_cusip.merge(df_metadata, on='ticker', how='left')
        else:
            # No metadata file - just use CUSIP cache
            df_merged = df_cusip.copy()

        # Remove any duplicate tickers (safety measure)
        df_merged = df_merged.drop_duplicates(subset=['ticker'], keep='first')

        # Reorder columns: cusip, ticker, company_name, sector, industry, then rest
        # First, ensure cusip and ticker are first two columns
        cols = df_merged.columns.tolist()

        # Build desired column order
        priority_cols = ['cusip', 'ticker']

        # Add other important columns next if they exist
        for col in ['company_name', 'sector', 'industry']:
            if col in cols:
                priority_cols.append(col)

        # Add all remaining columns (except last_updated)
        remaining_cols = [c for c in cols if c not in priority_cols and c != 'last_updated']
        priority_cols.extend(remaining_cols)

        # Add last_updated at the end if it exists
        if 'last_updated' in cols:
            priority_cols.append('last_updated')

        df_merged = df_merged[priority_cols]

        # Sort by ticker alphabetically for easier viewing
        df_merged = df_merged.sort_values('ticker')

        # Ensure output directory exists
        SECURITIES_FILE.parent.mkdir(parents=True, exist_ok=True)

        # Save to processed directory
        df_merged.to_csv(SECURITIES_FILE, index=False)

        # Calculate statistics
        total_securities = len(df_merged)

        # Count rows with metadata (have company_name populated)
        if 'company_name' in df_merged.columns:
            with_metadata = df_merged['company_name'].notna().sum()
        else:
            with_metadata = 0

        without_metadata = total_securities - with_metadata

        return {
            'success': True,
            'message': f'Successfully consolidated {total_securities} securities',
            'total_securities': total_securities,
            'with_metadata': with_metadata,
            'without_metadata': without_metadata
        }

    except Exception as e:
        return {
            'success': False,
            'message': f'Error during consolidation: {str(e)}',
            'total_securities': 0,
            'with_metadata': 0,
            'without_metadata': 0
        }


def get_securities_summary() -> Dict:
    """
    Get summary statistics about the consolidated securities file.

    Returns:
        Dict with total_securities, last_modified, has_data, etc.
    """
    if not SECURITIES_FILE.exists():
        return {
            'total_securities': 0,
            'last_modified': 'Never',
            'has_data': False
        }

    try:
        df = pd.read_csv(SECURITIES_FILE)

        from datetime import datetime
        mtime = SECURITIES_FILE.stat().st_mtime
        last_modified = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')

        summary = {
            'total_securities': len(df),
            'last_modified': last_modified,
            'has_data': True
        }

        # Add sector/industry counts if available
        if 'sector' in df.columns:
            summary['sectors'] = df['sector'].nunique()
        if 'industry' in df.columns:
            summary['industries'] = df['industry'].nunique()

        return summary

    except Exception as e:
        print(f"Error reading securities file: {e}")
        return {
            'total_securities': 0,
            'last_modified': 'Error',
            'has_data': False
        }


if __name__ == "__main__":
    # Test consolidation
    print("Testing security_consolidation.py...")
    print()

    result = consolidate_securities()

    if result['success']:
        print(f"Success: {result['message']}")
        print(f"Total securities: {result['total_securities']}")
        print(f"With metadata: {result['with_metadata']}")
        print(f"Without metadata: {result['without_metadata']}")
    else:
        print(f"Error: {result['message']}")

    print()

    # Test summary
    summary = get_securities_summary()
    print(f"Securities summary: {summary}")
