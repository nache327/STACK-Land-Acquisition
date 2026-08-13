"""Last Sale Date must reach the DB as a real date, never a string.

The 2026-08-13 Mercer CoStar upload failed whole-batch with
``invalid input for query argument $125: '2024-11-09 00:00:00'
('str' object has no attribute 'toordinal')`` — the CoStar parser mapped
Last Sale Date through ``to_str``, and asyncpg refuses strings for DATE
parameters. Blanking the column unblocked that ingest; this pins the fix
(``to_date``) so date-bearing exports work as shipped.
"""
from __future__ import annotations

import datetime as dt

from app.services.listings_parsers._common import to_date


def test_native_datetime_cell():
    assert to_date(dt.datetime(2024, 11, 9, 0, 0)) == dt.date(2024, 11, 9)


def test_native_date_cell():
    assert to_date(dt.date(2024, 11, 9)) == dt.date(2024, 11, 9)


def test_the_exact_prod_failure_string():
    """The literal value from the failed Mercer batch."""
    assert to_date("2024-11-09 00:00:00") == dt.date(2024, 11, 9)


def test_iso_and_us_text_formats():
    assert to_date("2024-11-09") == dt.date(2024, 11, 9)
    assert to_date("11/9/2024") == dt.date(2024, 11, 9)
    assert to_date("11/09/24") == dt.date(2024, 11, 9)


def test_blank_and_junk_are_none():
    assert to_date(None) is None
    assert to_date("") is None
    assert to_date("n/a") is None
    assert to_date("not a date") is None
    assert to_date(float("nan")) is None


def test_costar_parser_emits_date_not_str():
    """End-to-end through the CoStar parser: a Last Sale Date cell must
    come out as datetime.date on the ListingRow."""
    import pandas as pd

    from app.services.listings_parsers.costar import Parser

    df = pd.DataFrame([
        {
            "Property Address": "1437 E State St",
            "Sale Status": "Active",
            "Property Type": "Industrial",
            "Last Sale Date": dt.datetime(2024, 11, 9),
        },
        {
            "Property Address": "3430 Brunswick Pk",
            "Sale Status": "Active",
            "Property Type": "Industrial",
            "Last Sale Date": "2024-11-09 00:00:00",
        },
    ])
    result = Parser.parse_dataframe(df, "export.xlsx")
    dates = [r.last_sale_date for r in result.rows]
    assert dates == [dt.date(2024, 11, 9), dt.date(2024, 11, 9)]
    for d in dates:
        assert isinstance(d, dt.date) and not isinstance(d, dt.datetime)
