"""
Consolidate CUSIP cache and security metadata into master securities table.

This script:
1. Reads cusip_cache.csv (CUSIP↔Ticker mappings)
2. Reads security_metadata.csv (fundamental data)
3. Merges on ticker field (LEFT JOIN)
4. Outputs to data/processed/securities.csv

Run this after adding new securities or updating metadata.

Can be run manually or via Data Management page "Consolidate Securities" button.

Usage:
    python scripts/consolidate_securities.py
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utils.security_consolidation import consolidate_securities


def main():
    print("=" * 60)
    print("Securities Consolidation")
    print("=" * 60)
    print()

    result = consolidate_securities()

    if result['success']:
        print(f"Successfully consolidated {result['total_securities']} securities")
        print(f"  - With metadata: {result['with_metadata']}")
        print(f"  - Without metadata: {result['without_metadata']}")
        print()
        print(f"Output: data/processed/securities.csv")
    else:
        print(f"Error: {result['message']}")
        sys.exit(1)


if __name__ == "__main__":
    main()
