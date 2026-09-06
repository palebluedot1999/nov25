# Dashboard Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure the Streamlit dashboard from an 8-page portfolio tracker into a 5-page strategy-driven brokerage interface (Dashboard, Trades, Research, Signals, Admin).

**Architecture:** Three new utility modules (strategy_registry, brokerage, drift) form the foundation; five new page files replace the existing eight. Old pages are deleted only after new ones are verified working. Data layer stays CSV-only throughout.

**Tech Stack:** Python 3.12, Streamlit, Pandas, Plotly, pytest

---

## File Map

**Create (utilities):**
- `utils/strategy_registry.py` — auto-discover strategies from `strategies/` dir, manage Live/Research status
- `utils/brokerage.py` — brokerage holdings CRUD, trade staging, execution logging
- `utils/drift.py` — drift calculation and trade recommendation generation
- `strategies/__init__.py`
- `strategies/baker_bros_top10_ew.py` — migrated Strategy 1 logic with `generate_targets()`

**Create (data files):**
- `data/strategy_registry.csv` — `module_name, status` (auto-created on first write)
- `data/brokerage_holdings.csv` — `ticker, shares, last_updated`
- `data/staged_trades.csv` — `ticker, action, suggested_shares, actual_shares, exec_price, notes`
- `data/trade_log.csv` — full execution history

**Create (pages):**
- `dashboard/pages/1_Dashboard.py`
- `dashboard/pages/2_Trades.py`
- `dashboard/pages/3_Research.py`
- `dashboard/pages/4_Signals.py`
- `dashboard/pages/5_Admin.py`

**Create (tests):**
- `tests/test_strategy_registry.py`
- `tests/test_brokerage.py`
- `tests/test_drift.py`

**Delete (after new pages verified):**
- `dashboard/Home.py`
- `dashboard/pages/1_Overview.py`
- `dashboard/pages/2_Fund_Tracking.py`
- `dashboard/pages/5_Calendar.py`
- `dashboard/pages/6_Data_Management.py`
- `dashboard/pages/7_Portfolio_Size.py`
- `dashboard/pages/8_Price_Graphs.py`
- `dashboard/pages/9_Strategy_1.py`

---

## Task 1: Strategy Registry

**Files:**
- Create: `strategies/__init__.py`
- Create: `strategies/baker_bros_top10_ew.py`
- Create: `utils/strategy_registry.py`
- Create: `tests/test_strategy_registry.py`

- [ ] **Step 1: Create `strategies/__init__.py` (empty)**

```python
```

- [ ] **Step 2: Create `strategies/baker_bros_top10_ew.py`**

```python
# strategies/baker_bros_top10_ew.py
STRATEGY_CONFIG = {
    "name": "Baker Bros Top-10 Equal Weight",
    "parameters": {
        "top_n": {"type": "int", "min": 1, "max": 50, "default": 10, "label": "Top N Holdings"},
        "min_weight_pct": {"type": "float", "min": 0.0, "max": 10.0, "default": 2.0, "label": "Min Weight (%)"},
        "rebal_threshold_bp": {"type": "int", "min": 10, "max": 500, "default": 50, "label": "Rebal Threshold (bp)"},
    },
}


def generate_targets(portfolio_id: str, filing_date: str | None = None, top_n: int = 10, min_weight_pct: float = 2.0, **kwargs) -> dict[str, float]:
    """Return {ticker: target_weight_pct} for the top-N equal-weight strategy."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from utils.csv_data import load_holdings_by_date, get_all_filings

    if filing_date is None:
        filings = get_all_filings(portfolio_id)
        if filings.empty:
            return {}
        filing_date = str(filings.iloc[0]["filing_date"])

    holdings = load_holdings_by_date(portfolio_id, filing_date)
    if holdings.empty:
        return {}

    top = holdings.nlargest(top_n, "value")
    n = len(top)
    if n == 0:
        return {}

    weight = 100.0 / n
    if weight < min_weight_pct:
        return {}

    return {str(row["ticker"]): round(weight, 4) for _, row in top.iterrows()}
```

- [ ] **Step 3: Create `utils/strategy_registry.py`**

```python
# utils/strategy_registry.py
import importlib.util
import pandas as pd
from pathlib import Path

STRATEGIES_DIR = Path(__file__).parent.parent / "strategies"
REGISTRY_CSV = Path(__file__).parent.parent / "data" / "strategy_registry.csv"


def _load_registry() -> pd.DataFrame:
    if not REGISTRY_CSV.exists():
        return pd.DataFrame(columns=["module_name", "status"])
    return pd.read_csv(REGISTRY_CSV)


def _save_registry(df: pd.DataFrame) -> None:
    REGISTRY_CSV.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(REGISTRY_CSV, index=False)


def _get_status(module_name: str) -> str:
    df = _load_registry()
    row = df[df["module_name"] == module_name]
    return str(row.iloc[0]["status"]) if not row.empty else "Research"


def _set_status(module_name: str, status: str) -> None:
    df = _load_registry()
    if module_name in df["module_name"].values:
        df.loc[df["module_name"] == module_name, "status"] = status
    else:
        df = pd.concat(
            [df, pd.DataFrame([{"module_name": module_name, "status": status}])],
            ignore_index=True,
        )
    _save_registry(df)


def discover_strategies() -> list[dict]:
    """Return list of strategy config dicts from strategies/ directory."""
    configs = []
    for path in sorted(STRATEGIES_DIR.glob("*.py")):
        if path.stem.startswith("_"):
            continue
        try:
            spec = importlib.util.spec_from_file_location(path.stem, path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            if not hasattr(mod, "STRATEGY_CONFIG"):
                continue
            config = mod.STRATEGY_CONFIG.copy()
            config["module"] = path.stem
            config["status"] = _get_status(path.stem)
            config["generate_targets"] = mod.generate_targets
            configs.append(config)
        except Exception:
            continue
    return configs


def set_live(module_name: str) -> None:
    """Set one strategy as Live; demote all others to Research."""
    df = _load_registry()
    df["status"] = "Research"
    if module_name in df["module_name"].values:
        df.loc[df["module_name"] == module_name, "status"] = "Live"
    else:
        df = pd.concat(
            [df, pd.DataFrame([{"module_name": module_name, "status": "Live"}])],
            ignore_index=True,
        )
    _save_registry(df)


def get_live_strategy() -> dict | None:
    """Return the Live strategy config dict, or None."""
    strategies = discover_strategies()
    live = [s for s in strategies if s["status"] == "Live"]
    return live[0] if live else None
```

- [ ] **Step 4: Write failing tests**

```python
# tests/test_strategy_registry.py
import pandas as pd
import pytest
from pathlib import Path


def test_discover_strategies_finds_baker_bros(monkeypatch, tmp_path):
    """discover_strategies() returns baker_bros_top10_ew from strategies/ dir."""
    import utils.strategy_registry as sr
    monkeypatch.setattr(sr, "REGISTRY_CSV", tmp_path / "strategy_registry.csv")
    strategies = sr.discover_strategies()
    assert len(strategies) >= 1
    modules = [s["module"] for s in strategies]
    assert "baker_bros_top10_ew" in modules


def test_discovered_strategy_has_required_keys(monkeypatch, tmp_path):
    """Each discovered strategy has name, module, status, parameters, generate_targets."""
    import utils.strategy_registry as sr
    monkeypatch.setattr(sr, "REGISTRY_CSV", tmp_path / "strategy_registry.csv")
    strategies = sr.discover_strategies()
    for s in strategies:
        assert "name" in s
        assert "module" in s
        assert "status" in s
        assert "parameters" in s
        assert callable(s["generate_targets"])


def test_default_status_is_research(monkeypatch, tmp_path):
    """A strategy with no registry entry defaults to Research status."""
    import utils.strategy_registry as sr
    monkeypatch.setattr(sr, "REGISTRY_CSV", tmp_path / "strategy_registry.csv")
    strategies = sr.discover_strategies()
    assert all(s["status"] == "Research" for s in strategies)


def test_set_live_updates_status(monkeypatch, tmp_path):
    """set_live() writes Live status; all others become Research."""
    import utils.strategy_registry as sr
    monkeypatch.setattr(sr, "REGISTRY_CSV", tmp_path / "strategy_registry.csv")
    strategies = sr.discover_strategies()
    module = strategies[0]["module"]
    sr.set_live(module)
    updated = sr.discover_strategies()
    live = [s for s in updated if s["status"] == "Live"]
    assert len(live) == 1
    assert live[0]["module"] == module


def test_set_live_demotes_previous(monkeypatch, tmp_path):
    """set_live() on a second strategy demotes the first."""
    import utils.strategy_registry as sr
    monkeypatch.setattr(sr, "REGISTRY_CSV", tmp_path / "strategy_registry.csv")
    # Manually write two entries
    pd.DataFrame([
        {"module_name": "strat_a", "status": "Live"},
        {"module_name": "strat_b", "status": "Research"},
    ]).to_csv(tmp_path / "strategy_registry.csv", index=False)
    sr.set_live("strat_b")
    df = pd.read_csv(tmp_path / "strategy_registry.csv")
    assert df[df["module_name"] == "strat_b"].iloc[0]["status"] == "Live"
    assert df[df["module_name"] == "strat_a"].iloc[0]["status"] == "Research"


def test_get_live_strategy_returns_none_when_all_research(monkeypatch, tmp_path):
    """get_live_strategy() returns None when no strategy is Live."""
    import utils.strategy_registry as sr
    monkeypatch.setattr(sr, "REGISTRY_CSV", tmp_path / "strategy_registry.csv")
    result = sr.get_live_strategy()
    assert result is None


def test_get_live_strategy_returns_live_one(monkeypatch, tmp_path):
    """get_live_strategy() returns the Live strategy after set_live()."""
    import utils.strategy_registry as sr
    monkeypatch.setattr(sr, "REGISTRY_CSV", tmp_path / "strategy_registry.csv")
    strategies = sr.discover_strategies()
    module = strategies[0]["module"]
    sr.set_live(module)
    result = sr.get_live_strategy()
    assert result is not None
    assert result["module"] == module
```

- [ ] **Step 5: Run tests — expect FAIL**

```
pytest tests/test_strategy_registry.py -v
```

Expected: most tests fail with `ModuleNotFoundError` or `AssertionError`.

- [ ] **Step 6: Run tests — expect PASS**

```
pytest tests/test_strategy_registry.py -v
```

Expected: all 7 tests pass.

- [ ] **Step 7: Commit**

```
git add strategies/ utils/strategy_registry.py tests/test_strategy_registry.py
git commit -m "feat: add strategy registry with baker_bros_top10_ew"
```

---

## Task 2: Brokerage Data Layer

**Files:**
- Create: `utils/brokerage.py`
- Create: `tests/test_brokerage.py`

- [ ] **Step 1: Create `utils/brokerage.py`**

```python
# utils/brokerage.py
import pandas as pd
from datetime import datetime
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
BROKERAGE_HOLDINGS_FILE = DATA_DIR / "brokerage_holdings.csv"
STAGED_TRADES_FILE = DATA_DIR / "staged_trades.csv"
TRADE_LOG_FILE = DATA_DIR / "trade_log.csv"

HOLDINGS_COLS = ["ticker", "shares", "last_updated"]
STAGED_COLS = ["ticker", "action", "suggested_shares", "actual_shares", "exec_price", "notes"]
LOG_COLS = ["executed_at", "strategy", "ticker", "action", "suggested_shares", "actual_shares", "exec_price", "total_value", "notes"]


def load_brokerage_holdings() -> pd.DataFrame:
    if not BROKERAGE_HOLDINGS_FILE.exists():
        return pd.DataFrame(columns=HOLDINGS_COLS)
    return pd.read_csv(BROKERAGE_HOLDINGS_FILE)


def save_brokerage_holdings(df: pd.DataFrame) -> None:
    df = df.copy()
    df["last_updated"] = datetime.now().strftime("%Y-%m-%d")
    df[HOLDINGS_COLS].to_csv(BROKERAGE_HOLDINGS_FILE, index=False)


def load_staged_trades() -> pd.DataFrame:
    if not STAGED_TRADES_FILE.exists():
        return pd.DataFrame(columns=STAGED_COLS)
    return pd.read_csv(STAGED_TRADES_FILE)


def save_staged_trades(df: pd.DataFrame) -> None:
    df[STAGED_COLS].to_csv(STAGED_TRADES_FILE, index=False)


def clear_staged_trades() -> None:
    pd.DataFrame(columns=STAGED_COLS).to_csv(STAGED_TRADES_FILE, index=False)


def load_trade_log() -> pd.DataFrame:
    if not TRADE_LOG_FILE.exists():
        return pd.DataFrame(columns=LOG_COLS)
    return pd.read_csv(TRADE_LOG_FILE)


def confirm_execution(staged_df: pd.DataFrame, strategy_name: str, notes: str = "") -> None:
    """Append staged trades to trade log, update holdings, clear staging area."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_rows = []
    for _, row in staged_df.iterrows():
        actual = float(row.get("actual_shares") if pd.notna(row.get("actual_shares")) else row["suggested_shares"])
        price = float(row.get("exec_price") if pd.notna(row.get("exec_price")) else 0)
        log_rows.append({
            "executed_at": now,
            "strategy": strategy_name,
            "ticker": row["ticker"],
            "action": row["action"],
            "suggested_shares": float(row["suggested_shares"]),
            "actual_shares": actual,
            "exec_price": price,
            "total_value": round(abs(actual) * price, 2),
            "notes": notes,
        })

    new_log = pd.DataFrame(log_rows, columns=LOG_COLS)
    if TRADE_LOG_FILE.exists():
        existing = pd.read_csv(TRADE_LOG_FILE)
        new_log = pd.concat([existing, new_log], ignore_index=True)
    new_log.to_csv(TRADE_LOG_FILE, index=False)

    # Update brokerage holdings
    holdings = load_brokerage_holdings()
    for _, row in staged_df.iterrows():
        actual = float(row.get("actual_shares") if pd.notna(row.get("actual_shares")) else row["suggested_shares"])
        ticker = str(row["ticker"])
        delta = actual if row["action"] == "BUY" else -actual
        if ticker in holdings["ticker"].values:
            holdings.loc[holdings["ticker"] == ticker, "shares"] += delta
        else:
            holdings = pd.concat(
                [holdings, pd.DataFrame([{"ticker": ticker, "shares": delta, "last_updated": now}])],
                ignore_index=True,
            )

    save_brokerage_holdings(holdings)
    clear_staged_trades()
```

- [ ] **Step 2: Write failing tests**

```python
# tests/test_brokerage.py
import pandas as pd
import pytest
from pathlib import Path


@pytest.fixture()
def brokerage(monkeypatch, tmp_path):
    import utils.brokerage as b
    monkeypatch.setattr(b, "BROKERAGE_HOLDINGS_FILE", tmp_path / "brokerage_holdings.csv")
    monkeypatch.setattr(b, "STAGED_TRADES_FILE", tmp_path / "staged_trades.csv")
    monkeypatch.setattr(b, "TRADE_LOG_FILE", tmp_path / "trade_log.csv")
    return b


def test_load_brokerage_holdings_returns_empty_df_when_no_file(brokerage):
    df = brokerage.load_brokerage_holdings()
    assert df.empty
    assert list(df.columns) == ["ticker", "shares", "last_updated"]


def test_save_and_load_brokerage_holdings(brokerage):
    df = pd.DataFrame({"ticker": ["ABBV", "BEAM"], "shares": [100.0, 200.0], "last_updated": ["", ""]})
    brokerage.save_brokerage_holdings(df)
    loaded = brokerage.load_brokerage_holdings()
    assert set(loaded["ticker"]) == {"ABBV", "BEAM"}
    assert loaded[loaded["ticker"] == "ABBV"].iloc[0]["shares"] == 100.0


def test_save_staged_and_load(brokerage):
    staged = pd.DataFrame({
        "ticker": ["BEAM"],
        "action": ["BUY"],
        "suggested_shares": [142.0],
        "actual_shares": [141.0],
        "exec_price": [87.45],
        "notes": [""],
    })
    brokerage.save_staged_trades(staged)
    loaded = brokerage.load_staged_trades()
    assert len(loaded) == 1
    assert loaded.iloc[0]["ticker"] == "BEAM"


def test_confirm_execution_updates_holdings(brokerage):
    # Start with 100 ABBV
    initial = pd.DataFrame({"ticker": ["ABBV"], "shares": [100.0], "last_updated": ["2026-01-01"]})
    brokerage.save_brokerage_holdings(initial)

    staged = pd.DataFrame({
        "ticker": ["ABBV", "BEAM"],
        "action": ["SELL", "BUY"],
        "suggested_shares": [10.0, 50.0],
        "actual_shares": [10.0, 50.0],
        "exec_price": [136.0, 62.0],
        "notes": ["", ""],
    })
    brokerage.confirm_execution(staged, strategy_name="Top-10 EW")

    holdings = brokerage.load_brokerage_holdings()
    abbv = holdings[holdings["ticker"] == "ABBV"].iloc[0]["shares"]
    beam = holdings[holdings["ticker"] == "BEAM"].iloc[0]["shares"]
    assert abbv == 90.0   # 100 - 10
    assert beam == 50.0   # 0 + 50


def test_confirm_execution_writes_trade_log(brokerage):
    staged = pd.DataFrame({
        "ticker": ["BEAM"],
        "action": ["BUY"],
        "suggested_shares": [142.0],
        "actual_shares": [141.0],
        "exec_price": [87.45],
        "notes": ["test note"],
    })
    brokerage.confirm_execution(staged, strategy_name="Top-10 EW", notes="test")
    log = brokerage.load_trade_log()
    assert len(log) == 1
    assert log.iloc[0]["ticker"] == "BEAM"
    assert log.iloc[0]["strategy"] == "Top-10 EW"


def test_confirm_execution_clears_staged_trades(brokerage):
    staged = pd.DataFrame({
        "ticker": ["BEAM"], "action": ["BUY"],
        "suggested_shares": [10.0], "actual_shares": [10.0],
        "exec_price": [87.0], "notes": [""],
    })
    brokerage.save_staged_trades(staged)
    brokerage.confirm_execution(staged, strategy_name="Top-10 EW")
    remaining = brokerage.load_staged_trades()
    assert remaining.empty
```

- [ ] **Step 3: Run tests — expect FAIL**

```
pytest tests/test_brokerage.py -v
```

Expected: fails with `ModuleNotFoundError`.

- [ ] **Step 4: Run tests — expect PASS**

```
pytest tests/test_brokerage.py -v
```

Expected: all 6 tests pass.

- [ ] **Step 5: Commit**

```
git add utils/brokerage.py tests/test_brokerage.py
git commit -m "feat: add brokerage data layer (holdings, staging, trade log)"
```

---

## Task 3: Drift Calculation

**Files:**
- Create: `utils/drift.py`
- Create: `tests/test_drift.py`

- [ ] **Step 1: Create `utils/drift.py`**

```python
# utils/drift.py
import pandas as pd


def calculate_drift(
    target_weights: dict[str, float],
    brokerage_holdings: pd.DataFrame,
    prices: pd.DataFrame,
) -> pd.DataFrame:
    """
    Compute drift between strategy targets and actual brokerage holdings.

    Args:
        target_weights: {ticker: weight_pct} from strategy.generate_targets()
        brokerage_holdings: DataFrame with columns [ticker, shares]
        prices: DataFrame with columns [ticker, close]

    Returns:
        DataFrame: ticker, target_weight, actual_weight, drift_bp, action
        Sorted by abs(drift_bp) descending.
    """
    merged = brokerage_holdings.merge(prices[["ticker", "close"]], on="ticker", how="left")
    merged["value"] = merged["shares"] * merged["close"].fillna(0)
    total_value = merged["value"].sum()

    actual_weights: dict[str, float] = {}
    if total_value > 0:
        for _, row in merged.iterrows():
            actual_weights[str(row["ticker"])] = row["value"] / total_value * 100

    all_tickers = set(target_weights) | set(actual_weights)
    rows = []
    for ticker in all_tickers:
        target = target_weights.get(ticker, 0.0)
        actual = actual_weights.get(ticker, 0.0)
        drift_bp = round((target - actual) * 100)
        if drift_bp > 0:
            action = "BUY"
        elif drift_bp < 0:
            action = "SELL"
        else:
            action = "HOLD"
        rows.append({
            "ticker": ticker,
            "target_weight": round(target, 2),
            "actual_weight": round(actual, 2),
            "drift_bp": drift_bp,
            "action": action,
        })

    df = pd.DataFrame(rows)
    df = df.sort_values("drift_bp", key=abs, ascending=False).reset_index(drop=True)
    return df


def generate_trade_recommendations(
    drift_df: pd.DataFrame,
    total_portfolio_value: float,
    prices: pd.DataFrame,
) -> pd.DataFrame:
    """
    Convert drift into suggested share counts given a total portfolio value.

    Returns:
        DataFrame: ticker, action, drift_bp, suggested_shares, delta_value, price, priority
    """
    prices_dict = dict(zip(prices["ticker"], prices["close"]))
    rows = []
    for _, row in drift_df.iterrows():
        drift_bp = row["drift_bp"]
        if drift_bp == 0:
            continue
        ticker = row["ticker"]
        target_value = total_portfolio_value * row["target_weight"] / 100
        actual_value = total_portfolio_value * row["actual_weight"] / 100
        delta_value = target_value - actual_value
        price = prices_dict.get(ticker, 0.0)
        suggested_shares = round(delta_value / price) if price > 0 else 0
        abs_drift = abs(drift_bp)
        priority = "High" if abs_drift >= 100 else ("Medium" if abs_drift >= 50 else "Low")
        rows.append({
            "ticker": ticker,
            "action": row["action"],
            "drift_bp": drift_bp,
            "suggested_shares": suggested_shares,
            "delta_value": round(delta_value, 2),
            "price": round(price, 2),
            "priority": priority,
        })

    df = pd.DataFrame(rows)
    if df.empty:
        return df
    return df.sort_values("drift_bp", key=abs, ascending=False).reset_index(drop=True)
```

- [ ] **Step 2: Write failing tests**

```python
# tests/test_drift.py
import pandas as pd
import pytest
from utils.drift import calculate_drift, generate_trade_recommendations


def make_prices(*tickers_prices):
    tickers, closes = zip(*tickers_prices)
    return pd.DataFrame({"ticker": list(tickers), "close": list(closes)})


def test_calculate_drift_no_holdings_all_buy():
    """With empty holdings, all target positions show as BUY."""
    targets = {"ABBV": 50.0, "BEAM": 50.0}
    holdings = pd.DataFrame(columns=["ticker", "shares"])
    prices = make_prices(("ABBV", 100.0), ("BEAM", 50.0))
    result = calculate_drift(targets, holdings, prices)
    assert set(result["ticker"]) == {"ABBV", "BEAM"}
    assert all(result["actual_weight"] == 0.0)
    assert all(result["action"] == "BUY")


def test_calculate_drift_perfectly_aligned():
    """Equal holdings at equal prices → zero drift."""
    targets = {"ABBV": 50.0, "BEAM": 50.0}
    holdings = pd.DataFrame({"ticker": ["ABBV", "BEAM"], "shares": [5.0, 10.0]})
    prices = make_prices(("ABBV", 100.0), ("BEAM", 50.0))
    # ABBV: 5*100=500, BEAM: 10*50=500 → each 50%
    result = calculate_drift(targets, holdings, prices)
    assert all(result["drift_bp"] == 0)
    assert all(result["action"] == "HOLD")


def test_calculate_drift_excess_position_is_sell():
    """Holding more than target produces negative drift and SELL action."""
    targets = {"ABBV": 30.0, "BEAM": 70.0}
    holdings = pd.DataFrame({"ticker": ["ABBV", "BEAM"], "shares": [5.0, 10.0]})
    prices = make_prices(("ABBV", 100.0), ("BEAM", 50.0))
    # ABBV: 500/1000=50% vs target 30% → -2000bp SELL
    result = calculate_drift(targets, holdings, prices)
    abbv = result[result["ticker"] == "ABBV"].iloc[0]
    assert abbv["drift_bp"] < 0
    assert abbv["action"] == "SELL"


def test_calculate_drift_sorted_by_abs_drift():
    """Rows are sorted by absolute drift descending."""
    targets = {"A": 90.0, "B": 10.0}
    holdings = pd.DataFrame({"ticker": ["A", "B"], "shares": [1.0, 9.0]})
    prices = make_prices(("A", 100.0), ("B", 100.0))
    # A: 100/1000=10% vs 90% → +8000bp; B: 900/1000=90% vs 10% → -8000bp
    result = calculate_drift(targets, holdings, prices)
    assert abs(result.iloc[0]["drift_bp"]) >= abs(result.iloc[1]["drift_bp"])


def test_calculate_drift_unknown_holding_shows_as_sell():
    """A holding not in targets appears with target_weight=0 and SELL action."""
    targets = {"ABBV": 100.0}
    holdings = pd.DataFrame({"ticker": ["ABBV", "EXTRA"], "shares": [5.0, 5.0]})
    prices = make_prices(("ABBV", 100.0), ("EXTRA", 100.0))
    result = calculate_drift(targets, holdings, prices)
    extra = result[result["ticker"] == "EXTRA"].iloc[0]
    assert extra["target_weight"] == 0.0
    assert extra["action"] == "SELL"


def test_generate_trade_recommendations_skips_zero_drift():
    """Positions with zero drift are excluded from recommendations."""
    drift_df = pd.DataFrame({
        "ticker": ["ABBV", "BEAM"],
        "action": ["HOLD", "BUY"],
        "target_weight": [50.0, 50.0],
        "actual_weight": [50.0, 0.0],
        "drift_bp": [0, 5000],
    })
    prices = make_prices(("ABBV", 100.0), ("BEAM", 50.0))
    result = generate_trade_recommendations(drift_df, total_portfolio_value=10000, prices=prices)
    assert "ABBV" not in result["ticker"].values
    assert "BEAM" in result["ticker"].values


def test_generate_trade_recommendations_calculates_shares():
    """Suggested shares = delta_value / price."""
    drift_df = pd.DataFrame({
        "ticker": ["BEAM"],
        "action": ["BUY"],
        "target_weight": [50.0],
        "actual_weight": [0.0],
        "drift_bp": [5000],
    })
    prices = make_prices(("BEAM", 50.0))
    result = generate_trade_recommendations(drift_df, total_portfolio_value=10000, prices=prices)
    # target_value = 10000 * 50% = 5000; actual = 0; delta = 5000; shares = 5000/50 = 100
    assert result.iloc[0]["suggested_shares"] == 100
```

- [ ] **Step 3: Run tests — expect FAIL**

```
pytest tests/test_drift.py -v
```

- [ ] **Step 4: Run tests — expect PASS**

```
pytest tests/test_drift.py -v
```

Expected: all 7 tests pass.

- [ ] **Step 5: Run full test suite to confirm no regressions**

```
pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```
git add utils/drift.py tests/test_drift.py
git commit -m "feat: add drift calculation and trade recommendation utilities"
```

---

## Task 4: Admin Page

Reorganize `6_Data_Management.py` into `5_Admin.py` using tabs instead of nested collapsibles. All utility function calls are preserved exactly — this is a layout-only change.

**Files:**
- Create: `dashboard/pages/5_Admin.py`
- (Do not delete `6_Data_Management.py` yet — wait until verified)

- [ ] **Step 1: Create `dashboard/pages/5_Admin.py`**

```python
# dashboard/pages/5_Admin.py
import sys
import time
import subprocess
import streamlit as st
import pandas as pd
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from utils.csv_data import load_portfolios, PROCESSED_DATA_DIR
from utils.price_operations import get_all_cached_tickers, get_fetch_status, save_fetch_status
from utils.security_operations import add_security_with_full_data, get_cusip_cache_summary
from utils.security_consolidation import get_securities_summary
from utils.fund_operations import parse_cik_input, batch_add_funds
from utils.metadata_operations import get_metadata_fetch_status, save_metadata_fetch_status

st.set_page_config(page_title="Admin", layout="wide")
st.title("Admin")

tab_fetch, tab_securities, tab_processing, tab_advanced = st.tabs(
    ["Data Fetch", "Securities", "Processing", "Advanced"]
)

# ── Data Fetch ─────────────────────────────────────────────────────────────────
with tab_fetch:
    st.subheader("13F Filings")
    portfolios = load_portfolios(portfolio_type="fund")
    if not portfolios.empty:
        fund_options = dict(zip(portfolios["name"], portfolios["id"]))
        selected_fund = st.selectbox("Fund", list(fund_options.keys()), key="admin_fund")
        portfolio_id = fund_options[selected_fund]
        col1, col2 = st.columns([1, 3])
        with col1:
            if st.button("Fetch latest 13Fs", key="fetch_13f"):
                from utils.fund_operations import pull_latest_13fs_all_funds
                with st.spinner("Fetching..."):
                    pull_latest_13fs_all_funds()
                st.success("Done")
    else:
        st.info("No funds configured. Add one in the Advanced tab.")

    st.divider()
    st.subheader("Prices")
    fetch_status = get_fetch_status()
    tickers = get_all_cached_tickers()
    fetched = fetch_status.get("fetched_count", 0)
    last_updated = fetch_status.get("last_updated", "Never")
    st.caption(f"{fetched}/{len(tickers)} tickers fetched · Last updated: {last_updated}")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Fetch incremental prices", key="fetch_prices_incr"):
            scripts_dir = Path(__file__).parent.parent.parent / "scripts"
            subprocess.Popen(["python", str(scripts_dir / "background_price_fetch.py")])
            st.info("Price fetch started in background. Refresh to see progress.")
    with col2:
        if st.button("Refresh status", key="refresh_price_status"):
            st.rerun()

    fetch_pct = fetched / len(tickers) if tickers else 0
    st.progress(fetch_pct)

    st.divider()
    st.subheader("Metadata")
    meta_status = get_metadata_fetch_status()
    meta_fetched = meta_status.get("fetched_count", 0)
    st.caption(f"{meta_fetched}/{len(tickers)} securities have metadata")

    if st.button("Fetch all metadata", key="fetch_meta"):
        scripts_dir = Path(__file__).parent.parent.parent / "scripts"
        subprocess.Popen(["python", str(scripts_dir / "background_metadata_fetch.py")])
        st.info("Metadata fetch started in background.")

# ── Securities ─────────────────────────────────────────────────────────────────
with tab_securities:
    summary = get_securities_summary()
    total = summary.get("total_count", 0)
    col1, col2 = st.columns([2, 1])
    with col1:
        st.metric("Securities", total)
    with col2:
        securities_path = PROCESSED_DATA_DIR / "securities.csv"
        if securities_path.exists():
            sec_df = pd.read_csv(securities_path)
            st.download_button("Export CSV", sec_df.to_csv(index=False), "securities.csv", "text/csv")

    st.subheader("Add Security")
    with st.form("add_security_form"):
        ticker_in = st.text_input("Ticker (required)")
        cusip_in = st.text_input("CUSIP (optional)")
        submitted = st.form_submit_button("Execute")
        if submitted and ticker_in:
            with st.spinner("Fetching prices and metadata..."):
                result = add_security_with_full_data(ticker_in.upper(), cusip_in or None, auto_consolidate=True)
            if result.get("success"):
                st.success(f"Added {ticker_in.upper()}")
            else:
                st.error(result.get("error", "Unknown error"))

    st.subheader("All Securities")
    if securities_path.exists():
        sec_df = pd.read_csv(securities_path)
        default_cols = ["ticker", "company_name", "sector", "industry", "market_cap", "pe_ratio"]
        available = [c for c in default_cols if c in sec_df.columns]
        with st.expander("Columns"):
            selected_cols = st.multiselect("Show columns", sec_df.columns.tolist(), default=available)
        if selected_cols:
            st.dataframe(sec_df[selected_cols], use_container_width=True)

# ── Processing ─────────────────────────────────────────────────────────────────
with tab_processing:
    scripts_dir = Path(__file__).parent.parent.parent / "scripts"

    def run_script(script_name: str, label: str):
        with st.spinner(f"Running {label}..."):
            result = subprocess.run(["python", str(scripts_dir / script_name)], capture_output=True, text=True)
        if result.returncode == 0:
            st.success(f"{label} complete")
        else:
            st.error(f"{label} failed: {result.stderr[:200]}")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Consolidate prices"):
            run_script("consolidate_prices.py", "Consolidate prices")
        if st.button("Consolidate holdings"):
            run_script("consolidate_holdings.py", "Consolidate holdings")
    with col2:
        if st.button("Consolidate securities"):
            run_script("consolidate_securities.py", "Consolidate securities")
        portfolios = load_portfolios(portfolio_type="fund")
        if not portfolios.empty:
            for _, p in portfolios.iterrows():
                if st.button(f"Compute QoQ — {p['name']}", key=f"qoq_{p['id']}"):
                    from utils.data_processing import compute_and_save_qoq_changes
                    with st.spinner("Computing..."):
                        compute_and_save_qoq_changes(p["id"])
                    st.success(f"QoQ changes computed for {p['name']}")

# ── Advanced ───────────────────────────────────────────────────────────────────
with tab_advanced:
    st.subheader("Batch Add Funds (CIK)")
    cik_text = st.text_area("CIK numbers (one per line or comma-separated)")
    start_date = st.date_input("Start date", value=pd.Timestamp("2020-01-01"))
    auto_fetch = st.checkbox("Auto-fetch prices after adding", value=True)

    if st.button("Process CIKs") and cik_text:
        ciks = parse_cik_input(cik_text)
        if ciks:
            with st.spinner(f"Adding {len(ciks)} fund(s)..."):
                batch_add_funds(ciks, str(start_date), callback=None)
            st.success(f"Added {len(ciks)} fund(s)")
        else:
            st.warning("No valid CIKs found")
```

- [ ] **Step 2: Start the app and verify Admin page loads**

```
streamlit run dashboard/Home.py
```

Navigate to Admin in the sidebar. Verify four tabs appear. Confirm all existing functionality (fetch buttons, securities table, processing buttons) works as before.

- [ ] **Step 3: Commit**

```
git add dashboard/pages/5_Admin.py
git commit -m "feat: add Admin page with tabs (replaces Data Management)"
```

---

## Task 5: Signals Page

Combines `2_Fund_Tracking.py` (Baker Bros tab) and `8_Price_Graphs.py` (Prices tab) into one page. Multi-ticker price chart replaces the single-ticker Bloomberg chart.

**Files:**
- Create: `dashboard/pages/4_Signals.py`

- [ ] **Step 1: Create `dashboard/pages/4_Signals.py`**

```python
# dashboard/pages/4_Signals.py
import sys
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from pathlib import Path
from datetime import timedelta

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from utils.csv_data import (
    load_portfolios, get_all_filings, load_holdings_by_date, load_qoq_changes, load_prices
)
from utils.data_processing import get_top_holdings_over_time, compute_and_save_qoq_changes

st.set_page_config(page_title="Signals", layout="wide")
st.title("Signals")

tab_bb, tab_prices = st.tabs(["Baker Bros", "Prices & Markets"])

# ── Baker Bros ─────────────────────────────────────────────────────────────────
with tab_bb:
    portfolios = load_portfolios(portfolio_type="fund")
    if portfolios.empty:
        st.warning("No fund portfolios found. Add one in Admin.")
        st.stop()

    portfolio_options = dict(zip(portfolios["name"], portfolios["id"]))
    portfolio_name = st.selectbox("Fund", list(portfolio_options.keys()), key="sig_fund")
    portfolio_id = portfolio_options[portfolio_name]

    filings = get_all_filings(portfolio_id)
    if filings.empty:
        st.warning("No filings found for this fund.")
        st.stop()

    filing_labels = {
        f"{row['period_end_date']} (filed {row['filing_date']})": row["filing_date"]
        for _, row in filings.iterrows()
    }
    selected_label = st.selectbox("Filing period", list(filing_labels.keys()), key="sig_period")
    filing_date = filing_labels[selected_label]

    holdings = load_holdings_by_date(portfolio_id, filing_date)
    filing_row = filings[filings["filing_date"] == filing_date].iloc[0]

    col1, col2, col3 = st.columns(3)
    col1.metric("Holdings", int(filing_row.get("num_positions", len(holdings))))
    col2.metric("AUM ($B)", f"{filing_row.get('total_value', 0) / 1e9:.2f}")
    col3.metric("Filed", filing_date)

    # Holdings table with QoQ
    st.subheader("Holdings")
    qoq = load_qoq_changes(portfolio_id, filing_date)
    if qoq.empty:
        with st.spinner("Computing QoQ changes..."):
            compute_and_save_qoq_changes(portfolio_id)
        qoq = load_qoq_changes(portfolio_id, filing_date)

    if not holdings.empty and not qoq.empty:
        display = holdings.merge(
            qoq[["cusip", "shares_delta_pct", "value_delta_pct", "qoq_weight_delta", "is_new"]],
            on="cusip", how="left"
        )
        display["QoQ Shares Δ%"] = display.apply(
            lambda r: "NEW" if r.get("is_new") else (f"{r['shares_delta_pct']:+.2f}%" if pd.notna(r.get("shares_delta_pct")) else "—"), axis=1
        )
        display["QoQ Weight Δ"] = display.apply(
            lambda r: "NEW" if r.get("is_new") else (f"{int(r['qoq_weight_delta']):+d}bp" if pd.notna(r.get("qoq_weight_delta")) else "—"), axis=1
        )
        cols = ["ticker", "company_name", "shares", "value", "weight", "QoQ Shares Δ%", "QoQ Weight Δ"]
        show_cols = [c for c in cols if c in display.columns]
        st.dataframe(display[show_cols], use_container_width=True, hide_index=True)
        st.download_button("Export CSV", display[show_cols].to_csv(index=False), "holdings.csv", "text/csv")
    else:
        st.dataframe(holdings, use_container_width=True)

    # Charts
    st.subheader("Charts")
    chart_view = st.radio("View", ["Chart", "Table"], horizontal=True, key="sig_chart_view")

    top_over_time = get_top_holdings_over_time(portfolio_id, top_n=10)
    if not top_over_time.empty:
        if chart_view == "Chart":
            fig = px.line(top_over_time, x="filing_date", y="weight", color="ticker",
                          title="Top 10 Weight Over Time")
            st.plotly_chart(fig, use_container_width=True)

            if not holdings.empty:
                top10 = holdings.nlargest(10, "value")
                fig2 = px.pie(top10, values="value", names="ticker", title="Portfolio Concentration")
                st.plotly_chart(fig2, use_container_width=True)
        else:
            st.dataframe(top_over_time, use_container_width=True)

# ── Prices & Markets ───────────────────────────────────────────────────────────
with tab_prices:
    prices_dir = Path(__file__).parent.parent.parent / "data" / "raw" / "yahoo_prices"

    @st.cache_data(ttl=300)
    def available_tickers() -> list[str]:
        if not prices_dir.exists():
            return []
        return sorted(p.stem for p in prices_dir.glob("*.csv"))

    all_tickers = available_tickers()
    if not all_tickers:
        st.warning("No price data found. Fetch prices in Admin.")
        st.stop()

    default_tickers = [t for t in ["XBI", "SPY"] if t in all_tickers]
    selected_tickers = st.multiselect("Ticker(s)", all_tickers, default=default_tickers, key="sig_tickers")

    timeframe = st.radio(
        "Timeframe", ["1M", "3M", "6M", "1Y", "3Y", "5Y", "ALL"],
        horizontal=True, index=3, key="sig_tf"
    )
    compare_as = st.radio("Compare as", ["Price", "% Return"], horizontal=True, key="sig_compare")

    tf_days = {"1M": 30, "3M": 90, "6M": 180, "1Y": 365, "3Y": 1095, "5Y": 1825, "ALL": 99999}

    if selected_tickers:
        all_price_data = []
        for ticker in selected_tickers:
            df = load_prices(ticker)
            if df is not None and not df.empty:
                df = df[["date", "close"]].copy()
                df["ticker"] = ticker
                df["date"] = pd.to_datetime(df["date"])
                all_price_data.append(df)

        if all_price_data:
            combined = pd.concat(all_price_data)
            if timeframe != "ALL":
                cutoff = combined["date"].max() - timedelta(days=tf_days[timeframe])
                combined = combined[combined["date"] >= cutoff]

            price_view = st.radio("View", ["Chart", "Table"], horizontal=True, key="sig_price_view")

            if compare_as == "% Return":
                # Normalize each ticker to 100 at start
                start_prices = combined.groupby("ticker")["close"].first()
                combined = combined.copy()
                combined["value"] = combined.apply(
                    lambda r: (r["close"] / start_prices[r["ticker"]] - 1) * 100, axis=1
                )
                y_col, y_label = "value", "Return (%)"
            else:
                combined["value"] = combined["close"]
                y_col, y_label = "value", "Price ($)"

            if price_view == "Chart":
                fig = px.line(combined, x="date", y=y_col, color="ticker",
                              labels={"date": "Date", y_col: y_label},
                              title=f"{'Return' if compare_as == '% Return' else 'Price'} — {', '.join(selected_tickers)}")
                st.plotly_chart(fig, use_container_width=True)
            else:
                pivot = combined.pivot(index="date", columns="ticker", values="value").reset_index()
                st.dataframe(pivot.sort_values("date", ascending=False), use_container_width=True)

            st.download_button(
                "Export CSV",
                combined.pivot(index="date", columns="ticker", values="value").reset_index().to_csv(index=False),
                "prices.csv", "text/csv"
            )
```

- [ ] **Step 2: Verify Signals page in browser**

Navigate to Signals. Confirm:
- Baker Bros tab shows holdings table with QoQ columns
- Charts toggle works (line chart and pie chart)
- Prices tab loads multi-ticker chart
- % Return mode normalizes all lines to 0

- [ ] **Step 3: Commit**

```
git add dashboard/pages/4_Signals.py
git commit -m "feat: add Signals page (Baker Bros holdings + multi-ticker price charts)"
```

---

## Task 6: Research Page

Simplified Strategy 1 — backtest and compare tabs only. No strategy builder.

**Files:**
- Create: `dashboard/pages/3_Research.py`

- [ ] **Step 1: Create `dashboard/pages/3_Research.py`**

```python
# dashboard/pages/3_Research.py
import sys
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from utils.strategy_registry import discover_strategies, set_live, get_live_strategy
from utils.csv_data import load_portfolios, get_all_filings, load_holdings_by_date

st.set_page_config(page_title="Research", layout="wide")
st.title("Research")

strategies = discover_strategies()
if not strategies:
    st.warning("No strategies found in `strategies/` directory.")
    st.stop()

strategy_options = {s["name"]: s for s in strategies}
selected_name = st.selectbox("Strategy", list(strategy_options.keys()), key="res_strategy")
strategy = strategy_options[selected_name]

live = get_live_strategy()
is_live = live is not None and live["module"] == strategy["module"]

col1, col2 = st.columns([3, 1])
with col1:
    badge = "🟢 Live" if is_live else "⚪ Research"
    st.caption(f"Status: {badge}")
with col2:
    if not is_live:
        if st.button("Set as Live"):
            set_live(strategy["module"])
            st.success(f"{strategy['name']} is now Live")
            st.rerun()
    else:
        st.caption("Currently Live strategy")

st.divider()

tab_backtest, tab_compare = st.tabs(["Backtest", "Compare"])

# ── Backtest ───────────────────────────────────────────────────────────────────
with tab_backtest:
    portfolios = load_portfolios(portfolio_type="fund")
    if portfolios.empty:
        st.warning("No fund portfolios. Add one in Admin.")
        st.stop()

    portfolio_options = dict(zip(portfolios["name"], portfolios["id"]))
    portfolio_name = st.selectbox("Fund", list(portfolio_options.keys()), key="res_fund")
    portfolio_id = portfolio_options[portfolio_name]

    col1, col2, col3 = st.columns(3)
    with col1:
        start_date = st.date_input("From", value=pd.Timestamp("2020-01-01"), key="res_start")
    with col2:
        end_date = st.date_input("To", value=pd.Timestamp.today(), key="res_end")
    with col3:
        initial_capital = st.number_input("Initial capital ($)", min_value=1000, value=100000, step=1000, key="res_capital")

    # Strategy parameter sliders
    params = {}
    if strategy.get("parameters"):
        with st.expander("Strategy parameters"):
            for param_key, param_cfg in strategy["parameters"].items():
                if param_cfg["type"] == "int":
                    params[param_key] = st.slider(
                        param_cfg["label"], param_cfg["min"], param_cfg["max"], param_cfg["default"], key=f"res_{param_key}"
                    )
                elif param_cfg["type"] == "float":
                    params[param_key] = st.slider(
                        param_cfg["label"], float(param_cfg["min"]), float(param_cfg["max"]),
                        float(param_cfg["default"]), key=f"res_{param_key}"
                    )

    if st.button("▶ Run backtest", type="primary"):
        try:
            from utils.strategy_engine import StrategyConfig, run_simulation
            config = StrategyConfig(
                portfolio_id=portfolio_id,
                start_date=str(start_date),
                end_date=str(end_date),
                initial_capital=float(initial_capital),
                **params,
            )
            with st.spinner("Running backtest..."):
                results = run_simulation(config)
            st.session_state["res_results"] = results
            st.session_state["res_config"] = config
        except Exception as e:
            st.error(f"Backtest failed: {e}")

    if "res_results" in st.session_state:
        results = st.session_state["res_results"]
        perf = results.get("performance", {})

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Return", f"{perf.get('total_return', 0):+.1f}%")
        col2.metric("vs XBI", f"{perf.get('vs_xbi', 0):+.1f}%")
        col3.metric("Sharpe", f"{perf.get('sharpe', 0):.2f}")
        col4.metric("Max Drawdown", f"{perf.get('max_drawdown', 0):.1f}%")

        bench_show = st.multiselect(
            "Benchmarks", ["XBI", "SPY", "Baker Bros"], default=["XBI", "SPY"], key="res_bench"
        )
        view = st.radio("View", ["Chart", "Table"], horizontal=True, key="res_view")

        returns_df = results.get("returns_df", pd.DataFrame())
        if not returns_df.empty:
            if view == "Chart":
                fig = go.Figure()
                fig.add_trace(go.Scatter(x=returns_df["date"], y=returns_df["strategy_return"],
                                         name=strategy["name"], line=dict(color="#1f77b4")))
                if "XBI" in bench_show and "xbi_return" in returns_df.columns:
                    fig.add_trace(go.Scatter(x=returns_df["date"], y=returns_df["xbi_return"],
                                             name="XBI", line=dict(color="#ff7f0e", dash="dash")))
                if "SPY" in bench_show and "spy_return" in returns_df.columns:
                    fig.add_trace(go.Scatter(x=returns_df["date"], y=returns_df["spy_return"],
                                             name="SPY", line=dict(color="#2ca02c", dash="dot")))
                fig.update_layout(title="Cumulative Return", xaxis_title="Date", yaxis_title="Return (%)")
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.dataframe(returns_df, use_container_width=True)

# ── Compare ────────────────────────────────────────────────────────────────────
with tab_compare:
    st.info("Run backtests for each strategy first, then use this tab to compare results side by side.")
    if len(strategies) > 1:
        selected_for_compare = st.multiselect(
            "Strategies to compare",
            [s["name"] for s in strategies],
            default=[s["name"] for s in strategies[:2]],
            key="res_compare_strats"
        )
        bench_compare = st.multiselect("Benchmarks", ["XBI", "SPY", "Baker Bros"], default=["XBI"], key="res_compare_bench")
        st.caption("Comparison view requires cached backtest results. Run each strategy's backtest first.")
    else:
        st.caption("Add more strategies to `strategies/` to enable comparison.")
```

- [ ] **Step 2: Verify Research page in browser**

Navigate to Research. Confirm:
- Strategy dropdown shows "Baker Bros Top-10 Equal Weight"
- "Set as Live" button appears and works
- Backtest tab shows parameter sliders
- Run backtest executes and displays metrics

- [ ] **Step 3: Commit**

```
git add dashboard/pages/3_Research.py
git commit -m "feat: add Research page (backtest + compare, no strategy builder)"
```

---

## Task 7: Dashboard Page

**Files:**
- Create: `dashboard/pages/1_Dashboard.py`

- [ ] **Step 1: Create `dashboard/pages/1_Dashboard.py`**

```python
# dashboard/pages/1_Dashboard.py
import sys
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from utils.strategy_registry import discover_strategies, get_live_strategy
from utils.brokerage import load_brokerage_holdings, load_trade_log
from utils.drift import calculate_drift
from utils.csv_data import load_portfolios, load_prices
from utils.holdings_operations import get_forward_filled_prices, calculate_portfolio_values
from utils.csv_data import load_processed_holdings

st.set_page_config(page_title="Dashboard", layout="wide")
st.title("Dashboard")

# ── Strategy selector ──────────────────────────────────────────────────────────
strategies = discover_strategies()
live = get_live_strategy()

if not strategies:
    st.warning("No strategies found. Create a strategy file in `strategies/` and register it.")
    st.stop()

strategy_options = {s["name"]: s for s in strategies}
default_idx = next(
    (i for i, s in enumerate(strategies) if s["status"] == "Live"), 0
)
selected_name = st.selectbox("Strategy", list(strategy_options.keys()), index=default_idx, key="dash_strategy")
strategy = strategy_options[selected_name]

# ── Header strip ───────────────────────────────────────────────────────────────
portfolios = load_portfolios(portfolio_type="fund")
if portfolios.empty:
    st.warning("No fund portfolios. Add one in Admin.")
    st.stop()

portfolio_id = portfolios.iloc[0]["id"]

trade_log = load_trade_log()
last_trade_date = "Never"
drift_age_str = "—"
if not trade_log.empty and strategy["name"] in trade_log["strategy"].values:
    strat_log = trade_log[trade_log["strategy"] == strategy["name"]]
    last_ts = pd.to_datetime(strat_log["executed_at"]).max()
    last_trade_date = last_ts.strftime("%Y-%m-%d")
    drift_age = (datetime.now() - last_ts).days
    drift_age_str = f"{drift_age} day{'s' if drift_age != 1 else ''}"

from utils.csv_data import get_all_filings
filings = get_all_filings(portfolio_id)
targets_updated = filings.iloc[0]["filing_date"] if not filings.empty else "—"

col1, col2, col3 = st.columns(3)
col1.metric("Targets last updated", str(targets_updated))
col2.metric("My last trade", last_trade_date)
col3.metric("Drift age", drift_age_str)

st.divider()

# ── Compute drift ──────────────────────────────────────────────────────────────
brokerage = load_brokerage_holdings()
generate_targets = strategy["generate_targets"]
target_weights = generate_targets(portfolio_id=portfolio_id)

prices_df = pd.DataFrame()
if not brokerage.empty:
    all_tickers = list(set(brokerage["ticker"].tolist()) | set(target_weights.keys()))
    price_rows = []
    for ticker in all_tickers:
        p = load_prices(ticker)
        if p is not None and not p.empty:
            latest = p.sort_values("date").iloc[-1]
            price_rows.append({"ticker": ticker, "close": float(latest["close"])})
    prices_df = pd.DataFrame(price_rows)

drift_df = calculate_drift(target_weights, brokerage, prices_df)

# ── Two-column layout ──────────────────────────────────────────────────────────
col_left, col_right = st.columns([1, 1])

with col_left:
    st.subheader("Positions & Drift")

    if not brokerage.empty and not prices_df.empty:
        holdings_with_prices = brokerage.merge(prices_df, on="ticker", how="left")
        holdings_with_prices["value"] = holdings_with_prices["shares"] * holdings_with_prices["close"].fillna(0)
        total_value = holdings_with_prices["value"].sum()
    else:
        total_value = 0.0

    col_a, col_b, col_c = st.columns(3)
    col_a.metric("Total Value", f"${total_value/1e6:.1f}M" if total_value >= 1e6 else f"${total_value:,.0f}")
    col_b.metric("Positions", len(brokerage))

    needs_rebal = drift_df[drift_df["drift_bp"].abs() >= 100]
    if not needs_rebal.empty:
        st.warning(f"⚠ {len(needs_rebal)} position(s) need rebalancing → [Go to Trades](/2_Trades)")

    if not drift_df.empty:
        display = drift_df[["ticker", "target_weight", "actual_weight", "drift_bp", "action"]].copy()
        display.columns = ["Ticker", "Target (%)", "Actual (%)", "Drift (bp)", "Action"]
        st.dataframe(display, use_container_width=True, hide_index=True)
    else:
        st.info("No positions yet. Enter your brokerage holdings in the Trades page.")

with col_right:
    st.subheader("Performance")
    bench_options = st.multiselect("vs.", ["XBI", "SPY", "Baker Bros"], default=["XBI", "SPY"], key="dash_bench")
    perf_view = st.radio("View", ["Chart", "Table"], horizontal=True, key="dash_perf_view")
    st.caption("Performance chart will populate once backtest results are available.")

st.divider()

# ── Portfolio value over time ──────────────────────────────────────────────────
st.subheader("Portfolio Value Over Time")
port_view = st.radio("View", ["Chart", "Table"], horizontal=True, key="dash_port_view")

try:
    holdings_hist = load_processed_holdings(portfolio_id, start_date="2025-01-01")
    if holdings_hist is not None and not holdings_hist.empty:
        start = pd.Timestamp("2025-01-01")
        end = pd.Timestamp.today()
        ff_prices = get_forward_filled_prices(str(start.date()), str(end.date()))
        port_values = calculate_portfolio_values(holdings_hist, ff_prices)

        if port_view == "Chart":
            daily_total = port_values.groupby("eod_date")["position_value"].sum().reset_index()
            daily_total.columns = ["date", "value"]
            fig = px.line(daily_total, x="date", y="value", title="Total Portfolio Value",
                          labels={"value": "Value ($)", "date": "Date"})
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.dataframe(port_values, use_container_width=True)
    else:
        st.info("No processed holdings. Run 'Consolidate holdings' in Admin.")
except Exception as e:
    st.info(f"Portfolio history unavailable: {e}")
```

- [ ] **Step 2: Verify Dashboard in browser**

Navigate to Dashboard. Confirm:
- Strategy selector appears at top
- Header strip shows "Targets last updated", "My last trade", "Drift age"
- Drift table renders (will show all BUY with 0 actual if no brokerage holdings yet)
- Portfolio Value chart loads from processed holdings

- [ ] **Step 3: Commit**

```
git add dashboard/pages/1_Dashboard.py
git commit -m "feat: add Dashboard page (drift table, performance, portfolio value)"
```

---

## Task 8: Trades Page

**Files:**
- Create: `dashboard/pages/2_Trades.py`

- [ ] **Step 1: Create `dashboard/pages/2_Trades.py`**

```python
# dashboard/pages/2_Trades.py
import sys
import streamlit as st
import pandas as pd
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from utils.strategy_registry import discover_strategies
from utils.brokerage import (
    load_brokerage_holdings, save_brokerage_holdings,
    load_staged_trades, save_staged_trades, clear_staged_trades,
    confirm_execution, load_trade_log,
)
from utils.drift import calculate_drift, generate_trade_recommendations
from utils.csv_data import load_portfolios, load_prices, get_all_filings

st.set_page_config(page_title="Trades", layout="wide")
st.title("Trades")

portfolios = load_portfolios(portfolio_type="fund")
if portfolios.empty:
    st.warning("No fund portfolios configured. Add one in Admin.")
    st.stop()
portfolio_id = portfolios.iloc[0]["id"]

strategies = discover_strategies()
if not strategies:
    st.warning("No strategies found in `strategies/`. Create a strategy file first.")
    st.stop()

# ── Stage 1: Configure ─────────────────────────────────────────────────────────
st.subheader("Configure")
strategy_options = {s["name"]: s for s in strategies}
selected_name = st.selectbox("Strategy", list(strategy_options.keys()), key="tr_strategy")
strategy = strategy_options[selected_name]

# Compute default capital from drift
brokerage = load_brokerage_holdings()
price_rows = []
all_tickers_needed = list(brokerage["ticker"].tolist()) if not brokerage.empty else []
for ticker in all_tickers_needed:
    p = load_prices(ticker)
    if p is not None and not p.empty:
        latest = p.sort_values("date").iloc[-1]
        price_rows.append({"ticker": ticker, "close": float(latest["close"])})
prices_df = pd.DataFrame(price_rows) if price_rows else pd.DataFrame(columns=["ticker", "close"])

target_weights = strategy["generate_targets"](portfolio_id=portfolio_id)

# Add any target tickers missing from prices
for ticker in target_weights:
    if not prices_df.empty and ticker in prices_df["ticker"].values:
        continue
    p = load_prices(ticker)
    if p is not None and not p.empty:
        latest = p.sort_values("date").iloc[-1]
        prices_df = pd.concat(
            [prices_df, pd.DataFrame([{"ticker": ticker, "close": float(latest["close"])}])],
            ignore_index=True,
        )

drift_df = calculate_drift(target_weights, brokerage, prices_df)

if not brokerage.empty and not prices_df.empty:
    merged = brokerage.merge(prices_df, on="ticker", how="left")
    merged["value"] = merged["shares"] * merged["close"].fillna(0)
    default_capital = merged["value"].sum()
else:
    default_capital = 10000.0

capital = st.number_input(
    "Capital to deploy ($)",
    min_value=0.0,
    value=round(default_capital, 2),
    step=100.0,
    format="%.2f",
    key="tr_capital",
    help="Pre-populated from total portfolio value. Edit to deploy more or less capital.",
)

# Strategy parameter sliders
params = {}
if strategy.get("parameters"):
    with st.expander("Strategy parameters"):
        for param_key, param_cfg in strategy["parameters"].items():
            if param_cfg["type"] == "int":
                params[param_key] = st.slider(
                    param_cfg["label"], param_cfg["min"], param_cfg["max"],
                    param_cfg["default"], key=f"tr_{param_key}"
                )
            elif param_cfg["type"] == "float":
                params[param_key] = st.slider(
                    param_cfg["label"], float(param_cfg["min"]), float(param_cfg["max"]),
                    float(param_cfg["default"]), key=f"tr_{param_key}"
                )

# Recompute with current params
if params:
    target_weights = strategy["generate_targets"](portfolio_id=portfolio_id, **params)
    drift_df = calculate_drift(target_weights, brokerage, prices_df)

# ── Stage 2: Prospective Trades ────────────────────────────────────────────────
st.divider()
st.subheader("Prospective Trades")

recs = generate_trade_recommendations(drift_df, total_portfolio_value=capital, prices=prices_df)

if recs.empty:
    st.success("No rebalancing needed — all positions within threshold.")
else:
    display_recs = recs[["ticker", "action", "suggested_shares", "delta_value", "price", "drift_bp", "priority"]].copy()
    display_recs.columns = ["Ticker", "Action", "Suggested Shares", "Delta ($)", "Price", "Drift (bp)", "Priority"]
    st.dataframe(display_recs, use_container_width=True, hide_index=True)

    net_capital = recs[recs["action"] == "BUY"]["delta_value"].sum() + recs[recs["action"] == "SELL"]["delta_value"].sum()
    st.caption(f"Net capital needed: ${net_capital:,.0f}")

    if st.button("→ Move to staging", type="primary"):
        staged = pd.DataFrame({
            "ticker": recs["ticker"],
            "action": recs["action"],
            "suggested_shares": recs["suggested_shares"].abs(),
            "actual_shares": recs["suggested_shares"].abs(),
            "exec_price": recs["price"],
            "notes": "",
        })
        save_staged_trades(staged)
        st.success("Trades staged. Review and confirm below.")
        st.rerun()

# ── Stage 3: Staging Area ──────────────────────────────────────────────────────
staged = load_staged_trades()
if not staged.empty:
    st.divider()
    st.subheader("Staging Area")
    st.caption("Adjust actual shares and execution price before confirming.")

    edited = st.data_editor(
        staged[["ticker", "action", "suggested_shares", "actual_shares", "exec_price", "notes"]],
        column_config={
            "ticker": st.column_config.TextColumn("Ticker", disabled=True),
            "action": st.column_config.TextColumn("Action", disabled=True),
            "suggested_shares": st.column_config.NumberColumn("Suggested", disabled=True),
            "actual_shares": st.column_config.NumberColumn("Actual Shares"),
            "exec_price": st.column_config.NumberColumn("Exec Price ($)", format="$%.2f"),
            "notes": st.column_config.TextColumn("Notes"),
        },
        use_container_width=True,
        hide_index=True,
        key="staging_editor",
    )

    col1, col2 = st.columns([1, 4])
    with col1:
        if st.button("✓ Confirm execution", type="primary"):
            confirm_execution(edited, strategy_name=strategy["name"])
            st.success("Trades confirmed and logged.")
            st.rerun()
    with col2:
        if st.button("✕ Clear staging"):
            clear_staged_trades()
            st.rerun()

# ── My Holdings ────────────────────────────────────────────────────────────────
st.divider()
with st.expander("My Holdings"):
    st.caption("Enter your current brokerage positions. Used to calculate drift on Dashboard and Trades.")
    if brokerage.empty:
        st.info("No holdings entered yet.")

    with st.form("holdings_form"):
        if not brokerage.empty:
            edited_holdings = st.data_editor(
                brokerage[["ticker", "shares"]],
                num_rows="dynamic",
                use_container_width=True,
                key="holdings_editor",
            )
        else:
            edited_holdings = st.data_editor(
                pd.DataFrame({"ticker": [""], "shares": [0.0]}),
                num_rows="dynamic",
                use_container_width=True,
                key="holdings_editor_empty",
            )

        uploaded = st.file_uploader("Import CSV from brokerage (ticker, shares columns)", type="csv")
        save_btn = st.form_submit_button("Save holdings")

        if save_btn:
            if uploaded is not None:
                imported = pd.read_csv(uploaded)
                if "ticker" in imported.columns and "shares" in imported.columns:
                    save_brokerage_holdings(imported[["ticker", "shares"]])
                    st.success(f"Imported {len(imported)} positions.")
                else:
                    st.error("CSV must have 'ticker' and 'shares' columns.")
            else:
                clean = edited_holdings[edited_holdings["ticker"].str.strip() != ""].copy()
                save_brokerage_holdings(clean)
                st.success("Holdings saved.")
            st.rerun()

# ── Trade History ──────────────────────────────────────────────────────────────
st.divider()
st.subheader("Trade History")
trade_log = load_trade_log()
hist_view = st.radio("View", ["Table", "Chart"], horizontal=True, key="tr_hist_view")

if trade_log.empty:
    st.info("No trade history yet. Confirm your first execution above.")
else:
    strat_log = trade_log[trade_log["strategy"] == strategy["name"]].copy()
    if strat_log.empty:
        st.info(f"No trade history for {strategy['name']} yet.")
    else:
        if hist_view == "Table":
            st.dataframe(strat_log.sort_values("executed_at", ascending=False), use_container_width=True, hide_index=True)
            st.download_button("Export CSV", strat_log.to_csv(index=False), "trade_history.csv", "text/csv")
        else:
            import plotly.express as px
            strat_log["executed_at"] = pd.to_datetime(strat_log["executed_at"])
            daily = strat_log.groupby(strat_log["executed_at"].dt.date)["total_value"].sum().reset_index()
            daily.columns = ["date", "value"]
            fig = px.bar(daily, x="date", y="value", title=f"Trade Volume — {strategy['name']}")
            st.plotly_chart(fig, use_container_width=True)
```

- [ ] **Step 2: Verify Trades page end-to-end**

Navigate to Trades. Walk through the full workflow:
1. Select a strategy
2. Verify prospective trades appear
3. Click "Move to staging" — staging area appears
4. Edit actual shares in the data editor
5. Click "Confirm execution" — staging clears, history appears
6. Open "My Holdings", add a ticker and save — verify drift updates on Dashboard

- [ ] **Step 3: Commit**

```
git add dashboard/pages/2_Trades.py
git commit -m "feat: add Trades page (3-stage order workflow, holdings entry, trade history)"
```

---

## Task 9: Cleanup

Delete old pages and update the entry point.

**Files:**
- Delete: `dashboard/Home.py`, all old pages
- Modify: create new minimal `dashboard/Home.py`

- [ ] **Step 1: Verify all 5 new pages are working**

Open the app and confirm each page loads without errors:
- Dashboard (`1_Dashboard.py`)
- Trades (`2_Trades.py`)
- Research (`3_Research.py`)
- Signals (`4_Signals.py`)
- Admin (`5_Admin.py`)

- [ ] **Step 2: Delete old pages**

```
git rm dashboard/Home.py
git rm "dashboard/pages/1_Overview.py"
git rm "dashboard/pages/2_Fund_Tracking.py"
git rm "dashboard/pages/5_Calendar.py"
git rm "dashboard/pages/6_Data_Management.py"
git rm "dashboard/pages/7_Portfolio_Size.py"
git rm "dashboard/pages/8_Price_Graphs.py"
git rm "dashboard/pages/9_Strategy_1.py"
```

- [ ] **Step 3: Create new minimal entry point**

```python
# dashboard/Home.py
import streamlit as st
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

st.set_page_config(page_title="Strategy Dashboard", layout="wide")
st.switch_page("pages/1_Dashboard.py")
```

- [ ] **Step 4: Run the full test suite one final time**

```
pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 5: Start app and do a full walkthrough**

```
streamlit run dashboard/Home.py
```

Verify:
- App auto-redirects to Dashboard
- Sidebar shows: Dashboard, Trades, Research, Signals, Admin (5 pages only)
- No old pages visible

- [ ] **Step 6: Final commit**

```
git add dashboard/Home.py
git commit -m "feat: complete dashboard redesign — 5-page strategy-driven interface"
```
