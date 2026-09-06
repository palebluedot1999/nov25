# Dashboard Redesign: Strategy-Driven Brokerage Interface

**Date:** 2026-05-09
**Status:** Approved for implementation

---

## Overview

Restructure the Streamlit dashboard from a portfolio tracker into a strategy-driven brokerage interface. The core loop is: check drift → stage and execute trades → evaluate strategy performance. Baker Bros 13F filings are one data input among many — not the clock driving the system.

The app should feel like a brokerage account running a systematic strategy, not a data viewer.

---

## Current State → Target State

### Pages Being Removed
| Page | Reason |
|------|--------|
| `Home.py` | Redundant with sidebar navigation |
| `1_Overview.py` | Absorbed into Dashboard |
| `5_Calendar.py` | Filing dates fold into Signals as a metadata detail |

### Pages Being Restructured
| Old Page | New Home |
|----------|----------|
| `2_Fund_Tracking.py` | Signals → Baker Bros tab |
| `6_Data_Management.py` | Admin (reorganized with tabs) |
| `7_Portfolio_Size.py` | Dashboard |
| `8_Price_Graphs.py` | Signals → Prices & Markets tab |
| `9_Strategy_1.py` | Split: Research (backtest/compare) + Trades (order staging) |

### New Navigation (5 pages)
```
Dashboard   — live strategy: drift, performance
Trades      — order staging, execution logging, history
Research    — backtest and compare strategies
Signals     — Baker Bros data + price/market explorer
Admin       — all data operations
```

---

## Page Designs

### 1. Dashboard

**Purpose:** Answer three questions instantly — what do I hold, am I drifted, how am I doing?

**Header strip:**
```
Strategy: [dropdown — independent per page]
Targets last updated: 2025-05-01  │  My last trade: 2025-05-03  │  Drift age: 6 days
```

- "Targets last updated" = when the strategy last recalculated target weights (strategy-cadence, not 13F-driven)
- "My last trade" = date I last recorded executing a trade batch in my brokerage (manually logged via Trades page)
- "Drift age" = days since my last trade

**Metrics strip:**
```
$2.4M total  │  10 positions  │  +12.3% YTD  │  +4.1% vs XBI
```

**Two-column layout:**

Left — Positions & Drift table:
- Columns: Ticker, Target weight, Actual weight, Drift (bp)
- Sorted by absolute drift descending
- Rebalance alert: "⚠ 3 positions need rebalancing → [Go to Trades]" if any position exceeds threshold
- Drift threshold is a strategy-level parameter

Right — Performance panel:
- Benchmark toggles: XBI, SPY, Baker Bros (checkboxes, all on by default)
- View toggle: Chart / Table
- Cumulative return lines for: my strategy + selected benchmarks

**Below fold — Portfolio Value Over Time:**
- View toggle: Chart / Table
- Chart: stacked area by position; Table: daily values by ticker
- Absorbed from `7_Portfolio_Size.py`

---

### 2. Trades

**Purpose:** Generate a trade order list, stage and adjust executions, log history.

**Three-stage workflow on one page:**

#### Stage 1: Configure
```
Strategy: [dropdown — independent]
Capital to deploy: [$10,300 ✎]   (pre-populated from total drift amount, editable)

▶ Strategy parameters (collapsed by default)
  [sliders for parameters exposed by the selected strategy]
```

- Capital field scales all trade sizes proportionally when changed
- Supports fixed-amount deployments (e.g., $250/month) or variable (e.g., after receiving cash)
- Sliders are strategy-level parameters only (e.g., top N, min weight, rebal threshold) — individual position overrides happen in Stage 2

#### Stage 2: Prospective Trades
```
Action  Ticker  Suggested shares  $Amount   Drift
BUY     BEAM    +142              $12,400   −110bp  [High]
SELL    ABBV    −88               $8,200    +120bp  [High]

Net capital needed: $10,300
[→ Move to staging]
```

- Updates live as sliders change
- Sorted by drift magnitude (highest priority first)
- "Move to staging" locks this list and pre-populates Stage 3

#### Stage 3: Staging Area
```
Ticker  Suggested  Actual shares  Exec price  Total
BEAM    +142        [141      ]    [$87.45  ]  $12,331
ABBV    −88         [−88      ]    [$94.10  ]  $8,281

Notes: [________________________]
[✓ Confirm execution]  [✕ Clear staging]
```

- Pre-loaded from Stage 2, all fields editable
- Actual shares can differ from suggested (partial fills, manual adjustments)
- Execution price recorded per position
- "Confirm execution" snapshots suggested vs. actual into trade history, logs "My last trade" date, updates drift on Dashboard

#### My Holdings (collapsed by default)
```
▶ MY HOLDINGS  [Edit]
  Ticker  Shares  Last updated
  ABBV    450     2025-05-03
  [Import CSV]  [Save changes]
```

- Manual entry or CSV import from brokerage export
- Partial rebalance = treat as full rebalance where some positions weren't touched

#### Trade History
```
View: [Chart] [Table]
Date        Strategy      Trades  Drift before  Drift after
2025-05-03  Top-10 EW      7      ±340bp         ±45bp
```

- Preserves suggested vs. actual shares for execution quality audit over time

---

### 3. Research

**Purpose:** Evaluate pre-coded strategies against historical data. Strategy logic is developed outside this app (with Claude, in code) and registered here as named strategies.

**Strategy selector + status badge:**
```
Strategy: [Baker Bros Top-10 EW ▼]
Status: ● Research          [Set as Live]
```

- One strategy can be Live at a time; promoting a new one demotes the previous
- "Set as Live" makes this strategy the default on Dashboard and Trades

**Two tabs:**

#### Backtest Tab
```
From: [2020-01-01]  To: [2026-05-09]  Capital: [$100,000]
[▶ Run backtest]

Total return: +42.3%  Sharpe: 1.2    Max drawdown: −18.4%
vs XBI: +8.2%         Win rate: 62%  Volatility: 14%

Benchmarks: [✓ XBI] [✓ SPY] [✓ Baker Bros]
View: [Chart] [Table]
```

#### Compare Tab
```
Strategies: [✓ Top-10 EW] [✓ Top-5 MW] [□ Sector EW]
Benchmarks: [✓ XBI] [✓ SPY] [✓ Baker Bros]
View: [Chart] [Table]

Metric         Top-10 EW   Top-5 MW   XBI     SPY
Total return   +42.3%      +38.1%     +34.1%  +28.5%
Sharpe         1.2         0.9        0.8     1.1
Max drawdown   −18.4%      −22.1%     −25.3%  −19.2%
Win rate       62%         57%        —       —
```

**What Research does NOT do:**
- No strategy builder UI (dropdowns, rule editors)
- No signal discovery
- Strategy R&D happens in conversation with Claude → code → registered as a Python strategy file

---

### 4. Signals

**Purpose:** Raw data explorer. Baker Bros holdings and price/market data, viewed as tables and charts. Used when thinking about strategy design or checking market context.

**Two tabs:**

#### Baker Bros Tab
```
Filing period: [Q1 2026 ▼]
161 holdings  │  $13.8B AUM  │  Filed 2026-03-31

▶ Holdings Table
Ticker  Shares    Value($M)  Weight  QoQ Shares Δ%  QoQ Weight Δ
ABBV    12.4M     $1,840     13.3%   +2.1%           +45bp
BEAM     8.2M     $890        6.4%   NEW             —
[Export CSV]

▶ Charts  View: [Chart] [Table]
  - Top 10 weight over time (line)
  - Portfolio concentration (pie)
  - QoQ changes: biggest buys/sells (bar)
```

- Filing calendar absorbed as metadata (filed date shown in metrics strip, not a separate page)
- QoQ data (shares Δ%, value Δ%, weight Δ bp) preserved from current Fund Tracking page

#### Prices & Markets Tab
```
Ticker(s): [ABBV ×] [BEAM ×] [XBI ×] [+ add]
Timeframe: [1M] [3M] [6M] [1Y] [3Y] [5Y] [Custom]
Compare as: [Price] [% Return]

[multi-line chart]

▶ Price Table  View: [Chart] [Table]
Date        ABBV    BEAM    XBI
2026-05-09  $136.2  $62.4   $84.1
[Export CSV]
```

- Multi-ticker support on one chart (upgraded from current single-ticker Bloomberg page)
- % Return mode normalizes prices to 100 at start date — meaningful cross-ticker comparison
- Replaces `8_Price_Graphs.py`

---

### 5. Admin

**Purpose:** Engine room for data operations. Rarely needed during daily use. Functional, not polished.

**Four tabs (replace current nested collapsibles):**

#### Data Fetch Tab
```
▶ 13F Filings
  Fund: [Baker Bros ▼]  [Fetch latest]
  Last fetched: 2026-03-31

▶ Prices
  [Fetch all prices]  [Fetch incremental]
  Status: 162 tickers │ last updated 2026-05-08
  [████████████████░░] 94%

▶ Metadata
  [Fetch all metadata]
  Status: 160/162 securities have metadata
```

#### Securities Tab
```
Total: 162  │  [Export CSV]

Add security: Ticker [____]  CUSIP [____]  [Execute]

[Full securities table with column selector]
```

#### Processing Tab
```
[Consolidate prices]      Last run: 2026-05-08
[Consolidate holdings]    Last run: 2026-05-01
[Consolidate securities]  Last run: 2026-05-08
[Compute QoQ changes]     Last run: 2026-05-01
```

- Last-run timestamps always visible so you know if data is stale before running anything
- Progress bars appear only when an operation is actively running

#### Advanced Tab
```
Batch add funds (CIK list)
[________________________]  [Process]
```

---

## Data Flow & Shared State

**Strategy selection is independent per page** — Dashboard, Trades, and Research each have their own strategy dropdown. Changing strategy on one page does not affect others.

**"My last trade" date** is written by the Trades page (on "Confirm execution") and read by the Dashboard header. Stored in `data/transactions.csv`.

**Brokerage holdings** are entered/imported on the Trades page and stored in a new file `data/brokerage_holdings.csv`. Read by Dashboard (for drift calculation) and Trades (for order generation).

**Strategy registry** — each strategy is a Python file in `strategies/`. The dropdown on Research, Trades, and Dashboard reads from this directory automatically. Each strategy exposes: name, status (Research/Live), parameters (for sliders), and a `generate_targets(date)` function.

**Drift calculation** — `target_weight - actual_weight` in basis points. Actual weight derived from brokerage holdings × current prices. Computed fresh on Dashboard and Trades page load.

---

## Number Formatting Conventions (unchanged)

- Shares: comma-separated integers (`27,525,640`)
- Price: `$45.23` with commas for large values
- Value: 2 decimal places in $M (`138.45`)
- Weight: 2 decimal places in % (`5.23%`)
- Δ%: always 2 decimal places with sign (`+12.34%`)
- Weight Δ: integer basis points with sign (`+125bp`)

---

## Out of Scope

- Brokerage API integration (future — manual CSV import is the bridge)
- Strategy builder UI (strategy R&D happens with Claude externally)
- Intraday data (daily granularity only)
- Multi-fund support beyond Baker Bros (Admin supports batch CIK, but UI is Baker Bros focused)
- Macro data ingestion (noted as future signal source, not in this redesign)
