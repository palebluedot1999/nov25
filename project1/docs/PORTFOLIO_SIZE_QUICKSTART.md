# Portfolio Size Analysis - Quick Start Guide

## What It Does

Calculates accurate daily portfolio values by combining:
- Quarterly 13F filings (holdings data)
- Daily price data from Yahoo Finance
- Smart forward-filling for gaps and weekends

**Result**: Track portfolio value every single day, not just quarterly filing dates.

## Getting Started

### Step 1: Generate Daily Holdings Table

**Option A - Command Line** (Recommended):
```bash
python scripts/consolidate_holdings.py
```

**Option B - Dashboard**:
1. Open dashboard: `streamlit run dashboard/app.py`
2. Navigate to "Data Management" page
3. Scroll to "Process Raw Data" section
4. Click "Consolidate Holdings" button
5. Wait ~10 seconds for processing

### Step 2: View Portfolio Size

1. Navigate to "Portfolio Size Analysis" page (sidebar)
2. Select portfolio from dropdown
3. View charts and metrics

## What You'll See

### Metrics
- **Total Portfolio Value**: Current total value (latest date)
- **Number of Positions**: Active positions (shares > 0)
- **Date Range**: 2025-01-01 to today

### Chart 1: Total Portfolio Value
- Line chart showing daily portfolio value
- Hover to see exact value on any date
- 2025 YTD only (current year)

### Chart 2: Position Breakdown
- Stacked area chart
- Top 10 positions by value + "Other" category
- Color-coded by ticker
- Shows how each position contributes to total value

### Top 10 Table
- Current holdings sorted by value
- Columns: Ticker, Shares, Price, Position Value, Weight %
- Formatted for readability

### Insights
- **YTD Performance**: % change since Jan 1, 2025
- **Average Daily Value**: Mean portfolio value YTD

## Accuracy

**Recent quarters (2024-2025)**: 4-6% error vs official 13F filings

| Quarter | Official | Calculated | Error |
|---------|----------|------------|-------|
| Q3 2025 | $13.84B | $13.23B | -4.42% |
| Q2 2025 | $10.31B | $9.86B | -4.32% |
| Q1 2025 | $9.04B | $8.58B | -5.03% |

**Why slightly under**: ~10-15% of positions have missing ticker data

## Exporting Data

Click "Export Portfolio Values to CSV" button to download:
- Date, Ticker, Shares, Close Price, Position Value
- All positions for all dates in YTD range
- CSV format (open in Excel)

## Updating Data

### When to Re-consolidate

**Triggers**:
- New 13F filing added (quarterly)
- Price data updated
- CUSIP cache updated with new tickers

**How**: Re-run consolidation script or click button in Data Management

### Automatic Updates

Holdings table does NOT auto-update. You must manually consolidate when:
- Quarterly 13F filings are added
- You want latest data reflected

## How It Works (Simple Version)

```
1. Load 13F filings (quarterly)
   Example: Q4 2024 filing says "Hold 10M shares of ABCL"

2. Forward-fill daily
   Apply those holdings every day until next filing
   Dec 31, 2024 → Hold 10M ABCL
   Jan 1, 2025 → Hold 10M ABCL
   Jan 2, 2025 → Hold 10M ABCL
   ... (until next quarter)

3. Get prices for each day
   Jan 1: ABCL closed at $3.05
   Jan 2: ABCL closed at $3.03
   Jan 3: Market closed (use Jan 2 price: $3.03)

4. Calculate position value
   Jan 1: 10M shares × $3.05 = $30.5M
   Jan 2: 10M shares × $3.03 = $30.3M
   Jan 3: 10M shares × $3.03 = $30.3M (weekend)

5. Sum all positions for total portfolio value
```

## Files Generated

- **`data/processed/holdings.csv`** (5.4 MB)
  - 118,839 daily records
  - Columns: portfolio, ticker, cusip, shares, eod_date
  - 2020-12-31 to today

## Troubleshooting

**Problem**: Page shows "Holdings data not found"
- **Solution**: Run consolidation script (Step 1)

**Problem**: Portfolio value is $0
- **Solution**: holdings.csv may be empty, re-run consolidation

**Problem**: Slow page load (>30 seconds)
- **Solution**: First load is slow (forward-fills prices), subsequent loads cached (<3s)

**Problem**: Error percentage very high (>20%)
- **Solution**: Check date - early quarters (2020-2022) have high error due to missing tickers

## Key Concepts

**Forward-Fill**: Copy last known value forward to fill gaps
- Holdings: Copy quarterly filing values daily until next quarter
- Prices: Copy last trading day price to weekends/holidays

**Position Exit**: When stock no longer in next filing
- Detected automatically
- Shares set to 0 on next quarter end date

**Position Coverage**: % of positions with price data
- Recent quarters: 80-90%
- Early quarters: 40-60%

**YTD (Year-to-Date)**: Jan 1 of current year to today
- Currently hardcoded to 2025
- Future enhancement: date range selector

## Data Management Workflow

```
1. Backfill 13F filings
   → python scripts/backfill_historical_holdings.py

2. Fetch prices
   → python scripts/fetch_all_prices.py

3. Consolidate prices
   → python scripts/consolidate_prices.py

4. Consolidate holdings
   → python scripts/consolidate_holdings.py

5. View portfolio size
   → Dashboard: Portfolio Size Analysis page
```

## Performance

- **Consolidation**: ~10 seconds (20 quarters → 118K records)
- **Page Load**: <3 seconds (after first load)
- **Export**: <1 second (generates CSV)

## Next Steps

Once comfortable with portfolio size:
- Explore YTD performance trends
- Compare position weights over time
- Export data for custom analysis
- Set up periodic re-consolidation (e.g., after quarterly filings)

## Support

For issues or questions:
- Check `docs/PORTFOLIO_SIZE_IMPLEMENTATION.md` (detailed technical docs)
- Review `CLAUDE.md` (project documentation)
- Check logs in consolidation script output
- Verify data files exist in `data/processed/`

---

**Quick Links**:
- Main docs: `CLAUDE.md`
- Technical details: `docs/PORTFOLIO_SIZE_IMPLEMENTATION.md`
- Dashboard: `streamlit run dashboard/app.py`
- Consolidation: `python scripts/consolidate_holdings.py`
