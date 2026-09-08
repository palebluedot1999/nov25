# 13F Value Column Scale Correction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Correct a silent 1000x unit inconsistency in the 13F `value` column (thousands of dollars before the SEC's Q4-2022 Form 13F amendment, whole dollars after) at every point it enters or is read from this codebase, and backfill the 32 already-scraped filings that predate the fix.

**Architecture:** One pure function (`normalize_13f_value`) is the single source of truth for the SEC's period-based rule. It's wired into `SECEdgarScraper.get_13f_holdings()` — the one method both current writers of 13F CSVs (`scrapers/sec_edgar.py` and `utils/fund_operations.py`) already call — so every future scrape is correct with no per-caller effort. A one-time, idempotent backfill script corrects the 32 already-scraped files using the same function, backing them up first. The one derived table that depends on cross-quarter `value` comparisons (`qoq_changes.csv`) is regenerated afterward.

**Tech Stack:** Python 3.12, pandas (already a project dependency).

## Global Constraints

- No change to how downstream code *uses* `value` (weight calculation, strategy selection, drift, the price-based Dashboard valuation pipeline) — per spec, all of that is already correct or already scale-invariant.
- The rule: `period_end_date < "2022-12-31"` → multiply by 1000; `period_end_date >= "2022-12-31"` → unchanged. String comparison on well-formed ISO `YYYY-MM-DD` dates.
- `normalize_13f_value()` must coerce its `period_end_date` argument to `str()` internally and treat an empty string or `"nan"` as a no-op (return `value` unchanged) — every caller gets this protection for free, not just the ones that remember to check.
- `data/processed/holdings.csv` does NOT need regenerating — confirmed its schema (`portfolio, ticker, cusip, shares, eod_date`) carries no value/price column and never reads 13F `value`.
- Follow the repo's PR-required workflow: branch off `develop`, commit, push, open a PR (direct pushes to `develop`/`main` are blocked by the repository ruleset).

---

### Task 0: Create the working branch

**Files:** none (git operations only)

- [ ] **Step 1: Sync `develop` and branch off it**

```bash
git checkout develop
git pull origin develop
git checkout -b fix/13f-value-scale
```

All commits in Tasks 1-5 go on this `fix/13f-value-scale` branch.

---

### Task 1: `normalize_13f_value()` — the shared rule, with tests

**Files:**
- Modify: `scrapers/sec_edgar.py:20-24` (add the function between the imports and the class)
- Create: `tests/test_sec_edgar.py`

**Interfaces:**
- Produces: `normalize_13f_value(value: float, period_end_date: str) -> float`, importable as `from scrapers.sec_edgar import normalize_13f_value`. Task 2 and Task 3 both depend on this exact name and signature.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_sec_edgar.py`:

```python
from scrapers.sec_edgar import normalize_13f_value


def test_pre_boundary_date_scaled_to_dollars():
    """A reporting period before the SEC's 2022-12-31 amendment is in thousands; multiply by 1000."""
    assert normalize_13f_value(149438.0, "2022-09-30") == 149438000.0


def test_post_boundary_date_unchanged():
    """A reporting period after the amendment is already in whole dollars."""
    assert normalize_13f_value(105860323.0, "2023-03-31") == 105860323.0


def test_boundary_date_itself_unchanged():
    """The exact effective-date period (2022-12-31) is already in whole dollars."""
    assert normalize_13f_value(19327911.0, "2022-12-31") == 19327911.0


def test_missing_period_end_date_returns_value_unscaled():
    """An empty or NaN period_end_date (as pandas produces for a missing value) is a no-op, not a scale-up."""
    assert normalize_13f_value(500.0, "") == 500.0
    assert normalize_13f_value(500.0, float("nan")) == 500.0
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sec_edgar.py -v
```

Expected: FAIL with `ImportError: cannot import name 'normalize_13f_value' from 'scrapers.sec_edgar'` (the function doesn't exist yet).

- [ ] **Step 3: Implement the function**

In `scrapers/sec_edgar.py`, find (lines 20-24):

```python
from utils.cusip_mapping import cusip_to_ticker


class SECEdgarScraper:
    """Scraper for SEC EDGAR 13F filings."""
```

Replace with:

```python
from utils.cusip_mapping import cusip_to_ticker


def normalize_13f_value(value: float, period_end_date: str) -> float:
    """Normalize a 13F-reported value to whole dollars.

    SEC's Form 13F amendment (effective for reporting periods ending
    2022-12-31 and later) changed the required unit from thousands of
    dollars to whole dollars. Filings for earlier periods must be
    multiplied by 1000 to match; later filings are already correct.
    """
    period_end_date = str(period_end_date)
    if not period_end_date or period_end_date == "nan":
        return value
    if period_end_date < "2022-12-31":
        return value * 1000
    return value


class SECEdgarScraper:
    """Scraper for SEC EDGAR 13F filings."""
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
.venv/Scripts/python.exe -m pytest tests/test_sec_edgar.py -v
```

Expected: all 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add scrapers/sec_edgar.py tests/test_sec_edgar.py
git commit -m "feat: add normalize_13f_value() for the SEC's 2022-12-31 unit change"
```

---

### Task 2: Wire the normalization into both writers of 13F CSVs

**Files:**
- Modify: `scrapers/sec_edgar.py` (the `get_13f_holdings` method signature/body, the `fetch_and_save_filings` call site, and the stale comment in `_parse_holding_entry`)
- Modify: `utils/fund_operations.py:362` (the `fetch_incremental_filings_for_fund` call site)

**Interfaces:**
- Consumes: `normalize_13f_value(value, period_end_date)` from Task 1.
- Produces: `SECEdgarScraper.get_13f_holdings(self, cik: str, accession_number: str, period_end_date: str) -> list` — the new required third parameter. Nothing later depends on this beyond the two call sites updated in this same task.

- [ ] **Step 1: Add the `period_end_date` parameter and normalize inside `get_13f_holdings`**

In `scrapers/sec_edgar.py`, find the full `get_13f_holdings` method:

```python
    def get_13f_holdings(self, cik: str, accession_number: str) -> list:
        """Parse holdings from a 13F information table."""
        # Format accession number for URL (remove dashes)
        acc_formatted = accession_number.replace('-', '')
        cik_padded = cik.zfill(10)

        # First, get the filing index to find the information table
        index_url = f"{SEC_EDGAR_BASE_URL}/Archives/edgar/data/{cik_padded}/{acc_formatted}/index.json"

        try:
            response = self._make_request(index_url)
            index_data = response.json()

            # Find the information table XML file
            info_table_file = None
            for item in index_data.get('directory', {}).get('item', []):
                name = item.get('name', '').lower()
                if 'infotable' in name and name.endswith('.xml'):
                    info_table_file = item.get('name')
                    break

            if not info_table_file:
                # Try alternative naming
                for item in index_data.get('directory', {}).get('item', []):
                    name = item.get('name', '').lower()
                    if name.endswith('.xml') and 'form13f' in name:
                        info_table_file = item.get('name')
                        break

            if not info_table_file:
                print(f"Could not find information table for {accession_number}")
                return []

            # Fetch the information table XML
            table_url = f"{SEC_EDGAR_BASE_URL}/Archives/edgar/data/{cik_padded}/{acc_formatted}/{info_table_file}"
            response = self._make_request(table_url)

            return self._parse_info_table(response.text)

        except Exception as e:
            print(f"Error fetching holdings for {accession_number}: {e}")
            return []
```

Replace with:

```python
    def get_13f_holdings(self, cik: str, accession_number: str, period_end_date: str) -> list:
        """Parse holdings from a 13F information table, with value normalized to whole dollars."""
        # Format accession number for URL (remove dashes)
        acc_formatted = accession_number.replace('-', '')
        cik_padded = cik.zfill(10)

        # First, get the filing index to find the information table
        index_url = f"{SEC_EDGAR_BASE_URL}/Archives/edgar/data/{cik_padded}/{acc_formatted}/index.json"

        try:
            response = self._make_request(index_url)
            index_data = response.json()

            # Find the information table XML file
            info_table_file = None
            for item in index_data.get('directory', {}).get('item', []):
                name = item.get('name', '').lower()
                if 'infotable' in name and name.endswith('.xml'):
                    info_table_file = item.get('name')
                    break

            if not info_table_file:
                # Try alternative naming
                for item in index_data.get('directory', {}).get('item', []):
                    name = item.get('name', '').lower()
                    if name.endswith('.xml') and 'form13f' in name:
                        info_table_file = item.get('name')
                        break

            if not info_table_file:
                print(f"Could not find information table for {accession_number}")
                return []

            # Fetch the information table XML
            table_url = f"{SEC_EDGAR_BASE_URL}/Archives/edgar/data/{cik_padded}/{acc_formatted}/{info_table_file}"
            response = self._make_request(table_url)

            holdings = self._parse_info_table(response.text)
            for holding in holdings:
                holding['value'] = normalize_13f_value(holding['value'], period_end_date)
            return holdings

        except Exception as e:
            print(f"Error fetching holdings for {accession_number}: {e}")
            return []
```

- [ ] **Step 2: Update the stale comment in `_parse_holding_entry`**

In `scrapers/sec_edgar.py`, find:

```python
                'value': float(get_text(entry, 'value') or 0),  # Value already in correct scale
```

Replace with:

```python
                'value': float(get_text(entry, 'value') or 0),  # Raw XML value; normalized to whole dollars in get_13f_holdings()
```

- [ ] **Step 3: Update the call site in `fetch_and_save_filings`**

In `scrapers/sec_edgar.py`, find:

```python
            holdings = self.get_13f_holdings(cik, filing['accession_number'])
```

Replace with:

```python
            holdings = self.get_13f_holdings(cik, filing['accession_number'], period_end)
```

(`period_end` is already assigned two lines above this call, from `filing['report_date']` — no other change needed at this call site.)

- [ ] **Step 4: Update the call site in `utils/fund_operations.py`**

In `utils/fund_operations.py`, find (line 362):

```python
            holdings = scraper.get_13f_holdings(cik, filing['accession_number'])
```

Replace with:

```python
            holdings = scraper.get_13f_holdings(cik, filing['accession_number'], period_end)
```

(`period_end` is already assigned above this call, from `filing['report_date']` — no other change needed at this call site. No new import is needed: `fund_operations.py` already imports `SECEdgarScraper` from `scrapers.sec_edgar`.)

- [ ] **Step 5: Run the full test suite**

```bash
.venv/Scripts/python.exe -m pytest tests/ -v
```

Expected: all tests pass (the existing 37 plus the 4 added in Task 1 — 41 total). This is a signature change to a method with no existing test coverage calling it directly, so this run confirms nothing else in the test suite broke, not that the new behavior itself is tested (Task 1 already covers that).

- [ ] **Step 6: Commit**

```bash
git add scrapers/sec_edgar.py utils/fund_operations.py
git commit -m "fix: normalize 13F value inside get_13f_holdings, covering both writers"
```

---

### Task 3: One-time backfill of the 32 already-scraped filings

**Files:**
- Create: `scripts/backfill_13f_value_scale.py`

**Interfaces:**
- Consumes: `normalize_13f_value(value, period_end_date)` from Task 1, `RAW_DATA_DIR` from `config.settings` (already used the same way in `scrapers/sec_edgar.py`).
- Produces: nothing consumed by other tasks — this is a standalone one-time script. Task 4 depends on its *effect* (corrected raw files), not on any function it exports.

- [ ] **Step 1: Write the backfill script**

Create `scripts/backfill_13f_value_scale.py`:

```python
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
```

- [ ] **Step 2: Run the backfill**

```bash
.venv/Scripts/python.exe scripts/backfill_13f_value_scale.py
```

Expected: prints "Backed up 46 files to ...13f_filings_backup", then "Processed 46 files, rescaled 32.", with each of the 32 pre-2022-12-31 filings marked `RESCALED` and the other 14 marked `unchanged`. Ends with an "Audit log written to ...docs/13f_value_scale_backfill_<timestamp>.log" line.

- [ ] **Step 3: Verify the backfill did not double-scale anything by re-running it**

```bash
.venv/Scripts/python.exe scripts/backfill_13f_value_scale.py
```

Expected: prints "Backup already exists ..., skipping." and then the exact same 46-processed/32-rescaled summary with **identical** old/new totals to Step 2's run (proving the second run corrected from the same untouched backup, not from its own already-corrected output — a bug here would show doubled `new_total_value` figures on this second run).

- [ ] **Step 4: Price cross-check verification**

```bash
.venv/Scripts/python.exe -c "
import pandas as pd
df = pd.read_csv('data/raw/13f_filings/baker-bros_2021-02-16_holdings.csv')
row = df[df['cusip'] == '00288U106'].iloc[0]
print('value:', row['value'], 'shares:', row['shares'], 'implied_price:', row['value'] / row['shares'])
"
```

Expected: `implied_price` around `40` (AbCellera traded in the $35-45 range in February 2021) — not around `0.04`, which is what the pre-backfill thousands-scaled value implied.

- [ ] **Step 5: Aggregate AUM check**

```bash
.venv/Scripts/python.exe -c "
from utils.csv_data import get_all_filings
df = get_all_filings('baker-bros')
print(df[['filing_date', 'period_end_date', 'total_value']].to_string())
"
```

Expected: `total_value` for filings before `period_end_date=2022-12-31` is now roughly the same order of magnitude (billions) as filings after it, not 1000x smaller. There should be no sharp discontinuity at the boundary.

- [ ] **Step 6: Commit**

```bash
git add scripts/backfill_13f_value_scale.py data/raw/13f_filings docs/13f_value_scale_backfill_*.log
git commit -m "fix: backfill 32 pre-2022-12-31 13F filings to whole-dollar value"
```

Note: `data/` is covered by `.gitignore`'s `data/` rule, so `git add data/raw/13f_filings` will not actually stage anything — the corrected raw CSVs stay local, matching how every other raw/processed data file in this repo is handled. Only the script and the log file (under `docs/`, git-tracked) are expected to actually appear in `git status` before this commit. Do not force-add anything under `data/`.

---

### Task 4: Regenerate `qoq_changes.csv`

**Files:** none created or modified — this task runs existing code against the now-corrected raw data.

**Interfaces:**
- Consumes: `utils.data_processing.compute_and_save_qoq_changes(portfolio_id: str) -> pd.DataFrame` (already exists, unchanged).

- [ ] **Step 1: Regenerate the QoQ table**

```bash
.venv/Scripts/python.exe -c "
from utils.data_processing import compute_and_save_qoq_changes
df = compute_and_save_qoq_changes('baker-bros')
print(f'{len(df)} rows written to data/processed/qoq_changes.csv')
"
```

Expected: completes without error, prints a row count.

- [ ] **Step 2: Verify the Q3 2022 → Q4 2022 outlier is gone**

```bash
.venv/Scripts/python.exe -c "
import pandas as pd
df = pd.read_csv('data/processed/qoq_changes.csv')
df = df[df['portfolio_id'] == 'baker-bros']
boundary = df[df['filing_date'] == '2023-02-14']
other = df[df['filing_date'] != '2023-02-14']
print('boundary quarter value_delta_pct describe:')
print(boundary['value_delta_pct'].describe())
print()
print('all other quarters value_delta_pct describe (for comparison):')
print(other['value_delta_pct'].describe())
"
```

Expected: the boundary quarter's `value_delta_pct` distribution (mean, std, min, max) is now in the same rough range as other quarters' — no longer showing values near +99,900% (the signature of a still-present 1000x jump). Exact figures will vary; the check is "no longer an outlier by orders of magnitude," not a specific number.

- [ ] **Step 3: Commit**

```bash
git add data/processed/qoq_changes.csv
git commit -m "fix: regenerate qoq_changes.csv from corrected 13F values"
```

Note: like Task 3, `data/` is gitignored — this `git add` will not stage anything, and that's expected. If `git status` shows nothing to commit here, skip this commit; there's nothing to record in git for a gitignored file.

---

### Task 5: Documentation fix and final verification

**Files:**
- Modify: `CLAUDE.md` (Notes section)

- [ ] **Step 1: Replace the incorrect Notes explanation**

In `CLAUDE.md`, find:

```
- Values in 13F are reported in thousands (scraper multiplies by 1000)
  - **Note**: Early filings (2020-2022 Q3) have unscaled values (in thousands)
  - Later filings (2022 Q4+) have scaled values (in dollars)
  - This inconsistency occurred when SEC scraper was updated but old files weren't regenerated
```

Replace with:

```
- 13F values are in whole dollars. SEC's Form 13F amendment (effective for reporting
  periods ending 2022-12-31 and later) changed the required unit from thousands of
  dollars to whole dollars; filings for earlier periods were originally scraped in
  thousands and have been corrected via a one-time backfill (see
  scrapers/sec_edgar.py's normalize_13f_value()). New scrapes are normalized at
  ingestion time, so this should never need correcting again.
```

- [ ] **Step 2: Run the full test suite one final time**

```bash
.venv/Scripts/python.exe -m pytest tests/ -v
```

Expected: all 41 tests passing (the pre-existing 37 plus the 4 added in Task 1).

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: correct CLAUDE.md's explanation of the 13F value scale change"
```

---

### Task 6: Push and open the PR

**Files:** none (git/GitHub operations only)

- [ ] **Step 1: Push the branch**

```bash
git push -u origin fix/13f-value-scale
```

- [ ] **Step 2: Open a PR against `develop`**

```bash
gh pr create --base develop --title "fix: correct 13F value column unit inconsistency (thousands vs. whole dollars)" --body "Implements docs/superpowers/specs/2026-09-08-13f-value-scale-fix-design.md. Adds normalize_13f_value(), wires it into both writers of 13F holdings CSVs (scrapers/sec_edgar.py and utils/fund_operations.py), backfills the 32 affected raw filings (backed up first), regenerates qoq_changes.csv, and corrects CLAUDE.md's prior incorrect explanation. No change to how downstream code uses value."
```

- [ ] **Step 3: Report the PR URL to the user for review.**
