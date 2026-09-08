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
- **Code:** `strategies/baker_bros_top10_ew.py` (feeds the live strategy registry / drift / Trades page) and `_select_top_holdings()` in `utils/strategy_engine.py` (a separate implementation of the same logic, used by the backtest engine)
- **Baseline result (default parameters, hard stop -40%):** -20.2% portfolio return vs. XBI +32.4% (2020-11-30 to 2026-02-06, $1,000/month contribution). See `docs/backtest_log.csv` for the full parameter set and all runs.

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
