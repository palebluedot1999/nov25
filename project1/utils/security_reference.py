"""
Security reference data: sweep 13F filings for CUSIPs, resolve identifiers,
and build data/processed/security_reference.csv — the joinable master table.

See docs/superpowers/specs/2026-09-08-security-reference-data-design.md
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from config.settings import RAW_DATA_DIR, PROCESSED_DATA_DIR, PROJECT_ROOT

FILINGS_DIR = RAW_DATA_DIR / "13f_filings"
SECURITY_IDENTIFIERS_FILE = RAW_DATA_DIR / "security_identifiers.csv"
SECURITY_REFERENCE_FILE = PROCESSED_DATA_DIR / "security_reference.csv"
SECURITY_OVERRIDES_FILE = PROJECT_ROOT / "config" / "security_overrides.csv"

_ISIN_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def _isin_check_digit(body: str) -> str:
    """Luhn mod-10 check digit over an alphanumeric ISIN body (no check digit)."""
    digits = "".join(str(_ISIN_CHARS.index(c)) for c in body.upper())
    total = 0
    # Double every second digit counting from the rightmost, which is odd-indexed
    # from the left of the reversed string.
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 0:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return str((10 - (total % 10)) % 10)


def cusip_to_isin(cusip) -> str:
    """Derive the US ISIN for a 9-char numeric-leading CUSIP. '' for CINS / malformed."""
    if not isinstance(cusip, str):
        return ""
    c = cusip.strip().upper()
    if len(c) != 9 or not all(ch in _ISIN_CHARS for ch in c) or not c[0].isdigit():
        return ""
    body = "US" + c
    return body + _isin_check_digit(body)
