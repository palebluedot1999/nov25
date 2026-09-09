"""
Security reference data: sweep 13F filings for CUSIPs, resolve identifiers,
and build data/processed/security_reference.csv — the joinable master table.

See docs/superpowers/specs/2026-09-08-security-reference-data-design.md
"""

import sys
from pathlib import Path

import pandas as pd

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


def collect_filing_cusips(filings_dir: Path = FILINGS_DIR) -> pd.DataFrame:
    """Sweep every 13F filing CSV; return one row per distinct CUSIP with history."""
    frames = []
    for path in sorted(Path(filings_dir).glob("*.csv")):
        df = pd.read_csv(path, dtype=str)
        if df.empty:
            continue
        df = df[["cusip", "company_name", "ticker", "period_end_date"]].copy()
        df["cusip"] = df["cusip"].str.strip().str.upper()
        df = df[df["cusip"].notna() & (df["cusip"] != "")]
        frames.append(df)

    if not frames:
        return pd.DataFrame(
            columns=["cusip", "name", "ticker_in_filing", "first_seen_quarter",
                     "last_seen_quarter", "n_filings", "is_active"]
        )

    allrows = pd.concat(frames, ignore_index=True)
    allrows["company_name"] = allrows["company_name"].fillna("").str.strip()
    allrows["ticker"] = allrows["ticker"].fillna("").str.strip()
    latest_quarter = allrows["period_end_date"].max()

    def _latest_nonempty(series_df, col):
        s = series_df[series_df[col] != ""].sort_values("period_end_date")
        return s[col].iloc[-1] if not s.empty else ""

    out_rows = []
    for cusip, g in allrows.groupby("cusip"):
        quarters = g["period_end_date"]
        out_rows.append({
            "cusip": cusip,
            "name": _latest_nonempty(g, "company_name"),
            "ticker_in_filing": _latest_nonempty(g, "ticker"),
            "first_seen_quarter": quarters.min(),
            "last_seen_quarter": quarters.max(),
            "n_filings": g["period_end_date"].nunique(),
            "is_active": bool((quarters == latest_quarter).any()),
        })
    return pd.DataFrame(out_rows)
