"""
Build data/processed/security_reference.csv from the 13F filing corpus.

Usage:
    python scripts/build_security_reference.py            # resolve only new CUSIPs
    python scripts/build_security_reference.py --force    # re-resolve everything
    python scripts/build_security_reference.py --no-api   # cache + overrides only
"""
import argparse
import sys
from datetime import date
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utils.security_reference import (
    collect_filing_cusips, resolve_cusips, build_security_reference,
    load_security_reference,
)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="re-resolve all CUSIPs")
    ap.add_argument("--no-api", action="store_true", help="skip OpenFIGI/SEC calls")
    args = ap.parse_args()

    sweep = collect_filing_cusips()
    print(f"Swept {len(sweep)} distinct CUSIPs from 13F filings.")

    if not args.no_api:
        want = sweep[["cusip", "name"]]
        resolved = resolve_cusips(want, force=args.force)
        print(f"Resolved {len(resolved)} new CUSIP(s) this run.")

    stats = build_security_reference()
    print(f"Wrote {stats['path']}: {stats['total']} rows "
          f"({stats['resolved']} resolved, {stats['ticker_only']} ticker_only, "
          f"{stats['name_only']} name_only, {stats['unresolved']} unresolved).")

    ref = load_security_reference()
    worklist = ref[ref["resolution_status"].isin(["ticker_only", "name_only", "unresolved"])]
    report = project_root / "docs" / f"security_reference_coverage_{date.today()}.log"
    with report.open("w", encoding="utf-8") as fh:
        fh.write(f"Security reference coverage — {date.today()}\n")
        for k, v in stats.items():
            fh.write(f"  {k}: {v}\n")
        fh.write("\nManual-triage worklist (add rows to config/security_overrides.csv):\n")
        fh.write(worklist[["cusip", "name", "first_seen_quarter", "last_seen_quarter",
                           "n_filings", "is_active", "resolution_status"]]
                 .to_csv(index=False))
    print(f"Coverage report: {report}")


if __name__ == "__main__":
    main()
