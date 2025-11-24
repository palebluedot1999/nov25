"""
One-time migration script to convert existing JSON filing data to CSV format.
Converts each JSON file into two CSV files: filing metadata and holdings data.
"""

import json
import pandas as pd
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from config.settings import RAW_DATA_DIR


def migrate_json_to_csv(archive_json=False):
    """
    Convert all JSON filing files to CSV format.

    Args:
        archive_json: If True, move JSON files to archive folder instead of deleting
    """
    json_files = list(RAW_DATA_DIR.glob("*.json"))

    if not json_files:
        print("No JSON files found to migrate.")
        return

    print(f"Found {len(json_files)} JSON files to migrate")
    print("-" * 60)

    filing_count = 0
    holdings_count = 0

    for json_file in json_files:
        print(f"\nProcessing {json_file.name}...")

        try:
            with open(json_file) as f:
                data = json.load(f)
        except Exception as e:
            print(f"  ERROR: Could not read JSON file: {e}")
            continue

        # Extract components
        filing = data.get('filing', {})
        holdings = data.get('holdings', [])
        fetched_at = data.get('fetched_at', '')

        # Base name without extension (e.g., "baker-bros_0001104659-24-118899")
        base_name = json_file.stem

        # Create filing CSV
        filing_csv = RAW_DATA_DIR / f"{base_name}_filing.csv"
        try:
            filing_df = pd.DataFrame([{**filing, 'fetched_at': fetched_at}])
            filing_df.to_csv(filing_csv, index=False)
            print(f"  [OK] Created {filing_csv.name}")
            filing_count += 1
        except Exception as e:
            print(f"  ERROR: Could not create filing CSV: {e}")
            continue

        # Create holdings CSV (if any holdings exist)
        if holdings:
            holdings_csv = RAW_DATA_DIR / f"{base_name}_holdings.csv"
            try:
                holdings_df = pd.DataFrame(holdings)
                holdings_df.to_csv(holdings_csv, index=False)
                print(f"  [OK] Created {holdings_csv.name} ({len(holdings)} holdings)")
                holdings_count += 1
            except Exception as e:
                print(f"  ERROR: Could not create holdings CSV: {e}")
        else:
            print(f"  [SKIP] No holdings in this filing")

        # Archive or delete the JSON file
        if archive_json:
            archive_dir = RAW_DATA_DIR / "json_archive"
            archive_dir.mkdir(exist_ok=True)
            archive_path = archive_dir / json_file.name
            json_file.rename(archive_path)
            print(f"  [ARCHIVE] Moved JSON to {archive_path.relative_to(RAW_DATA_DIR)}")
        else:
            json_file.unlink()
            print(f"  [DELETE] Removed {json_file.name}")

    print("\n" + "=" * 60)
    print(f"Migration complete!")
    print(f"  Filing CSVs created: {filing_count}")
    print(f"  Holdings CSVs created: {holdings_count}")
    print(f"  JSON files {'archived' if archive_json else 'deleted'}: {len(json_files)}")
    print("=" * 60)


if __name__ == "__main__":
    # Archive JSON files instead of deleting (safer)
    migrate_json_to_csv(archive_json=True)
