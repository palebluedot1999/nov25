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
