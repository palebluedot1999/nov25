# Security Reference Data Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a regenerable master security-reference table keyed by CUSIP (full identifiers + provenance + filing history) and stop the daily-holdings pipeline from silently dropping positions it cannot map.

**Architecture:** A new `utils/security_reference.py` sweeps every 13F filing for CUSIPs, resolves them via OpenFIGI (`utils/cusip_mapping.CUSIPMapper`, extended) with a stdlib name-match fallback against SEC `company_tickers.json`, caches raw results in `data/raw/security_identifiers.csv`, and merges cache + a committed `config/security_overrides.csv` + filing history into `data/processed/security_reference.csv`. A shared `enrich_holdings_with_reference()` fills tickers/names from that table at both the consolidation and read layers. `utils/holdings_operations.py` is changed to carry every position by CUSIP with a forward-filled `filing_value`, and its price join becomes a left join so unpriced positions survive.

**Tech Stack:** Python 3.12, pandas ≥2.0, numpy ≥1.24, `requests`, stdlib `difflib`, pytest. Streamlit dashboard.

**Spec:** `docs/superpowers/specs/2026-09-08-security-reference-data-design.md`

## Global Constraints

- All of `data/` is gitignored (`.gitignore:12`). `config/security_overrides.csv` is the **only** committed data-shaped file — it holds manual identifier work that must survive a fresh checkout.
- **Key on `cusip` everywhere.** No `security_id` column — it would be byte-identical to `cusip` today.
- **Blank ticker is `""`, never `NaN`**, at every point in the holdings pipeline (a `NaN` in the categorical cast / sort in `save_processed_holdings` is order-unstable).
- Merge precedence, highest first: **override > openfigi > company_tickers > filing**.
- `resolution_source ∈ {override, openfigi, company_tickers, filing}`.
- `resolution_status ∈ {resolved, ticker_only, name_only, unresolved}` where `resolved` = ticker + FIGI, `ticker_only` = ticker but no FIGI, `name_only` = name only / low-confidence or suppressed, `unresolved` = CUSIP + filing name only.
- Persisted `holdings.csv` stays **price-free**: columns are exactly `portfolio, cusip, ticker, shares, filing_value, eod_date`. `has_price`, `close`, `position_value` are computed at consume time only.
- Name matching uses **stdlib `difflib`** (this refines spec §5.4, which named `rapidfuzz`); no new dependency is added.
- OpenFIGI: reuse `utils/cusip_mapping.CUSIPMapper`; API key from `config.settings.OPENFIGI_API_KEY`; ≤100 jobs per request.
- An override row with a **blank `ticker`** is a *suppression*: it forces `ticker=""` and caps `resolution_status` at `name_only`, beating any OpenFIGI hit.
- ISIN is derived only when `cusip[0].isdigit()` (a CINS code has a leading letter and is not US-ISIN-derivable).
- **Tests never hit live APIs.** Mock `requests` / patch `CUSIPMapper` methods; use `tmp_path` + `monkeypatch` for file paths.
- New test files start with the repo boilerplate:
  ```python
  import sys
  from pathlib import Path
  sys.path.insert(0, str(Path(__file__).parent.parent))
  ```
- Commit after every task. Conventional-commit prefixes (`feat:`, `fix:`, `test:`, `docs:`, `refactor:`). End messages with:
  ```
  Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01FFaEjmTxb9upSimabpBAvL
  ```

---

## File Structure

| File | Responsibility |
|---|---|
| `utils/security_reference.py` *(new)* | Path constants; `cusip_to_isin`; `collect_filing_cusips`; `resolve_cusips` (+ `_match_company_tickers`); `load_security_reference`; `build_security_reference`; `enrich_holdings_with_reference`. |
| `utils/cusip_mapping.py` *(modify)* | Add `CUSIPMapper.lookup_full(cusip) -> dict` returning the whole OpenFIGI record, not just the ticker. |
| `config/security_overrides.csv` *(new, committed)* | Hand-maintained identifier overrides + suppressions. Header comment documents the format. |
| `scripts/build_security_reference.py` *(new)* | CLI: sweep → resolve → build; writes a coverage report to `docs/`. |
| `utils/holdings_operations.py` *(modify)* | Use `enrich_holdings_with_reference`; carry every CUSIP; add `filing_value`; re-key exits on `cusip`; `inner`→`left` price join; blank-ticker invariant. |
| `utils/csv_data.py` *(modify)* | `load_holdings_by_date` and `load_processed_holdings` left-join `name`/`resolution_status` from the reference table, degrading gracefully when it is absent. |
| `dashboard/pages/1_Dashboard.py` *(modify)* | "Portfolio Value Over Time": caption for unpriced positions using `filing_value`. |
| `dashboard/pages/5_Admin.py` *(modify)* | "Build security reference" button + coverage metric. |
| `dashboard/pages/4_Signals.py` *(modify)* | Show issuer `name` when `ticker` is blank. |
| `tests/test_security_reference.py` *(new)* | Unit tests for the new module. |
| `tests/test_holdings_operations.py` *(new)* | Regression tests for the two drops + exit re-key + blank-ticker round-trip. |
| `CLAUDE.md` *(modify)* | Key Files, a Data Platform pointer, stale-entry fixes. |

---

## Task 1: `cusip_to_isin` + module scaffold

**Files:**
- Create: `utils/security_reference.py`
- Test: `tests/test_security_reference.py`

**Interfaces:**
- Produces: `cusip_to_isin(cusip: str) -> str` — returns `"US" + cusip + check_digit` when `cusip` is 9 alphanumerics with a leading digit; `""` otherwise (malformed, or a CINS code with a leading letter).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_security_reference.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.security_reference import cusip_to_isin


class TestCusipToIsin:
    def test_known_us_equity(self):
        # Apple: CUSIP 037833100 -> ISIN US0378331005
        assert cusip_to_isin("037833100") == "US0378331005"

    def test_known_us_equity_with_letters(self):
        # Alphabet class C: CUSIP 02079K107 -> ISIN US02079K1079
        assert cusip_to_isin("02079K107") == "US02079K1079"

    def test_cins_leading_letter_returns_empty(self):
        # CINS codes (non-US) have a leading letter and are not US-ISIN-derivable
        assert cusip_to_isin("G0692U109") == ""

    def test_malformed_returns_empty(self):
        assert cusip_to_isin("") == ""
        assert cusip_to_isin("123") == ""
        assert cusip_to_isin("0378331000000") == ""
        assert cusip_to_isin(None) == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_security_reference.py -v`
Expected: FAIL — `ModuleNotFoundError` / `ImportError: cannot import name 'cusip_to_isin'`.

- [ ] **Step 3: Write minimal implementation**

```python
# utils/security_reference.py
"""
Security reference data: sweep 13F filings for CUSIPs, resolve identifiers,
and build data/processed/security_reference.csv — the joinable master table.

See docs/superpowers/specs/2026-09-08-security-reference-data-design.md
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from config.settings import RAW_DATA_DIR, PROCESSED_DATA_DIR, PROJECT_ROOT

FILINGS_DIR = RAW_DATA_DIR / "13f_filings"
SECURITY_IDENTIFIERS_FILE = RAW_DATA_DIR / "security_identifiers.csv"
SECURITY_REFERENCE_FILE = PROCESSED_DATA_DIR / "security_reference.csv"
SECURITY_OVERRIDES_FILE = PROJECT_ROOT / "config" / "security_overrides.csv"

_ISIN_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def _isin_check_digit(body: str) -> str:
    """Luhn mod-10 check digit over an alphanumeric ISIN body (no check digit)."""
    digits = "".join(str(_ISIN_CHARS.index(c)) for c in body.upper())
    total = 0
    # Double every second digit counting from the rightmost, which is odd-indexed
    # from the left of the reversed string.
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 0:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return str((10 - (total % 10)) % 10)


def cusip_to_isin(cusip) -> str:
    """Derive the US ISIN for a 9-char numeric-leading CUSIP. '' for CINS / malformed."""
    if not isinstance(cusip, str):
        return ""
    c = cusip.strip().upper()
    if len(c) != 9 or not all(ch in _ISIN_CHARS for ch in c) or not c[0].isdigit():
        return ""
    body = "US" + c
    return body + _isin_check_digit(body)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_security_reference.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add utils/security_reference.py tests/test_security_reference.py
git commit -m "feat: add cusip_to_isin and security_reference module scaffold"
```

---

## Task 2: `collect_filing_cusips`

**Files:**
- Modify: `utils/security_reference.py`
- Test: `tests/test_security_reference.py`

**Interfaces:**
- Consumes: `FILINGS_DIR` from Task 1.
- Produces: `collect_filing_cusips(filings_dir: Path = FILINGS_DIR) -> pd.DataFrame` with columns `cusip, name, ticker_in_filing, first_seen_quarter, last_seen_quarter, n_filings, is_active`. One row per distinct CUSIP. `name` / `ticker_in_filing` = the most recent non-empty value by `period_end_date`. `is_active` = CUSIP present in the filing(s) with the max `period_end_date`.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_security_reference.py
import pandas as pd
from utils.security_reference import collect_filing_cusips

_FILING_COLS = [
    "company_name", "share_class", "cusip", "value", "shares", "option_type",
    "investment_discretion", "voting_authority_sole", "voting_authority_shared",
    "voting_authority_none", "ticker", "portfolio_id", "filing_date", "period_end_date",
]


def _write_filing(path: Path, rows: list[dict], filing_date: str, period_end: str):
    df = pd.DataFrame(rows)
    df["portfolio_id"] = "baker-bros"
    df["filing_date"] = filing_date
    df["period_end_date"] = period_end
    for col in _FILING_COLS:
        if col not in df.columns:
            df[col] = ""
    df[_FILING_COLS].to_csv(path, index=False)


class TestCollectFilingCusips:
    def test_two_filings_aggregate(self, tmp_path):
        _write_filing(
            tmp_path / "baker-bros_2024-02-14_holdings.csv",
            [
                {"company_name": "Acme Bio Inc.", "cusip": "111111111", "ticker": "", "value": 100, "shares": 10},
                {"company_name": "Old Co", "cusip": "222222222", "ticker": "OLD", "value": 50, "shares": 5},
            ],
            "2024-02-14", "2023-12-31",
        )
        _write_filing(
            tmp_path / "baker-bros_2024-05-15_holdings.csv",
            [
                {"company_name": "Acme Bio Inc.", "cusip": "111111111", "ticker": "ACME", "value": 120, "shares": 12},
            ],
            "2024-05-15", "2024-03-31",
        )

        out = collect_filing_cusips(tmp_path).set_index("cusip")

        assert set(out.index) == {"111111111", "222222222"}
        assert out.loc["111111111", "n_filings"] == 2
        assert out.loc["111111111", "first_seen_quarter"] == "2023-12-31"
        assert out.loc["111111111", "last_seen_quarter"] == "2024-03-31"
        assert out.loc["111111111", "ticker_in_filing"] == "ACME"   # most recent non-empty
        assert bool(out.loc["111111111", "is_active"]) is True
        assert bool(out.loc["222222222", "is_active"]) is False     # absent from latest filing
        assert out.loc["222222222", "n_filings"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_security_reference.py::TestCollectFilingCusips -v`
Expected: FAIL — `ImportError: cannot import name 'collect_filing_cusips'`.

- [ ] **Step 3: Write minimal implementation**

```python
# add to utils/security_reference.py
import pandas as pd


def collect_filing_cusips(filings_dir: Path = FILINGS_DIR) -> pd.DataFrame:
    """Sweep every 13F filing CSV; return one row per distinct CUSIP with history."""
    frames = []
    for path in sorted(Path(filings_dir).glob("*.csv")):
        df = pd.read_csv(path, dtype=str)
        if df.empty:
            continue
        df = df[["cusip", "company_name", "ticker", "period_end_date"]].copy()
        df["cusip"] = df["cusip"].str.strip().str.upper()
        df = df[df["cusip"].notna() & (df["cusip"] != "")]
        frames.append(df)

    if not frames:
        return pd.DataFrame(
            columns=["cusip", "name", "ticker_in_filing", "first_seen_quarter",
                     "last_seen_quarter", "n_filings", "is_active"]
        )

    allrows = pd.concat(frames, ignore_index=True)
    allrows["company_name"] = allrows["company_name"].fillna("").str.strip()
    allrows["ticker"] = allrows["ticker"].fillna("").str.strip()
    latest_quarter = allrows["period_end_date"].max()

    def _latest_nonempty(series_df, col):
        s = series_df[series_df[col] != ""].sort_values("period_end_date")
        return s[col].iloc[-1] if not s.empty else ""

    out_rows = []
    for cusip, g in allrows.groupby("cusip"):
        quarters = g["period_end_date"]
        out_rows.append({
            "cusip": cusip,
            "name": _latest_nonempty(g, "company_name"),
            "ticker_in_filing": _latest_nonempty(g, "ticker"),
            "first_seen_quarter": quarters.min(),
            "last_seen_quarter": quarters.max(),
            "n_filings": g["period_end_date"].nunique(),
            "is_active": bool((quarters == latest_quarter).any()),
        })
    return pd.DataFrame(out_rows)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_security_reference.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add utils/security_reference.py tests/test_security_reference.py
git commit -m "feat: add collect_filing_cusips filing sweep"
```

---

## Task 3: `CUSIPMapper.lookup_full`

**Files:**
- Modify: `utils/cusip_mapping.py` (add method to `CUSIPMapper`, near `lookup` ~line 150)
- Test: `tests/test_security_reference.py`

**Interfaces:**
- Produces: `CUSIPMapper.lookup_full(cusip: str) -> dict | None` — POSTs one CUSIP to OpenFIGI `/v3/mapping` and returns `{"ticker","name","figi","composite_figi","share_class_figi","security_type","market_sector","exch_code"}` (missing keys → `""`), or `None` if the API returns no data. Does **not** touch the ticker-only cache.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_security_reference.py
from unittest.mock import patch
from utils.cusip_mapping import CUSIPMapper


class _Resp:
    def __init__(self, payload):
        self._payload = payload
    def raise_for_status(self):
        pass
    def json(self):
        return self._payload


class TestLookupFull:
    def test_maps_openfigi_fields(self):
        payload = [{"data": [{
            "ticker": "ACME", "name": "ACME BIO INC",
            "figi": "BBG000000001", "compositeFIGI": "BBG000000002",
            "shareClassFIGI": "BBG000000003", "securityType": "Common Stock",
            "marketSector": "Equity", "exchCode": "US",
        }]}]
        with patch("utils.cusip_mapping.requests.post", return_value=_Resp(payload)):
            rec = CUSIPMapper().lookup_full("111111111")
        assert rec == {
            "ticker": "ACME", "name": "ACME BIO INC", "figi": "BBG000000001",
            "composite_figi": "BBG000000002", "share_class_figi": "BBG000000003",
            "security_type": "Common Stock", "market_sector": "Equity", "exch_code": "US",
        }

    def test_no_data_returns_none(self):
        with patch("utils.cusip_mapping.requests.post", return_value=_Resp([{"warning": "no match"}])):
            assert CUSIPMapper().lookup_full("999999999") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_security_reference.py::TestLookupFull -v`
Expected: FAIL — `AttributeError: 'CUSIPMapper' object has no attribute 'lookup_full'`.

- [ ] **Step 3: Write minimal implementation**

```python
# utils/cusip_mapping.py — add inside class CUSIPMapper, after lookup()
def lookup_full(self, cusip: str) -> dict | None:
    """Full OpenFIGI record for one CUSIP (not just ticker). None if unmatched."""
    if not cusip:
        return None
    cusip = cusip.strip().upper()
    headers = {"Content-Type": "application/json"}
    if OPENFIGI_API_KEY:
        headers["X-OPENFIGI-APIKEY"] = OPENFIGI_API_KEY
    payload = [{"idType": "ID_CUSIP", "idValue": cusip, "exchCode": "US"}]
    try:
        resp = requests.post("https://api.openfigi.com/v3/mapping",
                             headers=headers, json=payload, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:  # noqa: BLE001
        print(f"Warning: OpenFIGI lookup_full failed for {cusip}: {e}")
        return None
    if not data or "data" not in data[0] or not data[0]["data"]:
        return None
    d = data[0]["data"][0]
    return {
        "ticker": d.get("ticker") or "",
        "name": d.get("name") or "",
        "figi": d.get("figi") or "",
        "composite_figi": d.get("compositeFIGI") or "",
        "share_class_figi": d.get("shareClassFIGI") or "",
        "security_type": d.get("securityType") or d.get("securityType2") or "",
        "market_sector": d.get("marketSector") or "",
        "exch_code": d.get("exchCode") or "",
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_security_reference.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add utils/cusip_mapping.py tests/test_security_reference.py
git commit -m "feat: add CUSIPMapper.lookup_full for the full OpenFIGI record"
```

---

## Task 4: `resolve_cusips` + `_match_company_tickers`

**Files:**
- Modify: `utils/security_reference.py`
- Test: `tests/test_security_reference.py`

**Interfaces:**
- Consumes: `CUSIPMapper.lookup_full` (Task 3); `SECURITY_IDENTIFIERS_FILE` (Task 1).
- Produces:
  - `_normalize_issuer_name(name: str) -> str` — lowercase, strip punctuation and corporate suffixes (`inc corp corporation ltd limited llc co company plc sa nv ag holdings group com class a/b/c common stock`).
  - `_match_company_tickers(name: str, sec_index: list[tuple[str, str, str]], threshold: float = 0.90) -> dict | None` — best `difflib.SequenceMatcher` ratio of the normalized `name` against normalized SEC titles; returns `{"ticker","name","cik"}` when ratio ≥ threshold, else `None`. `sec_index` items are `(normalized_title, ticker, cik_str)`.
  - `resolve_cusips(cusips, *, force: bool = False, sec_tickers: dict | None = None, mapper: "CUSIPMapper | None" = None) -> pd.DataFrame` — for each CUSIP not already present in `security_identifiers.csv` (unless `force`): try `mapper.lookup_full`; if that yields no ticker, try `_match_company_tickers` against `sec_tickers` (SEC `company_tickers.json` shape: `{"0": {"cik_str":.., "ticker":.., "title":..}}`, fetched via `CUSIPMapper._fetch_sec_tickers()` when `None`). Upsert successes into `security_identifiers.csv` with columns `cusip, ticker, name, cik, figi, composite_figi, share_class_figi, security_type, market_sector, exch_code, source, resolved_at`. Return the rows resolved this call. `name`-supplied CUSIPs need a `name` — accept `cusips` as either a list of CUSIP strings or a DataFrame with `cusip`/`name` columns.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_security_reference.py
from datetime import datetime
from utils import security_reference as sr


class _FakeMapper:
    def __init__(self, table):
        self.table = table
    def lookup_full(self, cusip):
        return self.table.get(cusip)


class TestResolveCusips:
    def test_openfigi_hit(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sr, "SECURITY_IDENTIFIERS_FILE", tmp_path / "ids.csv")
        mapper = _FakeMapper({"111111111": {
            "ticker": "ACME", "name": "ACME BIO INC", "figi": "BBG1",
            "composite_figi": "BBG2", "share_class_figi": "BBG3",
            "security_type": "Common Stock", "market_sector": "Equity", "exch_code": "US",
        }})
        df = pd.DataFrame([{"cusip": "111111111", "name": "Acme Bio Inc."}])

        out = sr.resolve_cusips(df, sec_tickers={}, mapper=mapper)

        row = out.set_index("cusip").loc["111111111"]
        assert row["ticker"] == "ACME"
        assert row["source"] == "openfigi"
        assert (tmp_path / "ids.csv").exists()

    def test_name_match_fallback_captures_cik(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sr, "SECURITY_IDENTIFIERS_FILE", tmp_path / "ids.csv")
        mapper = _FakeMapper({})  # OpenFIGI misses everything
        sec_tickers = {"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}}
        df = pd.DataFrame([{"cusip": "037833100", "name": "APPLE INC"}])

        out = sr.resolve_cusips(df, sec_tickers=sec_tickers, mapper=mapper)

        row = out.set_index("cusip").loc["037833100"]
        assert row["ticker"] == "AAPL"
        assert row["source"] == "company_tickers"
        assert str(row["cik"]) == "320193"

    def test_unresolved_not_written(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sr, "SECURITY_IDENTIFIERS_FILE", tmp_path / "ids.csv")
        df = pd.DataFrame([{"cusip": "999999999", "name": "Totally Unknown Holdings"}])

        out = sr.resolve_cusips(df, sec_tickers={}, mapper=_FakeMapper({}))

        assert out.empty
        assert not (tmp_path / "ids.csv").exists() or pd.read_csv(tmp_path / "ids.csv").empty

    def test_skips_already_cached(self, tmp_path, monkeypatch):
        ids = tmp_path / "ids.csv"
        pd.DataFrame([{"cusip": "111111111", "ticker": "OLD", "name": "x", "cik": "",
                       "figi": "", "composite_figi": "", "share_class_figi": "",
                       "security_type": "", "market_sector": "", "exch_code": "",
                       "source": "openfigi", "resolved_at": "2026-01-01"}]).to_csv(ids, index=False)
        monkeypatch.setattr(sr, "SECURITY_IDENTIFIERS_FILE", ids)

        called = []
        class _Spy(_FakeMapper):
            def lookup_full(self, cusip):
                called.append(cusip)
                return None
        out = sr.resolve_cusips(["111111111"], sec_tickers={}, mapper=_Spy({}))

        assert called == []          # cached CUSIP not re-queried
        assert out.empty
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_security_reference.py::TestResolveCusips -v`
Expected: FAIL — `AttributeError: module 'utils.security_reference' has no attribute 'resolve_cusips'`.

- [ ] **Step 3: Write minimal implementation**

```python
# add to utils/security_reference.py
import re
from datetime import datetime
from difflib import SequenceMatcher

_IDENTIFIER_COLS = ["cusip", "ticker", "name", "cik", "figi", "composite_figi",
                    "share_class_figi", "security_type", "market_sector",
                    "exch_code", "source", "resolved_at"]

_SUFFIXES = {"inc", "corp", "corporation", "ltd", "limited", "llc", "co",
             "company", "plc", "sa", "nv", "ag", "holdings", "holding", "group",
             "com", "common", "stock", "class", "a", "b", "c", "the"}


def _normalize_issuer_name(name: str) -> str:
    tokens = re.sub(r"[^a-z0-9 ]", " ", str(name).lower()).split()
    return " ".join(t for t in tokens if t not in _SUFFIXES)


def _sec_index(sec_tickers: dict) -> list[tuple[str, str, str]]:
    idx = []
    for row in (sec_tickers or {}).values():
        idx.append((_normalize_issuer_name(row.get("title", "")),
                    str(row.get("ticker", "")).upper(),
                    str(row.get("cik_str", ""))))
    return idx


def _match_company_tickers(name, sec_index, threshold: float = 0.90):
    target = _normalize_issuer_name(name)
    if not target:
        return None
    best, best_ratio = None, 0.0
    for norm_title, ticker, cik in sec_index:
        if not norm_title or not ticker:
            continue
        r = SequenceMatcher(None, target, norm_title).ratio()
        if r > best_ratio:
            best, best_ratio = (ticker, cik), r
    if best and best_ratio >= threshold:
        return {"ticker": best[0], "name": name, "cik": best[1]}
    return None


def _load_identifiers() -> pd.DataFrame:
    if SECURITY_IDENTIFIERS_FILE.exists():
        return pd.read_csv(SECURITY_IDENTIFIERS_FILE, dtype=str).fillna("")
    return pd.DataFrame(columns=_IDENTIFIER_COLS)


def resolve_cusips(cusips, *, force: bool = False, sec_tickers=None, mapper=None) -> pd.DataFrame:
    from utils.cusip_mapping import CUSIPMapper
    mapper = mapper or CUSIPMapper()
    if sec_tickers is None:
        sec_tickers = mapper._fetch_sec_tickers()
    sec_index = _sec_index(sec_tickers)

    if isinstance(cusips, pd.DataFrame):
        want = cusips[["cusip", "name"]].copy()
    else:
        want = pd.DataFrame({"cusip": list(cusips)})
        want["name"] = ""
    want["cusip"] = want["cusip"].str.strip().str.upper()

    existing = _load_identifiers()
    if not force:
        want = want[~want["cusip"].isin(set(existing["cusip"]))]

    new_rows = []
    for _, r in want.iterrows():
        cusip, name = r["cusip"], r.get("name", "")
        rec = mapper.lookup_full(cusip)
        if rec and rec.get("ticker"):
            new_rows.append({**{c: "" for c in _IDENTIFIER_COLS}, **rec,
                             "cusip": cusip, "source": "openfigi",
                             "resolved_at": datetime.utcnow().isoformat()})
            continue
        m = _match_company_tickers(name, sec_index)
        if m:
            new_rows.append({**{c: "" for c in _IDENTIFIER_COLS}, **m,
                             "cusip": cusip, "source": "company_tickers",
                             "resolved_at": datetime.utcnow().isoformat()})

    resolved = pd.DataFrame(new_rows, columns=_IDENTIFIER_COLS)
    if not resolved.empty:
        combined = pd.concat([existing, resolved], ignore_index=True)
        combined = combined.drop_duplicates(subset=["cusip"], keep="last")
        SECURITY_IDENTIFIERS_FILE.parent.mkdir(parents=True, exist_ok=True)
        combined.to_csv(SECURITY_IDENTIFIERS_FILE, index=False)
    return resolved
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_security_reference.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add utils/security_reference.py tests/test_security_reference.py
git commit -m "feat: add resolve_cusips with OpenFIGI + company_tickers name-match"
```

---

## Task 5: overrides file + `load_security_reference` + `build_security_reference`

**Files:**
- Create: `config/security_overrides.csv`
- Modify: `utils/security_reference.py`
- Test: `tests/test_security_reference.py`

**Interfaces:**
- Consumes: `collect_filing_cusips` (Task 2), `_load_identifiers` (Task 4), `cusip_to_isin` (Task 1), `SECURITY_OVERRIDES_FILE` / `SECURITY_REFERENCE_FILE` (Task 1).
- Produces:
  - `_load_overrides() -> pd.DataFrame` — reads `config/security_overrides.csv` (skips `#` comment lines), columns `cusip, ticker, name, security_type, cik, note`; `""` DataFrame if absent.
  - `build_security_reference() -> dict` — merge filing sweep ⨝ identifiers cache ⨝ overrides; apply precedence **override > openfigi > company_tickers > filing**; derive `isin`, `resolution_source`, `resolution_status`; write `SECURITY_REFERENCE_FILE` with columns `cusip, ticker, name, cik, isin, figi, composite_figi, share_class_figi, security_type, market_sector, exch_code, is_active, first_seen_quarter, last_seen_quarter, n_filings, resolution_source, resolution_status, built_at`. Returns `{"total","resolved","ticker_only","name_only","unresolved","path"}`.
  - `load_security_reference() -> pd.DataFrame` — read `SECURITY_REFERENCE_FILE`; empty typed frame if absent.
  - Suppression rule: an override row whose `ticker` is blank forces final `ticker=""` and `resolution_status="name_only"`, `resolution_source="override"`, even when the identifiers cache has an OpenFIGI ticker.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_security_reference.py
class TestBuildSecurityReference:
    def _setup(self, tmp_path, monkeypatch, identifiers_rows, overrides_text):
        monkeypatch.setattr(sr, "SECURITY_REFERENCE_FILE", tmp_path / "security_reference.csv")
        monkeypatch.setattr(sr, "SECURITY_IDENTIFIERS_FILE", tmp_path / "ids.csv")
        monkeypatch.setattr(sr, "SECURITY_OVERRIDES_FILE", tmp_path / "security_overrides.csv")
        pd.DataFrame(identifiers_rows, columns=sr._IDENTIFIER_COLS).to_csv(sr.SECURITY_IDENTIFIERS_FILE, index=False)
        (tmp_path / "security_overrides.csv").write_text(overrides_text)
        _write_filing(
            tmp_path / "f1.csv",
            [
                {"company_name": "Acme Bio Inc.", "cusip": "111111111", "ticker": "", "value": 1, "shares": 1},
                {"company_name": "Bond Co", "cusip": "00484MAA4", "ticker": "", "value": 1, "shares": 1},
                {"company_name": "Ghost Inc", "cusip": "222222222", "ticker": "", "value": 1, "shares": 1},
            ],
            "2024-05-15", "2024-03-31",
        )
        monkeypatch.setattr(sr, "FILINGS_DIR", tmp_path)

    def test_precedence_and_status(self, tmp_path, monkeypatch):
        ids = [
            {**{c: "" for c in sr._IDENTIFIER_COLS}, "cusip": "111111111", "ticker": "WRONG",
             "name": "ACME BIO INC", "figi": "BBG1", "source": "openfigi", "resolved_at": "x"},
            {**{c: "" for c in sr._IDENTIFIER_COLS}, "cusip": "00484MAA4", "ticker": "BONDX",
             "name": "BOND CO", "figi": "BBG9", "source": "openfigi", "resolved_at": "x"},
        ]
        overrides = (
            "# cusip,ticker,name,security_type,cik,note\n"
            "111111111,ACME,Acme Bio Inc.,Common Stock,,corrected\n"
            "00484MAA4,,Bond Co,Corp Bond,,no tradable ticker\n"
        )
        self._setup(tmp_path, monkeypatch, ids, overrides)

        stats = sr.build_security_reference()
        ref = sr.load_security_reference().set_index("cusip")

        # override beats openfigi
        assert ref.loc["111111111", "ticker"] == "ACME"
        assert ref.loc["111111111", "resolution_source"] == "override"
        assert ref.loc["111111111", "resolution_status"] == "resolved"
        assert ref.loc["111111111", "isin"] == "US1111111117"
        # suppression: blank-ticker override beats a confident openfigi hit
        assert ref.loc["00484MAA4", "ticker"] == ""
        assert ref.loc["00484MAA4", "resolution_status"] == "name_only"
        # CINS-safe / unresolved
        assert ref.loc["222222222", "resolution_status"] == "unresolved"
        assert ref.loc["222222222", "ticker"] == ""
        assert stats["total"] == 3
        assert stats["unresolved"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_security_reference.py::TestBuildSecurityReference -v`
Expected: FAIL — `AttributeError: ... 'build_security_reference'`.

- [ ] **Step 3: Write minimal implementation**

```python
# add to utils/security_reference.py
_OVERRIDE_COLS = ["cusip", "ticker", "name", "security_type", "cik", "note"]
_REFERENCE_COLS = ["cusip", "ticker", "name", "cik", "isin", "figi", "composite_figi",
                   "share_class_figi", "security_type", "market_sector", "exch_code",
                   "is_active", "first_seen_quarter", "last_seen_quarter", "n_filings",
                   "resolution_source", "resolution_status", "built_at"]


def _load_overrides() -> pd.DataFrame:
    if not SECURITY_OVERRIDES_FILE.exists():
        return pd.DataFrame(columns=_OVERRIDE_COLS)
    df = pd.read_csv(SECURITY_OVERRIDES_FILE, dtype=str, comment="#").fillna("")
    for c in _OVERRIDE_COLS:
        if c not in df.columns:
            df[c] = ""
    df["cusip"] = df["cusip"].str.strip().str.upper()
    return df[df["cusip"] != ""]


def load_security_reference() -> pd.DataFrame:
    if SECURITY_REFERENCE_FILE.exists():
        return pd.read_csv(SECURITY_REFERENCE_FILE, dtype=str).fillna("")
    return pd.DataFrame(columns=_REFERENCE_COLS)


def _status(ticker: str, figi: str, source: str, suppressed: bool) -> str:
    if suppressed:
        return "name_only"
    if ticker and figi:
        return "resolved"
    if ticker:
        return "ticker_only"
    if source == "company_tickers":
        return "name_only"
    return "unresolved"


def build_security_reference() -> dict:
    sweep = collect_filing_cusips().set_index("cusip")
    ids = _load_identifiers().set_index("cusip")
    ovr = _load_overrides().set_index("cusip")

    rows = []
    for cusip, s in sweep.iterrows():
        idr = ids.loc[cusip].to_dict() if cusip in ids.index else {}
        ov = ovr.loc[cusip].to_dict() if cusip in ovr.index else {}
        suppressed = bool(ov) and ov.get("ticker", "") == ""

        if ov and not suppressed:
            source = "override"
            ticker = ov.get("ticker", "")
            name = ov.get("name") or idr.get("name") or s["name"]
        elif suppressed:
            source = "override"
            ticker = ""
            name = ov.get("name") or idr.get("name") or s["name"]
        elif idr.get("ticker"):
            source = idr.get("source", "openfigi")
            ticker = idr["ticker"]
            name = idr.get("name") or s["name"]
        elif idr.get("source") == "company_tickers":
            source = "company_tickers"
            ticker = ""
            name = idr.get("name") or s["name"]
        else:
            source = "filing"
            ticker = s["ticker_in_filing"]
            name = s["name"]

        figi = "" if source == "override" or suppressed else idr.get("figi", "")
        sec_type = ov.get("security_type") or idr.get("security_type", "")
        rows.append({
            "cusip": cusip, "ticker": ticker, "name": name,
            "cik": ov.get("cik") or idr.get("cik", ""),
            "isin": cusip_to_isin(cusip),
            "figi": figi,
            "composite_figi": "" if source == "override" else idr.get("composite_figi", ""),
            "share_class_figi": "" if source == "override" else idr.get("share_class_figi", ""),
            "security_type": sec_type,
            "market_sector": idr.get("market_sector", ""),
            "exch_code": idr.get("exch_code", ""),
            "is_active": bool(s["is_active"]),
            "first_seen_quarter": s["first_seen_quarter"],
            "last_seen_quarter": s["last_seen_quarter"],
            "n_filings": int(s["n_filings"]),
            "resolution_source": source,
            "resolution_status": _status(ticker, figi, source, suppressed),
            "built_at": datetime.utcnow().isoformat(),
        })

    ref = pd.DataFrame(rows, columns=_REFERENCE_COLS)
    SECURITY_REFERENCE_FILE.parent.mkdir(parents=True, exist_ok=True)
    ref.to_csv(SECURITY_REFERENCE_FILE, index=False)
    vc = ref["resolution_status"].value_counts().to_dict()
    return {
        "total": len(ref),
        "resolved": vc.get("resolved", 0) + vc.get("ticker_only", 0),
        "ticker_only": vc.get("ticker_only", 0),
        "name_only": vc.get("name_only", 0),
        "unresolved": vc.get("unresolved", 0),
        "path": str(SECURITY_REFERENCE_FILE),
    }
```

Then create `config/security_overrides.csv`:

```csv
# Security identifier overrides and suppressions. Committed to git.
# Highest precedence when building data/processed/security_reference.csv.
#
# Columns: cusip,ticker,name,security_type,cik,note
#   - A row with a non-blank ticker SUPPLIES that ticker (and any other
#     non-blank fields).
#   - A row with a BLANK ticker is a SUPPRESSION: it forces ticker="" and caps
#     resolution_status at "name_only", overriding even a confident OpenFIGI
#     hit. Use for recycled / delisted CUSIPs with no tradable ticker.
#
cusip,ticker,name,security_type,cik,note
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_security_reference.py -v`
Expected: PASS (all classes).

- [ ] **Step 5: Commit**

```bash
git add utils/security_reference.py config/security_overrides.csv tests/test_security_reference.py
git commit -m "feat: build_security_reference merge with override/suppression precedence"
```

---

## Task 6: `enrich_holdings_with_reference`

**Files:**
- Modify: `utils/security_reference.py`
- Test: `tests/test_security_reference.py`

**Interfaces:**
- Consumes: `load_security_reference` (Task 5).
- Produces: `enrich_holdings_with_reference(df: pd.DataFrame) -> pd.DataFrame` — given a holdings frame with a `cusip` column, returns a copy where:
  - `ticker` is filled from the reference table where the incoming `ticker` is blank/NaN (a non-blank incoming `ticker` is left as-is); result `ticker` is always a string, `""` never `NaN`.
  - `name` column added/updated from the reference (`company_name` used as the source if the frame already has one and reference lacks the row).
  - `resolution_status` column added (`"unresolved"` when the CUSIP is not in the reference / reference is absent).
  - If the reference file does not exist, the frame is returned with `ticker` normalized to `""` and `resolution_status="unresolved"`, no exception.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_security_reference.py
class TestEnrichHoldings:
    def test_fills_blank_tickers(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sr, "SECURITY_REFERENCE_FILE", tmp_path / "ref.csv")
        pd.DataFrame([
            {**{c: "" for c in sr._REFERENCE_COLS}, "cusip": "111111111", "ticker": "ACME",
             "name": "Acme Bio Inc.", "resolution_status": "resolved"},
            {**{c: "" for c in sr._REFERENCE_COLS}, "cusip": "222222222", "ticker": "",
             "name": "Ghost Inc", "resolution_status": "unresolved"},
        ]).to_csv(tmp_path / "ref.csv", index=False)

        df = pd.DataFrame([
            {"cusip": "111111111", "ticker": None, "shares": 10},
            {"cusip": "222222222", "ticker": "", "shares": 5},
            {"cusip": "333333333", "ticker": "KEEP", "shares": 1},
        ])
        out = sr.enrich_holdings_with_reference(df).set_index("cusip")

        assert out.loc["111111111", "ticker"] == "ACME"
        assert out.loc["111111111", "name"] == "Acme Bio Inc."
        assert out.loc["222222222", "ticker"] == ""
        assert out.loc["222222222", "resolution_status"] == "unresolved"
        assert out.loc["333333333", "ticker"] == "KEEP"        # incoming ticker preserved
        assert out["ticker"].isna().sum() == 0

    def test_missing_reference_degrades(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sr, "SECURITY_REFERENCE_FILE", tmp_path / "nope.csv")
        df = pd.DataFrame([{"cusip": "111111111", "ticker": None, "shares": 1}])
        out = sr.enrich_holdings_with_reference(df)
        assert out.loc[0, "ticker"] == ""
        assert out.loc[0, "resolution_status"] == "unresolved"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_security_reference.py::TestEnrichHoldings -v`
Expected: FAIL — `AttributeError: ... 'enrich_holdings_with_reference'`.

- [ ] **Step 3: Write minimal implementation**

```python
# add to utils/security_reference.py
def enrich_holdings_with_reference(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "ticker" not in out.columns:
        out["ticker"] = ""
    out["ticker"] = out["ticker"].fillna("").astype(str).str.strip()
    out["cusip"] = out["cusip"].astype(str).str.strip().str.upper()

    ref = load_security_reference()
    if ref.empty:
        out["name"] = out["company_name"] if "company_name" in out.columns else ""
        out["resolution_status"] = "unresolved"
        return out

    ref = ref.set_index("cusip")
    ref_ticker = out["cusip"].map(ref["ticker"]).fillna("")
    blank = out["ticker"] == ""
    out.loc[blank, "ticker"] = ref_ticker[blank]
    out["ticker"] = out["ticker"].fillna("")

    ref_name = out["cusip"].map(ref["name"]).fillna("")
    if "company_name" in out.columns:
        out["name"] = ref_name.where(ref_name != "", out["company_name"].fillna(""))
    else:
        out["name"] = ref_name
    out["resolution_status"] = out["cusip"].map(ref["resolution_status"]).fillna("unresolved")
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_security_reference.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add utils/security_reference.py tests/test_security_reference.py
git commit -m "feat: add enrich_holdings_with_reference shared helper"
```

---

## Task 7: `scripts/build_security_reference.py` CLI

**Files:**
- Create: `scripts/build_security_reference.py`

**Interfaces:**
- Consumes: `collect_filing_cusips`, `resolve_cusips`, `build_security_reference`, `load_security_reference` (Tasks 2, 4, 5).
- Produces: a runnable script. `python scripts/build_security_reference.py [--force] [--no-api]`. Writes `docs/security_reference_coverage_<YYYY-MM-DD>.log`.

- [ ] **Step 1: Write the script**

```python
"""
Build data/processed/security_reference.csv from the 13F filing corpus.

Usage:
    python scripts/build_security_reference.py            # resolve only new CUSIPs
    python scripts/build_security_reference.py --force    # re-resolve everything
    python scripts/build_security_reference.py --no-api   # cache + overrides only
"""
import argparse
import sys
from datetime import date
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utils.security_reference import (
    collect_filing_cusips, resolve_cusips, build_security_reference,
    load_security_reference,
)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="re-resolve all CUSIPs")
    ap.add_argument("--no-api", action="store_true", help="skip OpenFIGI/SEC calls")
    args = ap.parse_args()

    sweep = collect_filing_cusips()
    print(f"Swept {len(sweep)} distinct CUSIPs from 13F filings.")

    if not args.no_api:
        want = sweep[["cusip", "name"]]
        resolved = resolve_cusips(want, force=args.force)
        print(f"Resolved {len(resolved)} new CUSIP(s) this run.")

    stats = build_security_reference()
    print(f"Wrote {stats['path']}: {stats['total']} rows "
          f"({stats['resolved']} resolved, {stats['name_only']} name_only, "
          f"{stats['unresolved']} unresolved).")

    ref = load_security_reference()
    worklist = ref[ref["resolution_status"].isin(["name_only", "unresolved"])]
    report = project_root / "docs" / f"security_reference_coverage_{date.today()}.log"
    with report.open("w", encoding="utf-8") as fh:
        fh.write(f"Security reference coverage — {date.today()}\n")
        for k, v in stats.items():
            fh.write(f"  {k}: {v}\n")
        fh.write("\nManual-triage worklist (add rows to config/security_overrides.csv):\n")
        fh.write(worklist[["cusip", "name", "first_seen_quarter", "last_seen_quarter",
                           "n_filings", "is_active", "resolution_status"]]
                 .to_csv(index=False))
    print(f"Coverage report: {report}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Smoke-test with the API disabled**

Run: `python scripts/build_security_reference.py --no-api`
Expected: prints a sweep count (~490), writes `data/processed/security_reference.csv` and a coverage log; exit 0. (Most rows `unresolved` at this point — that is fine; Task 12 does the real resolve run.)

- [ ] **Step 3: Commit**

```bash
git add scripts/build_security_reference.py
git commit -m "feat: add build_security_reference CLI with coverage report"
```

---

## Task 8: Holdings pipeline — keep every CUSIP + carry `filing_value`

**Files:**
- Modify: `utils/holdings_operations.py` (`resolve_tickers_from_cusip_cache` ~26-72; `process_quarterly_filings_to_daily_holdings` body ~141-243)
- Test: `tests/test_holdings_operations.py` *(new)*

**Interfaces:**
- Consumes: `enrich_holdings_with_reference` (Task 6).
- Produces: `process_quarterly_filings_to_daily_holdings(portfolio_id, start_date=..., end_date=None) -> pd.DataFrame` now returns columns `portfolio, cusip, ticker, shares, filing_value, eod_date` — **no rows dropped for a blank ticker**; `ticker` blank is `""`. `filing_value` = the filing's `value` for that position, forward-filled across the date range; exit records carry `filing_value=0.0`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_holdings_operations.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import pytest
from utils import holdings_operations as ho
from utils import security_reference as sr

_FILING_COLS = [
    "company_name", "share_class", "cusip", "value", "shares", "option_type",
    "investment_discretion", "voting_authority_sole", "voting_authority_shared",
    "voting_authority_none", "ticker", "portfolio_id", "filing_date", "period_end_date",
]


def _filing(path, rows, filing_date, period_end):
    df = pd.DataFrame(rows)
    df["portfolio_id"] = "baker-bros"
    df["filing_date"] = filing_date
    df["period_end_date"] = period_end
    for c in _FILING_COLS:
        if c not in df.columns:
            df[c] = ""
    df[_FILING_COLS].to_csv(path, index=False)


@pytest.fixture
def filings_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(ho, "FILINGS_DIR", tmp_path)
    # reference with one resolved, one unresolved CUSIP
    ref = tmp_path / "ref.csv"
    pd.DataFrame([
        {**{c: "" for c in sr._REFERENCE_COLS}, "cusip": "111111111", "ticker": "ACME",
         "name": "Acme Bio Inc.", "resolution_status": "resolved"},
        {**{c: "" for c in sr._REFERENCE_COLS}, "cusip": "999999999", "ticker": "",
         "name": "Ghost Inc", "resolution_status": "unresolved"},
    ]).to_csv(ref, index=False)
    monkeypatch.setattr(sr, "SECURITY_REFERENCE_FILE", ref)
    return tmp_path


def test_unresolved_position_is_kept_with_filing_value(filings_dir):
    _filing(filings_dir / "baker-bros_2025-02-14_holdings.csv", [
        {"company_name": "Acme Bio Inc.", "cusip": "111111111", "ticker": "ACME", "value": 100.0, "shares": 10},
        {"company_name": "Ghost Inc", "cusip": "999999999", "ticker": "", "value": 40.0, "shares": 4},
    ], "2025-02-14", "2024-12-31")

    out = ho.process_quarterly_filings_to_daily_holdings("baker-bros", start_date="2024-12-31", end_date="2025-01-05")

    assert set(out.columns) == {"portfolio", "cusip", "ticker", "shares", "filing_value", "eod_date"}
    ghost = out[out["cusip"] == "999999999"]
    assert not ghost.empty                      # NOT dropped
    assert (ghost["ticker"] == "").all()        # blank string, not NaN
    assert ghost["ticker"].isna().sum() == 0
    assert (ghost["filing_value"] == 40.0).all()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_holdings_operations.py -v`
Expected: FAIL — `KeyError: 'filing_value'` or the ghost row is missing (old `notna()` drop) / `AttributeError` on `ho.FILINGS_DIR` if not module-level. If `FILINGS_DIR` is not a module constant, add `FILINGS_DIR = PROJECT_ROOT / "data" / "raw" / "13f_filings"` near the top of `holdings_operations.py` and have `process_quarterly_filings_to_daily_holdings` use it (it currently hardcodes the glob via a local — check line ~131).

- [ ] **Step 3: Write the implementation**

In `utils/holdings_operations.py`:

1. Replace `resolve_tickers_from_cusip_cache` with a thin wrapper (keep the name as a back-compat alias, or rename + update the call site at ~142):

```python
from utils.security_reference import enrich_holdings_with_reference

def resolve_tickers_from_reference(holdings_df: pd.DataFrame) -> pd.DataFrame:
    """Fill blank tickers and add name/resolution_status from security_reference.csv."""
    return enrich_holdings_with_reference(holdings_df)

# keep old name working for any external caller
resolve_tickers_from_cusip_cache = resolve_tickers_from_reference
```

2. In `process_quarterly_filings_to_daily_holdings`, change the per-filing call (line ~142) to `resolve_tickers_from_reference(df)`.

3. **Delete the drop** at line ~175. Replace:

```python
        # Filter to valid tickers only (skip unresolved)
        valid_holdings = filing_df[filing_df['ticker'].notna()].copy()
        if len(valid_holdings) < len(filing_df):
            skipped = len(filing_df) - len(valid_holdings)
            logger.warning(f"  Skipping {skipped} positions with unresolved tickers")
```

with:

```python
        # Keep every position; unresolved ones carry a blank ticker + their filing value.
        valid_holdings = filing_df.copy()
        valid_holdings['ticker'] = valid_holdings['ticker'].fillna('').astype(str)
        unresolved = int((valid_holdings['ticker'] == '').sum())
        if unresolved:
            logger.info(f"  {unresolved} positions have no ticker yet (kept, keyed by CUSIP)")
```

4. In the per-position record builder (line ~187), add `filing_value`:

```python
            ticker_df = pd.DataFrame({
                'portfolio': portfolio_id,
                'ticker': row['ticker'],
                'cusip': row['cusip'],
                'shares': row['shares'],
                'filing_value': row['value'],
                'eod_date': date_range,
            })
```

5. In the exit-record builder (line ~211), add `filing_value` and defer the CUSIP lookup to Task 9 (for now use `row`-free construction from `detect_position_exits` output — Task 9 changes that function to return CUSIPs). Interim: build exit rows with `'filing_value': [0.0]`.

6. Final `sort_values` at line ~238 stays `['eod_date', 'ticker']` (ticker is now always a string).

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_holdings_operations.py -v`
Expected: PASS.

- [ ] **Step 5: Run the full suite**

Run: `pytest tests/ -v`
Expected: PASS (existing tests unaffected; `test_drift.py`, `test_strategy_registry.py`, etc. green).

- [ ] **Step 6: Commit**

```bash
git add utils/holdings_operations.py utils/security_reference.py tests/test_holdings_operations.py
git commit -m "fix: stop dropping blank-ticker 13F positions; carry filing_value"
```

---

## Task 9: Holdings pipeline — re-key `detect_position_exits` on CUSIP

**Files:**
- Modify: `utils/holdings_operations.py` (`detect_position_exits` ~76-95; exit-record builder ~203-224)
- Test: `tests/test_holdings_operations.py`

**Interfaces:**
- Produces: `detect_position_exits(current_filing_df, next_filing_df) -> list[str]` — now returns **CUSIPs** present in `current` but not `next`. The exit-record builder keys on CUSIP and no longer does a ticker→cusip `.iloc[0]` lookup.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_holdings_operations.py
def test_exit_detected_for_blank_ticker_position(filings_dir):
    _filing(filings_dir / "baker-bros_2025-02-14_holdings.csv", [
        {"company_name": "Acme Bio Inc.", "cusip": "111111111", "ticker": "ACME", "value": 100.0, "shares": 10},
        {"company_name": "Ghost Inc", "cusip": "999999999", "ticker": "", "value": 40.0, "shares": 4},
    ], "2025-02-14", "2024-12-31")
    _filing(filings_dir / "baker-bros_2025-05-15_holdings.csv", [
        {"company_name": "Acme Bio Inc.", "cusip": "111111111", "ticker": "ACME", "value": 110.0, "shares": 11},
    ], "2025-05-15", "2025-03-31")

    out = ho.process_quarterly_filings_to_daily_holdings("baker-bros", start_date="2024-12-31", end_date="2025-04-01")

    ghost = out[(out["cusip"] == "999999999")]
    # a shares=0 record on the next period end (2025-03-31)
    assert (ghost["shares"] == 0.0).any()
    assert ghost[ghost["shares"] == 0.0]["eod_date"].iloc[0] == "2025-03-31"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_holdings_operations.py::test_exit_detected_for_blank_ticker_position -v`
Expected: FAIL — exit not detected (old code keyed on `ticker.dropna()`, so a blank-ticker exit is invisible) or `IndexError` in the ticker→cusip `.iloc[0]` lookup.

- [ ] **Step 3: Write the implementation**

```python
# detect_position_exits
def detect_position_exits(current_filing_df: pd.DataFrame, next_filing_df: pd.DataFrame) -> List[str]:
    """CUSIPs present in the current filing but absent from the next one."""
    cur = set(current_filing_df['cusip'].dropna())
    nxt = set(next_filing_df['cusip'].dropna())
    exited = cur - nxt
    if exited:
        logger.info(f"Detected {len(exited)} position exits: {sorted(exited)[:10]}...")
    return list(exited)
```

```python
# exit-record builder (~211) — iterate CUSIPs, no ticker lookup
            for exited_cusip in exited_tickers:   # now CUSIPs
                exit_df = pd.DataFrame({
                    'portfolio': [portfolio_id],
                    'ticker': [''],
                    'cusip': [exited_cusip],
                    'shares': [0.0],
                    'filing_value': [0.0],
                    'eod_date': [pd.to_datetime(next_period_end)],
                })
                exit_records.append(exit_df)
```

(Rename the loop var / `exited_tickers` → `exited_cusips` for clarity.)

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_holdings_operations.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add utils/holdings_operations.py tests/test_holdings_operations.py
git commit -m "fix: re-key position-exit detection on CUSIP, not ticker"
```

---

## Task 10: Holdings pipeline — left price join + `has_price` + blank-ticker invariant

**Files:**
- Modify: `utils/holdings_operations.py` (`calculate_portfolio_values` ~329-373; `save_processed_holdings` ~376-409)
- Test: `tests/test_holdings_operations.py`

**Interfaces:**
- Produces:
  - `calculate_portfolio_values(holdings_df, prices_df) -> pd.DataFrame` with columns `eod_date, cusip, ticker, shares, filing_value, close, has_price, position_value`. Left join on `['ticker','eod_date']`; `has_price = close.notna()`; `position_value = shares*close` where `has_price` else `NaN`. Rows are **never dropped**.
  - `save_processed_holdings(df, path)` asserts `df['ticker']` has no NaN before the categorical cast and writes exactly `portfolio, cusip, ticker, shares, filing_value, eod_date`.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_holdings_operations.py
def test_left_join_keeps_unpriced_rows():
    holdings = pd.DataFrame([
        {"portfolio": "baker-bros", "cusip": "111111111", "ticker": "ACME", "shares": 10,
         "filing_value": 100.0, "eod_date": "2025-01-02"},
        {"portfolio": "baker-bros", "cusip": "999999999", "ticker": "", "shares": 4,
         "filing_value": 40.0, "eod_date": "2025-01-02"},
        {"portfolio": "baker-bros", "cusip": "111111111", "ticker": "ACME", "shares": 10,
         "filing_value": 100.0, "eod_date": "2025-01-03"},   # price gap this day
    ])
    prices = pd.DataFrame([{"ticker": "ACME", "date": "2025-01-02", "close": 5.0}])

    out = ho.calculate_portfolio_values(holdings, prices)

    assert len(out) == 3                        # nothing dropped
    priced = out[(out["cusip"] == "111111111") & (out["eod_date"] == "2025-01-02")].iloc[0]
    assert priced["has_price"] is True or priced["has_price"] == True
    assert priced["position_value"] == 50.0
    gap = out[(out["cusip"] == "111111111") & (out["eod_date"] == "2025-01-03")].iloc[0]
    assert bool(gap["has_price"]) is False
    assert pd.isna(gap["position_value"])
    blank = out[out["cusip"] == "999999999"].iloc[0]
    assert bool(blank["has_price"]) is False


def test_save_processed_holdings_roundtrips_blank_tickers(tmp_path):
    df = pd.DataFrame([
        {"portfolio": "baker-bros", "cusip": "111111111", "ticker": "ACME", "shares": 10,
         "filing_value": 100.0, "eod_date": "2025-01-02"},
        {"portfolio": "baker-bros", "cusip": "999999999", "ticker": "", "shares": 4,
         "filing_value": 40.0, "eod_date": "2025-01-02"},
    ])
    out_file = tmp_path / "holdings.csv"
    ho.save_processed_holdings(df, out_file)
    back = pd.read_csv(out_file, dtype={"ticker": str}).fillna({"ticker": ""})
    assert list(back.columns) == ["portfolio", "cusip", "ticker", "shares", "filing_value", "eod_date"]
    assert back["ticker"].tolist() == ["ACME", ""]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_holdings_operations.py -v`
Expected: FAIL — `calculate_portfolio_values` drops the gap row (`how='inner'`) and has no `has_price` column; `save_processed_holdings` writes the wrong column set / errors on the blank-ticker category sort.

- [ ] **Step 3: Write the implementation**

```python
# calculate_portfolio_values
    merged = holdings_df.merge(
        prices_df,
        left_on=['ticker', 'eod_date'],
        right_on=['ticker', 'date'],
        how='left',
    )
    merged['has_price'] = merged['close'].notna()
    merged['position_value'] = merged['shares'] * merged['close']   # NaN where no close

    total = len(holdings_df)
    unpriced = int((~merged['has_price']).sum())
    if unpriced:
        logger.info(f"{unpriced}/{total} position-days unpriced (kept, position_value=NaN)")

    cols = ['eod_date', 'cusip', 'ticker', 'shares', 'filing_value', 'close',
            'has_price', 'position_value']
    return merged[[c for c in cols if c in merged.columns]].copy()
```

```python
# save_processed_holdings
    df = holdings_df.copy()
    df['ticker'] = df['ticker'].fillna('').astype(str)
    assert not df['ticker'].isna().any(), "blank ticker must be '' not NaN"
    keep = ['portfolio', 'cusip', 'ticker', 'shares', 'filing_value', 'eod_date']
    df = df[keep]
    df['ticker'] = df['ticker'].astype('category')
    df['portfolio'] = df['portfolio'].astype('category')
    df = df.sort_values(['eod_date', 'ticker']).reset_index(drop=True)
    df.to_csv(output_file, index=False)
```

Update both docstrings to the new column lists.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_holdings_operations.py -v && pytest tests/ -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add utils/holdings_operations.py tests/test_holdings_operations.py
git commit -m "fix: left-join prices so unpriced positions survive; add has_price"
```

---

## Task 11: `csv_data` read-time enrichment

**Files:**
- Modify: `utils/csv_data.py` (`load_holdings_by_date` ~135-165; `load_processed_holdings` ~187-215)
- Test: `tests/test_holdings_operations.py` (or a new `tests/test_csv_data.py` — keep it with the other holdings tests)

**Interfaces:**
- Consumes: `enrich_holdings_with_reference` (Task 6).
- Produces:
  - `load_holdings_by_date(portfolio_id, filing_date)` — result additionally has `ticker` blanks filled and `name` / `resolution_status` columns from the reference; unchanged when the reference file is absent (no exception, `resolution_status="unresolved"`).
  - `load_processed_holdings(portfolio_id, start_date=None)` — result has `name` and `resolution_status` left-joined from the reference; `ticker` normalized to `""`.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_holdings_operations.py
from utils import csv_data


def test_load_holdings_by_date_enriches_blank_ticker(tmp_path, monkeypatch):
    hd = tmp_path / "baker-bros_2025-02-14_holdings.csv"
    _filing(hd, [
        {"company_name": "Ghost Inc", "cusip": "999999999", "ticker": "", "value": 40.0, "shares": 4},
        {"company_name": "Acme Bio Inc.", "cusip": "111111111", "ticker": "", "value": 100.0, "shares": 10},
    ], "2025-02-14", "2024-12-31")
    monkeypatch.setattr(csv_data, "HOLDINGS_DIR", tmp_path)
    ref = tmp_path / "ref.csv"
    pd.DataFrame([
        {**{c: "" for c in sr._REFERENCE_COLS}, "cusip": "111111111", "ticker": "ACME",
         "name": "Acme Bio Inc.", "resolution_status": "resolved"},
    ]).to_csv(ref, index=False)
    monkeypatch.setattr(sr, "SECURITY_REFERENCE_FILE", ref)

    out = csv_data.load_holdings_by_date("baker-bros", "2025-02-14").set_index("cusip")
    assert out.loc["111111111", "ticker"] == "ACME"
    assert out.loc["999999999", "ticker"] == ""
    assert out.loc["999999999", "resolution_status"] == "unresolved"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_holdings_operations.py::test_load_holdings_by_date_enriches_blank_ticker -v`
Expected: FAIL — `ticker` stays blank; no `resolution_status` column.

- [ ] **Step 3: Write the implementation**

In `utils/csv_data.py`, import at top: `from utils.security_reference import enrich_holdings_with_reference`.

In `load_holdings_by_date`, after `df = pd.read_csv(filepath)` and before the weight calc:

```python
    if not df.empty:
        df = enrich_holdings_with_reference(df)
```

In `load_processed_holdings`, before `return df`:

```python
    if not df.empty:
        df = enrich_holdings_with_reference(df)
```

(Enrichment is a no-op-safe pass-through when the reference file is missing.)

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/ -v`
Expected: PASS. Watch `tests/test_drift.py` and `tests/test_strategy_registry.py` — they exercise `load_holdings_by_date` transitively; they must stay green.

- [ ] **Step 5: Commit**

```bash
git add utils/csv_data.py tests/test_holdings_operations.py
git commit -m "feat: enrich holdings with security_reference at read time"
```

---

## Task 12: Real resolve run + override triage + regenerate holdings

**Files:**
- Modify: `config/security_overrides.csv` (add triaged rows)
- Regenerates (gitignored): `data/raw/security_identifiers.csv`, `data/processed/security_reference.csv`, `data/processed/holdings.csv`
- Adds: `docs/security_reference_coverage_<date>.log`

**This task makes live OpenFIGI / SEC calls. Not a unit test — an operational run.**

- [ ] **Step 1: Full build**

Run: `python scripts/build_security_reference.py`
Expected: ~490 CUSIPs swept; a few hundred resolved via OpenFIGI; a coverage report at `docs/security_reference_coverage_<date>.log`. Note the `unresolved` / `name_only` counts.

- [ ] **Step 2: Triage the worklist**

Open the coverage log. For each `is_active` CUSIP that is `unresolved` or `name_only`, add a row to `config/security_overrides.csv`:
- known ticker → `cusip,TICKER,Name,Common Stock,,source`
- delisted / no tradable ticker → `cusip,,Name,,,<reason>` (suppression)
Re-run `python scripts/build_security_reference.py` until every `is_active` CUSIP is `resolved` or a deliberate suppression.

- [ ] **Step 3: Regenerate holdings**

Run: `python scripts/consolidate_holdings.py`
Expected: unique CUSIP count up from ~155; `save_processed_holdings` logs the new column set `['portfolio','cusip','ticker','shares','filing_value','eod_date']`; no crash on blank tickers.

- [ ] **Step 4: Sanity-check the numbers**

Run:
```bash
python -c "import pandas as pd; d=pd.read_csv('data/processed/holdings.csv'); print('rows',len(d),'cusips',d.cusip.nunique(),'blank tk',(d.ticker.fillna('')=='').mean())"
```
Expected: more CUSIPs than before; a non-zero but minority blank-ticker share; `filing_value` populated.

- [ ] **Step 5: Commit** (overrides + coverage report only — `data/` is gitignored)

```bash
git add config/security_overrides.csv docs/security_reference_coverage_*.log
git commit -m "chore: triage security identifier overrides to full active coverage"
```

---

## Task 13: Downstream UI guards (Dashboard, Admin, Signals)

**Files:**
- Modify: `dashboard/pages/1_Dashboard.py` (~119-140, "Portfolio Value Over Time")
- Modify: `dashboard/pages/5_Admin.py` (Processing tab, near the consolidate buttons ~124-130)
- Modify: `dashboard/pages/4_Signals.py` (holdings display ~42-72)

**Interfaces:**
- Consumes: `load_processed_holdings` (now carries `resolution_status`, Task 11); `calculate_portfolio_values` (now carries `has_price`, `filing_value`, Task 10); `build_security_reference` / `load_security_reference` (Task 5).

- [ ] **Step 1: Dashboard — unpriced caption**

In `dashboard/pages/1_Dashboard.py`, after `port_values = calculate_portfolio_values(holdings_hist, ff_prices)`:

```python
        unpriced = port_values[~port_values["has_price"]]
        if not unpriced.empty:
            latest = port_values["eod_date"].max()
            gap = unpriced.loc[unpriced["eod_date"] == latest, "filing_value"].sum()
            n = unpriced.loc[unpriced["eod_date"] == latest, "cusip"].nunique()
            st.caption(f"{n} positions unpriced on {latest} — ${gap:,.0f} by last 13F value "
                       f"(excluded from the priced total below).")
```

Keep the existing `groupby("eod_date")["position_value"].sum()` — `.sum()` already skips NaN.

- [ ] **Step 2: Admin — build button + coverage metric**

In `dashboard/pages/5_Admin.py`, Processing tab, add beside "Consolidate securities":

```python
        if st.button("Build security reference"):
            run_script("build_security_reference.py", "Build security reference")

    from utils.security_reference import load_security_reference
    _ref = load_security_reference()
    if not _ref.empty:
        vc = _ref["resolution_status"].value_counts()
        resolved = int(vc.get("resolved", 0) + vc.get("ticker_only", 0))
        st.caption(f"security_reference.csv: {len(_ref)} CUSIPs — {resolved} resolved, "
                   f"{int(vc.get('name_only', 0))} name-only, {int(vc.get('unresolved', 0))} unresolved")
```

(Confirm `run_script` is the existing helper in that file; match its call signature.)

- [ ] **Step 3: Signals — show name when ticker blank**

In `dashboard/pages/4_Signals.py`, where the holdings table is built for display, add a display column:

```python
    holdings["display"] = holdings["ticker"].where(
        holdings["ticker"].astype(str) != "", holdings.get("name", holdings.get("company_name", ""))
    )
```

and include `"display"` (or swap it for `ticker`) in the shown columns / export.

- [ ] **Step 4: Smoke-test**

Run: `streamlit run dashboard/app.py` — open Dashboard (caption renders when unpriced positions exist), Admin → Processing (button + caption render), Signals (blank-ticker rows show the issuer name). No tracebacks.

- [ ] **Step 5: Commit**

```bash
git add dashboard/pages/1_Dashboard.py dashboard/pages/5_Admin.py dashboard/pages/4_Signals.py
git commit -m "feat: surface unpriced positions and security-reference coverage in the dashboard"
```

---

## Task 14: Docs — CLAUDE.md + spec note

**Files:**
- Modify: `CLAUDE.md`
- Modify: `docs/superpowers/specs/2026-09-08-security-reference-data-design.md` (one note)

- [ ] **Step 1: CLAUDE.md — Key Files**

Add under the Key Files list:
```
- `utils/security_reference.py` - Sweep 13F CUSIPs, resolve identifiers (OpenFIGI + SEC company_tickers name-match), build the master security_reference.csv; `enrich_holdings_with_reference()` fills tickers/names everywhere
- `scripts/build_security_reference.py` - Build data/processed/security_reference.csv + a coverage report
- `config/security_overrides.csv` - Committed manual CUSIP->identifier overrides / suppressions
- `data/processed/security_reference.csv` - Master security reference: one row per CUSIP ever held, with identifiers + provenance + filing history
```

- [ ] **Step 2: CLAUDE.md — Data platform pointer + stale fixes**

- Add a line under "Design Decisions" or a new short "## Data Platform" section:
  `- **Data layout**: raw inputs in \`data/raw/\`, derived tables in \`data/processed/\` (all gitignored); full schema catalogue in \`docs/superpowers/specs/2026-09-08-security-reference-data-design.md\` §3.`
- Fix stale entries: the dashboard page roster is now `1_Dashboard, 2_Trades, 3_Research, 4_Signals, 5_Admin` (not the "8 pages" list); `data/holdings/*.csv` → `data/raw/13f_filings/*.csv`; `data/portfolios.csv` → `data/raw/portfolios.csv`.
- Note `processed/holdings.csv` schema is now `portfolio, cusip, ticker, shares, filing_value, eod_date` and no longer drops unresolved positions.

- [ ] **Step 3: Spec note**

In the spec, §5.4, add: "Implementation note: the name match uses stdlib `difflib.SequenceMatcher` on normalized names (threshold 0.90), not `rapidfuzz` — avoids a new dependency."

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md docs/superpowers/specs/2026-09-08-security-reference-data-design.md
git commit -m "docs: document security reference platform in CLAUDE.md"
```

---

## Self-Review

**1. Spec coverage**

| Spec section | Task(s) |
|---|---|
| §3 data platform catalogue | Task 14 (pointer); catalogue already in the spec |
| §5.1 `security_identifiers.csv` | Task 4 (writes it), Task 3 (fields) |
| §5.2 `security_reference.csv` (all columns incl. `cik`, `share_class_figi`, `isin` CINS gate) | Task 5 (`build_security_reference`), Task 1 (`cusip_to_isin`) |
| §5.3 `config/security_overrides.csv` + suppression semantics | Task 5 (file + `_load_overrides` + suppression logic), Task 12 (triage) |
| §5.4 resolver (OpenFIGI + `company_tickers` name match, `cik_str` capture) | Task 3, Task 4 |
| §5.5 CLI + coverage report + Admin button | Task 7, Task 13 step 2 |
| §6.1 read from reference w/ cusip_cache fallback | Task 8 step 3.1 (via `enrich_holdings_with_reference`; `load_security_reference` returns empty frame when absent — cusip_cache fallback is **dropped** as unnecessary since enrichment degrades gracefully and Task 12 builds the reference before holdings regen) |
| §6.2 remove drop #1 | Task 8 |
| §6.3 re-key exits on cusip incl. `:212` | Task 9 |
| §6.4 inner→left, `has_price`, reworded warning | Task 10 |
| §6.5 holdings.csv schema, `filing_value`, `name` not persisted | Task 8 (filing_value), Task 10 (schema), Task 11 (`name` at read time) |
| §6.6 blank-ticker `""` invariant | Task 8 step 3.3, Task 10 (`save_processed_holdings` assert) |
| §7 `load_processed_holdings` graceful degrade | Task 11, Task 6 (degrade path) |
| §7 Dashboard caption | Task 13 step 1 |
| §7 QoQ enrichment from reference | Task 11 (QoQ calls `load_holdings_by_date`, enriched transitively — no separate task) |
| §7 strategy_engine explicit resolved filter | Covered: `_select_top_holdings` already filters `ticker != ""`; post-enrichment a blank ticker == not-resolved, so the existing guard is now well-founded. No code change. |
| §7 Signals show name | Task 13 step 3 |
| §7 Admin build button + coverage | Task 13 step 2 |
| §9 tests | Tasks 1-11 each carry their tests; Task 12 = manual checks |

*Deviation logged:* §6.1's `cusip_cache.csv` fallback inside the pipeline is dropped — `enrich_holdings_with_reference` already returns a safe pass-through when `security_reference.csv` is absent, and Task 12 builds the reference before the first post-change holdings regen, so the fallback would be dead code. `cusip_cache.csv` itself is untouched (still written by the Add-Security flow), per spec §10.

**2. Placeholder scan** — no TBD/TODO; every code step has real code; no "add error handling" hand-waves; test bodies are concrete.

**3. Type consistency**
- `_IDENTIFIER_COLS` (Task 4) ⊇ the dict `lookup_full` returns (Task 3) + `cusip, source, resolved_at` — consistent.
- `_REFERENCE_COLS` (Task 5) matches the spec §5.2 column list and every `ref[...]` access in Tasks 6, 11, 13.
- `collect_filing_cusips` output columns (Task 2) are consumed by name in `build_security_reference` (Task 5): `name, ticker_in_filing, first_seen_quarter, last_seen_quarter, n_filings, is_active` — consistent.
- `enrich_holdings_with_reference` (Task 6) adds `ticker`(filled), `name`, `resolution_status` — consumed in Tasks 8, 11, 13 under those exact names.
- `calculate_portfolio_values` output `eod_date, cusip, ticker, shares, filing_value, close, has_price, position_value` (Task 10) — consumed in Task 13 step 1 (`has_price`, `filing_value`, `cusip`, `eod_date`, `position_value`) — consistent.
- `detect_position_exits` returns CUSIPs (Task 9); the exit-record builder in Task 8 step 3.5 is explicitly reconciled in Task 9 step 3 — consistent.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-09-08-security-reference-data.md`. Two execution options:

1. **Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
