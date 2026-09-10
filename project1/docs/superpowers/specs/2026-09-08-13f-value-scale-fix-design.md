# 13F Value Column Scale Correction

**Date:** 2026-09-08
**Status:** Approved for implementation

---

## Overview

Auditing the 13F ingestion/transform/use pipeline surfaced a silent, unflagged unit inconsistency in the `value` column of every raw 13F filing CSV in `data/raw/13f_filings/`: filings for reporting periods before 2022-12-31 report `value` in **thousands of dollars**; filings from 2022-12-31 onward report it in **whole dollars**. Nothing in the schema or code marks which regime applies to a given row.

This is not a scraper bug. It's the SEC's own June 2022 Form 13F amendment, which requires whole-dollar reporting effective for reporting periods ending 2022-12-31 and later ([Toppan Merrill](https://www.toppanmerrill.com/blog/sec-updates-edgar-on-jan-3-2023-for-form-13f-changes/); [Harvard Law/CorpGov](https://corpgov.law.harvard.edu/2022/08/06/amendments-to-form-13f/)). Verified directly in this project's data: the `period_end_date=2022-09-30` filing (`baker-bros_2022-11-14_holdings.csv`) is in thousands; the very next filing, `period_end_date=2022-12-31` (`baker-bros_2023-02-14_holdings.csv`), is in whole dollars — an exact match to the rule's effective date, with no partial/mixed filings at the boundary.

**Confirmed downstream damage** (from a same-position sanity check on a security held unchanged across the boundary — AbCellera Biologics, CUSIP `00288U106`, 10,450,180 shares held through the transition):
- `utils/csv_data.py`'s `get_all_filings()` sums raw `value` into `total_value`, shown as "AUM ($B)" on the Signals page — wrong by 1000x for every one of the 32 filings before the 2022-12-31 period (roughly two-thirds of this fund's 46-filing history).
- `utils/data_processing.py`'s `compute_and_save_qoq_changes()` computes `value_delta_pct` by diffing raw `value` between adjacent quarters — for the one quarter-pair spanning the boundary (Q3 2022 → Q4 2022), every single held position gets a nonsensical ~1000x "change."
- Weight-based figures (top-N selection, `qoq_weight_delta` in basis points) are **not** affected — those divide `value` by that same filing's own total, so the scale cancels out within a single file. Only cross-file dollar comparisons break.
- The existing Dashboard portfolio-value line (`utils/holdings_operations.py`) is also unaffected — it reprices via `shares × Yahoo Finance close price`, never reading the 13F `value` field at all. That's a separate, independent pipeline; it was never a fix for this bug, just accidentally immune to it.

`scrapers/sec_edgar.py:185` currently has a comment claiming `# Value already in correct scale` — true only for filings scraped after the 2023 rule change, false for the majority of the historical archive.

**Explicitly out of scope:** any change to how `value` is *used* downstream (weight calculation, strategy selection, the price-based portfolio valuation pipeline) — none of that needs to change. This project only corrects the raw and derived `value` figures at the source.

---

## Components

### 1. `normalize_13f_value()` — the single source of truth for the rule

New module-level function in `scrapers/sec_edgar.py`:

```python
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
```

The `str()` coercion happens inside the function, not at each call site — the backfill script reads `period_end_date` back out of a CSV via pandas, which could in principle infer a non-string dtype, so every caller gets this protection for free rather than needing to remember it. The empty/missing guard matters for the same reason: an empty string sorts before `"2022-12-31"`, so without the guard a missing value would be wrongly scaled ×1000. No filing in the current archive is missing it, but the guard is one line and closes a real footgun.

(String comparison is otherwise safe here — a well-formed `period_end_date` is always an ISO `YYYY-MM-DD` string, which sorts identically to date comparison.)

Every writer of 13F holdings data calls this one function, from a single choke point (Component 2) — no second implementation of the rule anywhere.

### 2. Scraper fix — normalize inside the shared fetch method, not at each call site

**There are two writers of 13F holdings to CSV, not one:** `scrapers/sec_edgar.py`'s `fetch_and_save_filings()`, and a second, hand-rolled copy of the same metadata-attaching loop in `utils/fund_operations.py` (around lines 358-378, comment: "same logic as fetch_and_save_filings") — reachable from the dashboard's Admin page via `pull_latest_13fs_all_funds()`. Both call `SECEdgarScraper.get_13f_holdings(cik, accession_number)` directly and then attach `portfolio_id`/`filing_date`/`period_end_date` themselves. Fixing only `fetch_and_save_filings()` would leave the `fund_operations.py` path — and any future third caller — free to reintroduce the bug.

The robust fix is to normalize inside `get_13f_holdings()` itself, since that's the one method both current call sites (and any future one) already go through to get holdings data at all. It currently has no `period_end_date` parameter — but both call sites already have `period_end`/`filing['report_date']` in scope at the point they call it, so threading it in is a small, natural change:

```python
def get_13f_holdings(self, cik: str, accession_number: str, period_end_date: str) -> list:
    """Parse holdings from a 13F information table, with value normalized to whole dollars."""
    ...
    holdings = self._parse_info_table(response.text)
    for holding in holdings:
        holding['value'] = normalize_13f_value(holding['value'], period_end_date)
    return holdings
```

(Both existing early-return paths — `return []` when the info table can't be found — are unaffected; there's nothing to normalize when there are no holdings.)

Update both call sites to pass the period end date they already have:
- `scrapers/sec_edgar.py`'s `fetch_and_save_filings()`: `self.get_13f_holdings(cik, filing['accession_number'], period_end)`
- `utils/fund_operations.py`'s new-filings loop: `scraper.get_13f_holdings(cik, filing['accession_number'], period_end)`

Neither call site needs its own `normalize_13f_value()` call anymore — holdings come back already normalized. Each still separately sets `holding['period_end_date'] = period_end` afterward, unchanged.

Also correct the stale comment at line 185 (`# Value already in correct scale`) — the raw XML value is only normalized in `get_13f_holdings()`, after `_parse_info_table()` returns, not at parse time.

This makes every future scrape — through either call site, live incremental or a from-scratch historical backfill — correct with no separate correction step, and closes the door on a third caller reintroducing the bug.

### 3. One-time backfill script (`scripts/backfill_13f_value_scale.py`)

Corrects the 32 already-scraped files for periods before 2022-12-31. Must be idempotent (safe to re-run) and must not risk permanent data loss on the gitignored, non-git-tracked `data/` directory.

**Design for idempotency and safety:**

1. If `data/raw/13f_filings_backup/` does not already exist: copy every file from `data/raw/13f_filings/` into a fresh temp directory (`data/raw/13f_filings_backup.tmp/`) first, then rename the temp directory to `13f_filings_backup/` only after every file has copied successfully. The rename is what makes this atomic — a crash or interruption partway through the copy leaves an orphaned `.tmp` directory and no `13f_filings_backup/`, so the next run starts the backup over from scratch rather than trusting a partial snapshot. Never treat a `.tmp` directory as a valid backup.
2. This snapshot is taken **once**, from whatever files exist in `data/raw/13f_filings/` at the time the script first runs. A re-run never overwrites an existing (fully-renamed) backup, so the backup always reflects that original one-time state regardless of how many times the script runs afterward — but this also means any filing files added to the live directory *after* the first run are invisible to this script, since it iterates the backup, not the live directory. Acceptable for a one-time migration of the current archive; not a general-purpose repair tool.
3. For every file in the **backup** (not the live directory — reading from the immutable snapshot every time is what makes correction idempotent by construction: even a repeated run always starts from the same untouched source, never from a previously-corrected file):
   - Load the CSV.
   - Apply `normalize_13f_value(row.value, row.period_end_date)` per row (per-row, not per-file — defensive, since the schema already carries `period_end_date` on every row and this doesn't assume all rows in a file share one period).
   - Write the result to the corresponding path in the **live** `data/raw/13f_filings/` directory, overwriting it.
4. Print a per-file summary — filename, period_end_date, row count, whether it was rescaled, and old-vs-new total `value` sum — and **also write that same summary to a timestamped file under `docs/`** (e.g. `docs/13f_value_scale_backfill_<date>.log`), not stdout alone. This is a destructive rewrite of non-version-controlled data; a durable, committed audit trail of exactly what changed matters more here than it would for a script whose output is easy to reproduce or whose input is git-tracked.

### 4. Regenerate derived tables

After the backfill completes, re-run `utils.data_processing.compute_and_save_qoq_changes("baker-bros")` to rebuild `data/processed/qoq_changes.csv`, which carries `value`, `prior_value`, and `value_delta_pct` derived from the raw files.

`scripts/consolidate_holdings.py` (`data/processed/holdings.csv`) does **not** need to be re-run: its actual output schema is `portfolio, ticker, cusip, shares, eod_date` — no value or price column at all, confirmed by inspection. That pipeline never reads 13F `value` (consistent with Component 1's Overview note that the Dashboard's price-based valuation is independent of this bug), so regenerating it would produce byte-identical output.

### 5. Verification

- **Price cross-check:** for a handful of positions with a resolved ticker and Yahoo Finance price coverage spanning the 2022-12-31 boundary (AbCellera/`00288U106` is a known-good example, held unchanged across the transition), confirm the corrected `value / shares` implies a plausible price close to the real market price on `period_end_date`, for filings on both sides of the boundary.
- **Aggregate check:** confirm `get_all_filings()`'s `total_value` for a pre-2023 filing is now ~1000x its old value, and that the QoQ `value_delta_pct` for the Q3 2022 → Q4 2022 transition is no longer an outlier (should now be in the same rough magnitude as adjacent quarters' deltas).
- **Unit test:** `normalize_13f_value()` is a pure function with no I/O — add a focused test file (`tests/test_sec_edgar.py`, new — this codebase currently has zero scraper tests) covering: a pre-boundary date gets multiplied by 1000; a post-boundary date is unchanged; the boundary date itself (`2022-12-31`) is treated as already-correct (matches the SEC rule's "effective for periods ending 2022-12-31 **and later**").

### 6. Documentation fix

`CLAUDE.md`'s Notes section currently says:

```
- Values in 13F are reported in thousands (scraper multiplies by 1000)
  - **Note**: Early filings (2020-2022 Q3) have unscaled values (in thousands)
  - Later filings (2022 Q4+) have scaled values (in dollars)
  - This inconsistency occurred when SEC scraper was updated but old files weren't regenerated
```

Replace with the accurate explanation (real SEC rule, exact boundary, and that it's now corrected):

```
- 13F values are in whole dollars. SEC's Form 13F amendment (effective for reporting
  periods ending 2022-12-31 and later) changed the required unit from thousands of
  dollars to whole dollars; filings for earlier periods were originally scraped in
  thousands and have been corrected via a one-time backfill (see
  scrapers/sec_edgar.py's normalize_13f_value()). New scrapes are normalized at
  ingestion time, so this should never need correcting again.
```

---

## Testing

- New unit test for `normalize_13f_value()` (see Verification above) — this is the only new automated test coverage in this project, and it's warranted: this is a pure function with a real historical bug behind it, unlike the strategy-tracking project's earlier decision to skip tests for spec/doc work.
- No existing tests should be affected — this project doesn't touch `utils/brokerage.py`, `utils/drift.py`, `utils/strategy_registry.py`, or `utils/security_operations.py`. Run the full suite once at the end to confirm (`pytest tests/ -v` — expect the existing 37 plus the new ones, all passing).
- The backfill script and the derived-table regeneration are verified manually (real data, real numbers), not via a test suite — consistent with how the rest of this data pipeline (which has no test coverage today) is exercised.

---

## Explicitly Out of Scope

- Any change to how downstream code *uses* `value` (weight calculation, strategy selection, drift, the price-based Dashboard valuation pipeline) — all already correct or already scale-invariant.
- Multi-fund support for the Dashboard page's missing fund selector (a separate, already-identified gap — not part of this fix).
- Broader ticker-resolution-gap remediation (the 77%→8% missing-ticker trend over time) — a separate, larger project.
- Adding a `value_scale` marker column to the CSV schema — once corrected, every file uniformly means "whole dollars," so a marker column would carry no information going forward. The one-time backfill's logged summary (Component 3) is the audit trail.
