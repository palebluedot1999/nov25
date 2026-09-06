---
name: dashboard-feature-reference
description: Reference for how four Data Management / Fund Tracking dashboard features work internally (View Securities, Add New Security, Bulk Metadata Fetch, QoQ Analytics) — use when modifying, debugging, or explaining these specific features.
---

### View Securities Section
Prominent display of all securities with full metadata in Data Management page:

**What it is:**
- Single master table combining CUSIP cache + security metadata
- File: `data/processed/securities.csv`
- 162 securities total (161 holdings + XBI benchmark)
- 32 columns: CUSIP, ticker, company_name, sector, industry, + 27 metadata fields
- **Displayed in bordered container box** for easy visibility
- Shows "Number of Securities" metric at top
- Column selector expander labeled "Columns" for customizing view
- Export to CSV button included

**How to view:**
- Navigate to Data Management page
- "View Securities" section is always visible (not collapsed)
- Default columns shown: ticker, company_name, sector, industry, market_cap, pe_ratio
- Expand "Columns" to select additional columns from all 32 available
- Click "Export Securities to CSV" to download full table

**Location:** Data Management page → "View Securities" section (always visible)
**Backend:** `utils/security_consolidation.py` + `scripts/consolidate_securities.py`
**Data Flow:** `cusip_cache.csv` + `security_metadata.csv` → LEFT JOIN → `securities.csv`

### Add New Security Feature
**One-click workflow** for adding securities with automatic data fetching:

**How it works:**
1. Enter ticker symbol (e.g., "MSFT") or CUSIP in the form
2. Click **"Execute"** button (primary blue button)
3. **Automatically executes full pipeline** (~7-10 seconds):
   - Resolves CUSIP ↔ Ticker via OpenFIGI API
   - Fetches 5-year price history (2020-01-01 to present)
   - Fetches 31 metadata fields from Yahoo Finance
   - Consolidates into master securities table
4. Shows detailed results with expandable step-by-step status
5. **Immediately visible** in View Securities table below

**UI Design:**
- **Bordered container box** for clear visual separation
- Caption: "Automatically fetch prices and metadata for a new security"
- Two input fields: Ticker (required) and CUSIP (optional)
- Single **"Execute"** button that runs entire workflow
- Progress spinner during operation
- Success/error messages with detailed step breakdown

**Resolution Logic:**
- **CUSIP → Ticker**: Auto-resolved via OpenFIGI API (primary use case for 13F filings)
- **Ticker → CUSIP**: Cache lookup only (prompts for manual entry if not found)
- **Both provided**: Added directly to cache
- OpenFIGI and Yahoo Finance APIs don't provide CUSIP data (proprietary)

**Error Handling:**
- Graceful partial failures (continues even if price/metadata fetch fails)
- Shows what succeeded/failed with detailed error messages
- Manual CUSIP entry prompt if ticker lookup fails

**Location:** Data Management page → "Add New Security" section (top, always visible)
**Backend:** `utils/security_operations.py` → `add_security_with_full_data()`
**Cache:** `data/raw/cusip_cache.csv` (162 entries)
**Orchestration:** Chains `add_security_to_cache()` + `fetch_incremental_prices()` + `fetch_security_metadata()` + `consolidate_securities()`

### Bulk Metadata Fetch Feature
Background metadata fetching for all securities with real-time progress tracking:

**How it works:**
- Expand **"Bulk Operations (Advanced)"** section
- Click "Fetch Metadata Now" button
- Runs in background via `scripts/background_metadata_fetch.py`
- Fetches 31 fundamental fields for all 162 securities from Yahoo Finance
- Progress bar updates every 2 seconds
- Takes ~1-2 minutes (0.5s rate limit between requests)
- Status tracked in `data/raw/metadata_fetch_status.json`

**After completion:**
- Click "Consolidate Securities" to merge into master table
- View results in "View Securities" section

**Use case:**
- Bulk updating metadata for all existing securities
- For single security additions, use "Add New Security" one-click workflow instead

**Location:** Data Management page → "Bulk Operations (Advanced)" → "Bulk Metadata Fetch"
**Backend:** `scripts/background_metadata_fetch.py` + `utils/metadata_operations.py`

**31 Data Fields Fetched:**
- **Company Info**: Name, sector, industry, website, business summary
- **Market Data**: Market cap, beta, shares outstanding, float shares, exchange
- **Valuation**: P/E ratio, forward P/E, price-to-book, dividend yield
- **Financial**: Revenue, EBITDA, profit margin, operating margin, ROE, ROA
- **Balance Sheet**: Debt-to-equity, current ratio
- **Institutional**: Held by institutions/insiders, short interest, short ratio
- **Dividends**: Rate, payout ratio
- **Metadata**: Last updated timestamp

**Features:**
- Bulk fetch for all securities in CUSIP cache
- Automatic updates and merging (keeps latest)
- Rate limiting to respect API limits
- Used for sector allocation, valuation analysis, portfolio insights

**Files:**
- **Raw Data**: `data/raw/security_metadata.csv` (161 securities, 31 fields)
- **Processed Data**: `data/processed/securities.csv` (162 securities with CUSIP + metadata merged)
- **Status File**: `data/raw/metadata_fetch_status.json` (background fetch progress)
- **Scripts**:
  - Background: `python scripts/background_metadata_fetch.py`
  - Interactive: `python scripts/fetch_security_metadata.py`
- **Backend**: `utils/metadata_operations.py`

**Current coverage:** 160 securities with metadata, 2 without (newly added CUSIPs)
**Sector breakdown:** Predominantly Healthcare/Biotechnology sector

### QoQ Analytics on Fund Tracking Page
Quarter-over-quarter change metrics on the Fund Tracking holdings table.

**Columns shown (adjacent to the column they describe):**
- **Shares → QoQ Shares Δ%**: Percent change in shares held vs prior quarter (e.g. `+12.34%`)
- **Value ($M) → QoQ Value Δ%**: Percent change in 13F-reported value vs prior quarter
- **Weight (%) → QoQ Weight Δ**: Weight change in **basis points** (e.g. `+125bp`), per Bloomberg/FactSet convention

**Behaviour:**
- Auto-computed on Fund Tracking page load if `qoq_changes.csv` is missing/stale for the selected period (runs ~2s spinner, then instant on reload)
- "NEW" shown for positions not present in prior quarter
- "—" shown for the earliest available filing (no prior quarter)
- CSV export also includes absolute deltas (`QoQ Shares Δ`, `QoQ Value Δ`)

**Manual re-computation:**
- Data Management → Bulk Operations (Advanced) → "Compute QoQ Changes" (per-fund button)

**Key files:**
- **Data**: `data/processed/qoq_changes.csv` — columns: portfolio_id, filing_date, prior_filing_date, period_end_date, cusip, ticker, shares, prior_shares, shares_delta, shares_delta_pct, value, prior_value, value_delta_pct, weight_13f, prior_weight_13f, qoq_weight_delta, is_new
- **Compute**: `utils/data_processing.py` → `compute_and_save_qoq_changes(portfolio_id)`
- **Load**: `utils/csv_data.py` → `load_qoq_changes(portfolio_id, filing_date)`
- **Dashboard**: `dashboard/pages/2_Fund_Tracking.py`

**Number formatting conventions (Bloomberg-style):**
- Shares: comma-separated integers (`27,525,640`)
- Price: `$45.23` with commas for large values
- Value: 2 decimal places in $M (`138.45`)
- Weight: 2 decimal places in % (`5.23`)
- Δ%: always 2 decimal places with sign (`+12.34%`)
- Weight Δ: integer basis points with sign (`+125bp`)
