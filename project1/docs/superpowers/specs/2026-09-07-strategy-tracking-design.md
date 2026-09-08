# Strategy Tracking: Documentation + Backtest Result Persistence

**Date:** 2026-09-07
**Status:** Approved for implementation

---

## Overview

Investigating a failing backtest surfaced that this project has done significantly more strategy design work than the codebase or docs currently show: a 4-strategy × 2-variant framework (`STRATEGY_REGISTRY` in commit `bd40951`) was built with working selector functions, then reverted in the very next commit with no recorded reason. Only one of those eight "streams" — Strategy 1, Top Holdings Equal Weight — survived, rebuilt from scratch three weeks later during the dashboard redesign, without the registry pattern or the other three selectors.

Separately, the backtest engine (`utils/strategy_engine.py`) silently overwrites the same 3 output CSVs on every run, and those CSVs live under the gitignored `data/` tree — so no backtest result has ever been kept past the next run.

Net effect: real design thinking exists, most of it is invisible except via manual git archaeology, and the one surviving strategy has been tested exactly once with no durable record of the result. This project fixes that with three durable artifacts — a narrative doc, a tracked result log, and per-run raw output — plus the minimal code and doc changes needed to populate and surface them, without touching any strategy logic itself.

**Explicitly out of scope:** reviving or backtesting Strategies 2-4. This project only makes sure that work stays visible; whether to rebuild it is a separate future decision made deliberately from `docs/STRATEGIES.md` rather than forgotten.

---

## Components

### 1. `docs/STRATEGIES.md` — narrative record (human-maintained)

One file, git-tracked, one `##` section per conceived strategy plus one for the shared risk overlay. This is the "why" — thesis and rationale — that a CSV can't hold.

**Format per strategy:**
```markdown
## Strategy N: <name>

**Status:** Conceived | Implemented | Backtested | Live
**Thesis:** <1-2 sentences — what market behavior this is trying to capture>
**Selection logic:** <how candidates are chosen>
**Weighting:** <how capital is split across selected candidates>
**Code:** <path, or commit hash + path if not currently in the tree>
**Latest result:** <one line, e.g. "-20.2% vs XBI +32.4% (2020-11 to 2026-02) — see docs/backtest_log.csv" or "Never run">
```

**Initial content** (recovered this session):

- **Strategy 1 — Top Holdings, Equal Weight.** Status: Implemented, Backtested. Top-10 Baker Bros holdings by 13F value, equal-weighted. Code: `strategies/baker_bros_top10_ew.py`. Result: -20.2% vs XBI +32.4%.
- **Strategy 2 — Top Holdings, Conviction Rank.** Status: Conceived (reverted). Same selection as #1, weighted by 13F portfolio weight itself with a 15% per-name cap instead of equal weight. Code: `utils/strategy_selectors.py` at commit `bd40951` (not in current tree). Never run.
- **Strategy 3 — Active Accumulation, Conviction Rank.** Status: Conceived (reverted). Selects positions where both QoQ weight *and* QoQ shares increased — follows what the fund is actively buying more of — weighted by magnitude of the increase. Code: same commit. Never run.
- **Strategy 4 — New Initiations, Equal Weight.** Status: Conceived (reverted). Selects brand-new 13F positions plus ≥50% QoQ share step-ups, equal-weighted; may hold fewer than 10 names. Code: same commit. Never run.
- **Risk overlay (applies to all strategies).** Hard stop -40%, relative bleed -25% return AND -15pp vs XBI, freeze at -10% + underperforming XBI, 3-month minimum hold before any sell, capacity eviction of the worst frozen position when a new entrant needs a slot and the portfolio is full. Lives in `utils/strategy_engine.py`'s `StrategyConfig` defaults, not in any strategy module — currently untested in isolation, so its own contribution to Strategy 1's result is unknown.

**Future-proofing note:** if the strategy roster grows large enough, or individual entries need much more depth than this format allows, revisit splitting into `docs/strategies/<name>.md` files at that point. Not needed yet — a single file with ~5 entries is easier to scan and keep in sync.

### 2. `docs/backtest_log.csv` — quantitative record (script-appended)

Git-tracked (lives under `docs/`, not `data/`, specifically because `data/` is entirely gitignored — a log that lived there would have the exact disappearing-history problem this project exists to fix).

**Columns:**
```
run_id, strategy, monthly_contribution, max_positions, min_hold_months, trade_day,
hard_stop_return, relative_bleed_return, relative_bleed_xbi_underperformance,
freeze_return_threshold, portfolio_id, period_start, period_end,
cumulative_invested, ending_value, portfolio_return, xbi_return, vs_xbi_pp,
active_positions, sold_positions, output_dir
```

One row per backtest run: every `StrategyConfig` param that can vary, plus every metric currently printed in the CLI summary. `output_dir` points at the matching raw-output folder (below) for drill-down. `strategy` is the module name (currently always `baker_bros_top10_ew`, but the column exists so future strategies slot in without a schema change).

### 3. `data/processed/backtest_runs/<run_id>/` — raw per-run output

One folder per run instead of one shared, overwritten set of files. `run_id` is a timestamp (`YYYY-MM-DD_HHMMSS`). Contains the same 3 CSVs the engine already produces (`positions.csv`, `transactions.csv`, `performance.csv`), just no longer destroyed by the next run. Stays gitignored like the rest of `data/` — this is regenerable bulk output, not the durable record (that's job #2).

### 4. `run_simulation()` change (`utils/strategy_engine.py`)

Scoped to one function. Verified via `grep` that nothing else in the codebase reads `STRATEGY_1_POSITIONS_CSV`/`TRANSACTIONS_CSV`/`PERFORMANCE_CSV` by path — the Research page calls `run_simulation()` directly and uses the returned DataFrames from `st.session_state`, not a re-read from disk — so this is a safe, self-contained change:

- Replace the three fixed `to_csv()` calls with writes into a new `data/processed/backtest_runs/<run_id>/` folder.
- After saving, append one row to `docs/backtest_log.csv` (creating it with a header row if it doesn't exist yet).
- `run_backtest.py`'s CLI output and argument parsing are unchanged.

### 5. `CLAUDE.md` addition

One short `## Strategies` section (a few sentences): what the strategy/backtest system is, pointing to `docs/STRATEGIES.md` for the roster and `docs/backtest_log.csv` for run history. No content duplication — consistent with the trim already applied to this file.

---

## Testing

No new automated tests. This is a documentation project plus a file-path/logging change to `run_simulation()`, which has no existing test coverage to extend. Verification is manual: run the backtest twice with different `--hard-stop` values and confirm two distinct timestamped folders exist under `data/processed/backtest_runs/` and two rows with differing params/results land in `docs/backtest_log.csv`.

---

## Explicitly Out of Scope

- Reviving Strategies 2-4's selector logic or running them through the backtest engine.
- Testing the risk overlay in isolation (e.g., a run with hard-stop/relative-bleed/freeze disabled).
- Any change to strategy *logic* — selection, weighting, or risk rules.
- A UI for browsing `backtest_log.csv` (it's a CSV; open it directly or load it in a notebook/pandas for now).
