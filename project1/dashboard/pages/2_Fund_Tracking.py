"""
Fund Tracking page - view 13F holdings by fund and filing period.
"""

import re
import sys
import pandas as pd
import streamlit as st
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from utils.csv_data import (
    load_portfolios,
    get_all_filings,
    load_holdings_by_date,
    load_qoq_changes,
    get_holdings_files,
    PROCESSED_DATA_DIR,
)
from utils.fund_operations import (
    fetch_fund_name_from_sec,
    create_portfolio_entry,
    pull_latest_13fs_all_funds,
    fetch_incremental_filings_for_fund,
)
from utils.price_operations import fetch_incremental_prices
from scrapers.sec_edgar import SECEdgarScraper

st.title("Fund Tracking")

# ============================================================================
# HELPERS
# ============================================================================

def period_end_to_quarter(period_end_date: str) -> str:
    """Convert period end date to quarter label, e.g. 'Q4 2024'."""
    try:
        dt = pd.to_datetime(period_end_date)
        month = dt.month
        if month <= 3:
            q = "Q1"
        elif month <= 6:
            q = "Q2"
        elif month <= 9:
            q = "Q3"
        else:
            q = "Q4"
        return f"{q} {dt.year}"
    except Exception:
        return period_end_date


def get_prior_filing_date(filings_df: pd.DataFrame, current_filing_date: str):
    """Return the filing_date immediately before current_filing_date, or None."""
    dates = filings_df.sort_values("filing_date", ascending=False)["filing_date"].tolist()
    try:
        idx = dates.index(current_filing_date)
        if idx + 1 < len(dates):
            return dates[idx + 1]
    except ValueError:
        pass
    return None


@st.cache_data(ttl=300)
def load_master_prices() -> dict:
    """Load latest closing price per ticker from master prices.csv. Cached 5 min."""
    prices_path = PROCESSED_DATA_DIR / "prices.csv"
    if not prices_path.exists():
        return {}
    df = pd.read_csv(prices_path, parse_dates=["date"])
    latest = df.sort_values("date").groupby("ticker").tail(1)[["ticker", "close"]]
    return dict(zip(latest["ticker"], latest["close"]))


# ============================================================================
# SECTION A: FUND & PERIOD SELECTORS
# ============================================================================

all_portfolios = load_portfolios(portfolio_type="fund")

# Only show funds that have a CIK (exclude benchmark-style entries)
fund_portfolios = all_portfolios[
    all_portfolios["cik"].notna() & (all_portfolios["cik"].astype(str).str.strip() != "")
]

if fund_portfolios.empty:
    st.warning("No funds are being tracked yet. Use 'Add New Fund' below to get started.")
    fund_name_map = {}
else:
    fund_name_map = dict(zip(fund_portfolios["name"], fund_portfolios.to_dict("records")))

col_fund, col_period = st.columns(2)

with col_fund:
    selected_fund_name = st.selectbox(
        "Fund",
        list(fund_name_map.keys()) if fund_name_map else ["— no funds tracked —"],
        key="ft_fund",
    )

selected_portfolio = fund_name_map.get(selected_fund_name)

if not selected_portfolio:
    st.info("Add a fund below to get started.")
    filings_df = pd.DataFrame()
    selected_filing_date = None
    selected_period_end = None
else:
    portfolio_id = selected_portfolio["id"]
    cik = str(int(float(str(selected_portfolio["cik"]).strip())))

    filings_df = get_all_filings(portfolio_id)

    if filings_df.empty:
        st.warning(f"No filings found for {selected_fund_name}.")
        selected_filing_date = None
        selected_period_end = None
    else:
        # Build period labels newest-first
        filings_df = filings_df.sort_values("filing_date", ascending=False).reset_index(drop=True)
        filings_df["label"] = filings_df.apply(
            lambda r: f"{period_end_to_quarter(r['period_end_date'])} — filed {r['filing_date']}",
            axis=1,
        )

        with col_period:
            selected_label = st.selectbox(
                "Filing Period",
                filings_df["label"].tolist(),
                key="ft_period",
            )

        selected_row = filings_df[filings_df["label"] == selected_label].iloc[0]
        selected_filing_date = selected_row["filing_date"]
        selected_period_end = selected_row["period_end_date"]

# ============================================================================
# SECTION B: HOLDINGS TABLE
# ============================================================================

if selected_portfolio and selected_filing_date:
    current_df = load_holdings_by_date(portfolio_id, selected_filing_date)

    if current_df.empty:
        st.warning("No holdings data for the selected period.")
    else:
        # --- QoQ: load prior filing and pre-computed metrics ---
        prior_filing_date = get_prior_filing_date(filings_df, selected_filing_date)
        is_first_filing = prior_filing_date is None

        # Load pre-computed QoQ table; auto-compute silently if missing
        qoq_df = load_qoq_changes(portfolio_id, selected_filing_date)
        if not is_first_filing and qoq_df.empty:
            from utils.data_processing import compute_and_save_qoq_changes
            with st.spinner("Computing QoQ changes…"):
                compute_and_save_qoq_changes(portfolio_id)
            qoq_df = load_qoq_changes(portfolio_id, selected_filing_date)
        has_qoq_table = not qoq_df.empty

        if not is_first_filing:
            prior_df = load_holdings_by_date(portfolio_id, prior_filing_date)
            if not prior_df.empty:
                prior_total_value = prior_df["value"].sum()
                prior_subset = prior_df[["cusip", "shares", "value"]].rename(
                    columns={"shares": "prior_shares", "value": "prior_value"}
                )
                merged = current_df.merge(prior_subset, on="cusip", how="left")
            else:
                prior_total_value = 0
                merged = current_df.copy()
                merged["prior_shares"] = None
                merged["prior_value"] = None
        else:
            prior_total_value = 0
            merged = current_df.copy()
            merged["prior_shares"] = None
            merged["prior_value"] = None

        # --- Latest prices ---
        latest_prices = load_master_prices()
        merged["latest_price"] = merged["ticker"].map(latest_prices)

        # Display value: shares × latest_price if available, else 13F value
        merged["display_value"] = merged.apply(
            lambda r: r["shares"] * r["latest_price"]
            if pd.notna(r["latest_price"])
            else r["value"],
            axis=1,
        )

        # Recompute weight from display value
        total_display_value = merged["display_value"].sum()
        merged["display_weight"] = (
            (merged["display_value"] / total_display_value * 100).round(2)
            if total_display_value > 0
            else 0.0
        )

        # Sort by display value descending and add rank
        merged = merged.sort_values("display_value", ascending=False).reset_index(drop=True)
        merged["rank"] = merged.index + 1

        # --- QoQ absolute deltas (for CSV export) ---
        def fmt_qoq_shares(row):
            if is_first_filing:
                return "—"
            if pd.isna(row.get("prior_shares")):
                return "NEW"
            delta = row["shares"] - row["prior_shares"]
            return f"{delta:+,.0f}"

        def fmt_qoq_value(row):
            if is_first_filing:
                return "—"
            if pd.isna(row.get("prior_value")):
                return "NEW"
            delta = (row["display_value"] - row["prior_value"]) / 1_000_000
            return f"${delta:+,.2f}M"

        merged["QoQ Shares Δ"] = merged.apply(fmt_qoq_shares, axis=1)
        merged["QoQ Value Δ"] = merged.apply(fmt_qoq_value, axis=1)

        # --- QoQ percent / weight columns (from pre-computed table) ---
        if has_qoq_table:
            qoq_lookup = qoq_df.set_index("cusip")

            def _lookup_shares_pct(row):
                cusip = row["cusip"]
                if cusip not in qoq_lookup.index:
                    return "NEW"
                val = qoq_lookup.loc[cusip, "shares_delta_pct"]
                if pd.isna(val):
                    return "N/A"
                return f"{val:+.2f}%"

            def _lookup_value_pct(row):
                cusip = row["cusip"]
                if cusip not in qoq_lookup.index:
                    return "NEW"
                val = qoq_lookup.loc[cusip, "value_delta_pct"]
                if pd.isna(val):
                    return "N/A"
                return f"{val:+.2f}%"

            def _lookup_weight_delta(row):
                cusip = row["cusip"]
                if cusip not in qoq_lookup.index:
                    return "NEW"
                val = qoq_lookup.loc[cusip, "qoq_weight_delta"]
                if pd.isna(val):
                    return "N/A"
                bps = int(round(val * 100))
                return f"{bps:+d}bp"

            merged["QoQ Shares Δ%"] = merged.apply(_lookup_shares_pct, axis=1)
            merged["QoQ Value Δ%"] = merged.apply(_lookup_value_pct, axis=1)
            merged["QoQ Weight Δ"] = merged.apply(_lookup_weight_delta, axis=1)
        else:
            merged["QoQ Shares Δ%"] = "—"
            merged["QoQ Value Δ%"] = "—"
            merged["QoQ Weight Δ"] = "—"

        # --- Build display DataFrame ---
        # QoQ delta columns are placed immediately after the column they describe:
        #   Shares → QoQ Shares Δ%,  Value → QoQ Value Δ%,  Weight → QoQ Weight Δ
        display_df = pd.DataFrame({
            "Rank":          merged["rank"],
            "Company":       merged["company_name"],
            "Ticker":        merged["ticker"].fillna(""),
            "CUSIP":         merged["cusip"].fillna(""),
            "Shares":        merged["shares"].apply(lambda x: f"{x:,.0f}"),
            "QoQ Shares Δ%": merged["QoQ Shares Δ%"],
            "Price":         merged["latest_price"].apply(
                                 lambda x: f"${x:,.2f}" if pd.notna(x) else "N/A"
                             ),
            "Value ($M)":    (merged["display_value"] / 1_000_000).round(2),
            "QoQ Value Δ%":  merged["QoQ Value Δ%"],
            "Weight (%)":    merged["display_weight"],
            "QoQ Weight Δ":  merged["QoQ Weight Δ"],
        })

        # CSV export adds absolute delta columns alongside their percent counterparts
        export_df = pd.DataFrame({
            "Rank":          merged["rank"],
            "Company":       merged["company_name"],
            "Ticker":        merged["ticker"].fillna(""),
            "CUSIP":         merged["cusip"].fillna(""),
            "Shares":        merged["shares"].apply(lambda x: f"{x:,.0f}"),
            "QoQ Shares Δ":  merged["QoQ Shares Δ"],
            "QoQ Shares Δ%": merged["QoQ Shares Δ%"],
            "Price":         merged["latest_price"].apply(
                                 lambda x: f"${x:,.2f}" if pd.notna(x) else "N/A"
                             ),
            "Value ($M)":    (merged["display_value"] / 1_000_000).round(2),
            "QoQ Value Δ":   merged["QoQ Value Δ"],
            "QoQ Value Δ%":  merged["QoQ Value Δ%"],
            "Weight (%)":    merged["display_weight"],
            "QoQ Weight Δ":  merged["QoQ Weight Δ"],
        })

        # --- Render ---
        with st.container(border=True):
            # Metrics row
            m1, m2, m3, m4 = st.columns(4)
            with m1:
                val_b = total_display_value / 1_000_000_000
                st.metric("Total Value", f"${val_b:,.2f}B")
            with m2:
                st.metric("Positions", len(merged))
            with m3:
                st.metric("Period End", selected_period_end)
            with m4:
                st.metric("Filed", selected_filing_date)

            if is_first_filing:
                st.info("First available filing — no QoQ comparison available.")
            elif not has_qoq_table:
                st.info(
                    "QoQ data unavailable for this period — run "
                    "**Compute QoQ Changes** in Data Management."
                )

            st.dataframe(display_df, use_container_width=True, hide_index=True)

            csv_bytes = export_df.to_csv(index=False).encode("utf-8")
            st.download_button(
                "Export to CSV",
                data=csv_bytes,
                file_name=f"{portfolio_id}_{selected_filing_date}_holdings.csv",
                mime="text/csv",
            )

# ============================================================================
# SECTION C: PULL LATEST 13Fs
# ============================================================================

with st.expander("Pull Latest 13Fs", expanded=False):
    st.caption("Check SEC EDGAR for new filings not yet downloaded locally.")

    if st.button("Pull Latest 13Fs for All Funds", type="primary", key="pull_13fs"):
        with st.spinner("Checking SEC EDGAR for new filings..."):
            result = pull_latest_13fs_all_funds()

        if result["funds_checked"] == 0:
            st.warning("No funds with CIKs are being tracked.")
        elif result["total_new_filings"] == 0:
            st.success(f"All funds are up to date. Checked {result['funds_checked']} fund(s).")
        else:
            st.success(
                f"Downloaded {result['total_new_filings']} new filing(s) "
                f"across {result['funds_checked']} fund(s)."
            )

        for detail in result.get("details", []):
            if detail["new_count"] > 0:
                dates_str = ", ".join(detail["downloaded"])
                st.info(f"**{detail['fund_name']}**: {detail['new_count']} new — {dates_str}")
            if detail.get("errors"):
                st.warning(f"**{detail['fund_name']}**: {len(detail['errors'])} error(s)")
                with st.expander(f"Errors for {detail['fund_name']}"):
                    for err in detail["errors"]:
                        st.text(f"{err['filing_date']}: {err['error']}")

        if result.get("total_new_filings", 0) > 0:
            st.rerun()

# ============================================================================
# SECTION D: ADD NEW FUND
# ============================================================================


with st.expander("Add New Fund", expanded=False):
    st.caption(
        "Add a new fund by CIK. Fetches all 13F filings from 2020 onward "
        "and downloads prices for all holdings."
    )

    cik_input = st.text_input(
        "CIK Number",
        placeholder="e.g. 1350694",
        key="new_fund_cik",
    )

    add_clicked = st.button(
        "Add Fund",
        type="primary",
        disabled=(not cik_input.strip()),
        key="add_fund_btn",
    )

    if add_clicked:
        # Step 1: Validate CIK
        cik_clean = re.sub(r"\D", "", cik_input.strip())
        if not (1 <= len(cik_clean) <= 10):
            st.error("Invalid CIK. Must be 1–10 digits.")
            st.stop()

        # Step 2: Check for duplicate
        existing_portfolios = load_portfolios()
        existing_ciks = existing_portfolios["cik"].astype(str).str.strip().tolist()
        if cik_clean in existing_ciks:
            existing_name = existing_portfolios[
                existing_portfolios["cik"].astype(str).str.strip() == cik_clean
            ]["name"].iloc[0]
            st.warning(f"CIK {cik_clean} is already tracked as **{existing_name}**.")
            st.stop()

        status = st.empty()

        with st.spinner("Adding fund — this may take a minute..."):
            # Step 3: Fetch fund name from SEC
            status.info("Step 1/4: Looking up fund name on SEC EDGAR...")
            fund_name = fetch_fund_name_from_sec(cik_clean)
            if not fund_name:
                st.error(f"Could not find a fund for CIK {cik_clean}. Please verify the CIK.")
                st.stop()

            # Step 4: Create portfolio entry
            status.info(f"Step 2/4: Creating portfolio entry for **{fund_name}**...")
            port_result = create_portfolio_entry(cik_clean, fund_name)
            if not port_result["success"]:
                st.error(f"Failed to create portfolio: {port_result['message']}")
                st.stop()
            new_portfolio_id = port_result["portfolio_id"]

            # Step 5: Fetch all 13Fs from 2020-01-01
            status.info(f"Step 3/4: Fetching 13F filings since 2020 for **{fund_name}**...")
            scraper = SECEdgarScraper()
            filings_fetched = scraper.fetch_and_save_filings(
                cik=cik_clean,
                portfolio_id=new_portfolio_id,
                start_date="2020-01-01",
            )

            # Step 6: Collect unique tickers from all new filings
            all_tickers = set()
            for filing_file in get_holdings_files(new_portfolio_id):
                try:
                    df_temp = pd.read_csv(filing_file)
                    tickers_in_file = df_temp["ticker"].dropna().astype(str)
                    all_tickers.update(t for t in tickers_in_file if t.strip() and t != "nan")
                except Exception:
                    pass

            # Step 7: Fetch prices for all tickers
            status.info(
                f"Step 4/4: Fetching prices for {len(all_tickers)} tickers "
                f"(this may take a while)..."
            )
            price_successes = 0
            total_records = 0
            for ticker in sorted(all_tickers):
                try:
                    r = fetch_incremental_prices(ticker, start_from="2020-01-01")
                    if r.get("success"):
                        price_successes += 1
                    total_records += r.get("records_added", 0)
                except Exception:
                    pass

        status.empty()

        st.success(f"**{fund_name}** added successfully!")
        r1, r2, r3 = st.columns(3)
        with r1:
            st.metric("Filings Downloaded", len(filings_fetched))
        with r2:
            st.metric("Tickers with Prices", f"{price_successes}/{len(all_tickers)}")
        with r3:
            st.metric("Price Records Added", f"{total_records:,}")

        st.rerun()
