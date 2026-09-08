# 13F Value Column Scale Correction

**Date:** 2026-09-08
**Status:** Approved for implementation

---

## Overview

Auditing the 13F ingestion/transform/use pipeline surfaced a silent, unflagged unit inconsistency in the `value` column of every raw 13F filing CSV in `data/raw/13f_filings/`: filings for reporting periods before 2022-12-31 report `value` in **thousands of dollars**; filings from 2022-12-31 onward report it in **whole dollars**. Nothing in the schema or code marks which regime applies to a given row.

This is not a scraper bug. It's the SEC's own June 2022 Form 13F amendment, which requires whole-dollar reporting effective for reporting periods ending 2022-12-31 and later ([Toppan Merrill](https://www.toppanmerrill.com/blog/sec-updates-edgar-on-jan-3-2023-for-form-13f-changes/); [Harvard Law/CorpGov](https://corpgov.law.harvard.edu/2022/08/06/amendments-to-form-13f/)). Verified directly in this project's data: the `period_end_date=2022-09-30` filing (`baker-bros_2022-11-14_holdings.csv`) is in thousands; the very next filing, `period_end_date=2022-12-31` (`baker-bros_2023-02-14_holdings.csv`), is in whole dollars — an exact match to the rule's effective date, with no partial/mixed filings at the boundary.

**Confirmed downstream damage** (from a same-position sanity check on a security held unchanged across the boundary — AbCellera Biologics, CUSIP `00288U106`, 10,450,180 shares held through the transition):
- `utils/csv_data.py`'s `get_all_filings()` sums raw `value` into `total_value`, shown as "AUM ($B)" on the Signals page — wrong by 1000x for every one of the 31 filings before the 2022-12-31 period (roughly two-thirds of this fund's 46-filing history).
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
    if period_end_date < "2022-12-31":
        return value * 1000
    return value
```

(String comparison is safe here — `period_end_date` is always an ISO `YYYY-MM-DD` string in this codebase, which sorts identically to date comparison.)

Both the scraper and the backfill script call this one function. No second implementation of the rule anywhere.

### 2. Scraper fix

In `scrapers/sec_edgar.py`'s `fetch_and_save_filings()`, inside the per-holding loop (currently around line 249-252):

```python
                    # Add metadata to each holding row
                    holding['portfolio_id'] = portfolio_id
                    holding['filing_date'] = filing_date
                    holding['period_end_date'] = period_end
```

add a call to normalize `value` right after `period_end_date` is set:

```python
                    # Add metadata to each holding row
                    holding['portfolio_id'] = portfolio_id
                    holding['filing_date'] = filing_date
                    holding['period_end_date'] = period_end
                    holding['value'] = normalize_13f_value(holding['value'], period_end)
```

Also correct the stale comment at line 185 (`# Value already in correct scale`) — the raw XML value is only normalized after this point, not at parse time.

This makes every future scrape — live incremental fetches or a from-scratch historical backfill — correct with no separate correction step.

### 3. One-time backfill script (`scripts/backfill_13f_value_scale.py`)

Corrects the 31 already-scraped files for periods before 2022-12-31. Must be idempotent (safe to re-run) and must not risk permanent data loss on the gitignored, non-git-tracked `data/` directory.

**Design for idempotency and safety:**

1. If `data/raw/13f_filings_backup/` does not already exist, create it and copy every file from `data/raw/13f_filings/` into it, unmodified. This snapshot is taken **once** — a re-run of the script never overwrites an existing backup, so the backup always reflects the true original raw data regardless of how many times the script runs.
2. For every file in the **backup** (not the live directory — reading from the immutable snapshot every time is what makes this idempotent by construction: even a botched or repeated run always starts from the same untouched source, never from a previously-corrected file):
   - Load the CSV.
   - Apply `normalize_13f_value(row.value, row.period_end_date)` per row (per-row, not per-file — defensive, since the schema already carries `period_end_date` on every row and this doesn't assume all rows in a file share one period).
   - Write the result to the corresponding path in the **live** `data/raw/13f_filings/` directory, overwriting it.
3. Print a per-file summary: filename, period_end_date, row count, whether it was rescaled, and old-vs-new total `value` sum.

### 4. Regenerate derived tables

After the backfill completes, re-run the existing consolidation logic so the fix reaches the dashboard instead of leaving stale cached numbers behind:

- `scripts/consolidate_holdings.py` — rebuilds `data/processed/holdings.csv`.
- `utils.data_processing.compute_and_save_qoq_changes("baker-bros")` — rebuilds `data/processed/qoq_changes.csv`.

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
- Adding a `value_scale` marker column to the CSV schema — once corrected, every file uniformly means "whole dollars," so a marker column would carry no information going forward. The one-time backfill's printed summary is the audit trail.
