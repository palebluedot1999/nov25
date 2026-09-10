"""
One-time backfill: normalize the `value` column in raw 13F filing CSVs for
reporting periods before 2022-12-31 to whole dollars, per SEC's Form 13F
amendment. See docs/superpowers/specs/2026-09-08-13f-value-scale-fix-design.md.

Safe to re-run ONLY against the same original archive: it backs up the raw
filings exactly once (via an atomic temp-dir-then-rename, so a crash mid-copy
can't leave a trusted partial backup), then always re-derives the corrected
live files from that immutable backup — never from its own prior output — so
repeated runs against that same input can't compound the scale correction.

MUST NOT be run against filings scraped after the scraper fix: those are
already in whole dollars, and re-scaling them (or capturing them as the
backup) would multiply the pre-2023 files by 1000 a second time. Two guards
defend against that: a one-shot sentinel file written on success
(`.value_scale_backfilled` in the filings dir), and a pre-flight per-share
sanity check that aborts if the pre-boundary data already looks like whole
dollars.

Because `data/` is gitignored, every clone/worktree has its own private copy
of the raw filings and needs its own one-time run of this script — done
BEFORE any re-scrape on that checkout, never after.

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
SENTINEL = FILINGS_DIR / ".value_scale_backfilled"

BOUNDARY = "2022-12-31"


def preflight_already_normalized() -> None:
    """Abort if the pre-boundary filings already look like whole dollars.

    Old thousands-scale data has value/shares near ~0.001-0.05 (a share price
    divided by 1000); corrected whole-dollar data sits near tens. If the median
    per-share value across all pre-boundary rows with positive shares is >= 1.0,
    the data has almost certainly already been normalized (e.g. re-scraped by
    the fixed scraper), and re-running would multiply by 1000 a second time.

    Runs BEFORE ensure_backup() so a refusal leaves zero trace on disk.
    """
    ratios = []
    for f in sorted(FILINGS_DIR.glob("*.csv")):
        try:
            df = pd.read_csv(f)
        except Exception:
            continue
        if df.empty or "period_end_date" not in df.columns:
            continue
        if str(df["period_end_date"].iloc[0]) >= BOUNDARY:
            continue
        if "value" not in df.columns or "shares" not in df.columns:
            continue
        rows = df[df["shares"] > 0]
        ratios.extend((rows["value"] / rows["shares"]).tolist())

    if not ratios:
        print("Sanity check skipped: no pre-boundary filings with usable "
              "shares data — cannot determine current scale.")
        return

    median_per_share = pd.Series(ratios).median()
    if median_per_share >= 1.0:
        print(
            "ABORT: the pre-2022-12-31 filings appear to ALREADY be in whole "
            f"dollars (median value/shares = {median_per_share:.4f}, which is a "
            "plausible real per-share price; thousands-scale data would be "
            "~0.001-0.05).\n"
            "Re-running this backfill would multiply those values by 1000 a "
            "second time. Nothing was backed up or written."
        )
        sys.exit(1)

    print(f"Sanity check passed: median pre-boundary value/shares = "
          f"{median_per_share:.5f} (thousands scale, as expected).")


def ensure_backup() -> None:
    """Create a one-time, immutable backup of the raw filings, if one doesn't already exist.

    Copies into a temp directory first, then renames it into place — the rename
    is atomic, so an interrupted copy leaves an orphaned .tmp directory and no
    13f_filings_backup/, rather than a partial backup a later run would trust.
    """
    if BACKUP_DIR.exists():
        csv_count = len(list(BACKUP_DIR.glob("*.csv")))
        if csv_count == 0:
            print(f"WARNING: backup directory {BACKUP_DIR} exists but contains "
                  "zero *.csv files — this is not a valid backup. Refusing to "
                  "proceed (would be a silent no-op). Remove or fix it first.")
            sys.exit(1)
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
        old_total = df["value"].sum() if not df.empty else 0

        if not df.empty:
            df["value"] = df.apply(
                lambda row: normalize_13f_value(row["value"], row["period_end_date"]), axis=1
            )
        new_total = df["value"].sum() if not df.empty else 0

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


def write_sentinel(rescaled_count: int) -> None:
    """Record that the backfill has run on this checkout, so it can't run twice."""
    SENTINEL.write_text(
        f"{datetime.now().isoformat()}\n"
        f"files_rescaled={rescaled_count}\n"
    )


def main() -> None:
    if SENTINEL.exists():
        print(f"Backfill already applied on this checkout ({SENTINEL}) — nothing to do.")
        return

    preflight_already_normalized()
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

    write_sentinel(rescaled_count)
    print(f"Sentinel written to {SENTINEL}")


if __name__ == "__main__":
    main()
