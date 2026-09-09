from scrapers.sec_edgar import normalize_13f_value


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
