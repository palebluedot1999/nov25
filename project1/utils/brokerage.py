import pandas as pd
from datetime import datetime
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
BROKERAGE_HOLDINGS_FILE = RAW_DATA_DIR / "brokerage_holdings.csv"
STAGED_TRADES_FILE = RAW_DATA_DIR / "staged_trades.csv"
TRADE_LOG_FILE = RAW_DATA_DIR / "trade_log.csv"

HOLDINGS_COLS = ["ticker", "shares", "last_updated"]
STAGED_COLS = ["ticker", "action", "suggested_shares", "actual_shares", "exec_price", "notes"]
LOG_COLS = ["executed_at", "strategy", "ticker", "action", "suggested_shares", "actual_shares", "exec_price", "total_value", "notes"]


def load_brokerage_holdings() -> pd.DataFrame:
    if not BROKERAGE_HOLDINGS_FILE.exists():
        return pd.DataFrame({
            "ticker": pd.Series(dtype="str"),
            "shares": pd.Series(dtype="float64"),
            "last_updated": pd.Series(dtype="str"),
        })
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


def save_trade_log(df: pd.DataFrame) -> None:
    """Overwrite the trade log with an edited DataFrame. Recomputes total_value and reconciles holdings."""
    df = df.copy()
    df["total_value"] = (df["actual_shares"].abs() * df["exec_price"]).round(2)
    df["notes"] = df["notes"].fillna("").astype(str)
    df[LOG_COLS].to_csv(TRADE_LOG_FILE, index=False)
    reconcile_holdings_from_log()


def _net_shares_by_ticker(log: pd.DataFrame) -> dict[str, float]:
    """BUY adds shares, SELL subtracts. Returns {ticker: net_shares}, omitting empty logs."""
    if log.empty:
        return {}

    def net_shares(grp):
        total = 0.0
        for _, row in grp.iterrows():
            actual = float(row["actual_shares"])
            if row["action"] == "BUY":
                total += actual
            elif row["action"] == "SELL":
                total -= actual
        return total

    return log.groupby("ticker").apply(net_shares, include_groups=False).to_dict()


def reconcile_holdings_from_log() -> None:
    """Recompute brokerage_holdings.csv from the full trade log.

    Holdings are always derived from trade history — BUY adds shares, SELL subtracts.
    Call this after any trade log mutation to keep the two in sync.
    """
    positions = _net_shares_by_ticker(load_trade_log())
    if not positions:
        pd.DataFrame(columns=HOLDINGS_COLS).to_csv(BROKERAGE_HOLDINGS_FILE, index=False)
        return

    df = pd.DataFrame(list(positions.items()), columns=["ticker", "shares"])
    df["last_updated"] = datetime.now().strftime("%Y-%m-%d")
    df[HOLDINGS_COLS].to_csv(BROKERAGE_HOLDINGS_FILE, index=False)


def set_manual_holdings(edited_df: pd.DataFrame) -> None:
    """Apply a manually-edited "current positions" table as trade-log adjustment entries.

    Holdings are always derived from trade_log.csv (see reconcile_holdings_from_log), so a
    manual edit must be recorded as history rather than written directly to the holdings
    file — a direct write would be silently discarded the next time any trade executes,
    since that rebuilds the holdings file from the log alone.

    Logs the delta between the edited shares and the current log-derived position per
    ticker (as a BUY/SELL with strategy "Manual Adjustment"), including closing out any
    ticker present in current holdings but absent from edited_df.
    """
    current = _net_shares_by_ticker(load_trade_log())
    edited = dict(zip(edited_df["ticker"], edited_df["shares"].astype(float)))

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_rows = []
    for ticker in set(current) | set(edited):
        delta = edited.get(ticker, 0.0) - current.get(ticker, 0.0)
        if abs(delta) < 1e-9:
            continue
        log_rows.append({
            "executed_at": now,
            "strategy": "Manual Adjustment",
            "ticker": ticker,
            "action": "BUY" if delta > 0 else "SELL",
            "suggested_shares": abs(delta),
            "actual_shares": abs(delta),
            "exec_price": 0.0,
            "total_value": 0.0,
            "notes": "Manual holdings entry",
        })

    if not log_rows:
        return

    new_log = pd.DataFrame(log_rows, columns=LOG_COLS)
    if TRADE_LOG_FILE.exists():
        existing = pd.read_csv(TRADE_LOG_FILE)
        new_log = pd.concat([existing, new_log], ignore_index=True)
    new_log.to_csv(TRADE_LOG_FILE, index=False)

    reconcile_holdings_from_log()


def confirm_execution(staged_df: pd.DataFrame, strategy_name: str, notes: str = "") -> None:
    """Append staged trades to trade log, reconcile holdings, clear staging area."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_rows = []
    for _, row in staged_df.iterrows():
        actual = float(row.get("actual_shares") if pd.notna(row.get("actual_shares")) else row["suggested_shares"])
        price = float(row.get("exec_price") if pd.notna(row.get("exec_price")) else 0)
        row_notes = str(row.get("notes") or "") or notes
        log_rows.append({
            "executed_at": now,
            "strategy": strategy_name,
            "ticker": row["ticker"],
            "action": row["action"],
            "suggested_shares": float(row["suggested_shares"]),
            "actual_shares": actual,
            "exec_price": price,
            "total_value": round(abs(actual) * price, 2),
            "notes": row_notes,
        })

    new_log = pd.DataFrame(log_rows, columns=LOG_COLS)
    if TRADE_LOG_FILE.exists():
        existing = pd.read_csv(TRADE_LOG_FILE)
        new_log = pd.concat([existing, new_log], ignore_index=True)
    new_log.to_csv(TRADE_LOG_FILE, index=False)

    reconcile_holdings_from_log()
    clear_staged_trades()
