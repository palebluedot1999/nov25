# Strategy Tracking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the project's strategy design history and backtest results durable and discoverable, without changing any strategy logic.

**Architecture:** Two new git-tracked files (`docs/STRATEGIES.md` narrative roster, `docs/backtest_log.csv` machine-appended run history) plus a small change to `utils/strategy_engine.py` so each backtest run writes to its own timestamped, gitignored output folder instead of overwriting the last one — and appends a summary row to the log. A short pointer section is added to `CLAUDE.md`.

**Tech Stack:** Python 3.12, pandas (already a project dependency — no new dependencies).

## Global Constraints

- No strategy selection/weighting/risk-rule logic changes — this project only affects documentation and *where results are saved*, per spec `docs/superpowers/specs/2026-09-07-strategy-tracking-design.md`.
- `docs/backtest_log.csv` must live under `docs/` (git-tracked), not `data/` (fully gitignored via `.gitignore`'s `data/` rule) — verified: `.gitignore` has no other pattern that would catch `docs/backtest_log.csv`.
- No new automated tests (per spec's Testing section) — verification is manual, by actually running the backtest.
- Follow the repo's existing PR-required workflow: branch off `develop`, commit, push, open a PR (direct pushes to `develop`/`main` are blocked by the repository ruleset).

---

### Task 0: Create the working branch

**Files:** none (git operations only)

- [ ] **Step 1: Sync `develop` and branch off it**

```bash
git checkout develop
git pull origin develop
git checkout -b docs/strategy-tracking
```

All commits in Tasks 1-3 go on this `docs/strategy-tracking` branch.

---

### Task 1: Write `docs/STRATEGIES.md`

**Files:**
- Create: `docs/STRATEGIES.md`

**Interfaces:**
- Consumes: nothing (pure documentation, no code dependencies)
- Produces: nothing consumed by other tasks — this is a standalone reference doc

- [ ] **Step 1: Create the file with the full strategy roster**

Write `docs/STRATEGIES.md` with exactly this content:

```markdown
# Strategies

Every strategy this project has conceived, whether or not it's currently implemented. The point of this file is to make sure design thinking survives even when the code doesn't — see `docs/superpowers/specs/2026-09-07-strategy-tracking-design.md` for why this exists.

Quantitative backtest results for anything marked "Backtested" live in `docs/backtest_log.csv` — one row per run, with the exact parameters used.

## Risk overlay (applies to all strategies below)

This is not itself a strategy — it's a risk-management layer in `utils/strategy_engine.py`'s `StrategyConfig` that wraps whichever strategy is being backtested. It has never been tested with itself disabled, so its own contribution to any strategy's result is currently unknown.

- **Minimum hold:** 3 months before a position is sell-eligible (freezing has no minimum hold).
- **Hard stop:** sell if a position is down ≤ -40% from its own average cost, regardless of the benchmark.
- **Relative bleed:** sell if a position is down ≤ -25% from cost *and* has underperformed XBI by ≤ -15 percentage points since entry.
- **Freeze:** stop adding new capital to a position (but keep holding it, and it can still be sold) once it's down ≥10% from cost *and* underperforming XBI. Unfreezes automatically once either condition clears.
- **Capacity eviction:** when a new 13F entrant needs a slot and the portfolio is already at its position cap, force-sell the worst-performing frozen position to make room.

## Strategy 1: Top Holdings, Equal Weight

- **Status:** Implemented, Backtested
- **Thesis:** Ride Baker Bros' highest-conviction (by reported 13F value) positions, on the assumption that a hedge fund's largest holdings reflect its strongest views.
- **Selection logic:** Top 10 Baker Bros holdings by 13F value at the most recent filing.
- **Weighting:** Equal weight across selected positions.
- **Code:** `strategies/baker_bros_top10_ew.py`
- **Latest result:** -20.2% portfolio return vs. XBI +32.4% (2020-11-30 to 2026-02-06, $1,000/month contribution). See `docs/backtest_log.csv` for the full parameter set and all runs.

## Strategy 2: Top Holdings, Conviction Rank

- **Status:** Conceived (built, then reverted same day — commit `bd40951`, reverted in `9e68388`, 2026-04-13)
- **Thesis:** Same universe as Strategy 1, but sizes positions by how much conviction Baker Bros itself expresses (13F weight) rather than flattening everything to equal weight.
- **Selection logic:** Same as Strategy 1 — top 10 by 13F value.
- **Weighting:** Weighted by 13F portfolio weight itself, capped at 15% per name (`conviction_cap` in `StrategyConfig`).
- **Code:** `select_top_holdings()` (weighting="conviction") in `utils/strategy_selectors.py` at commit `bd40951` — not in the current tree.
- **Latest result:** Never run.

## Strategy 3: Active Accumulation, Conviction Rank

- **Status:** Conceived (built, then reverted same day — commit `bd40951`, reverted in `9e68388`, 2026-04-13)
- **Thesis:** Follow what Baker Bros is actively adding to right now, rather than what they already hold a lot of — a fresh buy signal instead of a stale conviction signal.
- **Selection logic:** Positions where both QoQ weight *and* QoQ shares increased quarter-over-quarter (i.e., the fund grew both its dollar exposure and its literal share count — filters out positions that only look bigger because the stock price rose).
- **Weighting:** Weighted by magnitude of QoQ weight change, capped at 15% per name.
- **Code:** `select_active_accumulation()` in `utils/strategy_selectors.py` at commit `bd40951` — not in the current tree.
- **Latest result:** Never run.

## Strategy 4: New Initiations, Equal Weight

- **Status:** Conceived (built, then reverted same day — commit `bd40951`, reverted in `9e68388`, 2026-04-13)
- **Thesis:** Brand-new positions and big step-ups are the clearest, least-ambiguous buy signal a 13F can give — no need to guess whether a large existing holding is being trimmed or held.
- **Selection logic:** New positions (`is_new=True`) prioritized by value, plus non-new positions with a QoQ shares increase ≥50% (`step_up_threshold`). May select fewer than 10 names; does not backfill with lower-conviction names.
- **Weighting:** Equal weight.
- **Code:** `select_new_initiations()` in `utils/strategy_selectors.py` at commit `bd40951` — not in the current tree.
- **Latest result:** Never run.
```

- [ ] **Step 2: Verify the file renders sensibly**

Run: `cat docs/STRATEGIES.md` (or open it in an editor) and confirm all 5 sections (overlay + 4 strategies) are present and the markdown headers are well-formed (no broken `##`/`###` nesting).

- [ ] **Step 3: Commit**

```bash
git add docs/STRATEGIES.md
git commit -m "docs: add STRATEGIES.md strategy roster"
```

---

### Task 2: Persist backtest runs instead of overwriting them

**Files:**
- Modify: `utils/strategy_engine.py:1-37` (imports and module-level constants)
- Modify: `utils/strategy_engine.py:529-548` (`run_simulation()`'s output-saving section)

**Interfaces:**
- Consumes: `StrategyConfig` (already defined in this file, unchanged), `positions_df`/`transactions_df`/`performance_df` (already built earlier in `run_simulation()`, unchanged)
- Produces: `_append_backtest_log(run_id: str, config: StrategyConfig, performance_df: pd.DataFrame, positions_df: pd.DataFrame, output_dir: Path) -> None` — new private function, called only from within `run_simulation()`

- [ ] **Step 1: Add the `datetime` import**

In `utils/strategy_engine.py`, the current imports (lines 17-32) are:

```python
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
import sys

import pandas as pd

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from utils.csv_data import get_all_filings, load_holdings_by_date, PROCESSED_DATA_DIR
from utils.holdings_operations import get_forward_filled_prices

logger = logging.getLogger(__name__)
```

Change the `import logging` line to add a `datetime` import right after it:

```python
import logging
from datetime import datetime
from dataclasses import dataclass
from pathlib import Path
import sys
```

- [ ] **Step 2: Replace the fixed-output-path constants**

Find this block (currently lines 34-37):

```python
PRICES_FILE = PROCESSED_DATA_DIR / "prices.csv"
STRATEGY_1_POSITIONS_CSV    = PROCESSED_DATA_DIR / "strategy_1_positions.csv"
STRATEGY_1_TRANSACTIONS_CSV = PROCESSED_DATA_DIR / "strategy_1_transactions.csv"
STRATEGY_1_PERFORMANCE_CSV  = PROCESSED_DATA_DIR / "strategy_1_performance.csv"
```

Replace it with:

```python
PRICES_FILE = PROCESSED_DATA_DIR / "prices.csv"
BACKTEST_RUNS_DIR = PROCESSED_DATA_DIR / "backtest_runs"
BACKTEST_LOG_CSV = PROJECT_ROOT / "docs" / "backtest_log.csv"
BACKTEST_LOG_COLUMNS = [
    "run_id", "strategy", "monthly_contribution", "max_positions", "min_hold_months",
    "trade_day", "hard_stop_return", "relative_bleed_return",
    "relative_bleed_xbi_underperformance", "freeze_return_threshold", "portfolio_id",
    "period_start", "period_end", "cumulative_invested", "ending_value",
    "portfolio_return", "xbi_return", "vs_xbi_pp", "active_positions",
    "sold_positions", "output_dir",
]
```

(No other code in the repo references `STRATEGY_1_POSITIONS_CSV`, `STRATEGY_1_TRANSACTIONS_CSV`, or `STRATEGY_1_PERFORMANCE_CSV` — verified by `grep -rn` across the whole codebase — so removing them is safe.)

- [ ] **Step 3: Add the `_append_backtest_log` function**

Add this new function directly above `run_simulation` (i.e., just before the `# ---... Main simulation ...---` section header, or immediately above `def run_simulation`):

```python
def _append_backtest_log(
    run_id: str,
    config: StrategyConfig,
    performance_df: pd.DataFrame,
    positions_df: pd.DataFrame,
    output_dir: Path,
) -> None:
    """Append one summary row for this run to docs/backtest_log.csv.

    Creates the file with a header row if it doesn't exist yet. No-ops if
    performance_df has no data (e.g. cumulative_invested never went positive).
    """
    invested = performance_df[performance_df["cumulative_invested"] > 0]
    if invested.empty:
        return

    first = invested.iloc[0]
    last = performance_df.iloc[-1]

    row = {
        "run_id": run_id,
        "strategy": "baker_bros_top10_ew",
        "monthly_contribution": config.monthly_contribution,
        "max_positions": config.max_positions,
        "min_hold_months": config.min_hold_months,
        "trade_day": config.trade_day,
        "hard_stop_return": config.hard_stop_return,
        "relative_bleed_return": config.relative_bleed_return,
        "relative_bleed_xbi_underperformance": config.relative_bleed_xbi_underperformance,
        "freeze_return_threshold": config.freeze_return_threshold,
        "portfolio_id": config.portfolio_id,
        "period_start": first["date"],
        "period_end": last["date"],
        "cumulative_invested": last["cumulative_invested"],
        "ending_value": last["portfolio_value"],
        "portfolio_return": round(last["portfolio_return"], 6),
        "xbi_return": round(last["xbi_return"], 6),
        "vs_xbi_pp": round((last["portfolio_return"] - last["xbi_return"]) * 100, 2),
        "active_positions": int((positions_df["status"] == "active").sum()) if not positions_df.empty else 0,
        "sold_positions": int((positions_df["status"] == "sold").sum()) if not positions_df.empty else 0,
        "output_dir": str(output_dir.relative_to(PROJECT_ROOT)).replace("\\", "/"),
    }

    log_row_df = pd.DataFrame([row], columns=BACKTEST_LOG_COLUMNS)
    write_header = not BACKTEST_LOG_CSV.exists()
    BACKTEST_LOG_CSV.parent.mkdir(parents=True, exist_ok=True)
    log_row_df.to_csv(BACKTEST_LOG_CSV, mode="a", header=write_header, index=False)
```

- [ ] **Step 4: Replace the output-saving section of `run_simulation()`**

Find this block (currently lines 529-548, the end of `run_simulation`):

```python
    # --- Build output DataFrames ---
    latest_date = xbi_trading_dates[-1]
    print(f"\nBuilding output DataFrames (as of {latest_date})...")

    positions_df = _build_positions_df(positions, price_lookup, xbi_prices, latest_date, config)
    transactions_df = pd.DataFrame(transactions) if transactions else pd.DataFrame(
        columns=["date", "ticker", "company_name", "action", "shares", "price", "dollar_amount", "reason"]
    )
    performance_df = pd.DataFrame(daily_perf)

    # Save CSVs
    positions_df.to_csv(STRATEGY_1_POSITIONS_CSV, index=False)
    transactions_df.to_csv(STRATEGY_1_TRANSACTIONS_CSV, index=False)
    performance_df.to_csv(STRATEGY_1_PERFORMANCE_CSV, index=False)

    print(f"  Positions:    {len(positions_df)} rows -> {STRATEGY_1_POSITIONS_CSV.name}")
    print(f"  Transactions: {len(transactions_df)} rows -> {STRATEGY_1_TRANSACTIONS_CSV.name}")
    print(f"  Performance:  {len(performance_df)} rows -> {STRATEGY_1_PERFORMANCE_CSV.name}")

    return positions_df, transactions_df, performance_df
```

Replace it with:

```python
    # --- Build output DataFrames ---
    latest_date = xbi_trading_dates[-1]
    print(f"\nBuilding output DataFrames (as of {latest_date})...")

    positions_df = _build_positions_df(positions, price_lookup, xbi_prices, latest_date, config)
    transactions_df = pd.DataFrame(transactions) if transactions else pd.DataFrame(
        columns=["date", "ticker", "company_name", "action", "shares", "price", "dollar_amount", "reason"]
    )
    performance_df = pd.DataFrame(daily_perf)

    # Save to a run-specific folder so results aren't overwritten by the next run
    run_id = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    output_dir = BACKTEST_RUNS_DIR / run_id
    output_dir.mkdir(parents=True, exist_ok=True)

    positions_csv = output_dir / "positions.csv"
    transactions_csv = output_dir / "transactions.csv"
    performance_csv = output_dir / "performance.csv"

    positions_df.to_csv(positions_csv, index=False)
    transactions_df.to_csv(transactions_csv, index=False)
    performance_df.to_csv(performance_csv, index=False)

    print(f"  Positions:    {len(positions_df)} rows -> {positions_csv}")
    print(f"  Transactions: {len(transactions_df)} rows -> {transactions_csv}")
    print(f"  Performance:  {len(performance_df)} rows -> {performance_csv}")

    _append_backtest_log(run_id, config, performance_df, positions_df, output_dir)
    print(f"  Logged run {run_id} to {BACKTEST_LOG_CSV}")

    return positions_df, transactions_df, performance_df
```

- [ ] **Step 5: Run the backtest once with default parameters**

```bash
source .venv/Scripts/activate
python scripts/run_backtest.py
```

Expected: completes as before, but the final lines print a path like `data/processed/backtest_runs/2026-09-07_193712/positions.csv` (not the old fixed filename), plus a new `Logged run ... to ...docs/backtest_log.csv` line.

- [ ] **Step 6: Run the backtest again with a different hard-stop threshold**

```bash
python scripts/run_backtest.py --hard-stop -0.30
```

Expected: completes, prints a **different** run folder path (new timestamp) than Step 5.

- [ ] **Step 7: Verify both runs persisted independently**

```bash
ls data/processed/backtest_runs/
```

Expected: two distinct timestamped subfolders, each containing `positions.csv`, `transactions.csv`, `performance.csv`.

```bash
python -c "import pandas as pd; df = pd.read_csv('docs/backtest_log.csv'); print(df[['run_id', 'hard_stop_return', 'portfolio_return', 'vs_xbi_pp']])"
```

Expected: two rows, one with `hard_stop_return` = -0.4 (the default) and one with -0.3, with their own (likely different) `portfolio_return`/`vs_xbi_pp` values. This confirms the log isn't being overwritten and correctly reflects the parameters used in each run.

- [ ] **Step 8: Commit**

```bash
git add utils/strategy_engine.py docs/backtest_log.csv
git commit -m "feat: persist backtest runs to timestamped folders + docs/backtest_log.csv"
```

Note: `docs/backtest_log.csv` will already contain the two test rows from Steps 5-6 — that's fine, they're real runs and a reasonable way to seed the log. Do **not** commit anything under `data/processed/backtest_runs/` — it's covered by the existing `data/` entry in `.gitignore` and `git status` should not show it as untracked.

---

### Task 3: Point `CLAUDE.md` at the new docs

**Files:**
- Modify: `CLAUDE.md`

**Interfaces:**
- Consumes: nothing
- Produces: nothing consumed by other tasks

- [ ] **Step 1: Insert a new `## Strategies` section**

In `CLAUDE.md`, find the `## Design Decisions` section (a bullet list ending with `- **Data fetched on-demand when dashboard loads** (no background scheduler)`), immediately followed by `## What's Working`. Insert a new section between them:

```markdown
## Strategies

The strategy/backtest system (`strategies/`, `utils/strategy_registry.py`, `utils/strategy_engine.py`, `utils/drift.py`) turns a fund's 13F holdings into target weights, backtests them, and drives the Trades/Research pages. See `docs/STRATEGIES.md` for the full roster of every strategy conceived (including ones that were built and later reverted) and `docs/backtest_log.csv` for every backtest run's parameters and results.

```

- [ ] **Step 2: Verify placement**

```bash
grep -n "^## " CLAUDE.md
```

Expected: `## Strategies` appears exactly once, between `## Design Decisions` and `## What's Working`.

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: point CLAUDE.md at STRATEGIES.md and backtest_log.csv"
```

---

### Task 4: Open the PR

**Files:** none (git/GitHub operations only)

- [ ] **Step 1: Push the branch**

```bash
git push -u origin docs/strategy-tracking
```

- [ ] **Step 2: Open a PR against `develop`**

```bash
gh pr create --base develop --title "docs: strategy tracking system (STRATEGIES.md + backtest_log.csv)" --body "Implements docs/superpowers/specs/2026-09-07-strategy-tracking-design.md. Adds docs/STRATEGIES.md (full strategy roster, including reverted ones), persists backtest runs to timestamped folders instead of overwriting them, and appends run summaries to docs/backtest_log.csv. No strategy logic changed."
```

- [ ] **Step 3: Report the PR URL to the user for review.**
