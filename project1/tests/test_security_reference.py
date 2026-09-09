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


class TestBuildSecurityReference:
    _DEFAULT_FILING_ROWS = [
        {"company_name": "Acme Bio Inc.", "cusip": "111111111", "ticker": "", "value": 1, "shares": 1},
        {"company_name": "Bond Co", "cusip": "00484MAA4", "ticker": "", "value": 1, "shares": 1},
        {"company_name": "Ghost Inc", "cusip": "222222222", "ticker": "", "value": 1, "shares": 1},
    ]

    def _setup(self, tmp_path, monkeypatch, identifiers_rows, overrides_text, filing_rows=None):
        monkeypatch.setattr(sr, "SECURITY_REFERENCE_FILE", tmp_path / "security_reference.csv")
        monkeypatch.setattr(sr, "SECURITY_IDENTIFIERS_FILE", tmp_path / "ids.csv")
        monkeypatch.setattr(sr, "SECURITY_OVERRIDES_FILE", tmp_path / "security_overrides.csv")
        pd.DataFrame(identifiers_rows, columns=sr._IDENTIFIER_COLS).to_csv(sr.SECURITY_IDENTIFIERS_FILE, index=False)
        (tmp_path / "security_overrides.csv").write_text(overrides_text)
        filings = tmp_path / "filings"
        filings.mkdir()
        _write_filing(
            filings / "f1.csv",
            self._DEFAULT_FILING_ROWS if filing_rows is None else filing_rows,
            "2024-05-15", "2024-03-31",
        )
        monkeypatch.setattr(sr, "FILINGS_DIR", filings)

    def test_precedence_and_status(self, tmp_path, monkeypatch):
        ids = [
            {**{c: "" for c in sr._IDENTIFIER_COLS}, "cusip": "111111111", "ticker": "WRONG",
             "name": "ACME BIO INC", "figi": "BBG1", "source": "openfigi", "resolved_at": "x"},
            {**{c: "" for c in sr._IDENTIFIER_COLS}, "cusip": "00484MAA4", "ticker": "BONDX",
             "name": "BOND CO", "figi": "BBG9", "source": "openfigi", "resolved_at": "x"},
        ]
        overrides = (
            "# cusip,ticker,name,security_type,cik,note\n"
            "cusip,ticker,name,security_type,cik,note\n"
            "111111111,ACME,Acme Bio Inc.,Common Stock,,corrected\n"
            "00484MAA4,,Bond Co,Corp Bond,,no tradable ticker\n"
        )
        self._setup(tmp_path, monkeypatch, ids, overrides)

        stats = sr.build_security_reference()
        ref = sr.load_security_reference().set_index("cusip")

        # override beats openfigi
        assert ref.loc["111111111", "ticker"] == "ACME"
        assert ref.loc["111111111", "resolution_source"] == "override"
        assert ref.loc["111111111", "resolution_status"] == "ticker_only"
        assert ref.loc["111111111", "isin"] == "US1111111118"
        assert ref.loc["111111111", "figi"] == ""          # override rows never carry a figi
        # suppression: blank-ticker override beats a confident openfigi hit
        assert ref.loc["00484MAA4", "ticker"] == ""
        assert ref.loc["00484MAA4", "resolution_status"] == "name_only"
        assert ref.loc["00484MAA4", "resolution_source"] == "override"
        # CINS-safe / unresolved
        assert ref.loc["222222222", "resolution_status"] == "unresolved"
        assert ref.loc["222222222", "ticker"] == ""
        assert stats["total"] == 3
        assert stats["unresolved"] == 1

    def test_ladder_branches_and_status_values(self, tmp_path, monkeypatch):
        ids = [
            # OpenFIGI, ticker + figi -> resolved
            {**{c: "" for c in sr._IDENTIFIER_COLS}, "cusip": "111111111", "ticker": "ACME",
             "name": "ACME BIO INC", "figi": "BBG1", "source": "openfigi", "resolved_at": "x"},
            # OpenFIGI, ticker but no figi -> ticker_only
            {**{c: "" for c in sr._IDENTIFIER_COLS}, "cusip": "222222222", "ticker": "NOFI",
             "name": "NO FIGI CO", "figi": "", "source": "openfigi", "resolved_at": "x"},
            # company_tickers fuzzy match, non-empty ticker -> must NOT be promoted
            {**{c: "" for c in sr._IDENTIFIER_COLS}, "cusip": "333333333", "ticker": "FUZZY",
             "name": "FUZZY MATCH INC", "figi": "", "source": "company_tickers", "resolved_at": "x"},
        ]
        overrides = (
            "# cusip,ticker,name,security_type,cik,note\n"
            "cusip,ticker,name,security_type,cik,note\n"
        )
        filing_rows = [
            {"company_name": "Acme Bio Inc.", "cusip": "111111111", "ticker": "", "value": 1, "shares": 1},
            {"company_name": "No Figi Co", "cusip": "222222222", "ticker": "", "value": 1, "shares": 1},
            {"company_name": "Fuzzy Match Inc", "cusip": "333333333", "ticker": "", "value": 1, "shares": 1},
            # no identifier row, no override, but a ticker present in the filing -> filing fallback
            {"company_name": "Filing Only Corp", "cusip": "444444444", "ticker": "FILE", "value": 1, "shares": 1},
        ]
        self._setup(tmp_path, monkeypatch, ids, overrides, filing_rows=filing_rows)

        stats = sr.build_security_reference()
        ref = sr.load_security_reference().set_index("cusip")

        # resolved: OpenFIGI ticker + figi, no override
        assert ref.loc["111111111", "resolution_status"] == "resolved"
        assert ref.loc["111111111", "resolution_source"] == "openfigi"
        assert ref.loc["111111111", "figi"] != ""
        assert ref.loc["111111111", "ticker"] == "ACME"

        # plain OpenFIGI ticker_only: ticker but no figi
        assert ref.loc["222222222", "resolution_status"] == "ticker_only"
        assert ref.loc["222222222", "resolution_source"] == "openfigi"
        assert ref.loc["222222222", "ticker"] == "NOFI"

        # company_tickers fuzzy match is NOT promoted into the reference
        assert ref.loc["333333333", "ticker"] == ""
        assert ref.loc["333333333", "resolution_status"] == "name_only"
        assert ref.loc["333333333", "resolution_source"] == "company_tickers"

        # filing fallback: no identifier / override, ticker taken from the filing
        assert ref.loc["444444444", "resolution_source"] == "filing"
        assert ref.loc["444444444", "resolution_status"] == "ticker_only"
        assert ref.loc["444444444", "ticker"] == "FILE"

        assert stats["total"] == 4
        assert stats["resolved"] == 1
        assert stats["ticker_only"] == 2
        assert stats["name_only"] == 1
        assert stats["unresolved"] == 0
