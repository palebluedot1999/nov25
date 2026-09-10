import time
from unittest.mock import patch

from scrapers.sec_edgar import SECEdgarScraper, normalize_13f_value


def test_pre_boundary_date_scaled_to_dollars():
    """A reporting period before the SEC's 2022-12-31 amendment is in thousands; multiply by 1000."""
    assert normalize_13f_value(149438.0, "2022-09-30") == 149438000.0


def test_post_boundary_date_unchanged():
    """A reporting period after the amendment is already in whole dollars."""
    assert normalize_13f_value(105860323.0, "2023-03-31") == 105860323.0


def test_boundary_date_itself_unchanged():
    """The exact effective-date period (2022-12-31) is already in whole dollars."""
    assert normalize_13f_value(19327911.0, "2022-12-31") == 19327911.0


def test_missing_period_end_date_returns_value_unscaled():
    """An empty or NaN period_end_date (as pandas produces for a missing value) is a no-op, not a scale-up."""
    assert normalize_13f_value(500.0, "") == 500.0
    assert normalize_13f_value(500.0, float("nan")) == 500.0


class _StubResponse:
    """Minimal stand-in for requests.Response used by get_13f_holdings."""

    def json(self):
        return {"directory": {"item": [{"name": "form13fInfoTable.xml"}]}}

    @property
    def text(self):
        return ""


def test_get_13f_holdings_applies_normalization_to_parsed_rows():
    """The normalization loop inside get_13f_holdings must actually run on parsed holdings.

    Guards against the wiring being deleted: the pure-function tests above would
    still pass, but the scraper would silently emit thousands-scale values.
    """
    parsed = [{"cusip": "X", "shares": 100, "value": 5000.0}]

    with patch.object(SECEdgarScraper, "_make_request", return_value=_StubResponse()), \
         patch.object(SECEdgarScraper, "_parse_info_table", return_value=[dict(parsed[0])]):
        scaled = SECEdgarScraper().get_13f_holdings("0000000000", "acc-1", "2022-09-30")
    assert scaled[0]["value"] == 5000000.0

    with patch.object(SECEdgarScraper, "_make_request", return_value=_StubResponse()), \
         patch.object(SECEdgarScraper, "_parse_info_table", return_value=[dict(parsed[0])]):
        unchanged = SECEdgarScraper().get_13f_holdings("0000000000", "acc-1", "2023-03-31")
    assert unchanged[0]["value"] == 5000.0


# --- XML hardening (CodeQL py/xml-bomb) --------------------------------------

_GOOD_INFOTABLE = """<?xml version="1.0" encoding="UTF-8"?>
<informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable">
  <infoTable>
    <nameOfIssuer>ACME BIO INC</nameOfIssuer>
    <titleOfClass>COM</titleOfClass>
    <cusip>004225108</cusip>
    <value>123456</value>
    <shrsOrPrnAmt><sshPrnamt>7890</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt>
    <investmentDiscretion>SOLE</investmentDiscretion>
    <votingAuthority><Sole>7890</Sole><Shared>0</Shared><None>0</None></votingAuthority>
  </infoTable>
</informationTable>"""

# "Billion laughs": nested internal entities that a naive parser expands to ~1e9 chars.
_BILLION_LAUGHS = """<?xml version="1.0"?>
<!DOCTYPE lolz [
  <!ENTITY lol "lol">
  <!ENTITY lol1 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
  <!ENTITY lol2 "&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;">
  <!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;">
  <!ENTITY lol4 "&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;">
  <!ENTITY lol5 "&lol4;&lol4;&lol4;&lol4;&lol4;&lol4;&lol4;&lol4;&lol4;&lol4;">
]>
<informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable">
  <infoTable><nameOfIssuer>&lol5;</nameOfIssuer><cusip>004225108</cusip><value>1</value></infoTable>
</informationTable>"""


def test_parse_info_table_still_parses_a_normal_filing():
    """Swapping stdlib ElementTree for defusedxml must not change normal parsing."""
    holdings = SECEdgarScraper()._parse_info_table(_GOOD_INFOTABLE)
    assert len(holdings) == 1
    assert holdings[0]["cusip"] == "004225108"
    assert holdings[0]["company_name"] == "ACME BIO INC"
    assert holdings[0]["value"] == 123456.0
    assert holdings[0]["shares"] == 7890.0


def test_parse_info_table_refuses_entity_expansion_bomb():
    """An entity-expansion payload is refused before expansion — no hang, no crash, no rows."""
    start = time.monotonic()
    holdings = SECEdgarScraper()._parse_info_table(_BILLION_LAUGHS)
    elapsed = time.monotonic() - start

    assert holdings == []          # refused, caught, empty result
    assert elapsed < 1.0          # rejected up front, not expanded
