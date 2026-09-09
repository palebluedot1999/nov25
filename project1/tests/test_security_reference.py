import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
from utils.security_reference import cusip_to_isin, collect_filing_cusips

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
