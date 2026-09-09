"""
One-time backfill: normalize the `value` column in raw 13F filing CSVs for
reporting periods before 2022-12-31 to whole dollars, per SEC's Form 13F
amendment. See docs/superpowers/specs/2026-09-08-13f-value-scale-fix-design.md.

Safe to re-run: backs up the raw filings exactly once (via an atomic
temp-dir-then-rename, so a crash mid-copy can't leave a trusted partial
backup), then always re-derives the corrected live files from that backup —
never from its own prior output — so repeated runs can't compound the scale
correction.

Usage:
    python scripts/backfill_13f_value_scale.py
"""
import shutil
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import RAW_DATA_DIR
from scrapers.sec_edgar import normalize_13f_value

FILINGS_DIR = RAW_DATA_DIR / "13f_filings"
BACKUP_DIR = RAW_DATA_DIR / "13f_filings_backup"
BACKUP_TMP_DIR = RAW_DATA_DIR / "13f_filings_backup.tmp"


def ensure_backup() -> None:
    """Create a one-time, immutable backup of the raw filings, if one doesn't already exist.

    Copies into a temp directory first, then renames it into place — the rename
    is atomic, so an interrupted copy leaves an orphaned .tmp directory and no
    13f_filings_backup/, rather than a partial backup a later run would trust.
    """
    if BACKUP_DIR.exists():
        print(f"Backup already exists at {BACKUP_DIR}, skipping.")
        return

    if BACKUP_TMP_DIR.exists():
        shutil.rmtree(BACKUP_TMP_DIR)
    BACKUP_TMP_DIR.mkdir(parents=True)

    for f in FILINGS_DIR.glob("*.csv"):
        shutil.copy2(f, BACKUP_TMP_DIR / f.name)

    BACKUP_TMP_DIR.rename(BACKUP_DIR)
    print(f"Backed up {len(list(BACKUP_DIR.glob('*.csv')))} files to {BACKUP_DIR}")


def backfill() -> list[dict]:
    """Rewrite each live filing file from the backup, with value normalized.

    Always reads from BACKUP_DIR (never from the live directory or its own
    prior output), so re-running this function can never compound the scale
    correction. Returns one summary dict per file processed.
    """
    summary = []
    for backup_file in sorted(BACKUP_DIR.glob("*.csv")):
        df = pd.read_csv(backup_file)
        old_total = df["value"].sum()

        df["value"] = df.apply(
            lambda row: normalize_13f_value(row["value"], row["period_end_date"]), axis=1
        )
        new_total = df["value"].sum()

        live_file = FILINGS_DIR / backup_file.name
        df.to_csv(live_file, index=False)

        period_end = str(df["period_end_date"].iloc[0]) if not df.empty else ""
        summary.append({
            "filename": backup_file.name,
            "period_end_date": period_end,
            "rows": len(df),
            "rescaled": bool(new_total != old_total),
            "old_total_value": old_total,
            "new_total_value": new_total,
        })
    return summary


def write_log(summary: list[dict]) -> Path:
    """Write the backfill summary to a timestamped, git-tracked log file under docs/."""
    log_path = PROJECT_ROOT / "docs" / f"13f_value_scale_backfill_{datetime.now().strftime('%Y-%m-%d_%H%M%S')}.log"
    lines = ["filename,period_end_date,rows,rescaled,old_total_value,new_total_value"]
    for row in summary:
        lines.append(
            f"{row['filename']},{row['period_end_date']},{row['rows']},"
            f"{row['rescaled']},{row['old_total_value']},{row['new_total_value']}"
        )
    log_path.write_text("\n".join(lines) + "\n")
    return log_path


def main() -> None:
    ensure_backup()
    summary = backfill()

    rescaled_count = sum(1 for row in summary if row["rescaled"])
    print(f"\nProcessed {len(summary)} files, rescaled {rescaled_count}.")
    for row in summary:
        marker = "RESCALED" if row["rescaled"] else "unchanged"
        print(f"  {row['filename']} ({row['period_end_date']}): {marker} "
              f"[{row['old_total_value']:.0f} -> {row['new_total_value']:.0f}]")

    log_path = write_log(summary)
    print(f"\nAudit log written to {log_path}")


if __name__ == "__main__":
    main()
