# Security Reference Data — Design Spec

**Date:** 2026-09-08
**Status:** Approved for implementation planning
**Author:** Claude Sonnet 5 (session_01FFaEjmTxb9upSimabpBAvL)

---

## 1. Problem

13F filings identify every position by **CUSIP**. The dashboard, price joins,
QoQ analytics, and strategies all key on **ticker**. The bridge between the two
is incomplete, and the daily-holdings pipeline covers the gap by silently
dropping rows.

Measured against the current data (46 filings, 2015-02-17 → 2026-05-15):

| Layer | Unique CUSIPs | Ticker coverage |
|---|---|---|
| `data/raw/13f_filings/*.csv` (5,120 position-rows) | **490** | 2,812 rows blank (54.9%); **303 CUSIPs never carry a ticker in any filing** |
| `data/raw/cusip_cache.csv` | 199 | 303 raw CUSIPs absent from cache |
| `data/processed/securities.csv` | 166 | 335 raw CUSIPs absent |
| `data/processed/holdings.csv` | **155** | 0 blank — unresolved rows are dropped at `utils/holdings_operations.py:174` (`filing_df[filing_df['ticker'].notna()]`) |

Consequences:

- **~68% of securities ever held** (335 of 490 CUSIPs) never reach
  `processed/holdings.csv`, so they are invisible to the Portfolio Size page and
  any consumer of the daily table. Most are delisted / acquired biotechs
  (e.g. Acceleron `00434H108`), a few are debt CUSIPs (`00484MAA4`).
- There is **no bulk resolver**. `scrapers/sec_edgar.py` resolves one CUSIP at a
  time, only for filings it re-scrapes; `utils/cusip_mapping.py` has
  `bulk_lookup()` but nothing calls it across the filing corpus.
- The only identifiers we retain are `cusip` and `ticker`. No FIGI, ISIN,
  security type, or exchange — nothing to disambiguate a bad ticker match or to
  join against an external identifier later.

## 2. Goals / Non-goals

**Goals**

1. A single, regenerable **master reference table** — one row per distinct CUSIP
   ever seen in a 13F filing — carrying every identifier we can obtain, plus
   provenance (where each field came from) and filing-history metadata.
2. A **bulk resolver** that sweeps all filings, resolves via OpenFIGI, falls
   back to SEC `company_tickers.json` name-matching, and records what it could
   not resolve for manual triage.
3. A **committed manual-override** path so hand-resolved identifiers survive a
   fresh checkout (everything under `data/` is gitignored).
4. The daily-holdings pipeline **stops silently dropping** positions: unresolved
   positions flow through keyed by CUSIP with a `has_price` flag; downstream
   consumers get explicit guards, not surprises.
5. Documentation of the whole `data/` platform layout (§3) so the raw/processed
   contract is legible.

**Non-goals**

- Re-scraping historical 13F filings to capture new fields. The filings on disk
  are the input; this work sits downstream of the scraper.
- Parsing the SEC's official quarterly "13F securities list" PDF. Rejected in
  favour of `company_tickers.json` name-matching (same cross-check value, no PDF
  scraping).
- Folding Yahoo fundamentals into the reference table. `securities.csv` keeps
  its role; the two are joinable on `ticker` / `cusip`.
- Reworking `cusip_cache.csv` away. It stays as-is this change; a later change
  can make it a generated projection of the reference table.

## 3. Data platform organization (current + additions)

Everything lives under `data/`, which is **gitignored in full** (`.gitignore:12`,
`data/`). Each clone / worktree therefore builds its own copy. The one deviation
this spec introduces is `config/security_overrides.csv` (§5.3), committed so
manual identifier work is not lost.

Path constants: `config/settings.py` — `DATA_DIR`, `RAW_DATA_DIR = data/raw`,
`PROCESSED_DATA_DIR = data/processed`.

### 3.1 `data/raw/` — source-of-truth inputs (as scraped / fetched / entered)

| Path | Producer | Schema (columns) | Notes |
|---|---|---|---|
| `13f_filings/{portfolio}_{filing_date}_holdings.csv` | `scrapers/sec_edgar.py` | `company_name, share_class, cusip, value, shares, option_type, investment_discretion, voting_authority_sole, voting_authority_shared, voting_authority_none, ticker, portfolio_id, filing_date, period_end_date` | One file per 13F filing. 46 files, 2015-02-17 → 2026-05-15. `ticker` sparse (54.9% blank). `value` = whole dollars after the 2026-09-08 value-scale backfill. `period_end_date` is the reporting quarter. |
| `yahoo_prices/{ticker}.csv` | `scrapers/yahoo_finance.py` | `date, open, high, low, close, adj_close, volume` (+ `ticker`, `fetched_at` on write) | ~230 per-ticker OHLCV files. |
| `cusip_cache.csv` | `utils/cusip_mapping.py`, Add-Security flow | `cusip, ticker` | 199 rows. Incrementally built CUSIP→ticker map. **Superseded as a read source by `security_reference.csv`** (still written, for now). |
| `security_metadata.csv` | `utils/metadata_operations.py`, `scripts/fetch_security_metadata.py` | `ticker, company_name, sector, industry, market_cap, beta, pe_ratio, forward_pe, price_to_book, dividend_yield, dividend_rate, payout_ratio, shares_outstanding, float_shares, held_percent_institutions, held_percent_insiders, short_percent_float, short_ratio, revenue, ebitda, profit_margin, operating_margin, roe, roa, debt_to_equity, current_ratio, website, business_summary, exchange, currency, last_updated` | 167 rows. Yahoo fundamentals, keyed by ticker. |
| `portfolios.csv` | `utils/fund_operations.py`, `scripts/initialize_csv_files.py` | `id, name, portfolio_type, cik, description, benchmark, is_active` | Portfolio / fund definitions. |
| `trade_log.csv` | Trades page, strategy engine | `executed_at, strategy, ticker, action, suggested_shares, actual_shares, exec_price, total_value, notes` | Executed trades ledger. |
| `staged_trades.csv` | Trades page | `ticker, action, suggested_shares, actual_shares, exec_price, notes` | Pending/draft trades. |
| `transactions.csv` | `utils/csv_data.py` | `id, portfolio_id, ticker, cusip, transaction_date, transaction_time, transaction_type, quantity, price, fees, total_value, strategy, source, filing_date, notes, created_at` | Generic transaction ledger. |
| `brokerage_holdings.csv` | `utils/brokerage.py` (derived from `trade_log.csv`) | `ticker, shares, last_updated` | Current brokerage position snapshot. |
| `tags.csv` | dashboard | `name, tag_type, color, description` | UI tags. |
| `sec_13f_filing_periods_2026_2030.csv` | static reference | `Quarter, Start Date, End Date, Filing Deadline, Report Corresponds To` | SEC filing calendar. |
| `metadata_fetch_status.json`, `price_fetch_status.json` | background fetch scripts | job status blobs | Progress tracking for `scripts/background_*_fetch.py`. |
| **`security_identifiers.csv`** *(new, §5.1)* | `utils/security_reference.py` | `cusip, ticker, name, cik, figi, composite_figi, share_class_figi, security_type, market_sector, exch_code, source, resolved_at` | Append/upsert-by-CUSIP resolver output cache. `source ∈ {openfigi, company_tickers}`. `cik` populated only on a `company_tickers` match. |

### 3.2 `data/processed/` — derived tables (regenerated by `scripts/consolidate_*.py` / build scripts)

| Path | Producer | Schema | Notes |
|---|---|---|---|
| `holdings.csv` | `scripts/consolidate_holdings.py` → `utils/holdings_operations.py` | **current:** `portfolio, ticker, cusip, shares, eod_date` — **after this change (§6):** `portfolio, cusip, ticker, shares, filing_value, eod_date` | ~122K daily rows (forward-filled from quarterly filings). Currently drops unresolved-ticker positions **and** priced-name-during-price-gap rows (§6); §6 removes both. `name` is joined at read time, not persisted. |
| `prices.csv` | `scripts/consolidate_prices.py` | `ticker, date, open, high, low, close, adj_close, volume, source, fetched_at` | 188K+ rows. Master price table, keyed `ticker`. |
| `securities.csv` | `scripts/consolidate_securities.py` → `utils/security_consolidation.py` | `cusip, ticker, company_name, sector, industry, …29 fundamental fields…, last_updated` | 166 rows. `cusip_cache` LEFT JOIN `security_metadata` on `ticker`. Role unchanged by this spec. |
| `qoq_changes.csv` | `utils/data_processing.py` (Compute QoQ) | `portfolio_id, filing_date, prior_filing_date, period_end_date, cusip, ticker, company_name, shares, prior_shares, shares_delta, shares_delta_pct, value, prior_value, value_delta_pct, weight_13f, prior_weight_13f, qoq_weight_delta, is_new` | Per fund / quarter / CUSIP QoQ deltas. Computed from **raw per-quarter filings**, not `holdings.csv`. |
| `strategy_1_performance.csv` | `strategies/` + `utils/strategy_engine.py` | `date, portfolio_value, cumulative_invested, portfolio_return, xbi_value, xbi_return, active_positions, frozen_positions` | Backtest time series. |
| `strategy_1_positions.csv` | strategy engine | `ticker, company_name, status, entry_date, entry_price, avg_cost, shares, cost_basis, current_price, current_value, total_return, xbi_return_since_entry, relative_return_vs_xbi, days_held, sell_eligible, distance_to_hard_stop, distance_to_freeze, frozen_date, sold_date, sell_reason` | Backtest position ledger. |
| `strategy_1_transactions.csv` | strategy engine | `date, ticker, company_name, action, shares, price, dollar_amount, reason` | Backtest trades. |
| **`security_reference.csv`** *(new, §5.2)* | `scripts/build_security_reference.py` → `utils/security_reference.py` | `cusip, ticker, name, cik, isin, figi, composite_figi, share_class_figi, security_type, market_sector, exch_code, is_active, first_seen_quarter, last_seen_quarter, n_filings, resolution_source, resolution_status, built_at` | One row per distinct CUSIP in any 13F filing. The joinable master. |

### 3.3 `config/` — committed configuration

| Path | Schema | Notes |
|---|---|---|
| `config/settings.py` | — | Paths, SEC/Yahoo/OpenFIGI settings. `OPENFIGI_API_KEY` from env (currently set). |
| **`config/security_overrides.csv`** *(new, §5.3)* | `cusip, ticker, name, security_type, note` | Hand-maintained identifier overrides **and suppressions**. **Committed to git** — highest precedence in the merge. A row with blank `ticker` is a suppression: it forces `ticker=""` and caps `resolution_status` at `name_only`, beating any OpenFIGI hit. |

### 3.4 Two holdings read paths (important for §6/§7)

- **Per-quarter path** — `utils/csv_data.py::load_holdings_by_date` /
  `load_latest_holdings` read a raw `13f_filings/*.csv` directly and compute
  `weight` from `value`. Blank tickers pass through unharmed (no drop).
  Consumers: Signals page, `utils/strategy_engine.py`, `strategies/*`,
  `utils/data_processing.py` QoQ.
- **Daily consolidated path** — `utils/csv_data.py::load_processed_holdings`
  reads `processed/holdings.csv`. This is where rows are dropped, in **two**
  places inside `utils/holdings_operations.py`:
  1. `process_quarterly_filings_to_daily_holdings` (`~:175`) filters
     `filing_df[filing_df['ticker'].notna()]` — drops unresolved-ticker
     positions.
  2. `calculate_portfolio_values` (`:349`) does an **inner** merge of holdings
     against prices — silently drops any position with no forward-filled price
     on a given date, *including resolved tickers during price gaps*.
  Consumer: `dashboard/pages/1_Dashboard.py:121` (Portfolio Size /
  value-over-time), via `load_processed_holdings` + `calculate_portfolio_values`.

## 4. Approach (selected: incremental cache + consolidation)

Mirrors the existing `cusip_cache.csv` → `consolidate_securities.py` pattern:

```
data/raw/13f_filings/*.csv ─┐
                            ├─> collect_filing_cusips()  ── filing sweep (name, ticker-in-filing,
config/security_overrides.csv│                               first/last_seen, n_filings, is_active)
                            │
data/raw/security_identifiers.csv <── resolve_cusips()  ── OpenFIGI bulk  ──┐
        (upsert cache)                                     then            ├─> OpenFIGI / SEC APIs
                            │                              company_tickers ┘
                            ▼
                 build_security_reference()
                            ▼
        data/processed/security_reference.csv   (+ coverage report to docs/)
                            ▼
   utils/holdings_operations.py  ── resolve tickers, keep-by-cusip, carry
                                    filing_value, left-join prices + has_price flag
                            ▼
        data/processed/holdings.csv   ── consumed by dashboard/strategies/QoQ
```

Re-runs are cheap: `resolve_cusips()` only calls the API for CUSIPs absent from
`security_identifiers.csv` (unless `--force`). 303 unresolved CUSIPs ≈ 4 OpenFIGI
requests (≤100 jobs/request with a key).

## 5. New components

### 5.1 `data/raw/security_identifiers.csv` — resolver output cache

- Upsert by `cusip`. One row per CUSIP the resolver has *attempted and
  succeeded* on (failures are not written here; they surface in the report and
  can be added to `config/security_overrides.csv`).
- Columns: `cusip, ticker, name, cik, figi, composite_figi, share_class_figi,
  security_type, market_sector, exch_code, source, resolved_at`.
- `source ∈ {openfigi, company_tickers}`. `cik` is populated only on a
  `company_tickers` match (from `cik_str`); OpenFIGI does not return it.
- OpenFIGI field mapping (`POST /v3/mapping`, `idType=ID_CUSIP`, `exchCode=US`):
  `ticker→ticker`, `name→name`, `figi→figi`, `compositeFIGI→composite_figi`,
  `shareClassFIGI→share_class_figi`, `securityType`/`securityType2→security_type`,
  `marketSector→market_sector`, `exchCode→exch_code`.

### 5.2 `data/processed/security_reference.csv` — master reference

- One row per distinct CUSIP across all `13f_filings/*.csv`.
- Columns:

  | Column | Source | Meaning |
  |---|---|---|
  | `cusip` | filing | 9-char identifier (primary key) |
  | `ticker` | merge (§5.4) | best available ticker, or empty |
  | `name` | merge | best available issuer name |
  | `cik` | identifiers cache (`company_tickers`) | issuer CIK (**not** the fund's). Comes free with a `company_tickers.json` match (`cik_str` sits beside `title`/`ticker`); may also be filled from an override. Empty otherwise. |
  | `isin` | derived | `"US" + cusip + check_digit` (Luhn mod-10 over the 11 alphanumerics). **Only** when `cusip[0].isdigit()` — a CINS code (leading letter, non-US issuer, e.g. `G…`) is well-formed but not US-ISIN-derivable, so it yields empty, as does a malformed `cusip`. |
  | `figi`, `composite_figi` | identifiers cache | OpenFIGI FIGIs, or empty |
  | `share_class_figi` | identifiers cache | OpenFIGI share-class FIGI — the most stable cross-listing key; carried through from §5.1. |
  | `security_type` | identifiers cache / override | e.g. `Common Stock`, `Depositary Receipt`, `…Bond` |
  | `market_sector` | identifiers cache | OpenFIGI market sector (`Equity`, `Govt`, …) |
  | `exch_code` | identifiers cache | listing exchange code |
  | `is_active` | filing sweep | CUSIP appears in the most recent filing of any portfolio |
  | `first_seen_quarter` | filing sweep | min `period_end_date` containing the CUSIP |
  | `last_seen_quarter` | filing sweep | max `period_end_date` containing the CUSIP |
  | `n_filings` | filing sweep | count of filings containing the CUSIP |
  | `resolution_source` | merge | `override` \| `openfigi` \| `company_tickers` \| `filing` |
  | `resolution_status` | merge | `resolved` (ticker + FIGI) \| `ticker_only` (ticker, no FIGI) \| `name_only` (name only, low-confidence) \| `unresolved` (CUSIP + filing name only) |
  | `built_at` | build | ISO timestamp of the build run |

### 5.3 `config/security_overrides.csv` — committed manual overrides

- Columns: `cusip, ticker, name, security_type, cik, note`.
- Highest precedence in the merge. `note` is free text for the triager
  ("Acceleron — acquired by Merck 2021, XLRN delisted").
- Lives in `config/` (not `data/`) specifically so it is version-controlled.
- **Addition vs suppression:** a row with a non-blank `ticker` supplies that
  ticker (and any other non-blank fields). A row with **blank `ticker`** is a
  *suppression* — it forces `ticker=""` and caps `resolution_status` at
  `name_only` even if OpenFIGI returned a confident hit. This is how a
  recycled / delisted CUSIP with no tradable ticker is expressed; without it a
  documentation-only note row is indistinguishable from a real suppression.
- The file ships with a header comment documenting this format (it is
  hand-edited); a `docs/` sibling is optional.

### 5.4 `utils/security_reference.py` — module

- `collect_filing_cusips(filings_dir=RAW_DATA_DIR/'13f_filings') -> pd.DataFrame`
  Sweep all `*.csv`; return per-CUSIP `name` (most recent non-empty
  `company_name`), `ticker_in_filing` (most recent non-empty `ticker`),
  `first_seen_quarter`, `last_seen_quarter`, `n_filings`, `is_active`.
- `cusip_to_isin(cusip: str) -> str`
  ISIN check-digit derivation (Luhn mod-10 over the 11 alphanumerics of
  `"US" + cusip`). Returns `""` when `cusip` is malformed **or** when
  `cusip[0]` is not a digit (a CINS code — well-formed but not US-ISIN-derivable).
- `resolve_cusips(cusips: list[str], *, force=False) -> pd.DataFrame`
  For CUSIPs not already in `security_identifiers.csv` (unless `force`):
  1. OpenFIGI bulk (reuse `utils/cusip_mapping.CUSIPMapper`, extended to keep
     the full response — `figi, compositeFIGI, shareClassFIGI, securityType,
     marketSector, exchCode, name` — not just `ticker`), batched to API limits.
  2. For CUSIPs still without a ticker: `_match_company_tickers(name)` —
     normalise (`strip Inc|Corp|Ltd|LLC|COM|Common Stock|/…`, lowercase),
     `difflib.SequenceMatcher` against the `title` field of SEC
     `company_tickers.json`; accept only ≥ threshold (default 0.90), tag
     `source=company_tickers`, and capture the matched row's `cik_str` as `cik`.
     Implementation note: uses stdlib `difflib.SequenceMatcher` on normalized names, not `rapidfuzz` — avoids a new dependency.
  Upsert results into `security_identifiers.csv`; return the resolved frame.
- `build_security_reference() -> dict`
  Merge `collect_filing_cusips()` ⨝ `security_identifiers.csv` ⨝
  `config/security_overrides.csv`; apply precedence
  **override > openfigi > company_tickers > filing**; derive `isin`,
  `resolution_source`, `resolution_status`; write
  `data/processed/security_reference.csv`; return
  `{total, resolved, ticker_only, name_only, unresolved, wrote_path}`.

### 5.5 `scripts/build_security_reference.py` — CLI

- `collect → resolve (unresolved only, unless --force) → build`.
- Prints and writes a coverage report to
  `docs/security_reference_coverage_<date>.log`: counts by
  `resolution_status`, and a table of every non-`resolved` CUSIP with its
  filing `name`, `first/last_seen_quarter`, `n_filings` — the manual-triage
  worklist.
- Flags: `--force` (re-resolve all), `--no-api` (build from cache + overrides
  only).
- Wire a "Build security reference" button + a coverage metric into
  `dashboard/pages/5_Admin.py` beside the existing consolidate buttons.

## 6. Holdings pipeline change (`utils/holdings_operations.py`)

The key is `cusip` throughout. **No `security_id` column** — it would be
byte-for-byte identical to `cusip` today, so it is pure indirection; add it only
if/when a CUSIP ever needs to map to more than one security row.

1. `resolve_tickers_from_cusip_cache()` → rename to
   `resolve_tickers_from_reference()`; read
   `data/processed/security_reference.csv` (`cusip → ticker`), falling
   back to `data/raw/cusip_cache.csv` if the reference file does not exist yet.
2. **Remove drop #1** at `~:175`
   (`valid_holdings = filing_df[filing_df['ticker'].notna()]`). Every position is
   carried; `ticker` = resolved ticker or `""` (empty string, **never** `NaN` —
   see point 6).
3. `detect_position_exits` (`:76`) currently builds `set(df['ticker'].dropna())`
   at `:87-88` and, at `:212`, recovers a CUSIP from a ticker
   (`valid_holdings[valid_holdings['ticker'] == ticker]['cusip'].iloc[0]`).
   Re-key the whole function on `cusip`: compare CUSIP sets, emit exited CUSIPs,
   drop the `:212` ticker→cusip lookup entirely. A blank-ticker exit is then
   still detected.
4. **Fix drop #2** — `calculate_portfolio_values` (`:349`, note the real name is
   `calculate_portfolio_values`, not `calculate_position_values`) currently does
   `holdings_df.merge(prices_df, left_on=['ticker','eod_date'],
   right_on=['ticker','date'], how='inner')`. Change `how='inner'` → `how='left'`
   so a position with no forward-filled price on a date (unresolved ticker **or**
   a resolved ticker inside a price gap) is retained. Then:
   - `has_price` = `close.notna()`
   - `position_value` = `shares * close` where `has_price`, else `NaN`
   - the `missing_pct > 5` warning stays but is no longer a data-loss signal —
     reword it to "N position-days unpriced".
   - returned columns: `eod_date, cusip, ticker, shares, filing_value, close,
     has_price, position_value`.
5. `processed/holdings.csv` schema → `portfolio, cusip, ticker, shares,
   filing_value, eod_date`.
   - `ticker` stays persisted — it is the price-join key and keeps the file
     independently useful.
   - `filing_value` = the 13F reported dollar `value` for the position, carried
     from the source filing and forward-filled alongside `shares`. It is the
     only price-independent size signal for the now-included unpriced names (a
     delisted biotech still has a last-known 13F value); without it the
     Portfolio Size page shows those positions as a pure gap.
   - `name` is **not** persisted — it would denormalise into ~122K rows and
     drift whenever `security_reference.csv` is rebuilt without regenerating
     `holdings.csv`. `load_processed_holdings` left-joins `name` (and
     `resolution_status`) from `security_reference.csv` at read time (§7).
   - `has_price`, `close`, `position_value` are **not** persisted — the stored
     table stays price-free; they are produced by `calculate_portfolio_values`
     at consume time.
6. **Blank-ticker invariant.** `save_processed_holdings` (`:396`) casts `ticker`
   to `category` and `:400` sorts by it. A `NaN` in a categorical sort is
   fragile / order-unstable. Normalise `ticker` to `""` (not `NaN`) at the end
   of `resolve_tickers_from_reference` and assert it before the categorical
   cast, so the cast and sort are deterministic.

## 7. Downstream impact & guards

| Consumer | Reads | Change |
|---|---|---|
| `utils/csv_data.py::load_processed_holdings` | `holdings.csv` | left-join `name`, `resolution_status` from `security_reference.csv` at read time — **degrade gracefully** if that file is absent (fresh checkout before first build): return holdings with `name`/`resolution_status` empty rather than raising. Tolerate new columns; update docstring (currently promises `portfolio, ticker, cusip, shares, eod_date`). |
| `dashboard/pages/1_Dashboard.py:121` (Portfolio Size, value-over-time) | `load_processed_holdings` + `calculate_portfolio_values` | after the now-`left` price join, sum `position_value` with `.fillna(0)`; surface unpriced positions using `filing_value` as a fallback size, and show a caption "N positions unpriced — $X by last 13F value". |
| `utils/data_processing.py` QoQ | per-quarter raw filings | already value-based, blank ticker tolerated. Switch ticker/name enrichment from `cusip_cache` to `security_reference`. No drop. |
| `utils/strategy_engine.py`, `strategies/*` | `load_holdings_by_date` | target weights already value-based. Where a *tradable* ticker is required (`_select_top_holdings`, price lookups), filter explicitly on `resolution_status == 'resolved'` and log skipped names — a documented filter, not a silent `notna()`. |
| `dashboard/pages/4_Signals.py` | `load_holdings_by_date` | display `name` when `ticker` is blank; optional `resolution_status` column. |
| `dashboard/pages/5_Admin.py` | securities summary | add build button + coverage metric (§5.5). |
| `utils/security_consolidation.py` | `cusip_cache`, `security_metadata` | unchanged this spec. Optional follow-up: left-join `security_reference` first so identifier-only securities still list. |

## 8. Rollout

1. `utils/security_reference.py` + `tests/test_security_reference.py` (§9). Pure
   functions first (TDD): `cusip_to_isin`, precedence merge, filing sweep.
2. `scripts/build_security_reference.py`. Run it; commit the coverage report to
   `docs/`.
3. Triage the non-`resolved` worklist into `config/security_overrides.csv`;
   re-run until coverage is acceptable (target: every `is_active` CUSIP
   `resolved`).
4. Change `utils/holdings_operations.py` (§6 — both drops, the `cusip` re-key of
   `detect_position_exits`, `filing_value`, the blank-ticker invariant);
   regenerate `holdings.csv` via `scripts/consolidate_holdings.py`. Verify
   direction: more unique CUSIPs, priced `position_value` total rises by the
   now-included priced names, unpriced count is plausible and covered by
   `filing_value`.
5. Add §7 guards; smoke-test each dashboard page.
6. Update `CLAUDE.md`: "Key Files" (new module/script/tables), a "Data platform"
   pointer to this spec's §3, and fix stale entries noticed during this work
   (page roster is now `1_Dashboard … 5_Admin`; `data/holdings/*.csv` and
   `data/portfolios.csv` paths are now under `raw/`).

## 9. Testing

`tests/test_security_reference.py`:

- `cusip_to_isin("037833100") == "US0378331005"` (AAPL known ISIN); malformed
  input → `""`; **CINS** input `"G0692U109"` (leading letter) → `""`, not a
  bogus `"USG0692U109…"`.
- Precedence: a CUSIP present in overrides + identifiers cache + filing resolves
  to the **override** ticker with `resolution_source == "override"`.
- **Suppression:** an override row with blank `ticker` for a CUSIP that OpenFIGI
  resolves confidently → final `ticker == ""`, `resolution_status == "name_only"`.
- Filing sweep: 2-filing fixture → correct `first_seen_quarter`,
  `last_seen_quarter`, `n_filings`, `is_active`.
- `resolve_cusips` with **mocked** OpenFIGI + **mocked** `company_tickers.json`:
  OpenFIGI hit → `source=openfigi, resolution_status=resolved`; OpenFIGI miss +
  name match → `source=company_tickers, resolution_status=name_only`, and `cik`
  captured from `cik_str`; both miss → not written to cache, appears as
  `unresolved` in `build_security_reference`.

`tests/test_holdings_operations.py` (new or extended):

- **Regression for drop #1:** a filing with an unresolvable CUSIP → after
  `process_quarterly_filings_to_daily_holdings`, that `cusip` is present with
  `ticker == ""` (an empty string, not `NaN`) and a forward-filled
  `filing_value`.
- **Regression for drop #2:** a resolved ticker with a price gap on some
  `eod_date` → after `calculate_portfolio_values` the row is still present with
  `has_price == False`, `position_value` NaN (would have been dropped by the old
  inner join).
- `detect_position_exits` on two filings where an exited position has a blank
  ticker → the exit is detected (keyed on `cusip`).
- `save_processed_holdings` round-trips a frame containing blank tickers without
  a categorical/sort error.

Manual: full `scripts/build_security_reference.py` run against the real 46
filings; eyeball the coverage report; regenerate `holdings.csv` and diff the
Portfolio Size totals (expect more unique CUSIPs, higher priced total, a
non-zero unpriced-by-`filing_value` figure).

## 10. Risks / open questions

- **OpenFIGI limits** — key is set (`OPENFIGI_API_KEY`); ≤100 jobs/request,
  ≤25 requests/6 s. 303 CUSIPs ≈ 4 requests. Unauthenticated fallback (10
  jobs/request, 25/min) still completes in ~1 min.
- **Debt CUSIPs** (e.g. `00484MAA4`) — OpenFIGI may resolve these as bonds with
  no tradable equity ticker / no Yahoo price → computed `has_price = False`,
  `position_value` NaN, but a non-null `filing_value`. Expected and documented;
  they still appear in the reference table and holdings.
- **`lei` deferred** — entity-level, not security-level; free from GLEIF but
  needs its own fuzzy name-match with its own false-positive surface, and
  nothing here consumes it. A possible future column on `security_reference.csv`.
- **`sedol` excluded** — licensed (LSE), not returned by OpenFIGI, no free
  source; cannot be populated.
- **`filing_value` staleness** — it is the position's dollar value from its
  *source* 13F, forward-filled between filings (like `shares`). It does not
  track price between filings; for priced names `position_value` is the live
  figure and `filing_value` is only the fallback for unpriced ones.
- **Name-match false positives** — mitigated by a high threshold, `name_only`
  status never trusted for price joins or strategy selection, and the override
  path. Threshold is a tunable constant.
- **`security_reference.csv` is gitignored** (under `data/`) — rebuilt per
  checkout, consistent with the rest of the platform.
  `config/security_overrides.csv` is the deliberate exception so manual triage
  is not lost.
- **`cusip_cache.csv` divergence** — during the transition both files exist.
  `security_reference.csv` is authoritative for reads; `cusip_cache.csv` is
  still written by the Add-Security flow. Reconciling them (making the cache a
  projection) is explicitly deferred.

## 11. Changelog

- **2026-09-08 (initial)** — first draft.
- **2026-09-08 (review 1)** — incorporated code-verified review:
  - §3.4 / §6: named the **second** drop —
    `calculate_portfolio_values` (correct name; was mis-cited as
    `calculate_position_values`) uses `how='inner'` at `:349` and must become
    `how='left'`. Headline goal now covers both drops.
  - §6.3: `detect_position_exits` re-keyed on `cusip` including the `:212`
    ticker→cusip lookup.
  - §6: dropped the `security_id` column (byte-identical to `cusip` today).
  - §6.5: `name` no longer persisted in `holdings.csv` — joined at read time to
    avoid drift; added `filing_value` (forward-filled 13F dollars) as the
    price-independent size signal for unpriced names.
  - §6.6: blank ticker pinned to `""` (never `NaN`) for the categorical cast /
    sort in `save_processed_holdings` (`:396,400`).
  - §5.2: added `cik` (free from `company_tickers.json`) and `share_class_figi`
    (was in §5.1 cache but dropped from master); fixed `isin` derivation to gate
    on `cusip[0].isdigit()` so CINS codes yield empty.
  - §5.3: override file expresses **suppression** (blank-ticker row beats a
    confident OpenFIGI hit, caps status at `name_only`).
  - §10: `lei` deferred, `sedol` excluded, with reasons.
